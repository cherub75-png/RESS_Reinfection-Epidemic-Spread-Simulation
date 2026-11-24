"""1-B: ODE 적분기 검증.

각 테스트의 머리말에 (검증 내용 / 해석해의 가정 / 한계) 를 적었다.
"""

from dataclasses import dataclass

import numpy as np
import pytest
from scipy.optimize import brentq, fsolve

from conftest import make_params
from seir_sim.model import analysis as A
from seir_sim.model.drivers import Drivers, InterventionSchedule
from seir_sim.model.params import EpiParams
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet
from seir_sim.model.state import initial_state
from seir_sim.simulate.ode import integrate_ode

TIGHT = dict(rtol=1e-10, atol=1e-8)


def _no_reinfection_no_death(**kw):
    """최종 규모 해석해의 가정: 재감염 없음(lambda = 0, P(n >= 2) = 0), 사망 없음(f = 0).

    Pmin = 0, alpha = 1000 이면 exp(-1000) 은 배정밀도에서 정확히 0 이 되므로 P(2..M+1) = 0 이다.
    """
    p = make_params(lam=0.0, Pmin=0.0, alpha=1000.0, f1=0.0, **kw)
    assert np.all(p.P_next_by_n == 0.0) and np.all(p.f_by_n == 0.0) and p.lam == 0.0
    return p


# --------------------------------------------------------------------- 인구 보존

def test_population_conservation_full_model():
    """검증: 사망, 재감염, 이동, 시간가변 개입이 모두 켜진 지역망에서 sum(구획 + D) 보존,
    D 의 단조 증가, 비음수성. 한계: 보존은 사건 목록의 구조로 보장되므로, 이 테스트는
    주로 적분기의 반올림·허용오차 누적을 본다."""
    rng = np.random.default_rng(11)
    reg = RegionSet.synthetic_random(8, rng, total_population=1e7, mobility_scale=0.01)
    u = InterventionSchedule(8, [{"start": 30, "end": 90, "value": 0.5, "regions": [0, 1]},
                                 {"start": 60, "end": 120, "value": 0.3, "regions": None}])
    p = make_params(f1=0.05, lam=1 / 60)
    sysm = ReactionSystem(p, reg, Drivers(8, None, None, u), {"form": "power", "eta": 0.2})
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
    tr = integrate_ode(sysm, X0, 730)
    assert tr.meta["segments"] == 5          # 경계 30, 60, 90, 120
    assert tr.meta["max_rel_population_error"] < 1e-12
    D = tr.totals(tr.layout.D)
    assert np.all(np.diff(D) >= -1e-9)
    assert tr.meta["min_value"] > -1e-6
    assert D[-1] > 0


# --------------------------------------------------------------------- 초기 증가율

@pytest.mark.parametrize("R0", [1.3, 2.5, 4.0])
@pytest.mark.parametrize("seed_comp", ["I1", "E1"])
def test_initial_growth_rate(R0, seed_comp):
    """검증: 초기 지수 성장률이 1.6절 공식 r 과 일치.
    공식의 가정: 단일 지역, S = N (감수성 고갈 무시), E_1, I_1 만 존재, g = h = 1, u = 0.
    맞추는 방법: N = 1e12 이고, 측정 구간(40~60일)에서 고갈이 1e-5 미만인지 확인한다.
    빠른 고유모드(-(sigma+gamma)-r 근방)가 사라진 뒤 log I 의 기울기를 잰다.
    한계: 사망으로 N 이 줄어드는 효과는 무시할 만큼 작다고 확인할 뿐 0 은 아니다."""
    p = make_params()
    p = p.with_(c0=A.c0_reference(R0, p))
    sysm = ReactionSystem(p, RegionSet.single(1e12))
    X0 = initial_state(sysm.layout, sysm.regions.population, {0: 10.0}, seed_comp)
    tr = integrate_ode(sysm, X0, 60, **TIGHT)
    S = tr.X[:, 0, tr.layout.S]
    assert 1 - S[60] / 1e12 < 1e-5
    t, I = tr.t[40:61], np.log(tr.I_total[40:61])
    slope = np.polyfit(t, I, 1)[0]
    r = A.initial_growth_rate(p.sigma, p.gamma, A.kappa(p))
    assert slope == pytest.approx(r, rel=2e-5)


def test_network_growth_rate_equals_dominant_eigenvalue():
    """검증: 균형 이동 지역망에서 초기 성장률 = 감염 부분계 (F - V) 의 최대 실수 고유값.
    가정: 무감염 상태가 정지 상태여야 한다 (균형 이동, 확인함). (F - V) 와 drift 의 수치 야코비안
    일치는 test_analysis::test_ngm_matches_drift_jacobian_network 가 검증한다.
    한계: 선형화 영역(고갈 < 1e-4)만 본다."""
    rng = np.random.default_rng(5)
    reg = RegionSet.synthetic_random(6, rng, total_population=1e11, mobility_scale=0.02)
    sysm = ReactionSystem(make_params(), reg, h_spec={"form": "power", "eta": 0.2})
    assert reg.mobility_imbalance() < 1e-15
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    F, V = A.next_generation_matrices(sysm, A.disease_free_state(sysm))
    r = np.max(np.linalg.eigvals(F - V).real)
    X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
    tr = integrate_ode(sysm, X0, 120, **TIGHT)
    assert 1 - tr.totals(tr.layout.S)[-1] / reg.population.sum() < 1e-4
    slope = np.polyfit(tr.t[80:121], np.log(tr.I_total[80:121]), 1)[0]
    assert slope == pytest.approx(r, rel=1e-4)


def test_imbalanced_mobility_growth_follows_stationary_population():
    """검증 (1-B 에서 찾은 문제의 회귀 테스트): 이동이 불균형이면 무감염 상태에서도 지역 인구가
    정지 분포로 재분포된다. 그러면 장기 성장률은 t0 인구의 (F - V) 가 아니라
    정지 인구의 (F - V) 고유값을 따른다. R0_network_t0 는 이 경우 순간값일 뿐이다."""
    rng = np.random.default_rng(5)
    reg = RegionSet.synthetic_random(6, rng, total_population=1e11, mobility_scale=0.02,
                                     balanced=False)
    assert reg.mobility_imbalance() > 1e-3
    sysm = ReactionSystem(make_params(), reg, h_spec={"form": "power", "eta": 0.2})
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    rep = A.r0_report(sysm)
    assert rep["R0_network_t0"] == pytest.approx(2.5)
    assert abs(rep["R0_network_stationary"] - 2.5) > 0.1

    X_st = A.disease_free_state(sysm)
    X_st[:, 0] = reg.stationary_population()
    assert np.max(np.abs(reg.mobility_net_flow(X_st[:, 0]) / X_st[:, 0])) < 1e-10
    F, V = A.next_generation_matrices(sysm, X_st)
    r_st = np.max(np.linalg.eigvals(F - V).real)
    tr = integrate_ode(sysm, initial_state(sysm.layout, reg.population, {0: 10.0}), 200, **TIGHT)
    slope = np.polyfit(tr.t[150:201], np.log(tr.I_total[150:201]), 1)[0]
    assert 1 - tr.totals(tr.layout.S)[-1] / reg.population.sum() < 1e-3
    assert slope == pytest.approx(r_st, rel=2e-3)


# --------------------------------------------------------------------- 최종 유행 규모

def _final_size_single(R0, S0, N, EI0):
    """ln(S0/S_inf) = R0 (S0 - S_inf + E0 + I0) / N  (아래 test 머리말의 유도)."""
    f = lambda s: np.log(S0 / s) - R0 * (S0 - s + EI0) / N   # noqa: E731
    return brentq(f, 1e-12 * S0, S0 * (1 - 1e-15))


@pytest.mark.parametrize("R0", [1.5, 2.5, 4.0])
@pytest.mark.parametrize("seed_comp", ["I1", "E1"])
def test_final_size_single_region(R0, seed_comp):
    """검증: 최종 감수성 인구 S_inf 가 정확한 최종 규모 관계식을 만족.
    유도: dS/dt = -P1 Lambda S, Lambda = kappa_eff I / N 에서
      ln(S0/S_inf) = (P1 g c T1 / N) int I dt,  int I dt = (S0 - S_inf + E0 + I0) / gamma.
    두 번째 식은 "감염된 모든 사람이 I 를 율 gamma 로 정확히 한 번 거쳐 나간다" 에서 나온다.
    필요한 가정과 모형 설정의 일치 확인:
      - N 상수: f = 0 (사망 없음)                           -> f1 = 0
      - 재감염 없음: R 에서 E 로 가는 율 0                  -> lambda = 0, P(n>=2) = 0
      - 단일 지역, 이동 없음, g = 1, u = 0, h(rho_ref) = 1  -> RegionSet.single
    한계: t = 1500일에서 끝낸 값과 비교하므로, 남은 E + I (1e-6 미만으로 확인) 만큼 오차가 남는다."""
    p = _no_reinfection_no_death()
    p = p.with_(c0=A.c0_reference(R0, p))
    N = 1e6
    sysm = ReactionSystem(p, RegionSet.single(N))
    X0 = initial_state(sysm.layout, sysm.regions.population, {0: 10.0}, seed_comp)
    tr = integrate_ode(sysm, X0, 1500, **TIGHT)
    L = tr.layout
    XT = tr.X[-1, 0]
    assert XT[L.E_slice].sum() + XT[L.I_slice].sum() < 1e-6
    S_inf = _final_size_single(R0, N - 10.0, N, 10.0)
    assert XT[L.S] == pytest.approx(S_inf, rel=1e-7)
    assert XT[L.RW_slice].sum() == 0.0 and XT[L.D] == 0.0


def test_final_size_multigroup_network():
    """검증: 이질적 지역망(h 로 지역마다 다른 c_i, 임의의 C)의 지역별 최종 규모.
    유도 (지역 i):  ln(S_i0/S_i,inf) = P1 T1 g_i c_i sum_j C_ij (S_j0 - S_j,inf + E_j0 + I_j0) / (gamma N_j)
    가정: N_j 상수 -> f = 0 그리고 이동 없음(omega = 0). 재감염 없음. g, u 상수.
    한계: 이동(omega)이 있으면 N_j 가 변하고 감염자가 지역을 옮기므로 이 관계식이 성립하지 않는다.
    이동이 있는 지역망은 보존·증가율·대칭성 테스트로만 검증한다."""
    rng = np.random.default_rng(3)
    K = 5
    reg = RegionSet.synthetic_random(K, rng, total_population=1e7, mobility_scale=0.0)
    p = _no_reinfection_no_death()
    sysm = ReactionSystem(p, reg, h_spec={"form": "power", "eta": 0.2})
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    seeds = {0: 10.0, 3: 5.0}
    X0 = initial_state(sysm.layout, reg.population, seeds)
    tr = integrate_ode(sysm, X0, 2500, **TIGHT)
    L = tr.layout
    S0 = X0[:, L.S]
    I0 = X0[:, L.I_slice].sum(axis=1)
    N = reg.population
    coef = p.P1 * p.T1 * sysm.contact_rate(0.0)[:, None] * reg.contact / (p.gamma * N[None, :])

    def eqs(z):                         # z = ln(S0 / S_inf)
        s_inf = S0 * np.exp(-z)
        return z - coef @ (S0 - s_inf + I0)

    z = fsolve(eqs, np.ones(K), xtol=1e-14)
    assert np.max(np.abs(eqs(z))) < 1e-10
    S_inf = S0 * np.exp(-z)
    assert tr.X[-1, :, L.I_slice].sum() + tr.X[-1, :, L.E_slice].sum() < 1e-5
    np.testing.assert_allclose(tr.X[-1, :, L.S], S_inf, rtol=1e-7)


# --------------------------------------------------------------------- M 수렴

@dataclass(frozen=True)
class FrozenParams(EpiParams):
    """감염 횟수 함수를 M_freeze 이후 고정한 무한 칸 모형 (docs/MODEL.md 3절의 P~, T~, f~)."""
    M_freeze: int = 3

    @property
    def T_by_n(self):
        return self.T(np.minimum(np.arange(1, self.M + 1), self.M_freeze))

    @property
    def f_by_n(self):
        return self.f(np.minimum(np.arange(1, self.M + 1), self.M_freeze))

    @property
    def P_next_by_n(self):
        return self.P(np.minimum(np.arange(2, self.M + 2), self.M_freeze + 1))


def _aggregate(tr):
    L = tr.layout
    return np.stack([tr.totals(L.S), tr.totals(L.E_slice), tr.totals(L.I_slice),
                     tr.totals(L.RP_slice), tr.totals(L.RW_slice), tr.totals(L.D)], axis=1)


@pytest.mark.parametrize("M0,M1", [(1, 3), (3, 6), (4, 8)])
def test_truncation_equals_frozen_infinite_model(M0, M1):
    """검증 (정확한 동치): M0 칸 모형 == 함수를 M0 이후 고정한 M1 칸 모형 (구획 종류별 합).
    이것은 docs/MODEL.md 3절의 "R^P_M 에 P(M+1) 을 쓰는 절단 = 고정 함수 무한 칸 모형" 주장의 검증이다.
    색인 오류(예: P(M) 사용, m(n) 오류)가 있으면 이 동치가 깨진다.
    한계: 절단 자체의 오차(원래 함수와의 차이)는 다음 테스트에서 수치로 본다."""
    rng = np.random.default_rng(M0)
    reg = RegionSet.synthetic_random(3, rng, total_population=1e6, mobility_scale=0.01)
    base = dict(sigma=1 / 5.2, gamma=1 / 7, c0=0.5, P1=1.0, T1=1.0, Pmin=0.3, alpha=0.5,
                beta=0.3, lam=1 / 60, f1=0.02, phi_spec={"form": "power", "delta": 0.5})
    small = ReactionSystem(EpiParams(M=M0, **base), reg)
    big = ReactionSystem(FrozenParams(M=M1, M_freeze=M0, **base), reg)
    X0s = initial_state(small.layout, reg.population, {0: 10.0})
    X0b = initial_state(big.layout, reg.population, {0: 10.0})
    tight = dict(rtol=1e-12, atol=1e-10)
    a = _aggregate(integrate_ode(small, X0s, 1000, **tight))
    b = _aggregate(integrate_ode(big, X0b, 1000, **tight))
    # 차이는 적분 허용오차 수준이다 (rtol 1e-8 -> 1.5e-6, 1e-12 -> 1.8e-8 로 줄어듦을 확인함)
    np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-3)
    # 대조군: 고정 시점을 하나 틀리면 차이가 O(1) 이 되어야 한다
    wrong = ReactionSystem(FrozenParams(M=M1, M_freeze=M0 + 1, **base), reg)
    c = _aggregate(integrate_ode(wrong, X0b, 1000, **tight))
    assert np.max(np.abs(a - c) / np.maximum(np.abs(a), 1.0)) > 1e-2


def test_convergence_in_M():
    """검증: M 을 키우면 결과가 수렴 (기준 M = 16, 단일 지역, 365일, 기본 매개변수).
    지표: I_total(t) 의 최대 차이 / 최대값, 누적 사망 D(365) 의 상대 차이, 마지막 칸 점유율 진단.
    한계: 극한 모형(M -> 무한대)의 해석해가 없어서 M = 16 을 기준으로 삼는다.
    수렴 속도는 매개변수(lambda, R0)와 기간에 강하게 의존한다. 기간이 길어지면 같은 M 에서
    오차가 커진다 (docs/reports/1B_ode_validation.md 의 표). 이 테스트는 365일만 다룬다."""
    reg = RegionSet.single(1e6)
    out = {}
    for M in (1, 2, 3, 4, 5, 6, 8, 10, 16):
        sysm = ReactionSystem(make_params(M=M), reg)
        tr = integrate_ode(sysm, initial_state(sysm.layout, reg.population, {0: 10.0}), 365)
        out[M] = (tr.I_total, tr.totals(tr.layout.D)[-1], tr.meta["last_bin_share"]["infectious"])
    Iref, Dref, _ = out[16]
    eI = {M: np.max(np.abs(out[M][0] - Iref)) / Iref.max() for M in out}
    eD = {M: abs(out[M][1] - Dref) / Dref for M in out}
    seq = [1, 2, 3, 4, 5, 6, 8, 10]
    assert all(eI[a] > eI[b] for a, b in zip(seq, seq[1:])), eI
    assert all(eD[a] > eD[b] for a, b in zip(seq, seq[1:])), eD
    assert eI[10] < 1e-6 and eD[10] < 1e-6
    # 기본값 M = 4 는 365일에도 수 % 오차가 있다 (보고 대상)
    assert 0.01 < eI[4] < 0.05
    # 진단: 마지막 칸 점유율이 작으면 오차도 작다
    assert out[4][2] > 0.5 and out[10][2] < 1e-2


# --------------------------------------------------------------------- 단일 지역 vs 지역망

def test_identical_regions_reproduce_single_region():
    """검증: 같은 지역 K개(같은 인구·밀도, 같은 비율로 감염자 배치)는 임의의 행 확률 C 와
    대칭 omega 에서도 각 지역이 단일 지역 해와 같다. 사망, 재감염, 이동이 모두 켜진 상태다.
    가정 확인: 모든 지역의 I/N 이 같으므로 Lambda_i 가 같고, 대칭 omega 이므로 순이동이 0 이다.
    한계: 이질성이 없는 경우만 검사한다."""
    K, Npop = 4, 2.5e5
    rng = np.random.default_rng(8)
    C = rng.random((K, K))
    C /= C.sum(axis=1, keepdims=True)
    om = rng.random((K, K)) * 0.02
    om = om + om.T
    np.fill_diagonal(om, 0)
    reg = RegionSet(tuple(f"r{i}" for i in range(K)), np.full(K, Npop), np.full(K, 50.0), C, om,
                    synthetic=True)
    p = make_params(f1=0.03, lam=1 / 90)
    net = ReactionSystem(p, reg, h_spec={"form": "power", "eta": 0.2})
    one = ReactionSystem(p, RegionSet.single(Npop, 50.0), h_spec={"form": "power", "eta": 0.2})
    trn = integrate_ode(net, initial_state(net.layout, reg.population, {i: 3.0 for i in range(K)}),
                        730, **TIGHT)
    tr1 = integrate_ode(one, initial_state(one.layout, np.array([Npop]), {0: 3.0}), 730, **TIGHT)
    for i in range(K):
        np.testing.assert_allclose(trn.X[:, i, :], tr1.X[:, 0, :], rtol=1e-7, atol=1e-5)


def test_proportionate_mixing_aggregates_to_single_region():
    """검증: 비례 혼합 C_ij = N_j / N_total 이고 h 가 같으면, 감염자를 서로 다른 지역에 심어도
    전체 합이 인구 N_total 인 단일 지역 해와 같다 (재감염 포함).
    가정 확인: Lambda_i = g c sum_j (N_j/N) I_eff,j / N_j = g c I_eff,tot / N.
    이 등식은 N_j 가 상수일 때만 성립하므로 f = 0, 이동 없음으로 둔다.
    한계: 사망이나 이동이 있으면 N_j(t) 가 변해 정확히 성립하지 않는다 (그 경우는 검사하지 않는다)."""
    K = 5
    rng = np.random.default_rng(2)
    pop = rng.uniform(1e5, 1e6, K)
    C = np.tile(pop / pop.sum(), (K, 1))
    reg = RegionSet(tuple(f"r{i}" for i in range(K)), pop, np.full(K, 10.0), C, np.zeros((K, K)),
                    synthetic=True)
    p = make_params(f1=0.0, lam=1 / 90)
    net = ReactionSystem(p, reg)
    one = ReactionSystem(p, RegionSet.single(pop.sum(), 10.0))
    trn = integrate_ode(net, initial_state(net.layout, pop, {0: 7.0, 4: 3.0}), 730, **TIGHT)
    tr1 = integrate_ode(one, initial_state(one.layout, np.array([pop.sum()]), {0: 10.0}), 730, **TIGHT)
    np.testing.assert_allclose(trn.X.sum(axis=1), tr1.X[:, 0, :], rtol=1e-7, atol=1e-4)


# --------------------------------------------------------------------- 시간가변 입력·수치 해법

def test_full_intervention_stops_transmission_exactly():
    """검증: u = 1 인 구간 [20, 40) 에서 새 감염이 0 (S 상수). 끝나면 전파가 재개된다.
    구간을 나눠 적분하는 방식이 경계에서 율을 섞지 않는지 확인한다."""
    p = make_params()
    u = InterventionSchedule(1, [{"start": 20.0, "end": 40.0, "value": 1.0, "regions": None}])
    sysm = ReactionSystem(p, RegionSet.single(1e6), Drivers(1, None, None, u))
    tr = integrate_ode(sysm, initial_state(sysm.layout, np.array([1e6]), {0: 10.0}), 80, **TIGHT)
    S = tr.X[:, 0, tr.layout.S]
    assert np.all(S[20:41] == S[20])
    assert S[41] < S[40] and S[19] > S[20]
    assert tr.meta["segments"] == 3


def test_solvers_agree():
    """검증: 해법(DOP853, LSODA, Radau)에 따라 결과가 달라지지 않는다 (상대 1e-5).
    한계: 같은 우변을 쓰므로 우변 자체의 오류는 이 테스트로 찾을 수 없다."""
    rng = np.random.default_rng(4)
    reg = RegionSet.synthetic_random(4, rng, total_population=1e6, mobility_scale=0.01)
    sysm = ReactionSystem(make_params(), reg)
    X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
    ref = integrate_ode(sysm, X0, 365, method="DOP853", rtol=1e-11, atol=1e-9).X
    for m in ("LSODA", "Radau"):
        x = integrate_ode(sysm, X0, 365, method=m, rtol=1e-10, atol=1e-8).X
        assert np.max(np.abs(x - ref)) / np.max(ref) < 1e-5, m


def test_output_grid():
    sysm = ReactionSystem(make_params(), RegionSet.single(1e5))
    X0 = initial_state(sysm.layout, np.array([1e5]), {0: 1.0})
    tr = integrate_ode(sysm, X0, 10, output_dt=0.5)
    np.testing.assert_allclose(tr.t, np.arange(0, 10.01, 0.5))
    assert tr.X.shape == (21, 1, sysm.layout.ncomp)
    np.testing.assert_array_equal(tr.X[0], X0)
