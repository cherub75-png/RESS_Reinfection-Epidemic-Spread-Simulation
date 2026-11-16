"""서버 없이 브라우저에서 동작하는 사이트(site/dist) 를 만든다.

브라우저에서 ODE 엔진(site/src/engine.js)이 계산하므로, 필요한 자료를 JSON 으로 내보낸다.
  data/<데이터셋>.json : 지역 id·이름·인구·밀도(엔진과 같은 값), 접촉 행렬 C, 이동 omega(CSR), 월 기후, 경계 GeoJSON, 출처 요약
  data/flu_latest.json : 가장 최근 인플루엔자 최신 예측 작업 결과 (웹 작업 폴더)
  data/validation.json : 예측 검증 요약 (인플루엔자, COVID-19, 구간 보정)
  data/meta.json       : 감염병 기본값(가정), 자료 출처 목록, 가정값, 빌드 정보
엔진 대조용 기준 결과: site/test/reference_KOR.json (Python FastODE 와 같은 조건)
사용법: python -I scripts/build_static_site.py
"""

import datetime as dt
import json
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SITE = ROOT / "site"
DIST = SITE / "dist"
DATASETS = ("KOR_admin1", "world_countries")


def r(v, sig=12):
    return float(f"{float(v):.{sig}g}")


def export_dataset(name: str) -> dict:
    from seir_sim.data.dataset import RegionDataset
    from seir_sim.data.versions import Registry
    from seir_sim.web.datasets import geojson_for
    reg = Registry()
    e = reg.list()[name]
    ds = RegionDataset.load(reg.resolve(name))
    rs = ds.to_region_set()                                  # 엔진과 같은 반올림 인구·밀도
    K = rs.K
    om = rs.mobility
    indptr, indices, values = [0], [], []
    for i in range(K):
        js = np.flatnonzero(om[i] > 0)
        indices += js.tolist()
        values += [r(v, 15) for v in om[i, js]]
        indptr.append(len(indices))
    p = ds.provenance
    pop = p.get("population", {}) or {}
    clim = p.get("climate", {}) or {}
    return {"name": name, "version": e["active"], "K": K, "ids": list(rs.names), "names": list(ds.names),
            "population": [float(v) for v in rs.population], "density": [r(v, 15) for v in rs.density],
            "area_km2": [round(float(a), 1) for a in ds.area_km2],
            "C": [r(v, 15) for v in rs.contact.ravel()], "omega": {"indptr": indptr, "indices": indices, "values": values},
            "tavg": None if ds.tavg is None else [[round(float(v), 3) for v in row] for row in ds.tavg],
            "rh": None if ds.rh is None else [[round(float(v), 3) for v in row] for row in ds.rh],
            "geojson": geojson_for(name),
            "provenance": {"scope": p.get("scope"), "boundaries": p.get("boundaries"), "boundary_file": p.get("boundary_file"),
                           "population_source": pop.get("source") or (pop.get("primary") or {}).get("source"),
                           "population_year": p.get("population_year") or (p.get("period_selection") or {}).get("population_year"),
                           "period_selection": p.get("period_selection"), "assumptions": p.get("assumptions"),
                           "climate_periods": clim.get("periods"), "climate_sources": clim.get("sources")}}


def latest_flu() -> dict | None:
    best = None
    for st in (ROOT / "outputs" / "web_jobs").glob("*/status.json"):
        s = json.loads(st.read_text())
        if s.get("kind") == "flu_forecast" and s.get("state") == "done" and (st.parent / "result.json").exists():
            if best is None or s.get("finished_utc", "") > best[0]:
                best = (s.get("finished_utc", ""), st.parent / "result.json")
    return None if best is None else json.loads(best[1].read_text())


def validation() -> dict:
    rep = ROOT / "docs" / "reports"
    flu = json.loads((rep / "11_influenza_validation.json").read_text())
    cov = json.loads((rep / "5_forecast_validation.json").read_text())
    cal = json.loads((rep / "12_interval_calibration.json").read_text())
    keep = lambda d: {k: d[k] for k in ("persistence", "trend", "seasonal", "ml", "ml_cal", "seir") if k in d}  # noqa: E731
    return {"flu": {"run": flu["run"], "main": {h: {"n": v["n"], **{m: {"rel_wis": x["rel_wis"], "cov90": x["cov90"]} for m, x in keep(v).items()}}
                                                for h, v in flu["main"].items()},
                    "loco_KOR": flu.get("loco_KOR"), "climate_ablation": flu.get("climate_ablation"), "calibration": flu["calibration"],
                    "seir": flu.get("seir"), "seir_fit_summary": flu.get("seir_fit_summary")},
            "covid": {k: cov.get(k) for k in ("cases_by_h", "deaths_by_h", "first_origin", "last_origin", "knot_days")},
            "covid_calibration": cal["rows"]}


def meta() -> dict:
    import yaml
    from seir_sim.data.assumptions import ASSUMPTIONS
    from seir_sim.data.registry import TIER
    cfg = yaml.safe_load((ROOT / "configs" / "example_single_region.yaml").read_text())["disease"]
    num = lambda v: float(eval(str(v), {})) if isinstance(v, str) else float(v)                       # noqa: E731 (1/5.2 같은 분수)
    man = json.loads((ROOT / "data_raw" / "manifest.json").read_text())
    sources = [{"id": k, "title": v.get("title"), "source": v.get("source"), "license": v.get("license"),
                "time_reference": v.get("time_reference"), "retrieved_utc": v.get("retrieved_utc"), "status": v.get("status"),
                "tier": TIER.get(k, (None,))[0]} for k, v in man.items()]
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"disease_defaults": {"sigma": num(cfg["sigma"]), "gamma": num(cfg["gamma"]), "P1": num(cfg["P1"]), "T1": num(cfg["T1"]),
                                 "Pmin": num(cfg["Pmin"]), "alpha": num(cfg["alpha"]), "beta": num(cfg["beta"]), "lam": num(cfg["lam"]),
                                 "f1": num(cfg["f1"]), "phiDelta": num(cfg["phi"]["delta"]), "M": int(cfg["M"]), "R0": 2.5},
            "disease_label": "COVID 유사 코드 검증용 가정값 (실제 추정치 아님)", "assumptions": ASSUMPTIONS, "sources": sources,
            "build": {"commit": commit, "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}}


def reference_KOR() -> dict:
    """엔진 대조용: Python FastODE (RK4, 하루 4단계) 로 같은 조건을 계산한다."""
    from seir_sim.config.build import build_scenario
    from seir_sim.config.schema import Config
    from seir_sim.inference.fastode import FastODE
    from seir_sim.web.scenario import ScenarioRequest, build_config
    req = ScenarioRequest.model_validate({"title": "ref", "dataset": "KOR_admin1", "R0": 2.5, "method": "ode", "days": 180,
                                          "seeds": [{"region": "KR-11", "count": 10, "exposed": 5}], "initial_immune_fraction": 0.1,
                                          "interventions": [{"start": 30, "end": 90, "value": 0.3, "regions": None}], "eta": 0.2})
    sc = build_scenario(Config.model_validate(build_config(req)))
    fo = FastODE(sc.system, nsub=4)
    days = 180
    u = np.zeros((days, sc.system.regions.K))
    u[30:90] = 0.3
    gc = fo.gc_from_u(u)
    inf, ons, dea, xe = fo.run(sc.X0, gc)
    L = sc.system.layout
    I_end = xe[:, L.I_slice].sum(axis=1)
    return {"request": req.model_dump(mode="json"), "ids": list(sc.system.regions.names),
            "I_end": I_end.tolist(), "D_end": xe[:, L.D].tolist(), "S_end": xe[:, L.S].tolist(),
            "c0": float(sc.system.params.c0), "X0": sc.X0.reshape(-1).tolist(),
            "note": "Python FastODE, RK4 nsub=4, u 는 하루 단위 상수. 웹 시나리오의 초기 면역은 반올림 전 인구로 계산된다"}


def main():
    warnings.simplefilter("ignore")
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "data").mkdir(parents=True)
    for f in ("index.html", "app.js", "engine.js", "worker.js", "style.css"):
        if (SITE / "src" / f).exists():
            shutil.copy(SITE / "src" / f, DIST / f)
    leaflet = (ROOT / "seir_sim" / "web" / "static" / "vendor" / "leaflet-1.9.4" / "leaflet.css").read_text()
    (DIST / "style.css").write_text("/* Leaflet 1.9.4 (BSD-2-Clause) */\n" + leaflet + "\n" + (SITE / "src" / "style.css").read_text())
    for n in DATASETS:
        d = export_dataset(n)
        (DIST / "data" / f"{n}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
        print(n, d["K"], f"{(DIST / 'data' / f'{n}.json').stat().st_size / 1e6:.2f} MB")
    flu = latest_flu()
    (DIST / "data" / "flu_latest.json").write_text(json.dumps(flu, ensure_ascii=False, separators=(",", ":")))
    (DIST / "data" / "validation.json").write_text(json.dumps(validation(), ensure_ascii=False, separators=(",", ":")))
    (DIST / "data" / "meta.json").write_text(json.dumps(meta(), ensure_ascii=False, separators=(",", ":")))
    (SITE / "test").mkdir(exist_ok=True)
    (SITE / "test" / "reference_KOR.json").write_text(json.dumps(reference_KOR(), ensure_ascii=False))
    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"site/dist {total / 1e6:.2f} MB, 인플루엔자 기점 {flu and flu.get('origin')}")


if __name__ == "__main__":
    main()
