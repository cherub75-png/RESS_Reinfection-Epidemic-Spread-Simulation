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

    # ------------------------------------------------------------ 합성 자료

    @classmethod
    def single(cls, population: float, density: float = 1.0, name: str = "region0") -> "RegionSet":
        """단일 지역 (검증용)."""
        return cls((name,), np.array([population]), np.array([density]),
                   np.ones((1, 1)), np.zeros((1, 1)), synthetic=True,
                   provenance={"source": "synthetic single region"})

    @classmethod
    def synthetic_random(cls, K: int, rng: np.random.Generator, total_population: float = 1e6,
                         mobility_scale: float = 1e-3, self_contact: float = 0.8) -> "RegionSet":
        """무작위 합성 지역 집합 (검증용, 실제 지역 아님)."""
        pop = rng.dirichlet(np.ones(K)) * total_population
        dens = rng.lognormal(mean=5.0, sigma=1.0, size=K)
        off = rng.random((K, K))
        np.fill_diagonal(off, 0.0)
        if K > 1:
            off = off / off.sum(axis=1, keepdims=True) * (1.0 - self_contact)
            C = off + np.eye(K) * self_contact
        else:
            C = np.ones((1, 1))
        om = rng.random((K, K)) * mobility_scale
        np.fill_diagonal(om, 0.0)
        return cls(tuple(f"syn{i}" for i in range(K)), pop, dens, C, om, synthetic=True,
                   provenance={"source": "synthetic_random", "K": K})
