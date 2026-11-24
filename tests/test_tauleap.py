"""1-C: 이항 tau-leaping 검증."""

import numpy as np
import pytest
from scipy.linalg import expm

from conftest import make_params
from seir_sim.model import analysis as A
from seir_sim.model.drivers import Drivers, InterventionSchedule
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet
from seir_sim.model.state import initial_state
from seir_sim.simulate.ctmc import simulate_ctmc
from seir_sim.simulate.tauleap import simulate_tau

Z = 5.0


def _int_regions(reg):
    return RegionSet(reg.names, np.round(reg.population), reg.density, reg.contact, reg.mobility, True)


def test_reproducible_conservative_nonnegative():
    rng = np.random.default_rng(1)
    reg = _int_regions(RegionSet.synthetic_random(5, rng, total_population=2e5, mobility_scale=0.02))
    u = InterventionSchedule(5, [{"start": 20.0, "end": 50.0, "value": 0.4, "regions": [0, 2]}])
    sysm = ReactionSystem(make_params(M=4, f1=0.05, lam=1 / 30), reg, Drivers(5, None, None, u))
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, reg.population, {0: 5.0})
    a = simulate_tau(sysm, X0, 300, seed=11)
    b = simulate_tau(sysm, X0, 300, seed=11)
    c = simulate_tau(sysm, X0, 300, seed=12)
    np.testing.assert_array_equal(a.X, b.X)
    assert not np.array_equal(a.X, c.X)
    assert a.meta["max_abs_population_error"] == 0.0
    assert a.meta["min_value"] >= 0 and np.all(a.X == np.round(a.X))
    assert np.all(np.diff(a.totals(a.layout.D)) >= 0)


# --------------------------------------------------------------------- 선형계: 이항 leap 의 정확한 점화식

def _leap_matrix(sysm, tau):
    """c0 = 0 (선형)일 때 이항 leap 한 단계의 전이행렬 P (열 s = 구획 s 에 있던 한 사람의 도착 분포).
    이동은 (i, j, c) 쌍의 omega_ij 로 직접 만든다 (CSR 코드와 독립)."""
    L, ch, om = sysm.layout, sysm.channels, sysm.regions.mobility
    n = L.size
    P = np.zeros((n, n))
    for s in range(n):
        i, c = divmod(s, L.ncomp)
        if c == L.D:
            P[s, s] = 1.0
            continue
        rates = {}
        for j in np.flatnonzero(ch.src == s):
            rates[ch.dst[j]] = rates.get(ch.dst[j], 0.0) + ch.const[j]
        for jj in range(L.K):
            if om[i, jj] > 0:
                d = jj * L.ncomp + c
                rates[d] = rates.get(d, 0.0) + om[i, jj]
        Ks = sum(rates.values())
        if Ks == 0:
            P[s, s] = 1.0
            continue
        leave = -np.expm1(-Ks * tau)
        P[s, s] = 1.0 - leave
        for d, r in rates.items():
            P[d, s] += r / Ks * leave
    return P


def _linear_system():
    om = np.array([[0.0, 0.03], [0.02, 0.0]])
    reg = RegionSet(("a", "b"), np.array([300.0, 200.0]), np.ones(2), np.eye(2), om, True)
    sysm = ReactionSystem(make_params(M=2, c0=0.0, f1=0.2, lam=0.05), reg)
    L = sysm.layout
    X0 = L.empty()
    X0[:, L.S] = [100, 50]
    X0[0, L.E(1)], X0[0, L.I(1)], X0[1, L.I(2)] = 60, 40, 30
    X0[0, L.RP(1)], X0[1, L.RP(2)], X0[1, L.RW(1)] = 50, 40, 30
    return sysm, X0


def test_binomial_leap_matches_exact_recursion():
    """검증: 코드의 한 단계가 정확히 다항 분포 leap 인지 확인한다 (tau = 0.5 고정).
    정확한 점화식:  m' = P m,   Sigma' = P Sigma P^T + sum_s m_s (diag(p_s) - p_s p_s^T)
    4000회, 평균은 z < 5, 분산은 4차 모멘트 기반 SE 로 z < 5.
    한계: 감염(비선형) 사건의 leap 는 CTMC 비교 테스트에서 본다."""
    sysm, X0 = _linear_system()
    tau, steps = 0.5, 40           # 20일
    P = _leap_matrix(sysm, tau)
    m = X0.reshape(-1).copy()
    S = np.zeros((m.size, m.size))
    for _ in range(steps):
        noise = sum(m[s] * (np.diag(P[:, s]) - np.outer(P[:, s], P[:, s])) for s in range(m.size))
        S = P @ S @ P.T + noise
        m = P @ m
    R = 4000
    xs = np.stack([simulate_tau(sysm, X0, 20, output_dt=20, seed=s, eps=1e12, tau_max=tau).X[-1].reshape(-1)
                   for s in np.random.SeedSequence(77).spawn(R)])
    v = np.diag(S)
    mask = v > 1e-6
    mean, var = xs.mean(0), xs.var(0, ddof=1)
    m4 = ((xs - mean) ** 4).mean(0)
    zm = np.abs(mean - m)[mask] / np.sqrt(var[mask] / R)
    zv = np.abs(var - v)[mask] / np.sqrt(np.maximum(m4 - var ** 2, 0)[mask] / R)
    assert mask.sum() > 10
    assert zm.max() < Z and zv.max() < Z, (zm.max(), zv.max())


def test_leap_mean_converges_to_exact_mean_first_order():
    """검증: 선형계에서 leap 평균 P(tau)^n m0 와 정확한 평균 exp(A t) m0 의 차이가 O(tau) 이다.
    (결정론적 계산이며, 위 테스트가 코드 = P(tau) 임을 보였으므로 코드의 수렴 차수에 대한 진술이 된다.)"""
    sysm, X0 = _linear_system()
    L, ch, om = sysm.layout, sysm.channels, sysm.regions.mobility
    n = L.size
    Amat = np.zeros((n, n))
    for j in range(len(ch)):
        Amat[ch.dst[j], ch.src[j]] += ch.const[j]
        Amat[ch.src[j], ch.src[j]] -= ch.const[j]
    for i, jj in zip(*np.nonzero(om)):
        for c in range(L.D):
            Amat[jj * L.ncomp + c, i * L.ncomp + c] += om[i, jj]
            Amat[i * L.ncomp + c, i * L.ncomp + c] -= om[i, jj]
    exact = expm(Amat * 20.0) @ X0.reshape(-1)
    errs = []
    for tau in (1.0, 0.5, 0.25, 0.125):
        P = _leap_matrix(sysm, tau)
        errs.append(np.max(np.abs(np.linalg.matrix_power(P, int(round(20 / tau))) @ X0.reshape(-1) - exact)))
    ratios = np.array(errs[:-1]) / np.array(errs[1:])
    assert np.all((ratios > 1.8) & (ratios < 2.2)), ratios


# --------------------------------------------------------------------- 비선형: CTMC 와 분포 비교

def test_tau_leap_distribution_matches_ctmc():
    """검증: 전체 모형(재감염, 사망, M = 8)에서 tau-leap(기본 eps = 0.01)의 I_total 분포가 CTMC 와 같다.
    (eps = 0.03 에서는 후반부 z 가 +2.7~4.2 로 체계적 편향이 보여 기본값을 0.01 로 바꿨다. docs/reports/1C_tau.md 5절)
    N = 2e4, 초기 1%, 200일, 각 300회. 20일마다 평균은 두 표본 z < 5, 표준편차 비율은 [0.8, 1.25].
    한계: 소규모 수 영역(소멸)의 정확도는 여기서 보지 않는다. 하이브리드에서 CTMC 가 맡는다."""
    N = 2e4
    p = make_params(M=8)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 200.0})
    R = 300
    It = np.stack([simulate_tau(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(1).spawn(R)])
    Ic = np.stack([simulate_ctmc(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(2).spawn(R)])
    idx = np.arange(20, 201, 20)
    mt, mc = It[:, idx].mean(0), Ic[:, idx].mean(0)
    st, sc = It[:, idx].std(0, ddof=1), Ic[:, idx].std(0, ddof=1)
    z = np.abs(mt - mc) / np.sqrt((st ** 2 + sc ** 2) / R)
    assert z.max() < Z, z
    ok = sc > 5
    ratio = st[ok] / sc[ok]
    assert np.all((ratio > 0.8) & (ratio < 1.25)), ratio


def test_full_intervention_window_has_no_infections():
    p = make_params(M=2, lam=0.0)
    u = InterventionSchedule(1, [{"start": 10.0, "end": 30.0, "value": 1.0, "regions": None}])
    sysm = ReactionSystem(p, RegionSet.single(1e5), Drivers(1, None, None, u))
    X0 = initial_state(sysm.layout, np.array([1e5]), {0: 200.0})
    for s in range(10):
        S = simulate_tau(sysm, X0, 60, seed=s).X[:, 0, sysm.layout.S]
        assert np.all(S[10:31] == S[10]) and S[9] > S[10]
