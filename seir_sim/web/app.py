"""로컬 웹 애플리케이션 (FastAPI). 공개 배포용이 아니다: 기본으로 127.0.0.1 에만 연다.

실행: python -m seir_sim.web  (또는 scripts/run_web.py) -> http://127.0.0.1:8765
화면 구분: 시나리오(가정에 따른 결과) / 예측 검증(과거 자료로 잰 성능) / 최신 자료 예측(기점 이후 4주) / 자료 출처.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .jobs import JobManager

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
NAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")
EXPORTS = {"daily.csv": "text/csv", "regions.csv": "text/csv", "regions_daily.csv": "text/csv",
           "summary.json": "application/json", "run_record.json": "application/json",
           "ensemble.nc": "application/x-netcdf", "config.json": "application/json", "result.json": "application/json",
           "request.json": "application/json", "summary_daily.parquet": "application/vnd.apache.parquet",
           "summary_regions.parquet": "application/vnd.apache.parquet"}
USER_DIR = ROOT / "outputs" / "web_user"


CLIENT_HEADER = "x-seir-client"
LOCAL_HOSTS = ["127.0.0.1", "localhost", "[::1]", "testserver"]


def create_app(job_root: Path | None = None, max_concurrent: int = 1, allowed_hosts: list[str] | None = None,
               max_job_seconds: float = 6 * 3600, auto_updates: bool = False, user_dir: Path | None = None) -> FastAPI:
    """보안 (로컬 전용)
    - Host 헤더가 허용 목록(기본: 127.0.0.1, localhost)에 없으면 거부한다 (DNS 리바인딩 방지).
    - 상태를 바꾸는 요청(POST, DELETE)은 사용자 지정 헤더 X-SEIR-Client 가 있어야 한다. 다른 사이트의 페이지가 브라우저로
      보내는 요청은 이 헤더를 붙이려면 CORS 사전 요청을 거쳐야 하고, 이 서버는 CORS 를 허용하지 않으므로 막힌다 (CSRF 방지).
    """
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse as _JR
    app = FastAPI(title="재감염 SEIR 시뮬레이터 (로컬)", docs_url="/api/docs", redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or LOCAL_HOSTS)

    @app.middleware("http")
    async def require_client_header(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get(CLIENT_HEADER) != "web":
            return _JR({"detail": "상태를 바꾸는 요청에는 X-SEIR-Client: web 헤더가 필요하다"}, status_code=403)
        return await call_next(request)

    jobs = JobManager(job_root or ROOT / "outputs" / "web_jobs", max_concurrent=max_concurrent, max_seconds=max_job_seconds)
    app.state.jobs = jobs
    udir = Path(user_dir or USER_DIR)
    if auto_updates:                       # 사용자가 auto 로 정한 자료 중 기한이 지난 것만 갱신 확인 (기본은 수동)
        from ..data.updater import Updater
        up = Updater()
        for did, pol in up.policy().items():
            if pol.get("auto") and up.due(did):
                jobs.submit("update", {"id": did}, f"{did} 자동 갱신 확인")

    def _job_dir(job_id):
        try:
            return jobs.dir(job_id)
        except KeyError:
            raise HTTPException(404, "작업 없음")

    # ------------------------------------------------------------------ 기본
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/defaults")
    def defaults():
        from .scenario import ScenarioRequest, disease_defaults
        return {"disease": disease_defaults(), "disease_label": "COVID 유사 코드 검증용 가정 (실제 추정치 아님)",
                "scenario_schema": ScenarioRequest.model_json_schema()}

    # ------------------------------------------------------------------ 데이터셋
    @app.get("/api/datasets")
    def datasets():
        from ..data.versions import Registry
        out = []
        for n, e in Registry().list().items():
            out.append({"name": n, "active": e["active"], "history": e["history"],
                        "versions": [{k: v.get(k) for k in ("version", "registered_utc", "K", "population_total",
                                                             "population_source", "synthetic", "note", "sha256")}
                                     | {"validation": v["validation"], "diff_vs_active": v.get("diff_vs_active")}
                                     for v in e["versions"]]})
        return out

    DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def _period_path(name: str, boundary_date: str | None, population_year: int | None):
        """고른 경계 시점·인구 연도의 변형본 경로 (둘 다 없으면 None = 저장소 활성 버전)."""
        if not NAME.match(name) or (boundary_date and not DATE.match(boundary_date)) or \
                (population_year is not None and not 1960 <= population_year <= 2100):
            raise HTTPException(400, "잘못된 값")
        if boundary_date is None and population_year is None:
            return None
        from ..data.periods import variant
        try:
            return variant(name, population_year=population_year, boundary_date=boundary_date)
        except KeyError:
            raise HTTPException(404, "데이터셋 없음")
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/datasets/{name}/geojson")
    def dataset_geojson(name: str, version: str | None = None, boundary_date: str | None = None,
                        population_year: int | None = None):
        if not NAME.match(name) or (version and not re.match(r"^v\d{1,4}$", version)):
            raise HTTPException(400, "잘못된 이름")
        vp = _period_path(name, boundary_date, population_year)
        if vp is not None:
            return JSONResponse(json.loads(vp.with_suffix(".geojson").read_text()))
        from .datasets import geojson_for
        try:
            return geojson_for(name, version)
        except KeyError:
            raise HTTPException(404, "데이터셋 없음")

    @app.get("/api/datasets/{name}/regions")
    def dataset_regions(name: str, boundary_date: str | None = None, population_year: int | None = None):
        if not NAME.match(name):
            raise HTTPException(400, "잘못된 이름")
        from ..data.dataset import RegionDataset
        from ..data.versions import Registry
        vp = _period_path(name, boundary_date, population_year)
        try:
            ds = RegionDataset.load(vp if vp is not None else Registry().resolve(name))
        except KeyError:
            raise HTTPException(404, "데이터셋 없음")
        return {"ids": ds.ids, "names": ds.names, "population": [None if p != p else float(p) for p in ds.population],
                "area_km2": [round(float(a), 1) for a in ds.area_km2],
                "provenance": {k: ds.provenance.get(k) for k in ("scope", "boundaries", "population", "assumptions",
                                                                 "climate", "built_utc", "population_year",
                                                                 "period_selection", "boundary_file")}}

    @app.get("/api/datasets/{name}/periods")
    def dataset_periods(name: str):
        """고를 수 있는 경계 시점·인구 연도·기후 기간과 각각의 출처. 확보하지 못한 시기는 목록에 없다."""
        if not NAME.match(name):
            raise HTTPException(400, "잘못된 이름")
        from ..data import periods
        from ..data.dataset import RegionDataset
        from ..data.versions import Registry
        try:
            ds = RegionDataset.load(Registry().resolve(name))
        except KeyError:
            raise HTTPException(404, "데이터셋 없음")
        return periods.options(periods.family(ds.provenance))

    @app.post("/api/climate-periods")
    def climate_period_submit(body: dict = Body(...)):
        """ERA5 기간 월 평균 만들기 (네트워크 사용, 1년에 1~2분). 본문: {"start": "YYYY-MM", "end": "YYYY-MM"}."""
        ym = re.compile(r"^(19[4-9]\d|20\d\d)-(0[1-9]|1[0-2])$")
        st, en = str(body.get("start", "")), str(body.get("end", ""))
        if not (ym.match(st) and ym.match(en)) or en < st:
            raise HTTPException(422, "start, end 는 YYYY-MM (start <= end)")
        y0, m0 = map(int, st.split("-"))
        y1, m1 = map(int, en.split("-"))
        if (y1 - y0) * 12 + m1 - m0 + 1 > 120:
            raise HTTPException(422, "한 번에 10년(120개월)까지")
        return {"job_id": jobs.submit("climate", {"start": st, "end": en}, f"ERA5 기후 {st} ~ {en}")}

    @app.post("/api/datasets/{name}/activate")
    def dataset_activate(name: str, body: dict = Body(...)):
        from ..data.versions import Registry
        v = str(body.get("version", ""))
        if not NAME.match(name) or not re.match(r"^v\d{1,4}$", v):
            raise HTTPException(400, "잘못된 이름")
        try:
            Registry().activate(name, v)
        except (KeyError, ValueError) as e:
            raise HTTPException(409, str(e))
        return {"active": v}

    @app.post("/api/datasets/{name}/rollback")
    def dataset_rollback(name: str):
        from ..data.versions import Registry
        if not NAME.match(name):
            raise HTTPException(400, "잘못된 이름")
        try:
            return {"active": Registry().rollback(name)}
        except (KeyError, ValueError) as e:
            raise HTTPException(409, str(e))

    @app.post("/api/datasets/{name}/population-table")
    def dataset_population_table(name: str, body: dict = Body(...)):
        """본문: {"table_text": CSV 문자열, "note": 설명}. 새 버전을 만들어 등록한다 (활성화는 하지 않음)."""
        from .datasets import check_population_table
        if not NAME.match(name):
            raise HTTPException(400, "잘못된 이름")
        text = str(body.get("table_text", ""))
        try:
            chk = check_population_table(text)
        except (ValueError, KeyError) as e:
            raise HTTPException(422, str(e))
        jid = jobs.submit("dataset", {"name": name, "table_text": text, "note": str(body.get("note", ""))[:200]},
                          f"{name} 인구표 갱신")
        return {"job_id": jid, "check": chk}

    # ------------------------------------------------------------------ 작업
    def _check_scenario(body: dict):
        """요청 검증 + 인구와의 모순 점검 + 계산량 추정. (req, estimate) 또는 HTTPException."""
        from .scenario import ScenarioRequest, build_config, check_against_populations, estimate_cost
        from ..config.schema import Config
        try:
            req = ScenarioRequest.model_validate(body)
        except ValidationError as e:
            raise HTTPException(422, json.loads(e.json(include_url=False)))
        if req.dataset == "synthetic_single":
            if req.climate != "none":
                raise HTTPException(422, "합성 단일 지역에는 기후 자료가 없어 기후 효과를 켤 수 없다")
            pops = {"region0": float(req.population or 1e6)}
            req_check = req.model_copy(update={"seeds": [s.model_copy(update={"region": "region0"}) for s in req.seeds]})
        else:
            from ..data.versions import Registry
            from .scenario import load_request_dataset
            if req.dataset not in Registry().list():
                raise HTTPException(422, f"데이터셋 {req.dataset} 이 저장소에 없다")
            try:
                ds = load_request_dataset(req, with_climate=req.climate != "none")
            except ValueError as e:
                raise HTTPException(422, str(e)[:500])
            pops = dict(zip(ds.ids, ds.population.tolist()))
            if req.climate != "none" and ds.tavg is None:
                raise HTTPException(422, "이 데이터셋에는 기후 자료가 없어 기후 효과를 켤 수 없다 (미확보). 기후 기간을 고른다")
            req_check = req
        errs = check_against_populations(req_check, pops)
        if errs:
            raise HTTPException(422, "; ".join(errs[:5]))
        try:
            Config.model_validate(build_config(req, pops))
        except (ValidationError, ValueError) as e:
            raise HTTPException(422, str(e)[:500])
        return req, estimate_cost(req, len(pops), float(sum(v for v in pops.values() if v == v)))

    @app.post("/api/scenarios/check")
    def scenario_check(body: dict = Body(...)):
        req, est = _check_scenario(body)
        return {"ok": True, "estimate": est}

    @app.post("/api/scenarios")
    def scenario_submit(body: dict = Body(...)):
        req, est = _check_scenario(body)
        return {"job_id": jobs.submit("scenario", req.model_dump(mode="json"), req.title), "estimate": est}

    # ------------------------------------------------------------------ 감염병 설정 저장 (사용자 정의)
    def _diseases() -> dict:
        p = udir / "diseases.json"
        return json.loads(p.read_text()) if p.exists() else {}

    @app.get("/api/diseases")
    def diseases_list():
        return _diseases()

    @app.post("/api/diseases")
    def diseases_save(body: dict = Body(...)):
        from .scenario import DiseaseIn
        try:
            dz = DiseaseIn.model_validate(body.get("disease", {}))
        except ValidationError as e:
            raise HTTPException(422, json.loads(e.json(include_url=False)))
        name = dz.name.strip()
        if not name:
            raise HTTPException(422, "이름이 필요하다")
        allp = _diseases()
        if len(allp) >= 200 and name not in allp:
            raise HTTPException(422, "저장 개수 상한 (200)")
        allp[name] = {"disease": dz.model_dump(), "R0": body.get("R0"), "note": str(body.get("note", ""))[:300],
                      "label": "사용자 입력 (근거는 사용자가 기록한 메모 참고)"}
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "diseases.json").write_text(json.dumps(allp, ensure_ascii=False, indent=1))
        return {"saved": name}

    @app.delete("/api/diseases/{name}")
    def diseases_delete(name: str):
        allp = _diseases()
        if name not in allp:
            raise HTTPException(404, "없음")
        del allp[name]
        (udir / "diseases.json").write_text(json.dumps(allp, ensure_ascii=False, indent=1))
        return {"deleted": name}

    # ------------------------------------------------------------------ 이동 흐름 (지도 표시용)
    @app.get("/api/datasets/{name}/flows")
    def dataset_flows(name: str, top: int = 30):
        if not NAME.match(name) or not 1 <= top <= 200:
            raise HTTPException(400, "잘못된 값")
        import numpy as np
        from ..data.dataset import RegionDataset
        from ..data.versions import Registry
        try:
            ds = RegionDataset.load(Registry().resolve(name))
        except KeyError:
            raise HTTPException(404, "데이터셋 없음")
        if not np.all(np.isfinite(ds.mobility)):
            return {"flows": [], "note": "이동 행렬 없음 (인구 미확보)"}
        F = ds.mobility * np.nan_to_num(ds.population)[:, None]       # 하루 이동 인원 i -> j
        F = np.triu(F + F.T, 1)                                         # 양방향 합 (균형 이동이라 대칭)
        idx = np.dstack(np.unravel_index(np.argsort(F, axis=None)[::-1][:top], F.shape))[0]
        flows = [{"a": ds.ids[i], "b": ds.ids[j], "a_lonlat": [float(ds.lon[i]), float(ds.lat[i])],
                  "b_lonlat": [float(ds.lon[j]), float(ds.lat[j])], "per_day": float(F[i, j])} for i, j in idx if F[i, j] > 0]
        a = ds.provenance.get("assumptions", {})
        return {"flows": flows, "note": f"노선 수 비례 배분 x 가정 총량 (항공 {a.get('air_trips_per_day')} 회/일). 실측 승객 수가 아니다."}

    # ------------------------------------------------------------------ 원자료 갱신
    @app.get("/api/updates")
    def updates_status():
        from ..data.updater import Updater
        u = Updater()
        return {"datasets": u.status(), "log": u.log()[-50:]}

    @app.post("/api/updates/{did}/check")
    def updates_check(did: str):
        from ..data.registry import DATASETS
        if did not in DATASETS:
            raise HTTPException(404, "자료 없음")
        return {"job_id": jobs.submit("update", {"id": did}, f"{did} 갱신 확인")}

    @app.post("/api/updates/{did}/policy")
    def updates_policy(did: str, body: dict = Body(...)):
        from ..data.updater import Updater
        try:
            iv = body.get("interval_days")
            return Updater().set_policy(did, None if iv in (None, "", 0) else int(iv), bool(body.get("auto", False)))
        except KeyError:
            raise HTTPException(404, "자료 없음")
        except (ValueError, TypeError) as e:
            raise HTTPException(422, str(e))

    @app.post("/api/forecasts")
    def forecast_submit(body: dict = Body(...)):
        from ..surveillance.sources import COUNTRIES
        iso3 = str(body.get("iso3", ""))
        if iso3 not in COUNTRIES:
            raise HTTPException(422, f"지원 국가: {list(COUNTRIES)}")
        return {"job_id": jobs.submit("forecast", {"iso3": iso3, "origin": body.get("origin")}, f"{iso3} 최신 자료 예측")}

    @app.post("/api/flu/forecasts")
    def flu_forecast_submit(body: dict = Body(default={})):
        """인플루엔자 최신 자료 예측 (WHO FluNet; 1~3분, seir 를 켜면 몇 분 더)."""
        if not (ROOT / "data_raw" / "who_flunet" / "VIW_FNT.csv").exists():
            raise HTTPException(409, "FluNet 자료가 없다 (scripts/fetch_data.py who_flunet)")
        return {"job_id": jobs.submit("flu_forecast", {"seir": bool(body.get("seir", False))}, "인플루엔자 최신 자료 예측")}

    @app.get("/api/flu/latest")
    def flu_latest():
        """가장 최근에 끝난 인플루엔자 최신 예측 작업의 결과."""
        for j in jobs.list():
            if j.get("kind") == "flu_forecast" and j.get("state") == "done":
                p = jobs.dir(j["id"]) / "result.json"
                if p.exists():
                    return JSONResponse({"job_id": j["id"], **json.loads(p.read_text())})
        raise HTTPException(404, "아직 인플루엔자 예측 결과가 없다 (예측 실행)")

    @app.get("/api/jobs")
    def jobs_list():
        return jobs.list()

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        _job_dir(job_id)
        return {k: v for k, v in jobs.status(job_id).items() if k != "traceback"}

    @app.delete("/api/jobs/{job_id}")
    def job_cancel(job_id: str):
        _job_dir(job_id)
        return jobs.cancel(job_id)

    @app.post("/api/jobs/{job_id}/rename")
    def job_rename(job_id: str, body: dict = Body(...)):
        _job_dir(job_id)
        title = str(body.get("title", "")).strip()
        if not 1 <= len(title) <= 80:
            raise HTTPException(422, "제목은 1~80자")
        return jobs.rename(job_id, title)

    @app.delete("/api/jobs/{job_id}/files")
    def job_delete(job_id: str):
        """끝난 작업의 결과 폴더를 지운다 (실행 중이거나 대기 중이면 거부). 화면에서 사용자가 확인한 뒤에만 부른다."""
        _job_dir(job_id)
        try:
            jobs.delete(job_id)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"deleted": job_id}

    @app.get("/api/jobs/{job_id}/live")
    def job_live(job_id: str):
        d = _job_dir(job_id)
        if not (d / "live.json").exists():
            raise HTTPException(404, "아직 중간 결과가 없다")
        return JSONResponse(json.loads((d / "live.json").read_text()))

    @app.get("/api/jobs/{job_id}/summary")
    def job_summary(job_id: str):
        d = _job_dir(job_id)
        for f in ("summary.json", "result.json"):
            if (d / f).exists():
                return JSONResponse(json.loads((d / f).read_text()))
        raise HTTPException(404, "결과가 아직 없다")

    @app.get("/api/jobs/{job_id}/export/{fname}")
    def job_export(job_id: str, fname: str):
        d = _job_dir(job_id)
        if fname not in EXPORTS or not (d / fname).exists():
            raise HTTPException(404, "파일 없음")
        return FileResponse(d / fname, media_type=EXPORTS[fname], filename=f"{job_id[:8]}_{fname}")

    # ------------------------------------------------------------------ 검증·출처
    @app.get("/api/validation")
    def validation():
        out = {}
        for key, f in (("forecast", "5_forecast_validation.json"), ("calibration", "3_calibration.json"),
                       ("d007_d004", "D007_D004.json")):
            p = ROOT / "docs" / "reports" / f
            if p.exists():
                d = json.loads(p.read_text())
                if key == "calibration":
                    d = {"period": d.get("period"), "synthetic": d.get("synthetic"),
                         "countries": {c: {k: v.get(k) for k in ("success", "hessian_pd", "diagnostics", "delay_c", "k_f")}
                                       for c, v in d.get("countries", {}).items()},
                         "rho_profile": d.get("rho_profile"), "interpretation": d.get("interpretation")}
                if key == "d007_d004":
                    d = {"recommended_eps": d.get("D007_recommended_eps"), "reps": d.get("reps")}
                out[key] = d
        return out

    @app.get("/api/forecast-history")
    def forecast_history(iso3: str, var: str = "cases", knot: int = 14):
        import pandas as pd
        if not NAME.match(iso3) or var not in ("cases", "deaths") or knot not in (7, 14):
            raise HTTPException(400, "잘못된 값")
        p = ROOT / "outputs" / "stage5" / f"forecasts_k{knot}.parquet"
        if not p.exists():
            return {"iso3": iso3, "var": var, "rows": [], "label": "5단계 예측 결과 파일이 아직 없다 (scripts/report_stage5_forecast.py)"}
        df = pd.read_parquet(p)
        df = df[(df["iso3"] == iso3) & (df["var"] == var)]
        rows = df[["origin", "method", "h", "target_end", "truth", "q1", "q4", "q7"]].copy()
        rows["origin"] = rows["origin"].astype(str).str[:10]
        rows["target_end"] = rows["target_end"].astype(str).str[:10]
        rows = rows.astype(object).where(rows.notna(), None)
        return {"iso3": iso3, "var": var, "rows": rows.to_dict("records"),
                "label": "과거 자료 시간순 검증: 각 기점에서 그날까지의 자료만으로 만든 예측 (최종판 자료 사용)"}

    @app.get("/api/sources")
    def sources():
        from ..data.assumptions import ASSUMPTIONS
        from ..data.registry import TIER
        man = json.loads((ROOT / "data_raw" / "manifest.json").read_text()) if (ROOT / "data_raw" / "manifest.json").exists() else {}
        rows = []
        for did, e in man.items():
            rows.append({"id": did, "kind": e.get("kind"), "status": e.get("status"), "title": e.get("title"),
                         "source": e.get("source"), "license": e.get("license"), "version": e.get("version"),
                         "time_reference": e.get("time_reference"), "retrieved_utc": e.get("retrieved_utc"),
                         "tier": TIER.get(did, (None, None))[0], "redistribution": TIER.get(did, (None, None))[1],
                         "files": len(e.get("files", []))})
        return {"datasets": rows, "assumptions": ASSUMPTIONS,
                "note": "출처를 확인할 수 없는 자료는 실제 자료로 쓰지 않는다. 미확보 자료는 미확보로 표시한다."}

    # ------------------------------------------------------------------ 화면
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
