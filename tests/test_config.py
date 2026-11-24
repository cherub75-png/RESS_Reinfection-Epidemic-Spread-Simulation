"""설정 스키마와 시나리오 구성."""

from pathlib import Path

import numpy as np
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


def test_dataset_regions_missing_file_raises():
    raw = _raw("example_single_region.yaml")
    raw["regions"] = {"source": "dataset", "path": "/nonexistent/x.nc"}
    with pytest.raises(FileNotFoundError):
        build_scenario(Config.model_validate(raw))
    raw["regions"] = {"source": "dataset"}
    with pytest.raises(ValueError, match="path"):
        build_scenario(Config.model_validate(raw))


def test_default_r0_basis_is_reference_and_report_has_all_bases():
    """D-008 사용자 결정: 기본 reference. 모든 기준의 c0 와 R0 를 함께 기록한다."""
    raw = _raw("example_single_region.yaml")
    raw["disease"]["transmission"] = {"R0": 2.5}
    cfg = Config.model_validate(raw)
    assert cfg.disease.transmission.r0_reference == "reference"
    d = build_scenario(cfg).derived
    for k in ("R0_reference", "R0_network_t0", "R0_network_stationary",
              "mobility_imbalance_per_day", "R0_isolated_by_region", "R0_network_dominant_regions",
              "R0_network_dominant_population_share", "R0_isolated_population_weighted_mean",
              "population_share_isolated_R0_gt1", "c0_by_basis"):
        assert k in d
    assert d["R0_reference"] == pytest.approx(2.5)
    assert set(d["c0_by_basis"]) == {"reference", "network", "population_mean", "origin", "region"}


def _three_region_raw():
    return _raw("example_synthetic_network.yaml")        # 합성 17개 지역, h(rho) = (rho / rho_ref)^0.2


@pytest.mark.parametrize("basis", ["region", "origin", "population_mean", "reference", "network"])
def test_r0_bases_hit_their_targets_with_one_global_c0(basis):
    """각 기준으로 c0 를 정하면 그 기준의 R0 가 목표와 같다. c0 는 모든 지역에 하나다 (지역별 상대 전파력 유지)."""
    raw = _three_region_raw()
    sc0 = build_scenario(Config.model_validate(raw))
    names = list(sc0.system.regions.names)
    tr = {"R0": 2.0, "r0_reference": basis}
    if basis == "region":
        tr["reference_region"] = names[-1]
    raw["disease"]["transmission"] = tr
    sc = build_scenario(Config.model_validate(raw))
    d = sc.derived
    iso = d["R0_isolated_by_region"]
    target = {"region": iso[names[-1]], "origin": iso[raw["initial"]["seeds"][0]["region"]],
              "population_mean": d["R0_isolated_population_weighted_mean"], "reference": d["R0_reference"],
              "network": d["R0_network_t0"]}[basis]
    assert target == pytest.approx(2.0, rel=1e-9)
    assert d["c0"] == pytest.approx(d["c0_by_basis"][basis], rel=1e-12)
    # 지역 간 고립 R0 의 비는 기준과 무관하다 (인위적 왜곡 없음)
    ref = sc0.derived["R0_isolated_by_region"]
    ratios = [iso[n] / ref[n] for n in names]
    assert np.allclose(ratios, ratios[0], rtol=1e-12)


def test_reference_region_validation():
    raw = _three_region_raw()
    raw["disease"]["transmission"] = {"R0": 2.0, "r0_reference": "region"}
    with pytest.raises(ValueError, match="reference_region"):
        Config.model_validate(raw)
    raw["disease"]["transmission"] = {"R0": 2.0, "r0_reference": "region", "reference_region": "nowhere"}
    with pytest.raises(ValueError, match="기준 지역"):
        build_scenario(Config.model_validate(raw))
    raw["disease"]["transmission"] = {"R0": 2.0, "reference_region": "x"}
    with pytest.raises(ValueError, match="reference_region"):
        Config.model_validate(raw)


def test_seed_compartment_switch():
    raw = _raw("example_single_region.yaml")
    raw["initial"]["seed_compartment"] = "E1"
    sc = build_scenario(Config.model_validate(raw))
    L = sc.system.layout
    assert sc.X0[0, L.E(1)] == 10 and sc.X0[0, L.I(1)] == 0
    raw["initial"]["seeds"] = [{"region": "region0", "count": 4, "compartment": "I1"},
                               {"region": "region0", "count": 6}]
    sc = build_scenario(Config.model_validate(raw))
    assert sc.X0[0, L.I(1)] == 4 and sc.X0[0, L.E(1)] == 6 and sc.X0.sum() == pytest.approx(1e6)


def test_g_status_rules():
    raw = _raw("example_single_region.yaml")
    assert build_scenario(Config.model_validate(raw)).derived["g_status"] == "neutral_default"
    g = {"form": "exp_linear", "a_T": -0.02, "a_H": 0.0, "T_ref": 15.0, "H_ref": 60.0}
    raw["environment"] = {"g": g, "status": "neutral_default"}
    with pytest.raises(ValidationError, match="neutral_default"):
        Config.model_validate(raw)
    raw["environment"] = {"g": g, "status": "estimated"}
    with pytest.raises(ValidationError, match="estimate_ref"):
        Config.model_validate(raw)
    raw["environment"] = {"g": g, "status": "user_assumption"}
    Config.model_validate(raw)
