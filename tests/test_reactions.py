"""공통 사건 목록: 1.4절 방정식과 항 단위로 일치, 색인, 인구 보존."""

import numpy as np
import pytest

from conftest import make_params, random_state
from reference_ode import reference_rhs
from seir_sim.model import reactions as R
from seir_sim.model.drivers import Drivers, EnvironmentSeries, InterventionSchedule
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet
from seir_sim.model.state import Layout, initial_state


def _system(K, M, seed, with_env=False, with_u=False, mobility=1e-2):
    rng = np.random.default_rng(seed)
    p = make_params(M=M, alpha=0.7, beta=0.4, lam=0.03, f1=0.05)
    regions = RegionSet.synthetic_random(K, rng, total_population=1e5, mobility_scale=mobility)
    env = None
    g_spec = None
    if with_env:
        days = 10
        env = EnvironmentSeries(rng.normal(15, 8, (days, K)), rng.uniform(30, 90, (days, K)))
        g_spec = {"form": "exp_linear", "a_T": -0.02, "a_H": -0.005, "T_ref": 15.0, "H_ref": 60.0}
    u = InterventionSchedule(K, [{"start": 0.0, "end": 5.0, "value": 0.4, "regions": [0]},
                                 {"start": 2.0, "end": 8.0, "value": 0.2, "regions": None}]
                             if with_u else [])
    drivers = Drivers(K, g_spec, env, u)
    sysm = ReactionSystem(p, regions, drivers, {"form": "power", "eta": 0.25}, "pop_weighted_mean")
    return sysm, rng


@pytest.mark.parametrize("K,M", [(1, 1), (1, 2), (1, 4), (3, 1), (3, 4), (5, 6)])
@pytest.mark.parametrize("with_env,with_u", [(False, False), (True, True)])
def test_drift_matches_reference_equations(K, M, with_env, with_u):
    sysm, rng = _system(K, M, seed=100 * K + M, with_env=with_env, with_u=with_u)
    for t in (0.0, 3.5, 6.0):
        X = random_state(sysm.layout, rng)
        got = sysm.drift(X, t)
        ref = reference_rhs(sysm.params, sysm.regions, sysm.h_values, sysm.drivers.g(t),
                            sysm.drivers.u(t), X, sysm.layout)
        np.testing.assert_allclose(got, ref, rtol=1e-11, atol=1e-9)


@pytest.mark.parametrize("K,M", [(1, 4), (4, 4), (6, 3)])
def test_population_conservation_in_drift(K, M):
    sysm, rng = _system(K, M, seed=K * 7 + M)
    L = sysm.layout
    for _ in range(5):
        X = random_state(L, rng)
        d = sysm.drift(X, 0.0)
        assert abs(d.sum()) < 1e-9 * X.sum()                          # 총인구 (D 포함)
        assert d[:, L.alive_slice].sum() == pytest.approx(-d[:, L.D].sum(), rel=1e-12)
        assert np.all(d[:, L.D] >= 0)


def test_integer_events_conserve_population():
    sysm, rng = _system(4, 4, seed=3)
    X = np.floor(random_state(sysm.layout, rng))
    total = X.sum()
    for _ in range(200):
        counts = np.zeros(len(sysm.channels))
        j = rng.integers(len(sysm.channels))
        if X.reshape(-1)[sysm.channels.src[j]] >= 1:
            counts[j] = 1
        X = sysm.apply(X, counts)
        assert X.sum() == total and np.all(X >= 0)


@pytest.mark.parametrize("M", [1, 2, 4, 5])
def test_reinfection_channel_indices(M):
    sysm, _ = _system(2, M, seed=M)
    p, L, ch = sysm.params, sysm.layout, sysm.channels
    nc = L.ncomp
    for i in range(2):
        for l in range(1, M + 1):
            for kind, comp, susc in ((R.REINF_P, L.RP(l), float(p.P(l + 1))),
                                     (R.REINF_W, L.RW(l), p.P1)):
                sel = (ch.kind == kind) & (ch.src == i * nc + comp)
                assert sel.sum() == 1
                j = np.flatnonzero(sel)[0]
                assert ch.dst[j] == i * nc + L.E(min(l + 1, M))
                assert ch.susc[j] == pytest.approx(susc)
                assert ch.const[j] == 0.0
        sel = (ch.kind == R.INFECT_S) & (ch.src == i * nc + L.S)
        assert sel.sum() == 1 and ch.dst[sel][0] == i * nc + L.E(1)
        assert ch.susc[sel][0] == p.P1
    # 마지막 칸 R^P_M 은 P(M+1) 을 쓰고 E_M 으로 간다
    j = np.flatnonzero((ch.kind == R.REINF_P) & (ch.src == L.RP(M)))[0]
    assert ch.susc[j] == pytest.approx(float(p.P(M + 1)))
    assert ch.dst[j] == L.E(M)


def test_channel_count_and_mobility_structure():
    sysm, _ = _system(5, 4, seed=1)
    K, M = 5, 4
    assert len(sysm.channels) == K * (1 + 2 * M + 4 * M)
    mb = sysm.mobility
    om = sysm.regions.mobility
    np.testing.assert_allclose(mb.out_rate, om.sum(axis=1))
    for i in range(K):
        js = mb.indices[mb.indptr[i]:mb.indptr[i + 1]]
        np.testing.assert_array_equal(js, np.flatnonzero(om[i] > 0))
        probs = np.diff(np.concatenate([[0.0], mb.cumprob[mb.indptr[i]:mb.indptr[i + 1]]]))
        np.testing.assert_allclose(probs, om[i, js] / om[i].sum(), rtol=1e-12)


def test_mobility_drift_matches_pairwise_sum():
    """합친 이동 drift = (i, j, c) 쌍마다 omega_ij X_ic 를 옮기는 원래 식. D 는 움직이지 않는다."""
    sysm, rng = _system(4, 3, seed=5)
    L = sysm.layout
    X = random_state(L, rng)
    om = sysm.regions.mobility
    ref = np.zeros_like(X)
    for i in range(4):
        for j in range(4):
            for c in range(L.D):
                ref[i, c] -= om[i, j] * X[i, c]
                ref[j, c] += om[i, j] * X[i, c]
    np.testing.assert_allclose(sysm.mobility_drift(X), ref, rtol=1e-12, atol=1e-9)
    assert np.all(sysm.mobility_drift(X)[:, L.D] == 0)
    np.testing.assert_allclose(sysm.mobility_propensities(X), om.sum(axis=1) * L.alive(X))


def test_force_of_infection_handles_empty_region():
    sysm, rng = _system(3, 2, seed=9)
    X = random_state(sysm.layout, rng)
    X[1, :] = 0.0                      # 지역 1 인구 0
    lam = sysm.force_of_infection(X, 0.0)
    assert np.all(np.isfinite(lam))
    d = sysm.drift(X, 0.0)
    ref = reference_rhs(sysm.params, sysm.regions, sysm.h_values, np.ones(3), np.zeros(3),
                        X, sysm.layout)
    np.testing.assert_allclose(d, ref, rtol=1e-11, atol=1e-9)
    # 빈 지역에는 이동 유입만 있다
    L = sysm.layout
    inflow = sysm.regions.mobility[:, 1] @ X[:, : L.D]
    np.testing.assert_allclose(d[1, : L.D], inflow, rtol=1e-12)


def test_waning_only_dynamics_is_linear_at_rate_lambda():
    """감염자 0 이면 Lambda = 0 이고 R^P_n 은 율 lambda 로만 R^W_n 으로 간다."""
    sysm, rng = _system(1, 4, seed=2, mobility=0.0)
    L, lam = sysm.layout, sysm.params.lam
    X = L.empty()
    for n in range(1, 5):
        X[0, L.RP(n)] = 100.0 * n
        X[0, L.RW(n)] = 7.0
    X[0, L.S] = 1000
    d = sysm.drift(X, 0.0)
    for n in range(1, 5):
        assert d[0, L.RP(n)] == pytest.approx(-lam * X[0, L.RP(n)])
        assert d[0, L.RW(n)] == pytest.approx(lam * X[0, L.RP(n)])
    assert d[0, L.S] == 0.0


def test_initial_state_conserves_population():
    L = Layout(3, 4)
    pop = np.array([100.0, 200.0, 300.0])
    X = initial_state(L, pop, {0: 10.0}, "I1")
    assert X.sum() == pop.sum() and X[0, L.I(1)] == 10 and X[0, L.S] == 90
    with pytest.raises(ValueError):
        initial_state(L, pop, {0: 1000.0})
    with pytest.raises(ValueError):
        initial_state(L, pop, {0: 1.0}, "D")
    with pytest.raises(IndexError):
        L.E(5)
