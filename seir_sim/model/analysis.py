"""재생산수와 초기 증가율: 1.4절 방정식을 선형화해서 유도한다 (docs/MODEL.md 4절).

다음 세대 행렬 (van den Driessche & Watmough 2002)
  감염 구획 x = (E_{n,i}, I_{n,i})
  dx/dt = F x - V x
  K_ngm = F V^{-1},  R = 스펙트럼 반지름(K_ngm)

F[E_{n,i}, I_{k,j}] = A_{n,i} g_i c_i C_ij T(k) / N_j
  A_{n,i} = 1{n=1} P_1 S_i + sum_{l: m(l)=n} ( P(l+1) R^P_{l,i} + P_1 R^W_{l,i} )
V: E 이탈 sigma + sum_j omega_ij, I 이탈 gamma + sum_j omega_ij, 이동 유입 -omega_ji, E->I 는 -sigma.

감염자가 없는 상태(E = I = 0)에서는 정확한 선형화다. 그 밖의 상태에서는 감수성 인구를
그 시점 값으로 고정한 순간 재생산수 R_t 로 해석한다.

단일 지역, 전원 감수성, 이동 없음이면 F 와 V 가 2x2 가 되어 R0 = kappa / gamma 이다.
여기서 kappa = g c P_1 T_1, c = c0 h(rho)(1-u).
R0 는 c0 에 선형이다 (F 가 c0 에 비례하고 V 는 c0 와 무관). 따라서
  c0 = R0_target / R(c0 = 1)
이 정확하다. h, g, u, C, omega, 인구 분포의 영향은 모두 R(c0 = 1) 에 들어간다.
"""

from __future__ import annotations

import numpy as np

from .reactions import ReactionSystem


def _infected_index(system: ReactionSystem) -> np.ndarray:
    L = system.layout
    idx = []
    for i in range(L.K):
        idx += [L.flat(i, L.E(n)) for n in range(1, L.M + 1)]
        idx += [L.flat(i, L.I(n)) for n in range(1, L.M + 1)]
    return np.array(idx)


def next_generation_matrices(system: ReactionSystem, X: np.ndarray, t: float = 0.0):
    """(F, V) 를 감염 구획 순서 [지역 i: E_1..E_M, I_1..I_M] 로 반환한다."""
    p, L, reg = system.params, system.layout, system.regions
    K, M = L.K, L.M
    dim = 2 * M
    F = np.zeros((K * dim, K * dim))
    V = np.zeros((K * dim, K * dim))
    e = lambda i, n: i * dim + (n - 1)          # noqa: E731
    I = lambda i, n: i * dim + M + (n - 1)      # noqa: E731

    N = L.alive(X)
    gc = system.drivers.g(t) * system.contact_rate(t)
    T, P_next = p.T_by_n, p.P_next_by_n

    A = np.zeros((K, M))
    A[:, 0] += p.P1 * X[:, L.S]
    for l in range(1, M + 1):
        A[:, p.m(l) - 1] += P_next[l - 1] * X[:, L.RP(l)] + p.P1 * X[:, L.RW(l)]

    for i in range(K):
        for j in range(K):
            if N[j] <= 0 or reg.contact[i, j] == 0:
                continue
            for n in range(1, M + 1):
                for k in range(1, M + 1):
                    F[e(i, n), I(j, k)] = A[i, n - 1] * gc[i] * reg.contact[i, j] * T[k - 1] / N[j]

    om = reg.mobility
    out = om.sum(axis=1)
    for i in range(K):
        for n in range(1, M + 1):
            V[e(i, n), e(i, n)] = p.sigma + out[i]
            V[I(i, n), I(i, n)] = p.gamma + out[i]
            V[I(i, n), e(i, n)] = -p.sigma
            for j in range(K):
                if om[j, i] > 0:
                    V[e(i, n), e(j, n)] -= om[j, i]
                    V[I(i, n), I(j, n)] -= om[j, i]
    return F, V


def reproduction_number_full(system: ReactionSystem, X: np.ndarray, t: float = 0.0) -> float:
    """전체 (2KM x 2KM) 다음 세대 행렬로 계산한다. 검증용 (K 가 크면 느리다)."""
    F, V = next_generation_matrices(system, X, t)
    Kn = F @ np.linalg.inv(V)
    return float(np.max(np.abs(np.linalg.eigvals(Kn))))


def reduced_ngm(system: ReactionSystem, X: np.ndarray, t: float = 0.0) -> np.ndarray:
    """F V^{-1} 의 0이 아닌 고유값을 그대로 갖는 K x K 행렬 (정확한 축소).

    V 는 감염 횟수 n 마다 같은 블록 [[sigma I + L, 0], [-sigma I, gamma I + L]] 이다.
    L = diag(out) - omega^T 는 이동 생성자이다. 그러면 (V^{-1})_{I_n, E_n} = sigma (gamma I + L)^{-1} (sigma I + L)^{-1} = W 이다.
    F[E_n i, I_k j] = A_{n,i} gc_i C_ij T(k) / N_j 이므로, 고유값 문제는 y_i = sum_n T(n) x_{n,i} 로 줄어든다.
      K_red = diag(a_eff * gc) C diag(1/N) W,   a_eff_i = sum_n T(n) A_{n,i}
    """
    p, L, reg = system.params, system.layout, system.regions
    K, M = L.K, L.M
    N = L.alive(X)
    gc = system.drivers.g(t) * system.contact_rate(t)
    T, P_next = p.T_by_n, p.P_next_by_n
    A = np.zeros((K, M))
    A[:, 0] += p.P1 * X[:, L.S]
    for l in range(1, M + 1):
        A[:, p.m(l) - 1] += P_next[l - 1] * X[:, L.RP(l)] + p.P1 * X[:, L.RW(l)]
    a_eff = A @ T
    Lm = np.diag(reg.mobility.sum(axis=1)) - reg.mobility.T
    I = np.eye(K)
    W = p.sigma * np.linalg.solve(p.gamma * I + Lm, np.linalg.solve(p.sigma * I + Lm, I))
    invN = np.divide(1.0, N, out=np.zeros_like(N), where=N > 0)
    return (a_eff * gc)[:, None] * reg.contact * invN[None, :] @ W


def reproduction_number(system: ReactionSystem, X: np.ndarray, t: float = 0.0) -> float:
    """R = 스펙트럼 반지름(F V^{-1}). 축소 행렬 reduced_ngm 으로 계산한다 (전체 행렬과 같음: 테스트로 확인)."""
    return float(np.max(np.abs(np.linalg.eigvals(reduced_ngm(system, X, t)))))


def disease_free_state(system: ReactionSystem) -> np.ndarray:
    X = system.layout.empty()
    X[:, system.layout.S] = system.regions.population
    return X


def c0_reference(R0: float, params) -> float:
    """기준 조건(단일 지역, rho = rho_ref, g = 1, u = 0, 이동 없음)에서 R0 = c0 P_1 T_1 / gamma."""
    denom = params.P1 * params.T1
    if denom <= 0:
        raise ValueError("P1 * T1 > 0 이어야 R0 로부터 c0 를 정할 수 있다")
    return R0 * params.gamma / denom


def c0_network(R0: float, system: ReactionSystem, X: np.ndarray | None = None, t: float = 0.0) -> float:
    """주어진 지역망·시점 t 의 NGM 스펙트럼 반지름이 R0 가 되도록 c0 를 정한다."""
    X = disease_free_state(system) if X is None else X
    R_unit = reproduction_number(system.with_params(c0=1.0), X, t)
    if R_unit <= 0:
        raise ValueError("c0 = 1 에서 R = 0 이다. 전파가 불가능한 설정이다")
    return R0 / R_unit


def isolated_r0(system: ReactionSystem, t: float = 0.0) -> np.ndarray:
    """지역별 고립 R0: 지역 i 가 자기 주민끼리만 접촉하고 이동이 없을 때 g_i(t) c_i(t) P1 T1 / gamma (c0 에 비례)."""
    p = system.params
    return system.drivers.g(t) * system.contact_rate(t) * p.P1 * p.T1 / p.gamma


def c0_region(R0: float, system: ReactionSystem, region: int, t: float = 0.0) -> float:
    """사용자가 고른 기준 지역 region 의 고립 R0 가 목표가 되도록 c0 를 정한다 (D-008).
    모든 지역에 같은 c0 를 쓰므로 지역 간 상대 전파력(h(rho_i), g_i, u_i)은 그대로다."""
    unit = isolated_r0(system.with_params(c0=1.0), t)[region]
    if unit <= 0:
        raise ValueError(f"기준 지역 {system.regions.names[region]!r} 의 고립 R0 가 0 이다 (u = 1 또는 g = 0?)")
    return R0 / unit


def c0_population_mean(R0: float, system: ReactionSystem, t: float = 0.0) -> float:
    """인구가중 평균 고립 R0 가 목표가 되도록 c0 를 정한다 (D-008 비교용)."""
    unit = isolated_r0(system.with_params(c0=1.0), t)
    pop = system.regions.population
    m = float(np.sum(unit * pop) / pop.sum())
    if m <= 0:
        raise ValueError("인구가중 평균 고립 R0 가 0 이다")
    return R0 / m


def kappa(params, h: float = 1.0, g: float = 1.0, u: float = 0.0) -> float:
    """kappa = c P_1 T_1,  c = c0 h (1 - u),  g 를 곱한 실효값."""
    return g * params.c0 * h * (1.0 - u) * params.P1 * params.T1


def initial_growth_rate(sigma: float, gamma: float, kappa_: float) -> float:
    """r = [-(sigma + gamma) + sqrt((sigma - gamma)^2 + 4 sigma kappa)] / 2  (1.6절)."""
    return 0.5 * (-(sigma + gamma) + np.sqrt((sigma - gamma) ** 2 + 4.0 * sigma * kappa_))


def r0_report(system: ReactionSystem, t: float = 0.0) -> dict:
    """현재 c0 에서 여러 기준의 R0 를 모두 계산한다 (c0 를 어느 기준으로 정했는지와 무관).

    - R0_reference: 기준 조건(h = 1, g = 1, u = 0, 단일 지역) c0 P1 T1 / gamma
    - R0_network_t0: 전원 감수성, t0 인구 분포의 지역망 NGM 스펙트럼 반지름
    - R0_network_stationary: 이동만 있을 때의 정지 인구 분포에서의 NGM 스펙트럼 반지름.
      이동이 불균형이면(mobility_imbalance > 0) t0 인구가 유지되지 않으므로 이 값이 장기적으로 의미가 있다
    - R0_isolated_by_region: 지역 i 가 자기 주민끼리만 접촉하고(C_ii = 1) 이동이 없을 때
      g_i(t) c_i(t) P1 T1 / gamma. 최초 발생 지역(예: 해외 유입 원점)의 국지 전파력 비교용
    """
    p, reg = system.params, system.regions
    local = isolated_r0(system, t)
    X_st = disease_free_state(system)
    X_st[:, system.layout.S] = reg.stationary_population()
    dfe = disease_free_state(system)
    Kr = reduced_ngm(system, dfe, t)
    w, v = np.linalg.eig(Kr)
    k = int(np.argmax(np.abs(w)))
    y = np.abs(v[:, k].real)
    y = y / y.sum() if y.sum() > 0 else y
    order = np.argsort(y)[::-1]
    cover = order[: int(np.searchsorted(np.cumsum(y[order]), 0.9) + 1)]
    pop = reg.population
    dom_share = float(pop[cover].sum() / pop.sum()) if pop.sum() > 0 else 0.0
    return {
        "R0_reference": p.c0 * p.P1 * p.T1 / p.gamma,
        "R0_network_t0": float(np.abs(w[k])),
        "R0_network_stationary": reproduction_number(system, X_st, t),
        "mobility_imbalance_per_day": reg.mobility_imbalance(),
        "R0_isolated_by_region": dict(zip(reg.names, map(float, local))),
        # 지역망 R0 의 주 고유모드가 몰린 지역 (고유벡터 질량 90%) 과 그 인구 비율
        "R0_network_dominant_regions": [reg.names[i] for i in cover[:10]],
        "R0_network_dominant_population_share": dom_share,
        "R0_network_dominated_by_small_population": dom_share < 0.05,
        "R0_isolated_population_weighted_mean": float(np.sum(local * pop) / pop.sum()) if pop.sum() > 0 else 0.0,
        # R0 > 1 인구 비율: 고립 R0 > 1 인 지역의 인구 합 / 전체 인구 (지역 내 전파만으로 대유행이 가능한 인구의 비율).
        # 지역 간 이동으로 R0 < 1 지역에도 감염이 들어올 수 있으므로 "감염될 수 있는 인구" 를 뜻하지는 않는다.
        "population_share_isolated_R0_gt1": float(pop[local > 1].sum() / pop.sum()) if pop.sum() > 0 else 0.0,
    }
