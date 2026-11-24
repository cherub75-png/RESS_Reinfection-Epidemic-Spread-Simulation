"""7단계: 추정 결과 -> 엔진 설정 통합. 엔진(DOP853)이 추정용 FastODE 와 같은 궤적을 내는지 확인한다 (합성 매개변수)."""

import numpy as np
import pandas as pd
import pytest

from seir_sim.config.build import build_scenario
from seir_sim.config.schema import Config
from seir_sim.inference.calibrate import FitSpec, SingleRegionModel
from seir_sim.inference.export import calibrated_config
from seir_sim.model.params import EpiParams
from seir_sim.simulate.ode import integrate_ode

BASE8 = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1, T1=1, Pmin=0.3, alpha=0.5, beta=0.3,
             lam=1 / 180, f1=0.01, M=8)


def _model():
    m = SingleRegionModel(EpiParams(**BASE8), 5e6, FitSpec(start="2020-02-01", fit_end="2020-09-30"))
    th = np.zeros(len(m.names))
    rt = np.array([2.6, 2.0, 0.8, 0.7, 0.9, 1.1, 1.3, 1.2, 1.0, 0.9, 0.8, 0.9, 1.0, 1.1, 1.0, 1.0, 1.0, 1.0])[: m.n_knots]
    mm = rt / 6.0
    th[: m.n_knots] = np.log(mm / (1 - mm))
    th[m.idx["log_I0"]] = np.log(25.0)
    return m, th


def test_exported_config_reproduces_fastode():
    m, th = _model()
    cfg = Config.model_validate(calibrated_config(m, th, "SYN", "합성 검사", {"source": "test"}))
    sc = build_scenario(cfg)
    assert not sc.system.regions.synthetic                        # source: single = 실제 단일 지역 형식
    assert sc.derived["c0"] == pytest.approx(m.c0, rel=1e-12)
    tr = integrate_ode(sc.system, sc.X0, cfg.simulation.days, rtol=1e-10, atol=1e-8)
    par = m.unpack(th)
    L = m.layout
    X0 = L.empty()
    I0 = par["I0"]
    E0 = I0 * m.base.gamma / m.base.sigma
    X0[0, L.S] = m.N - I0 - E0
    X0[0, L.I(1)] = I0
    X0[0, L.E(1)] = E0
    np.testing.assert_allclose(sc.X0, X0, rtol=1e-12)
    inf, ons, dea, xe = m.fast.run(X0, m.fast.gc_from_u(m.u_days(par["m"], m.spec.n_fit_days)))
    assert np.max(np.abs(xe - tr.X[-1])) / m.N < 1e-8
    np.testing.assert_allclose(dea[:, 0], np.diff(tr.X[:, 0, L.D]), atol=1e-6 * tr.X[-1, 0, L.D])
    assert len(cfg.interventions) == m.n_knots and cfg.interventions[-1].end == m.spec.n_fit_days


def test_single_region_requires_population_source():
    m, th = _model()
    raw = calibrated_config(m, th, "SYN", "x", {})
    raw["regions"].pop("population_source")
    with pytest.raises(ValueError, match="population_source"):
        build_scenario(Config.model_validate(raw))


def test_integer_seeds_for_stochastic_methods():
    m, th = _model()
    cfg = Config.model_validate(calibrated_config(m, th, "SYN", "x", {}, integer_seeds=True, method="hybrid", n_runs=2))
    sc = build_scenario(cfg)
    assert np.allclose(sc.X0, np.round(sc.X0))
