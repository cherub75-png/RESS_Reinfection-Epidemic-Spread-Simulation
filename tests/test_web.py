"""8단계: 웹 API (FastAPI TestClient). 합성 단일 지역과 임시 데이터셋 저장소만 쓴다."""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from seir_sim.web.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(job_root=tmp_path / "jobs")
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
           {**BASE, "r0_reference": "region"}]                                       # 기준 지역 없음
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
