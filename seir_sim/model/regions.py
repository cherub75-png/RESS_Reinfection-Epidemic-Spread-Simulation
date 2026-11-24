"""지역 집합: 공통 지역 단위 i 의 인구, 밀도, 통근 접촉 C, 장거리 이동 omega.

1.3절
- C[i, j]: i 주민의 접촉 중 j 주민과의 비율 (행 합 1)
- omega[i, j]: i -> j 1인당 이동률 (1/일), 대각 0

실제 자료로 만든 지역 집합은 data 계층(1-D)에서 생성하며 provenance 를 채운다.
synthetic=True 인 지역 집합은 검증용 합성 자료이며 실제 지역을 뜻하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class RegionSet:
    names: tuple[str, ...]
    population: np.ndarray        # 초기 생존 인구 N_i(0) [명]
    density: np.ndarray           # 인구밀도 rho_i [명/km^2]
    contact: np.ndarray           # C [K, K], 행 합 1
    mobility: np.ndarray          # omega [K, K], 1/일
    synthetic: bool = False
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        K = len(self.names)
        object.__setattr__(self, "population", np.asarray(self.population, dtype=float))
        object.__setattr__(self, "density", np.asarray(self.density, dtype=float))
        object.__setattr__(self, "contact", np.asarray(self.contact, dtype=float))
        object.__setattr__(self, "mobility", np.asarray(self.mobility, dtype=float))
        if len(set(self.names)) != K:
            raise ValueError("지역 이름이 중복된다")
        if self.population.shape != (K,) or self.density.shape != (K,):
            raise ValueError("population, density 길이는 지역 수와 같아야 한다")
        if np.any(self.population < 0) or np.any(self.density <= 0):
            raise ValueError("population >= 0, density > 0 이어야 한다")
        if self.contact.shape != (K, K) or self.mobility.shape != (K, K):
            raise ValueError("contact, mobility 는 K x K 행렬이어야 한다")
        if np.any(self.contact < 0) or not np.allclose(self.contact.sum(axis=1), 1.0):
            raise ValueError("contact 는 음이 아니고 행 합이 1 이어야 한다")
        if np.any(self.mobility < 0) or np.any(np.diag(self.mobility) != 0):
            raise ValueError("mobility 는 음이 아니고 대각이 0 이어야 한다")

    @property
    def K(self) -> int:
        return len(self.names)

    def index(self, name: str) -> int:
        return self.names.index(name)

    def rho_ref(self, mode: str | float) -> float:
        """h(rho_ref) = 1 의 기준 밀도. 숫자 또는 'pop_weighted_mean'."""
        if isinstance(mode, (int, float)):
            return float(mode)
        if mode == "pop_weighted_mean":
            return float(np.sum(self.population * self.density) / np.sum(self.population))
        raise ValueError(f"알 수 없는 rho_ref: {mode!r}")

    # ------------------------------------------------------------ 이동 균형

    def mobility_net_flow(self, population: np.ndarray | None = None) -> np.ndarray:
        """지역별 순유입률 [명/일]: sum_j omega_ji N_j - sum_j omega_ij N_i."""
        N = self.population if population is None else population
        return self.mobility.T @ N - self.mobility.sum(axis=1) * N

    def mobility_imbalance(self) -> float:
        """max_i |순유입률_i| / N_i [1/일]. 0 이면 무감염 상태에서 인구가 변하지 않는다.

        0 이 아니면 감염이 없어도 이동만으로 지역 인구가 재분포된다. 그러면 t0 인구로 계산한
        R0_network_t0 는 그 순간의 값일 뿐이다 (docs/MODEL.md 4.1절).
        """
        N = self.population
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.abs(self.mobility_net_flow()) / N
        return float(np.nanmax(np.where(N > 0, r, 0.0))) if self.K else 0.0

    def stationary_population(self, horizon_days: float = 1e5) -> np.ndarray:
        """이동만 있을 때(감염·사망 없음) 현재 인구 분포에서 출발해 도달하는 장기 인구 분포.

        dN/dt = (omega^T - diag(omega 1)) N. 균형 이동이면 현재 인구가 이미 정지 상태이다.
        이동망이 여러 덩어리로 나뉘면 정지 분포가 유일하지 않으므로, 고유벡터 대신
        exp(Q T) N0 (T = horizon_days) 를 계산한다. 덩어리마다 인구가 보존된다.
        """
        N0 = self.population.astype(float)
        if not np.any(self.mobility) or self.mobility_imbalance() < 1e-12:
            return N0.copy()
        from scipy.linalg import expm
        Q = self.mobility.T - np.diag(self.mobility.sum(axis=1))
        x = expm(Q * horizon_days) @ N0
        x = np.maximum(x, 0.0)
        return x / x.sum() * N0.sum()

    # ------------------------------------------------------------ 합성 자료

    @classmethod
    def single(cls, population: float, density: float = 1.0, name: str = "region0") -> "RegionSet":
        """단일 지역 (검증용)."""
        return cls((name,), np.array([population]), np.array([density]),
                   np.ones((1, 1)), np.zeros((1, 1)), synthetic=True,
                   provenance={"source": "synthetic single region"})

    @classmethod
    def synthetic_random(cls, K: int, rng: np.random.Generator, total_population: float = 1e6,
                         mobility_scale: float = 1e-3, self_contact: float = 0.8,
                         balanced: bool = True) -> "RegionSet":
        """무작위 합성 지역 집합 (검증용, 실제 지역 아님).

        balanced=True 이면 이동이 양방향 같은 양(omega_ij N_i = omega_ji N_j)이 되도록 만든다.
        omega_ij = mobility_scale * W_ij * N_j / mean(N), W 는 대칭 무작위 행렬이다.
        이 경우 무감염 상태에서 지역 인구가 변하지 않는다.
        """
        pop = rng.dirichlet(np.ones(K)) * total_population
        dens = rng.lognormal(mean=5.0, sigma=1.0, size=K)
        off = rng.random((K, K))
        np.fill_diagonal(off, 0.0)
        if K > 1:
            off = off / off.sum(axis=1, keepdims=True) * (1.0 - self_contact)
            C = off + np.eye(K) * self_contact
        else:
            C = np.ones((1, 1))
        W = rng.random((K, K))
        if balanced:
            W = 0.5 * (W + W.T)
            om = mobility_scale * W * pop[None, :] / pop.mean()
        else:
            om = W * mobility_scale
        np.fill_diagonal(om, 0.0)
        return cls(tuple(f"syn{i}" for i in range(K)), pop, dens, C, om, synthetic=True,
                   provenance={"source": "synthetic_random", "K": K, "balanced_mobility": balanced})
