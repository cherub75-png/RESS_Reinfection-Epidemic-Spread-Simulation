"""1-C: 정확한 CTMC (Gillespie) 검증.

통계 검정의 판정 기준은 실행 전에 이론(표준오차, 점근 분포)으로 정했다. 시드를 고정했으므로
결과는 결정적이다. z < 5 기준은 정규 근사에서 검정 하나당 거짓 경보 확률이 6e-7 이하이다.
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from conftest import make_params, random_state
from seir_sim.model import analysis as A
from seir_sim.model.drivers import Drivers, InterventionSchedule
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet
from seir_sim.model.state import initial_state
from seir_sim.simulate import _kernels as Kn
from seir_sim.simulate.ctmc import kernel_args, simulate_ctmc
from seir_sim.simulate.ode import integrate_ode

Z = 5.0


def test_kernels_match_python():
    rng = np.random.default_rng(0)
    reg = RegionSet.synthetic_random(4, rng, mobility_scale=0.01)
    u = InterventionSchedule(4, [{"start": 0.0, "end": 9.0, "value": 0.3, "regions": [1]}])
    sysm = ReactionSystem(make_params(M=3), reg, Drivers(4, None, None, u), {"form": "power", "eta": 0.2})
    X = random_state(sysm.layout, rng)
    X[2] = 0.0
    src, dst, const, susc, region, C, Tn, K, ncomp, E0, I0, M, alive_end = kernel_args(sysm)
    gc = sysm.drivers.g(1.0) * sysm.contact_rate(1.0)
    lam = np.empty(K)
    Kn.force_of_infection(X.reshape(-1), K, ncomp, I0, M, alive_end, Tn, C, gc, lam)
    np.testing.assert_allclose(lam, sysm.force_of_infection(X, 1.0), rtol=1e-13)
    a = np.empty(src.size)
    a0 = Kn.propensities(X.reshape(-1), src, const, susc, region, lam, a)
    np.testing.assert_allclose(a, sysm.propensities(X, 1.0), rtol=1e-13)
    assert a0 == pytest.approx(a.sum(), rel=1e-13)
    m = np.empty(K)
    m0 = Kn.mobility_propensities(X.reshape(-1), K, ncomp, alive_end, sysm.mobility.out_rate, m)
    np.testing.assert_allclose(m, sysm.mobility_propensities(X), rtol=1e-13)
    assert m0 == pytest.approx(m.sum(), rel=1e-13)


def test_reproducible_conservative_integer_paths():
    rng = np.random.default_rng(1)
    reg = RegionSet.synthetic_random(3, rng, total_population=3e3, mobility_scale=0.02)
    reg = RegionSet(reg.names, np.round(reg.population), reg.density, reg.contact, reg.mobility, True)
    sysm = ReactionSystem(make_params(M=3, f1=0.05, lam=1 / 30), reg)
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, reg.population, {0: 5.0})
    a = simulate_ctmc(sysm, X0, 200, seed=123)
    b = simulate_ctmc(sysm, X0, 200, seed=123)
    c = simulate_ctmc(sysm, X0, 200, seed=124)
    np.testing.assert_array_equal(a.X, b.X)
    assert not np.array_equal(a.X, c.X)
    assert a.meta["max_abs_population_error"] == 0.0
    assert np.all(a.X == np.round(a.X)) and a.meta["min_value"] >= 0
    assert np.all(np.diff(a.totals(a.layout.D)) >= 0)
    assert a.meta["seed_entropy"] == "123"
    with pytest.raises(ValueError):
        simulate_ctmc(sysm, X0 + 0.5, 10, seed=0)


# --------------------------------------------------------------------- 선형계: 정확한 1·2차 모멘트

def _linear_moments(sysm, X0, times):
    """c0 = 0 이면 모든 율이 선형이므로 모멘트 방정식이 정확히 닫힌다.
      dm/dt = A m,   dSigma/dt = A Sigma + Sigma A^T + sum_j nu_j nu_j^T k_j m[src_j]
    """
    n = X0.size
    ch, L, om = sysm.channels, sysm.layout, sysm.regions.mobility
    # 이동은 합치지 않은 원래 형태 (i, j, c) 로 따로 넣는다 -> CTMC 의 합친 이동과 독립적인 기준
    src = list(ch.src)
    dst = list(ch.dst)
    k = list(ch.const)
    for i, j in zip(*np.nonzero(om)):
        for c in range(L.D):
            src.append(i * L.ncomp + c)
            dst.append(j * L.ncomp + c)
            k.append(om[i, j])
    src, dst, k = np.array(src), np.array(dst), np.array(k)
    Amat = np.zeros((n, n))
    for j in range(src.size):
        Amat[dst[j], src[j]] += k[j]
        Amat[src[j], src[j]] -= k[j]

    def rhs(t, y):
        m, S = y[:n], y[n:].reshape(n, n)
        B = np.zeros((n, n))
        rates = k * m[src]
        for j in range(src.size):
            s_, d_ = src[j], dst[j]
            B[s_, s_] += rates[j]
            B[d_, d_] += rates[j]
            B[s_, d_] -= rates[j]
            B[d_, s_] -= rates[j]
        return np.concatenate([Amat @ m, (Amat @ S + S @ Amat.T + B).reshape(-1)])

    y0 = np.concatenate([X0.reshape(-1), np.zeros(n * n)])
    sol = solve_ivp(rhs, (0, max(times)), y0, t_eval=times, rtol=1e-10, atol=1e-10)
    return sol.y[:n].T, np.array([np.diag(sol.y[n:, k].reshape(n, n)) for k in range(len(times))])


def test_linear_system_exact_mean_and_variance():
    """검증: 감염이 없는 선형 부분(발병, 회복, 사망, 면역 소실, 이동)의 CTMC 평균·분산이
    모멘트 방정식의 정확해와 일치한다. 두 지역, M = 2, 이동·사망 포함, 4000회.
    분산의 표준오차는 표본 4차 중심모멘트로 추정한다: SE(s^2) = sqrt((m4 - s^4) / R).
    한계: 감염(비선형) 사건은 c0 = 0 이라 여기서 검증되지 않는다 (아래 테스트들에서 본다)."""
    K, R = 2, 4000
    om = np.array([[0.0, 0.03], [0.02, 0.0]])
    reg = RegionSet(("a", "b"), np.array([300.0, 200.0]), np.ones(2), np.eye(2), om, True)
    sysm = ReactionSystem(make_params(M=2, c0=0.0, f1=0.2, lam=0.05), reg)
    L = sysm.layout
    X0 = L.empty()
    X0[:, L.S] = [100, 50]
    X0[0, L.E(1)], X0[0, L.I(1)], X0[1, L.I(2)] = 60, 40, 30
    X0[0, L.RP(1)], X0[1, L.RP(2)], X0[1, L.RW(1)] = 50, 40, 30
    times = np.array([2.0, 8.0, 25.0])
    m, v = _linear_moments(sysm, X0, times)
    ss = np.random.SeedSequence(2024).spawn(R)
    samples = np.stack([simulate_ctmc(sysm, X0, 25, output_dt=1.0, seed=s).X[times.astype(int)].reshape(3, -1)
                        for s in ss])                     # [R, 3, n]
    mean = samples.mean(axis=0)
    var = samples.var(axis=0, ddof=1)
    m4 = ((samples - mean) ** 4).mean(axis=0)
    se_mean = np.sqrt(var / R)
    se_var = np.sqrt(np.maximum(m4 - var ** 2, 0) / R)
    mask = v > 1e-6
    zm = np.abs(mean - m)[mask] / se_mean[mask]
    zv = np.abs(var - v)[mask] / se_var[mask]
    assert mask.sum() > 30
    assert zm.max() < Z, zm.max()
    assert zv.max() < Z, zv.max()


# --------------------------------------------------------------------- 초기 단계 평균 = ODE

def test_early_phase_mean_equals_ode():
    """검증: 초기 단계에서 CTMC 평균 = ODE (분기과정의 평균은 선형화 ODE 해와 같다).
    가정 확인: N = 1e7 이고 30일 동안 감수성 고갈이 1e-4 미만이어서 ODE 가 사실상 선형이다.
    소멸한 경로도 평균에 포함한다 (무조건부 평균). 3000회.
    한계: 비선형 영역(고갈)은 대수의 법칙 테스트에서 본다."""
    p = make_params(M=2)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), RegionSet.single(1e7))
    X0 = initial_state(sysm.layout, np.array([1e7]), {0: 5.0})
    ode = integrate_ode(sysm, X0, 30, rtol=1e-10, atol=1e-10)
    assert 1 - ode.totals(sysm.layout.S)[-1] / 1e7 < 1e-4
    R = 3000
    ss = np.random.SeedSequence(7).spawn(R)
    L = sysm.layout
    I = np.empty((R, 31))
    E = np.empty((R, 31))
    for r, s in enumerate(ss):
        tr = simulate_ctmc(sysm, X0, 30, seed=s)
        I[r], E[r] = tr.I_total, tr.totals(L.E_slice)
    for sample, ref in ((I, ode.I_total), (E, ode.totals(L.E_slice))):
        idx = np.arange(5, 31, 5)
        se = sample[:, idx].std(axis=0, ddof=1) / np.sqrt(R)
        z = np.abs(sample[:, idx].mean(axis=0) - ref[idx]) / se
        assert z.max() < Z, z


# --------------------------------------------------------------------- 소멸 확률

@pytest.mark.parametrize("R0,k,comp,expected", [
    (2.5, 1, "I1", 1 / 2.5), (2.5, 1, "E1", 1 / 2.5), (2.5, 2, "I1", (1 / 2.5) ** 2), (1.5, 1, "I1", 1 / 1.5)])
def test_extinction_probability_matches_branching_process(R0, k, comp, expected):
    """검증: 소규모 발생(조기 소멸) 확률 = (1/R0)^k.
    유도: 감염기간이 지수분포이면 감염자 한 명의 2차 감염 수는 평균 R0 인 기하분포이다.
    그 분기과정의 소멸 확률은 q = 1/R0 이다. E 에서는 사망이나 이탈이 없어 모두 I 가 되므로,
    E1 에 심어도 같다. 사망은 I 이탈율 gamma 의 일부이므로 결과에 영향이 없다.
    판정: E+I = 0 이면 소멸, E+I >= 200 이면 대유행으로 끝낸다 (그 뒤 소멸 확률 < q^200).
    N = 1e6 이므로 유한 인구 보정은 1e-4 수준이다. 4000회, 이항 표준오차로 z < 5.
    한계: 이질적 지역망의 소멸 확률(다유형 분기과정)은 검증하지 않았다."""
    p = make_params(M=2)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(R0, p)), RegionSet.single(1e6))
    X0 = initial_state(sysm.layout, np.array([1e6]), {0: float(k)}, comp)
    R = 4000
    ss = np.random.SeedSequence(99).spawn(R)
    ext = 0
    for s in ss:
        tr = simulate_ctmc(sysm, X0, 10_000, output_dt=10_000, seed=s,
                           stop_EI_at_or_below=0, stop_EI_at_or_above=200)
        assert tr.meta["stopped_at"] is not None
        fs = tr.meta["final_state"][0]
        ext += int(fs[sysm.layout.E_slice].sum() + fs[sysm.layout.I_slice].sum() == 0)
    phat = ext / R
    se = np.sqrt(expected * (1 - expected) / R)
    assert abs(phat - expected) / se < Z, (phat, expected)


# --------------------------------------------------------------------- 최종 규모 분포

def test_final_size_distribution_major_outbreak():
    """검증: 대유행이 일어났을 때 최종 규모의 평균과 분산이 점근 이론과 일치한다.
    평균: ln(S0/S_inf) = R0 (S0 - S_inf + I0)/N 의 해 (1-B 와 같은 결정론적 관계식)
    분산 (Andersson & Britton 2000, 정리 4.2; 지수 감염기간이면 CV^2 = 1):
      N Var(Z) -> z(1-z)(1 + R0^2 (1-z)) / (1 - R0 (1-z))^2
    가정 확인: 재감염 없음(lambda = 0, P(n>=2) = 0), 사망 없음(f = 0), 단일 지역. 잠복기는 최종 규모에 영향이 없다.
    N = 5000, I0 = 10, 600회. 대유행 판정 Z > 0.3 (I0 = 10 이면 소규모 발생 확률 1e-4).
    판정 기준(사전 설정): 평균은 4 SE + 10/N 이내 (O(1/N) 유한 인구 편향 허용),
    분산 비율은 [0.75, 1.33] 이내 (SE 약 6%, 유한 인구 보정 포함).
    한계: 점근 결과이므로 유한 N 에서 몇 % 의 차이는 남을 수 있다."""
    R0, N, I0 = 2.5, 5000.0, 10.0
    p = make_params(M=2, lam=0.0, Pmin=0.0, alpha=1000.0, f1=0.0)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(R0, p)), RegionSet.single(N))
    L = sysm.layout
    X0 = initial_state(L, np.array([N]), {0: I0})
    S0 = N - I0
    s_inf = brentq(lambda s: np.log(S0 / s) - R0 * (S0 - s + I0) / N, 1e-9, S0 * (1 - 1e-12))
    z_det = (S0 - s_inf) / N
    sig2 = z_det * (1 - z_det) * (1 + R0 ** 2 * (1 - z_det)) / (1 - R0 * (1 - z_det)) ** 2
    Zs = []
    for s in np.random.SeedSequence(5).spawn(600):
        tr = simulate_ctmc(sysm, X0, 10_000, output_dt=10_000, seed=s, stop_EI_at_or_below=0)
        Zs.append((S0 - tr.meta["final_state"][0, L.S]) / N)
    Zs = np.array(Zs)
    major = Zs[Zs > 0.3]
    assert major.size > 590
    se = major.std(ddof=1) / np.sqrt(major.size)
    assert abs(major.mean() - z_det) < 4 * se + 10 / N, (major.mean(), z_det, se)
    ratio = N * major.var(ddof=1) / sig2
    assert 0.75 < ratio < 1.33, ratio


# --------------------------------------------------------------------- 대수의 법칙 (전체 모형)

def test_law_of_large_numbers_full_model():
    """검증: 사망·재감염·면역 소실·M = 8 을 모두 켠 모형에서 N 이 크면 CTMC 평균이 ODE 에 가깝다 (Kurtz).
    N = 5e4, 초기 감염 1% (조기 소멸 무시 가능), 365일, 16회.
    판정(사전 설정): 모든 t 에서 |평균 - ODE| <= 4 SE_t + 0.02 * 최고값.
    (유한 N 편향 O(1/N) 과 초기 시점 흔들림으로 생기는 작은 체계적 차이를 2% 로 허용한다.)
    한계: 소규모 N 에서는 CTMC 평균이 ODE 와 다르며(소멸, 유한 인구 효과), 이는 정상이다.
    따라서 "소규모 N 에서 평균 = ODE" 는 선형계와 초기 단계에서만 정확히 성립하고, 그것은 위 테스트들이 검증한다."""
    N = 5e4
    p = make_params(M=8)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 500.0})
    ode = integrate_ode(sysm, X0, 365)
    R = 16
    I = np.stack([simulate_ctmc(sysm, X0, 365, seed=s).I_total for s in np.random.SeedSequence(3).spawn(R)])
    se = I.std(axis=0, ddof=1) / np.sqrt(R)
    dev = np.abs(I.mean(axis=0) - ode.I_total)
    assert np.all(dev <= 4 * se + 0.02 * ode.I_total.max()), (dev - 4 * se).max() / ode.I_total.max()


# --------------------------------------------------------------------- 시간가변 입력

def test_full_intervention_window_has_no_infections():
    """검증: u = 1 구간 [10, 30) 에서 감염 사건이 0 이다 (S 와 R->E 경로가 멈춤). 구간이 끝나면 다시 전파된다.
    구간 경계에서 대기 시간을 다시 뽑는 처리가 율을 섞지 않는지 확인한다."""
    p = make_params(M=2, lam=0.0)
    u = InterventionSchedule(1, [{"start": 10.0, "end": 30.0, "value": 1.0, "regions": None}])
    sysm = ReactionSystem(p, RegionSet.single(1e5), Drivers(1, None, None, u))
    X0 = initial_state(sysm.layout, np.array([1e5]), {0: 200.0})
    for s in range(20):
        tr = simulate_ctmc(sysm, X0, 60, seed=s)
        S = tr.X[:, 0, sysm.layout.S]
        assert np.all(S[10:31] == S[10])
        assert S[9] > S[10]
