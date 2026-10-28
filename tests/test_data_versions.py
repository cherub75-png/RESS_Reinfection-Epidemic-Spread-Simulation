"""6단계: 데이터셋 버전 관리, 로컬 인구표·기후표 입력 경로 (합성 3지역 자료로 검사)."""

import csv
from dataclasses import replace

import numpy as np
import pytest

from seir_sim.data.climate import attach_monthly_table
from seir_sim.data.dataset import RegionDataset
from seir_sim.data.versions import Registry, validate_dataset


def _ds(pop=(1e5, 2e5, 3e5)):
    pop = np.array(pop, float)
    K = pop.size
    C = np.full((K, K), 0.1)
    np.fill_diagonal(C, 0.0)
    C += np.diag(1 - C.sum(1))
    F = np.array([[0, 30, 10], [30, 0, 20], [10, 20, 0]], float)     # 대칭 이동량 -> 균형
    om = F / pop[:, None]
    return RegionDataset(["A", "B", "C"], ["a", "b", "c"], pop, np.array([10.0, 20, 30]), np.array([1.0, 2, 3]),
                         np.array([10.0, 11, 12]), C, om, {"population": {"source": "test"}, "boundaries": "test"},
                         synthetic=True)


def test_validate_flags_errors_and_warnings():
    v = validate_dataset(_ds())
    assert v["ok"] and any("합성" in w for w in v["warnings"])
    bad = _ds()
    bad.mobility[0, 1] *= 2                                          # 불균형
    assert not validate_dataset(bad)["ok"]
    bad = _ds()
    bad.contact[0, 0] += 0.1
    assert not validate_dataset(bad)["ok"]
    miss = _ds((1e5, np.nan, 3e5))
    v = validate_dataset(miss)
    assert any("결측" in w for w in v["warnings"])


def test_register_activate_rollback_and_integrity(tmp_path):
    reg = Registry(tmp_path / "store")
    p1 = tmp_path / "d1.nc"
    _ds().save(p1)
    assert reg.register("T", p1, "first") == "v1"
    reg.activate("T", "v1")
    p2 = tmp_path / "d2.nc"
    d2 = _ds((1e5, 2.4e5, 3e5))
    d2.mobility[:] = np.array([[0, 30, 10], [30, 0, 20], [10, 20, 0]], float) / d2.population[:, None]
    d2.save(p2)
    assert reg.register("T", p2, "update") == "v2"
    e = reg.list()["T"]["versions"][1]
    assert e["diff_vs_active"]["population_changed_over_5pct"] == ["B"]
    reg.activate("T", "v2")
    assert RegionDataset.load(reg.resolve("T")).population[1] == 2.4e5
    assert reg.rollback("T") == "v1"
    assert RegionDataset.load(reg.resolve("T")).population[1] == 2e5
    assert RegionDataset.load(reg.resolve("T@v2")).population[1] == 2.4e5
    # 같은 이름 새 Registry 객체로 읽어도 상태 유지
    assert Registry(tmp_path / "store").list()["T"]["active"] == "v1"
    # 파일이 바뀌면 거부
    f = tmp_path / "store" / "T" / "v1.nc"
    with open(f, "ab") as fh:
        fh.write(b"x")
    with pytest.raises(ValueError, match="SHA-256"):
        reg.resolve("T")


def test_invalid_version_cannot_be_activated(tmp_path):
    reg = Registry(tmp_path / "store")
    bad = _ds()
    bad.mobility[0, 1] = -1.0
    p = tmp_path / "bad.nc"
    bad.save(p)
    reg.register("B", p)
    with pytest.raises(ValueError, match="검증 실패"):
        reg.activate("B", "v1")


def test_population_table_and_climate_table(tmp_path):
    from seir_sim.data import population as popmod
    from seir_sim.data.boundaries import RegionGeometry
    t = tmp_path / "pop.csv"
    with open(t, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "population", "source", "tier", "reference_date"])
        w.writerow(["A", "100", "s1", "primary", "2020"])
        w.writerow(["C", "300", "s1", "primary", "2020"])
        w.writerow(["Z", "5", "s1", "primary", "2020"])

    class G:
        ids = ["A", "B", "C"]
    pop, meta = popmod.from_table(t, G)
    assert pop[0] == 100 and np.isnan(pop[1]) and pop[2] == 300          # 없는 지역은 NaN (보간 안 함)
    assert meta["missing"] == ["B"] and meta["unused_ids"] == ["Z"]
    with open(t, "a", newline="") as fh:
        csv.writer(fh).writerow(["A", "1", "s", "p", "x"])
    with pytest.raises(ValueError, match="중복"):
        popmod.from_table(t, G)
    c = tmp_path / "clim.csv"
    with open(c, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "month", "tavg", "rh", "source", "period"])
        for m in range(1, 13):
            w.writerow(["A", m, m, 50, "obs", "2020~2022"])
            w.writerow(["B", m, -m, 60, "obs", "2020~2022"])
    ds = attach_monthly_table(_ds(), c)
    assert ds.tavg.shape == (12, 3) and ds.tavg[4, 0] == 5 and np.all(np.isnan(ds.tavg[:, 2]))
    assert ds.provenance["climate"]["missing_cells"] == 24
    assert any("기후 결측" in w for w in validate_dataset(ds)["warnings"])


def test_config_reads_registry_path(tmp_path, monkeypatch):
    from seir_sim.config import build as B
    from seir_sim.config.schema import Config
    import seir_sim.data.versions as V
    store = tmp_path / "store"
    reg = Registry(store)
    p = tmp_path / "d.nc"
    replace(_ds(), synthetic=False).save(p)
    reg.register("T", p)
    reg.activate("T", "v1")
    monkeypatch.setattr(V, "STORE", store)
    monkeypatch.setattr(V.Registry.__init__, "__defaults__", (store,))
    cfg = Config.model_validate({
        "run_mode": "development", "meta": {"name": "t"},
        "disease": {"sigma": 0.2, "gamma": 0.15, "transmission": {"R0": 2.0}, "P1": 1, "T1": 1, "Pmin": 0.3,
                    "alpha": 0.5, "beta": 0.3, "lam": 0.005, "f1": 0.01, "M": 4},
        "regions": {"source": "dataset", "path": "registry:T"},
        "initial": {"start_date": "2020-01-01", "seeds": [{"region": "A", "count": 5}]},
        "simulation": {"days": 10, "method": "ode", "n_runs": 1}})
    sc = B.build_scenario(cfg)
    assert sc.system.regions.K == 3
