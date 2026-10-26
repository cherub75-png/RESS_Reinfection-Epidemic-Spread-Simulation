"""1-C 2b: SDE (화학 랑주뱅, Euler-Maruyama) 검증."""

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
from seir_sim.simulate.ode import integrate_ode
from seir_sim.simulate.sde import simulate_sde

Z = 5.0


def test_conservation_nonnegativity_reproducibility():
    rng = np.random.default_rng(1)
    reg = RegionSet.synthetic_random(5, rng, total_population=2e5, mobility_scale=0.02)
    u = InterventionSchedule(5, [{"start": 20.0, "end": 50.0, "value": 0.4, "regions": [0, 2]}])
    sysm = ReactionSystem(make_params(M=4, f1=0.05, lam=1 / 30), reg, Drivers(5, None, None, u))
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, reg.population, {0: 50.0})
    a = simulate_sde(sysm, X0, 300, seed=3)
    b = simulate_sde(sysm, X0, 300, seed=3)
    np.testing.assert_array_equal(a.X, b.X)
    assert a.meta["max_rel_population_error"] < 1e-12     # 반올림 수준
    assert a.meta["truncation"]["zero_clamp_added_over_population"] < 1e-12
    assert a.meta["min_value"] >= 0.0
    assert a.meta["truncation"]["mode"] == "flow_limit"
    sc = simulate_sde(sysm, X0, 300, seed=3, truncation="state_clip")
    assert sc.meta["truncation"]["zero_clamp_added_over_population"] > 1e-6   # 원안 방식은 인구를 더한다
    with pytest.raises(ValueError):
        simulate_sde(sysm, X0, 10, seed=0, truncation="nope")


# --------------------------------------------------------------------- 선형계: EM 의 정확한 모멘트 점화식

def _linear_large_system():
    """모든 흐름이 커서(a h >> 1) 흐름 제한이 일어나지 않는 선형계 (c0 = 0, M = 1)."""
    om = np.array([[0.0, 0.03], [0.02, 0.0]])
    reg = RegionSet(("a", "b"), np.array([2e5, 2e5]), np.ones(2), np.eye(2), om, True)
    sysm = ReactionSystem(make_params(M=1, c0=0.0, f1=0.2, lam=0.05), reg)
    L = sysm.layout
    X0 = L.empty()
    for i, k in enumerate((1.0, 0.7)):
        X0[i, L.S], X0[i, L.E(1)], X0[i, L.I(1)] = 1e4 * k, 6e4 * k, 4e4 * k
        X0[i, L.RP(1)], X0[i, L.RW(1)] = 5e4 * k, 3e4 * k
    return sysm, X0


def _drift_and_noise(sysm):
    """선형계 A (dm/dt = A m) 와 B(m) = sum_j nu_j nu_j^T k_j m_src (쌍 단위 이동 포함)."""
    L, ch, om = sysm.layout, sysm.channels, sysm.regions.mobility
    src, dst, k = list(ch.src), list(ch.dst), list(ch.const)
    for i, j in zip(*np.nonzero(om)):
        for c in range(L.D):
            src.append(i * L.ncomp + c)
            dst.append(j * L.ncomp + c)
            k.append(om[i, j])
    src, dst, k = map(np.array, (src, dst, k))
    n = L.size
    Amat = np.zeros((n, n))
    for j in range(src.size):
        Amat[dst[j], src[j]] += k[j]
        Amat[src[j], src[j]] -= k[j]

    def B(m):
        out = np.zeros((n, n))
        r = k * m[src]
        for j in range(src.size):
            s_, d_ = src[j], dst[j]
            out[s_, s_] += r[j]
            out[d_, d_] += r[j]
            out[s_, d_] -= r[j]
            out[d_, s_] -= r[j]
        return out
    return Amat, B


def test_euler_maruyama_matches_exact_moment_recursion():
    """검증: 코드의 한 단계가 정확히 EM 이다. 흐름 제한이 일어나지 않는 큰 수 선형계에서
      m' = (I + A h) m,   Sigma' = (I + A h) Sigma (I + A h)^T + h B(m)
    2000회, h = 0.05, 20일. 평균 z < 5, 분산 z < 5 (4차 모멘트 기반 SE).
    한계: 감염(비선형) 사건은 CTMC 비교에서 본다."""
    sysm, X0 = _linear_large_system()
    Amat, B = _drift_and_noise(sysm)
    h, steps = 0.05, 400
    G = np.eye(Amat.shape[0]) + Amat * h
    m = X0.reshape(-1).copy()
    S = np.zeros((m.size, m.size))
    for _ in range(steps):
        S = G @ S @ G.T + h * B(m)
        m = G @ m
    R = 2000
    trs = [simulate_sde(sysm, X0, 20, output_dt=20, seed=s, dt=h) for s in np.random.SeedSequence(5).spawn(R)]
    assert max(t.meta["truncation"]["limited_mass_over_flow"] for t in trs) == 0.0
    xs = np.stack([t.X[-1].reshape(-1) for t in trs])
    v = np.diag(S)
    mask = v > 1e-6
    mean, var = xs.mean(0), xs.var(0, ddof=1)
    m4 = ((xs - mean) ** 4).mean(0)
    zm = np.abs(mean - m)[mask] / np.sqrt(var[mask] / R)
    zv = np.abs(var - v)[mask] / np.sqrt(np.maximum(m4 - var ** 2, 0)[mask] / R)
    assert mask.sum() >= 8
    assert zm.max() < Z and zv.max() < Z, (zm.max(), zv.max())


def test_euler_maruyama_mean_first_order():
    """EM 평균 (I + A h)^n m0 와 정확한 평균 exp(A t) m0 의 차이가 O(h) (결정론적 계산)."""
    sysm, X0 = _linear_large_system()
    Amat, _ = _drift_and_noise(sysm)
    exact = expm(Amat * 20.0) @ X0.reshape(-1)
    errs = []
    for h in (0.4, 0.2, 0.1, 0.05):
        G = np.eye(Amat.shape[0]) + Amat * h
        errs.append(np.max(np.abs(np.linalg.matrix_power(G, int(round(20 / h))) @ X0.reshape(-1) - exact)))
    r = np.array(errs[:-1]) / np.array(errs[1:])
    assert np.all((r > 1.8) & (r < 2.2)), r


# --------------------------------------------------------------------- 비선형: CTMC 와 분포 비교

def _ctmc_reference(R=300):
    N = 2e4
    p = make_params(M=8)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 200.0})
    Ic = np.stack([simulate_ctmc(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(2).spawn(R)])
    return sysm, X0, Ic


def _compare(It, Ic, idx):
    R = It.shape[0]
    z = (It[:, idx].mean(0) - Ic[:, idx].mean(0)) / np.sqrt((It[:, idx].var(0, ddof=1) + Ic[:, idx].var(0, ddof=1)) / R)
    ratio = It[:, idx].std(0, ddof=1) / Ic[:, idx].std(0, ddof=1)
    return z, ratio


def test_sde_distribution_matches_ctmc_and_increment_clip_is_biased():
    """검증: 기본 방식(flow_limit)의 I_total 분포가 CTMC 와 같다 (평균 z < 5, 표준편차 비율 [0.8, 1.25]).
    회귀 기록: 1-C 에서 승인했던 increment_clip 은 같은 조건에서 |z| > 5 의 편향을 보인다 (DECISIONS D-004).
    조건: 전체 모형, M = 8, N = 2e4, 초기 1%, 200일, 각 300회, h = 0.05.
    한계: 감염자가 매우 적은 영역(소멸 확률)은 SDE 의 적용 범위 밖이다. 하이브리드에서는 CTMC 가 맡는다."""
    sysm, X0, Ic = _ctmc_reference()
    idx = np.arange(20, 201, 20)
    R = Ic.shape[0]
    It = np.stack([simulate_sde(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(1).spawn(R)])
    z, ratio = _compare(It, Ic, idx)
    assert np.abs(z).max() < Z, z
    assert np.all((ratio > 0.8) & (ratio < 1.25)), ratio
    Ib = np.stack([simulate_sde(sysm, X0, 200, seed=s, truncation="increment_clip").I_total
                   for s in np.random.SeedSequence(1).spawn(R)])
    zb, _ = _compare(Ib, Ic, idx)
    assert np.abs(zb).max() > Z


def test_large_population_close_to_ode():
    """검증: N = 1e7 (초기 1%) 에서 SDE 경로가 ODE 에 가깝다 (최고값 대비 1% 이내).
    확률적 흔들림은 1/sqrt(초기 감염 수) ~ 3e-3 수준이다."""
    p = make_params(M=8)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), RegionSet.single(1e7))
    X0 = initial_state(sysm.layout, np.array([1e7]), {0: 1e5})
    ode = integrate_ode(sysm, X0, 365).I_total
    dev = [np.max(np.abs(simulate_sde(sysm, X0, 365, seed=s).I_total - ode)) / ode.max() for s in range(3)]
    assert max(dev) < 0.01, dev


def test_full_intervention_window_has_no_infections():
    p = make_params(M=2, lam=0.0)
    u = InterventionSchedule(1, [{"start": 10.0, "end": 30.0, "value": 1.0, "regions": None}])
    sysm = ReactionSystem(p, RegionSet.single(1e5), Drivers(1, None, None, u))
    X0 = initial_state(sysm.layout, np.array([1e5]), {0: 200.0})
    S = simulate_sde(sysm, X0, 60, seed=1).X[:, 0, sysm.layout.S]
    assert np.all(S[10:31] == S[10]) and S[9] > S[10]
