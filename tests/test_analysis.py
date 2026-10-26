"""R0, 다음 세대 행렬, c0 역산, 초기 증가율 (1.6절 검증식)."""

import numpy as np
import pytest

from conftest import make_params
from seir_sim.model import analysis as A
from seir_sim.model.drivers import Drivers, InterventionSchedule
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet


def test_single_region_R0_equals_kappa_over_gamma(base_params):
    sysm = ReactionSystem(base_params, RegionSet.single(1e6))
    X = A.disease_free_state(sysm)
    kap = A.kappa(base_params)
    assert A.reproduction_number(sysm, X) == pytest.approx(kap / base_params.gamma, rel=1e-12)
    assert A.reproduction_number(sysm, X) == pytest.approx(2.5, rel=1e-12)


def test_c0_reference_formula(base_params):
    c0 = A.c0_reference(2.5, base_params)
    assert c0 == pytest.approx(2.5 * base_params.gamma / (base_params.P1 * base_params.T1))
    q = make_params(P1=0.8, T1=0.5)
    sysm = ReactionSystem(q.with_(c0=A.c0_reference(2.5, q)), RegionSet.single(1e5))
    assert A.reproduction_number(sysm, A.disease_free_state(sysm)) == pytest.approx(2.5)


def test_homogeneous_network_without_mobility_has_same_R0(base_params):
    """C 의 행 합이 1 이고 g, c 가 같으면 F 는 kappa diag(N) C diag(1/N) 과 닮음 -> R0 = kappa/gamma."""
    rng = np.random.default_rng(0)
    reg = RegionSet.synthetic_random(6, rng, mobility_scale=0.0)
    sysm = ReactionSystem(base_params, reg)          # h 상수
    R = A.reproduction_number(sysm, A.disease_free_state(sysm))
    assert R == pytest.approx(A.kappa(base_params) / base_params.gamma, rel=1e-10)


def test_R0_linear_in_c0_and_network_calibration(base_params):
    rng = np.random.default_rng(1)
    reg = RegionSet.synthetic_random(5, rng, mobility_scale=0.05)
    u = InterventionSchedule(5, [{"start": 0.0, "end": 10.0, "value": 0.3, "regions": [2]}])
    sysm = ReactionSystem(base_params, reg, Drivers(5, None, None, u), {"form": "power", "eta": 0.3})
    X = A.disease_free_state(sysm)
    R1 = A.reproduction_number(sysm.with_params(c0=1.0), X)
    R3 = A.reproduction_number(sysm.with_params(c0=3.0), X)
    assert R3 == pytest.approx(3 * R1, rel=1e-12)
    c0 = A.c0_network(2.5, sysm)
    assert A.reproduction_number(sysm.with_params(c0=c0), X) == pytest.approx(2.5, rel=1e-12)
    # 이질성(h, u)이 있으면 기준 조건의 c0 와 다르다 -> 단순 관계를 가정하지 않는다
    assert not np.isclose(c0, A.c0_reference(2.5, base_params))


def test_effective_R_with_immunity_single_region():
    """단일 지역: R_t = sum_n T(n) A_n g c / (N gamma)  (F 가 랭크 1)."""
    p = make_params(M=3)
    sysm = ReactionSystem(p, RegionSet.single(1e4))
    L = sysm.layout
    X = L.empty()
    X[0, L.S] = 4000
    X[0, L.RP(1)], X[0, L.RW(1)] = 2000, 1000
    X[0, L.RP(2)], X[0, L.RW(2)] = 1000, 500
    X[0, L.RP(3)], X[0, L.RW(3)] = 900, 600
    N = X.sum()
    An = np.zeros(3)
    An[0] = p.P1 * X[0, L.S]
    for l in range(1, 4):
        An[min(l + 1, 3) - 1] += float(p.P(l + 1)) * X[0, L.RP(l)] + p.P1 * X[0, L.RW(l)]
    expected = p.c0 * np.sum(p.T_by_n * An) / (N * p.gamma)
    assert A.reproduction_number(sysm, X) == pytest.approx(expected, rel=1e-12)


def _jacobian(sysm, X, eps=1e-3):
    x0 = X.reshape(-1)
    n = x0.size
    J = np.zeros((n, n))
    for k in range(n):
        xp, xm = x0.copy(), x0.copy()
        xp[k] += eps
        xm[k] -= eps
        J[:, k] = (sysm.drift(xp.reshape(X.shape), 0.0) - sysm.drift(xm.reshape(X.shape), 0.0)).reshape(-1) / (2 * eps)
    return J


@pytest.mark.parametrize("R0", [0.8, 1.5, 2.5, 4.0])
def test_growth_rate_matches_linearization_of_event_list(R0):
    p = make_params()
    p = p.with_(c0=A.c0_reference(R0, p))
    sysm = ReactionSystem(p, RegionSet.single(1e8))
    L = sysm.layout
    X = A.disease_free_state(sysm)
    J = _jacobian(sysm, X)
    idx = [L.E(1), L.I(1)]
    r_lin = np.max(np.linalg.eigvals(J[np.ix_(idx, idx)]).real)
    r_formula = A.initial_growth_rate(p.sigma, p.gamma, A.kappa(p))
    assert r_lin == pytest.approx(r_formula, rel=1e-6)
    assert np.sign(r_formula) == np.sign(R0 - 1)
    # 전체 야코비안의 최대 실수 고유값도 (양수일 때) 같다
    if R0 > 1:
        assert np.max(np.linalg.eigvals(J).real) == pytest.approx(r_formula, rel=1e-6)


def test_ngm_matches_drift_jacobian_network():
    """F - V 가 사건 목록 drift 의 감염 부분 야코비안과 같다 (이동, h, u 이질성 포함 지역망).
    drift 는 무감염 상태 근방에서 감염 구획에 선형이므로 중앙차분이 정확하다."""
    rng = np.random.default_rng(5)
    reg = RegionSet.synthetic_random(5, rng, total_population=1e9, mobility_scale=0.02)
    u = InterventionSchedule(5, [{"start": 0.0, "end": 10.0, "value": 0.3, "regions": [1]}])
    sysm = ReactionSystem(make_params(), reg, Drivers(5, None, None, u), {"form": "power", "eta": 0.2})
    X = A.disease_free_state(sysm)
    F, V = A.next_generation_matrices(sysm, X)
    idx = A._infected_index(sysm)
    x0 = X.reshape(-1)
    J = np.zeros((idx.size, idx.size))
    for a, k in enumerate(idx):
        xp, xm = x0.copy(), x0.copy()
        xp[k] += 1.0
        xm[k] -= 1.0
        J[:, a] = (sysm.drift(xp.reshape(X.shape), 0.0) - sysm.drift(xm.reshape(X.shape), 0.0)).reshape(-1)[idx] / 2
    np.testing.assert_allclose(J, F - V, atol=1e-12)


def test_balanced_synthetic_mobility_is_stationary():
    rng = np.random.default_rng(9)
    reg = RegionSet.synthetic_random(7, rng, total_population=1e7, mobility_scale=0.05)
    assert reg.mobility_imbalance() < 1e-14
    np.testing.assert_allclose(reg.stationary_population(), reg.population, rtol=1e-10)


@pytest.mark.parametrize("K,M", [(1, 1), (3, 2), (4, 3), (5, 4)])
def test_reduced_ngm_equals_full_ngm(K, M):
    """축소 K x K 행렬의 스펙트럼 반지름 = 전체 2KM x 2KM 다음 세대 행렬 (이동, 면역자, 이질성 포함)."""
    rng = np.random.default_rng(10 * K + M)
    reg = RegionSet.synthetic_random(K, rng, total_population=1e6, mobility_scale=0.05, balanced=False)
    u = InterventionSchedule(K, [{"start": 0.0, "end": 5.0, "value": 0.3, "regions": [0]}])
    sysm = ReactionSystem(make_params(M=M, alpha=0.7), reg, Drivers(K, None, None, u), {"form": "power", "eta": 0.3})
    L = sysm.layout
    X = rng.random((K, L.ncomp)) * 1e4
    X[:, L.E_slice] = 0.0
    X[:, L.I_slice] = 0.0
    assert A.reproduction_number(sysm, X) == pytest.approx(A.reproduction_number_full(sysm, X), rel=1e-9)
    X0 = A.disease_free_state(sysm)
    assert A.reproduction_number(sysm, X0) == pytest.approx(A.reproduction_number_full(sysm, X0), rel=1e-9)


def test_stationary_population_disconnected_network():
    """이동망이 두 덩어리로 나뉘고 불균형일 때 덩어리별 인구가 보존된다 (고유벡터 선택 오류 회귀 테스트)."""
    om = np.zeros((4, 4))
    om[0, 1], om[1, 0] = 0.02, 0.01          # 덩어리 {0,1}: 불균형
    om[2, 3], om[3, 2] = 0.01, 0.01          # 덩어리 {2,3}
    pop = np.array([100.0, 100.0, 300.0, 500.0])
    reg = RegionSet(tuple("abcd"), pop, np.ones(4), np.eye(4), om, True)
    st = reg.stationary_population()
    assert st[:2].sum() == pytest.approx(200.0) and st[2:].sum() == pytest.approx(800.0)
    np.testing.assert_allclose(reg.mobility_net_flow(st), 0.0, atol=1e-8)
    np.testing.assert_allclose(st, [200 / 3, 400 / 3, 400.0, 400.0], rtol=1e-8)
