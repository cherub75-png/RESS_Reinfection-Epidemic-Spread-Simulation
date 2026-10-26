"""설정 스키마와 시나리오 구성."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from seir_sim.config.build import build_scenario, load_config
from seir_sim.config.schema import Config

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def _raw(name):
    return yaml.safe_load((CONFIGS / name).read_text(encoding="utf-8"))


def test_single_region_example_builds():
    cfg = load_config(CONFIGS / "example_single_region.yaml")
    sc = build_scenario(cfg)
    d = cfg.disease
    assert d.sigma == pytest.approx(1 / 5.2) and d.gamma == pytest.approx(1 / 7)
    assert d.lam == pytest.approx(1 / 180)
    assert sc.derived["c0"] == pytest.approx(2.5 / 7)
    assert sc.derived["R0_reference"] == pytest.approx(2.5)
    assert sc.derived["R0_network_t0"] == pytest.approx(2.5)   # 단일 지역, rho = rho_ref
    L = sc.system.layout
    assert sc.X0.sum() == pytest.approx(1e6)
    assert sc.X0[0, L.I(1)] == 10
    assert sc.derived["regions_synthetic"] is True


def test_network_example_calibrates_R0():
    sc = build_scenario(load_config(CONFIGS / "example_synthetic_network.yaml"))
    assert sc.system.regions.K == 17
    assert sc.derived["R0_network_t0"] == pytest.approx(2.5, rel=1e-10)
    assert sc.X0.sum() == pytest.approx(5e7)


def test_transmission_requires_exactly_one():
    raw = _raw("example_single_region.yaml")
    raw["disease"]["transmission"] = {"R0": 2.5, "c0": 0.3}
    with pytest.raises(ValidationError):
        Config.model_validate(raw)
    raw["disease"]["transmission"] = {}
    with pytest.raises(ValidationError):
        Config.model_validate(raw)


def test_unknown_key_rejected():
    raw = _raw("example_single_region.yaml")
    raw["disease"]["sigmaa"] = 0.2
    with pytest.raises(ValidationError):
        Config.model_validate(raw)


def _dataset(role):
    return {"name": "x", "role": role, "source": "s", "version": "v", "license": "l",
            "resolution": "r", "time_range": "t"}


def test_data_role_separation():
    raw = _raw("example_single_region.yaml")
    raw["run_mode"] = "forecast"
    raw["datasets"] = [_dataset("historical_training")]
    with pytest.raises(ValidationError, match="current_input"):
        Config.model_validate(raw)
    raw["datasets"] = [_dataset("current_input")]
    Config.model_validate(raw)
    raw["run_mode"] = "calibration"
    with pytest.raises(ValidationError, match="누설"):
        Config.model_validate(raw)


def test_hybrid_threshold_order():
    raw = _raw("example_single_region.yaml")
    raw["simulation"]["hybrid"] = {"threshold_up": 10, "threshold_down": 50}
    with pytest.raises(ValidationError):
        Config.model_validate(raw)


def test_dataset_regions_not_implemented():
    raw = _raw("example_single_region.yaml")
    raw["regions"] = {"source": "dataset", "path": "x"}
    with pytest.raises(NotImplementedError):
        build_scenario(Config.model_validate(raw))
