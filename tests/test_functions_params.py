"""1.2절 함수와 매개변수 객체: 정의, 색인, 검증."""

import numpy as np
import pytest

from conftest import make_params
from seir_sim.model import functions as F
from seir_sim.model.params import EpiParams


def test_susceptibility_definition(base_params):
    p = base_params
    n = np.arange(1, 30)
    P = p.P(n)
    assert P[0] == pytest.approx(p.P1)
    expected = p.Pmin + (p.P1 - p.Pmin) * np.exp(-p.alpha * (n - 1))
    np.testing.assert_allclose(P, expected, rtol=0, atol=0)
    assert np.all(np.diff(P) < 0)                 # alpha > 0 이면 엄격히 감소
    assert P[-1] == pytest.approx(p.Pmin, abs=1e-5)


def test_transmissibility_definition(base_params):
    p = base_params
    n = np.arange(1, 10)
    np.testing.assert_allclose(p.T(n), p.T1 * n ** (-p.beta))
    assert p.T(1) == pytest.approx(p.T1)


def test_fatality_definition(base_params):
    p = base_params
    n = np.arange(1, p.M + 1)
    np.testing.assert_allclose(p.f_by_n, p.f1 * n ** -0.5)
    assert p.f_by_n[0] == pytest.approx(p.f1)


def test_waning_susceptibility_limits(base_params):
    p = base_params
    for n in range(1, 8):
        Pn = float(p.P(n))
        assert F.susceptibility_waning(n, 0.0, p.P1, p.Pmin, p.alpha, p.lam) == pytest.approx(Pn)
        assert F.susceptibility_waning(n, 1e6, p.P1, p.Pmin, p.alpha, p.lam) == pytest.approx(p.P1)
        tau = np.linspace(0, 1000, 50)
        v = F.susceptibility_waning(n, tau, p.P1, p.Pmin, p.alpha, p.lam)
        assert np.all(np.diff(v) >= -1e-15)       # tau 에 대해 단조 증가


@pytest.mark.parametrize("M", [1, 2, 3, 4, 7])
def test_index_arrays(M):
    p = make_params(M=M)
    np.testing.assert_allclose(p.P_next_by_n, [p.P(n + 1) for n in range(1, M + 1)])
    np.testing.assert_allclose(p.T_by_n, [p.T(n) for n in range(1, M + 1)])
    assert p.P_next_by_n.shape == (M,) and p.T_by_n.shape == (M,) and p.f_by_n.shape == (M,)
    assert [p.m(n) for n in range(1, M + 1)] == [min(n + 1, M) for n in range(1, M + 1)]
    assert p.m(M) == M


def test_validation_errors():
    with pytest.raises(ValueError, match="phi"):
        make_params(phi_spec={"form": "table", "values": [0.5, 0.4]})
    with pytest.raises(ValueError, match="f\\(n\\)"):
        make_params(f1=0.9, phi_spec={"form": "table", "values": [1.0, 2.0]})
    with pytest.raises(ValueError, match="Pmin"):
        make_params(Pmin=1.5)
    with pytest.raises(ValueError, match="M"):
        make_params(M=0)
    with pytest.raises(ValueError, match="form"):
        make_params(phi_spec={"form": "nope"})


def test_phi_table_extends_last_value():
    phi = F.build_phi({"form": "table", "values": [1.0, 0.5]})
    np.testing.assert_allclose(phi(np.array([1, 2, 3, 9])), [1.0, 0.5, 0.5, 0.5])


def test_h_and_g_reference_points():
    h = F.build_h({"form": "power", "eta": 0.2})
    assert h(np.array([123.0]), 123.0)[0] == pytest.approx(1.0)
    g = F.build_g({"form": "exp_linear", "a_T": -0.03, "a_H": -0.01, "T_ref": 15.0, "H_ref": 60.0})
    assert g(15.0, 60.0) == pytest.approx(1.0)
    assert g(25.0, 60.0) == pytest.approx(np.exp(-0.3))


def test_params_frozen_and_with(base_params):
    q = base_params.with_(c0=1.0)
    assert q.c0 == 1.0 and base_params.c0 != 1.0
    assert isinstance(q, EpiParams)
