"""1-E: 앙상블 실행기, 저장, 명령줄, 그림."""

import json
from pathlib import Path

import numpy as np
import pytest

from seir_sim.config.build import load_config
from seir_sim.ensemble.runner import run_ensemble

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


@pytest.fixture(scope="module")
def small_cfg():
    cfg = load_config(CONFIGS / "example_synthetic_network.yaml")
    cfg.simulation.days = 60
    cfg.disease.M = 3
    return cfg


def test_statistics_follow_section_1_6(small_cfg):
    res = run_ensemble(small_cfg, method="tau", n_runs=12, n_workers=1, outbreak_threshold=500.0)
    I = res.runs[:, 2].sum(axis=2).astype(float)
    s = res.summary()
    R = I.shape[0]
    np.testing.assert_allclose(s["mean"], I.mean(axis=0))
    np.testing.assert_allclose(s["var"], ((I - I.mean(axis=0)) ** 2).sum(axis=0) / (R - 1))   # 1/(R-1)
    np.testing.assert_allclose(s["q05"], np.percentile(I, 5, axis=0))
    np.testing.assert_allclose(s["q95"], np.percentile(I, 95, axis=0))
    assert s["outbreak_probability"] == pytest.approx(np.mean(I.max(axis=1) >= 500.0))
    # 지역 합 = 전체
    np.testing.assert_allclose(res.region_summary()["mean"].sum(axis=1), s["mean"], rtol=1e-6)
    # 저장한 S, E, I, D 의 지역 합은 총인구 - (R 구획) 이하이고 D 는 줄지 않는다
    assert np.all(np.diff(res.runs[:, 3].sum(axis=2), axis=1) >= 0)


def test_parallel_equals_serial_and_seeds_recorded(small_cfg):
    a = run_ensemble(small_cfg, method="hybrid", n_runs=6, n_workers=1)
    b = run_ensemble(small_cfg, method="hybrid", n_runs=6, n_workers=3)
    np.testing.assert_array_equal(a.runs, b.runs)
    assert [s["spawn_key"] for s in a.seeds] == [[r] for r in range(6)]
    assert a.seeds[0]["entropy"] == str(small_cfg.simulation.seed)


def test_ode_runs_once(small_cfg):
    res = run_ensemble(small_cfg, method="ode", n_runs=50)
    assert res.runs.shape[0] == 1
    assert np.all(res.summary()["var"] == 0)


def test_save_roundtrip(small_cfg, tmp_path):
    import pandas as pd
    import xarray as xr
    res = run_ensemble(small_cfg, method="sde", n_runs=4, n_workers=1)
    res.save(tmp_path)
    with xr.open_dataset(tmp_path / "ensemble.nc", engine="h5netcdf") as ds:
        np.testing.assert_array_equal(ds["I"].values, res.runs[:, 2])
        np.testing.assert_allclose(ds["I_total_mean"].values, res.summary()["mean"])
        rec = json.loads(ds.attrs["record"])
        assert ds.attrs["synthetic_regions"] == 1
    assert rec["method"] == "sde" and rec["n_runs"] == 4 and len(rec["seeds"]) == 4
    assert len(rec["config_sha256"]) == 64 and rec["environment"]["packages"]["numpy"]
    assert rec["regions_synthetic"] is True
    daily = pd.read_parquet(tmp_path / "summary_daily.parquet")
    np.testing.assert_allclose(daily["I_total_mean"].values, res.summary()["mean"])
    assert (tmp_path / "run_record.json").exists()


def test_cli_info_and_run(tmp_path, capsys):
    from seir_sim.cli import main
    main(["info", str(CONFIGS / "example_single_region.yaml")])
    out = json.loads(capsys.readouterr().out)
    assert out["K"] == 1 and out["derived"]["R0_network_t0"] == pytest.approx(2.5)
    main(["run", str(CONFIGS / "example_single_region.yaml"), "--out", str(tmp_path), "--method", "ode",
          "--days", "100"])
    out = json.loads(capsys.readouterr().out)
    assert out["runs"] == 1 and out["synthetic_regions"] is True
    for f in ("ensemble.nc", "summary_daily.parquet", "summary_regions.parquet", "I_total.png", "regions_heatmap.png"):
        assert (tmp_path / f).exists(), f
