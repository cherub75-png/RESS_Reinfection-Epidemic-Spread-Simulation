"""8단계: 웹 API (FastAPI TestClient). 합성 단일 지역과 임시 데이터셋 저장소만 쓴다."""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from seir_sim.web.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(job_root=tmp_path / "jobs", user_dir=tmp_path / "user")
    with TestClient(app, headers={"X-SEIR-Client": "web"}) as c:
        yield c


def test_security_host_and_client_header(tmp_path):
    app = create_app(job_root=tmp_path / "jobs")
    with TestClient(app) as c:
        # 헤더 없는 상태 변경 요청 (다른 사이트의 폼·단순 요청 흉내) 거부
        assert c.post("/api/scenarios", json=BASE).status_code == 403
        assert c.delete("/api/jobs/" + "0" * 32).status_code == 403
        assert c.post("/api/datasets/T/rollback").status_code == 403
        assert c.get("/api/health").status_code == 200                       # 읽기는 허용
        # 허용되지 않은 Host (DNS 리바인딩 흉내) 거부
        assert c.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
        # CORS 를 허용하지 않는다 (사전 요청에 허용 헤더가 없음)
        r = c.options("/api/scenarios", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
                                                 "Access-Control-Request-Headers": "x-seir-client"})
        assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def _wait(c, jid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = c.get(f"/api/jobs/{jid}").json()
        if s["state"] in ("done", "failed", "cancelled", "interrupted"):
            return s
        time.sleep(0.3)
    raise TimeoutError


BASE = {"title": "시험", "dataset": "synthetic_single", "population": 20000, "R0": 2.0, "method": "ode", "days": 60,
        "seeds": [{"region": "region0", "count": 10}]}


def test_static_and_health(client):
    assert client.get("/api/health").json() == {"ok": True}
    r = client.get("/")
    assert r.status_code == 200 and "재감염 SEIR" in r.text
    assert client.get("/app.js").status_code == 200
    d = client.get("/api/defaults").json()
    assert "가정" in d["disease_label"]


def test_scenario_run_summary_and_exports(client):
    r = client.post("/api/scenarios", json={**BASE, "interventions": [{"start": 20, "end": 40, "value": 0.5}]})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    s = _wait(client, jid)
    assert s["state"] == "done", s
    sm = client.get(f"/api/jobs/{jid}/summary").json()
    assert sm["labels"]["kind"] == "scenario" and "가정" in sm["labels"]["disease_values"]
    assert len(sm["daily"]["t"]) == 61 and sm["derived"]["c0_basis"] == "reference"
    assert sm["derived"]["R0_reference"] == pytest.approx(2.0)
    assert any("합성" in w for w in sm["warnings"])
    for f in ("daily.csv", "regions.csv", "summary.json", "run_record.json", "ensemble.nc", "config.json"):
        e = client.get(f"/api/jobs/{jid}/export/{f}")
        assert e.status_code == 200 and len(e.content) > 0
    assert client.get(f"/api/jobs/{jid}/export/status.json").status_code == 404     # 목록에 없는 파일
    assert any(j["id"] == jid for j in client.get("/api/jobs").json())


def test_stochastic_job_progress_and_cancel(client):
    req = {**BASE, "method": "ctmc", "population": 300000, "days": 200, "n_runs": 400, "R0": 3.0}
    jid = client.post("/api/scenarios", json=req).json()["job_id"]
    t0 = time.time()
    while client.get(f"/api/jobs/{jid}").json()["state"] != "running" and time.time() - t0 < 60:
        time.sleep(0.2)
    time.sleep(2.0)
    client.delete(f"/api/jobs/{jid}")
    s = _wait(client, jid, 120)
    assert s["state"] == "cancelled" and 0 < s["progress"] < 1


def test_input_validation(client):
    bad = [{**BASE, "method": "euler"}, {**BASE, "n_runs": 0}, {**BASE, "R0": -1}, {**BASE, "days": 99999},
           {**BASE, "unknown": 1}, {**BASE, "dataset": "../etc"}, {**BASE, "seeds": []},
           {**BASE, "interventions": [{"start": 0, "end": 10, "value": 1.5}]},
           {**BASE, "r0_reference": "region"},                                       # 기준 지역 없음
           {**BASE, "seeds": [{"region": "region0", "count": 30000}]},              # 인구(2만)보다 많은 초기 감염
           {**BASE, "interventions": [{"start": 50, "end": 10, "value": 0.2}]},     # 끝일 < 시작일
           {**BASE, "disease": {"incubation_days": 0}},
           {**BASE, "disease": {"unknown": 1}},
           {**BASE, "climate": "exp_linear"},                                      # 합성 지역에 기후 자료 없음
           {**BASE, "hybrid_up": 10, "hybrid_down": 20},
           {**BASE, "seeds": [{"region": "region0", "count": 0, "exposed": 0}]}]
    for b in bad:
        assert client.post("/api/scenarios", json=b).status_code == 422, b
    assert client.post("/api/scenarios", json={**BASE, "dataset": "NoSuchDataset"}).status_code == 422


def test_paths_are_not_traversable(client):
    assert client.get("/api/jobs/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/jobs/0123/summary").status_code == 404
    assert client.get("/api/jobs/" + "0" * 32 + "/export/..%2Fstatus.json").status_code == 404
    assert client.get("/api/datasets/..%2Fx/geojson").status_code in (400, 404)
    assert client.get("/api/forecast-history?iso3=../x").status_code == 400


def test_dataset_activate_and_rollback_via_api(client, tmp_path, monkeypatch):
    import seir_sim.data.versions as V
    from test_data_versions import _ds
    store = tmp_path / "store"
    monkeypatch.setenv("SEIR_SIM_DATASET_STORE", str(store))
    reg = V.Registry()
    p1, p2 = tmp_path / "a.nc", tmp_path / "b.nc"
    _ds().save(p1)
    d2 = _ds((1e5, 2e5, 4e5))
    d2.mobility[:] = np.array([[0, 30, 10], [30, 0, 20], [10, 20, 0]], float) / d2.population[:, None]
    d2.save(p2)
    reg.register("T", p1)
    reg.activate("T", "v1")
    reg.register("T", p2)
    ds = client.get("/api/datasets").json()
    assert ds[0]["name"] == "T" and ds[0]["active"] == "v1" and len(ds[0]["versions"]) == 2
    assert client.post("/api/datasets/T/activate", json={"version": "v2"}).json() == {"active": "v2"}
    assert client.post("/api/datasets/T/rollback").json() == {"active": "v1"}
    assert client.post("/api/datasets/T/rollback").status_code == 409
    assert client.post("/api/datasets/T/activate", json={"version": "v9"}).status_code == 409
    r = client.get("/api/datasets/T/regions").json()
    assert r["ids"] == ["A", "B", "C"]
    # 출처 열 없는 인구표는 받지 않는다
    r = client.post("/api/datasets/T/population-table", json={"table_text": "id,population\nA,5\n"})
    assert r.status_code == 422 and "출처" in r.json()["detail"]
    # 저장소 데이터셋으로 시나리오 (지역 이름 검사 포함)
    req = {**BASE, "dataset": "T", "population": None, "seeds": [{"region": "Z", "count": 3}]}
    assert client.post("/api/scenarios", json=req).status_code == 422
    req["seeds"] = [{"region": "A", "count": 3}]
    jid = client.post("/api/scenarios", json=req).json()["job_id"]
    s = _wait(client, jid)
    assert s["state"] == "done", s
    sm = client.get(f"/api/jobs/{jid}/summary").json()
    assert [r["id"] for r in sm["regions"]] == ["A", "B", "C"] and len(sm["frames"]["t"]) > 0
    # 지도와 그래프의 일관성: 지도 프레임(지역별 평균 I)의 합 = 그래프의 전체 I 평균 (같은 시점)
    t_daily = sm["daily"]["t"]
    for i, t in enumerate(sm["frames"]["t"]):
        k = t_daily.index(t)
        assert sum(sm["frames"]["I"][i]) == pytest.approx(sm["daily"]["mean"][k], abs=0.2)
        assert sum(sm["frames"]["D"][i]) == pytest.approx(sm["daily"]["D_mean"][k], abs=0.05)
    # 이동·통근을 끄면 A 밖으로 퍼지지 않는다
    jid = client.post("/api/scenarios", json={**req, "use_mobility": False, "use_commuting": False}).json()["job_id"]
    assert _wait(client, jid)["state"] == "done"
    sm = client.get(f"/api/jobs/{jid}/summary").json()
    assert [r["arrival_probability"] for r in sm["regions"]] == [1.0, 0.0, 0.0]
    assert any("이동" in w for w in sm["warnings"])
    # 이동 흐름 (가정 총량 기반이라는 설명 포함)
    f = client.get("/api/datasets/T/flows?top=5").json()
    assert len(f["flows"]) == 3 and "실측" in f["note"]
    assert client.post("/api/scenarios/check", json={**req, "climate": "exp_linear"}).status_code == 422   # 기후 자료 없음


def test_check_estimate_disease_params_and_immunity(client):
    r = client.post("/api/scenarios/check", json=BASE)
    assert r.status_code == 200 and r.json()["estimate"]["seconds"] >= 0
    req = {**BASE, "title": "면역 50%", "disease": {"name": "시험병", "incubation_days": 3, "infectious_days": 5, "immunity_days": 0,
                                                  "f1": 0.02, "M": 4}, "initial_immune_fraction": 0.5,
           "seeds": [{"region": "region0", "count": 5, "exposed": 5}]}
    jid = client.post("/api/scenarios", json=req).json()["job_id"]
    assert _wait(client, jid)["state"] == "done"
    sm = client.get(f"/api/jobs/{jid}/summary").json()
    src = sm["labels"]["parameters"]
    assert src["sigma"] == "사용자 입력" and src["P1"] == "기본 가정값"
    assert sm["labels"]["disease"]["sigma"] == pytest.approx(1 / 3) and sm["labels"]["disease"]["lam"] == 0.0
    assert sm["regions"][0]["population"] == pytest.approx(20000)
    assert sm["regions"][0]["attack_mean"] <= 0.5 + 1e-9                      # 절반은 시작부터 면역
    for k in ("I", "E", "D", "first", "I_q05", "I_q95"):
        assert len(sm["frames"][k]) == len(sm["frames"]["t"])
    for k in ("R_mean", "new_first_mean", "cum_first_mean", "D_q05", "q25", "q75"):
        assert len(sm["daily"][k]) == len(sm["daily"]["t"])
    assert client.get(f"/api/jobs/{jid}/export/regions_daily.csv").status_code == 200


def test_disease_presets(client):
    assert client.get("/api/diseases").json() == {}
    r = client.post("/api/diseases", json={"disease": {"name": "가상병", "incubation_days": 4}, "R0": 1.8, "note": "시험"})
    assert r.json() == {"saved": "가상병"}
    d = client.get("/api/diseases").json()
    assert d["가상병"]["disease"]["incubation_days"] == 4 and d["가상병"]["R0"] == 1.8
    assert client.post("/api/diseases", json={"disease": {"name": "x", "f1": 2}}).status_code == 422
    assert client.delete("/api/diseases/가상병").json() == {"deleted": "가상병"}
    assert client.delete("/api/diseases/가상병").status_code == 404


def test_update_policy_endpoints(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SEIR_SIM_RAW_DIR", str(tmp_path / "raw"))
    st = client.get("/api/updates").json()
    assert any(x["id"] == "openflights" for x in st["datasets"])
    r = client.post("/api/updates/openflights/policy", json={"interval_days": 30, "auto": False})
    assert r.json() == {"interval_days": 30, "auto": False}
    assert client.post("/api/updates/openflights/policy", json={"interval_days": 0.5}).status_code in (200, 422)
    assert client.post("/api/updates/nope/policy", json={"interval_days": 3}).status_code == 404
    assert client.post("/api/updates/nope/check").status_code == 404


def test_live_preview_and_parameter_uncertainty(client):
    """확률 실행: 시작 직후 ODE 미리보기 -> 실행 평균 -> final. 불확실성 범위: 실행마다 다른 매개변수 (재현 가능)."""
    req = {**BASE, "method": "tau", "n_runs": 4, "uncertainty": {"R0": [1.5, 3.0], "infectious_days": [5, 9]}}
    r = client.post("/api/scenarios", json=req)
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    s = _wait(client, jid)
    assert s["state"] == "done", s
    assert s["live_seq"] >= 2 and s["live_kind"] == "final"
    live = client.get(f"/api/jobs/{jid}/live").json()
    assert live["kind"] == "final" and live["runs_done"] == 4 and live["n_runs"] == 4
    assert len(live["I"]) == len(live["t_frames"]) and len(live["daily"]["S"]) == len(live["daily"]["t"])
    sm = client.get(f"/api/jobs/{jid}/summary").json()
    pu = sm["parameter_uncertainty"]
    assert pu["ranges"]["R0"] == [1.5, 3.0] and len(pu["draws"]) == 4
    assert all(1.5 <= d["R0"] <= 3.0 and 5 <= d["infectious_days"] <= 9 for d in pu["draws"])
    assert len({round(d["R0"], 6) for d in pu["draws"]}) == 4
    assert any("매개변수 불확실성" in w for w in sm["warnings"])
    from seir_sim.web.scenario import ScenarioRequest, parameter_draws
    assert parameter_draws(ScenarioRequest.model_validate(req)) == pu["draws"]          # 같은 시드 -> 같은 추출


def test_uncertainty_validation(client):
    for bad in ({"R0": [3.0, 2.0]}, {"R0": [0.0, 2.0]}, {"f1": [0.1, 1.5]}, {"unknown": [1, 2]}):
        r = client.post("/api/scenarios/check", json={**BASE, "uncertainty": bad})
        assert r.status_code == 422, (bad, r.text)


def test_rename_and_delete_saved_result(client):
    jid = client.post("/api/scenarios", json=BASE).json()["job_id"]
    assert _wait(client, jid)["state"] == "done"
    assert client.post(f"/api/jobs/{jid}/rename", json={"title": "새 이름"}).json()["title"] == "새 이름"
    assert client.post(f"/api/jobs/{jid}/rename", json={"title": ""}).status_code == 422
    assert client.delete(f"/api/jobs/{jid}/files").json() == {"deleted": jid}
    assert client.get(f"/api/jobs/{jid}").status_code == 404
    assert client.delete("/api/jobs/" + "f" * 32 + "/files").status_code == 404


def test_delete_refuses_running_job(client):
    jid = client.post("/api/scenarios", json={**BASE, "method": "ctmc", "population": 200000, "n_runs": 50,
                                               "days": 365}).json()["job_id"]
    t0 = time.time()
    while client.get(f"/api/jobs/{jid}").json()["state"] == "queued" and time.time() - t0 < 60:
        time.sleep(0.1)
    if client.get(f"/api/jobs/{jid}").json()["state"] == "running":
        assert client.delete(f"/api/jobs/{jid}/files").status_code == 409
    client.delete(f"/api/jobs/{jid}")
    _wait(client, jid)


def test_climate_period_input_validation(client):
    for bad in ({"start": "2025-13", "end": "2026-01"}, {"start": "2026-02", "end": "2026-01"},
                {"start": "1900-01", "end": "1900-02"}, {"start": "2000-01", "end": "2012-01"}, {}):
        assert client.post("/api/climate-periods", json=bad).status_code == 422, bad
    assert client.get("/api/datasets/KOR_admin1/regions?boundary_date=20261001").status_code == 400
    assert client.post("/api/scenarios/check", json={**BASE, "climate_period": "../etc"}).status_code == 422
