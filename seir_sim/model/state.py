"""상태 벡터 배치.

지역 i 마다 구획 ncomp = 4M + 2 개를 다음 순서로 둔다.
  0                    S
  1      + (n-1)       E_n      n = 1..M
  1 +  M + (n-1)       I_n
  1 + 2M + (n-1)       R^P_n
  1 + 3M + (n-1)       R^W_n
  1 + 4M               D
상태 X 의 모양은 (K, ncomp) 이고, 평탄화 색인은 i * ncomp + comp 이다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Layout:
    K: int
    M: int

    @property
    def ncomp(self) -> int:
        return 4 * self.M + 2

    @property
    def size(self) -> int:
        return self.K * self.ncomp

    S = 0

    def E(self, n: int) -> int:
        self._check(n)
        return 1 + (n - 1)

    def I(self, n: int) -> int:
        self._check(n)
        return 1 + self.M + (n - 1)

    def RP(self, n: int) -> int:
        self._check(n)
        return 1 + 2 * self.M + (n - 1)

    def RW(self, n: int) -> int:
        self._check(n)
        return 1 + 3 * self.M + (n - 1)

    @property
    def D(self) -> int:
        return 1 + 4 * self.M

    def _check(self, n: int):
        if not (1 <= n <= self.M):
            raise IndexError(f"감염 횟수 n={n} 은 1..{self.M} 범위여야 한다")

    # 구획 묶음 슬라이스 (comp 축)
    @property
    def E_slice(self) -> slice:
        return slice(1, 1 + self.M)

    @property
    def I_slice(self) -> slice:
        return slice(1 + self.M, 1 + 2 * self.M)

    @property
    def RP_slice(self) -> slice:
        return slice(1 + 2 * self.M, 1 + 3 * self.M)

    @property
    def RW_slice(self) -> slice:
        return slice(1 + 3 * self.M, 1 + 4 * self.M)

    @property
    def alive_slice(self) -> slice:
        return slice(0, 1 + 4 * self.M)

    def flat(self, i: int, comp: int) -> int:
        return i * self.ncomp + comp

    def labels(self) -> list[str]:
        M = self.M
        return (["S"] + [f"E{n}" for n in range(1, M + 1)] + [f"I{n}" for n in range(1, M + 1)]
                + [f"RP{n}" for n in range(1, M + 1)] + [f"RW{n}" for n in range(1, M + 1)] + ["D"])

    def empty(self) -> np.ndarray:
        return np.zeros((self.K, self.ncomp))

    def alive(self, X: np.ndarray) -> np.ndarray:
        """N_i = S + sum_n (E + I + R^P + R^W)."""
        return X[:, self.alive_slice].sum(axis=1)

    def infectious_total(self, X: np.ndarray) -> np.ndarray:
        """지역별 I_i = sum_n I_{n,i}."""
        return X[:, self.I_slice].sum(axis=1)


def initial_state(layout: Layout, population: np.ndarray, seeds: dict[int, float],
                  compartment: str = "I1") -> np.ndarray:
    """전원 감수성인 초기 상태에 감염자를 심는다. seeds: {지역 색인: 인원}.

    심은 인원은 해당 지역 S 에서 빼므로 총인구는 보존된다.
    """
    X = layout.empty()
    X[:, layout.S] = population
    labels = layout.labels()
    if compartment not in labels or compartment == "D" or compartment == "S":
        raise ValueError(f"초기 감염 구획은 E/I/R 중 하나여야 한다: {compartment!r}")
    comp = labels.index(compartment)
    for i, k in seeds.items():
        if k > X[i, layout.S]:
            raise ValueError(f"지역 {i} 의 초기 감염자 {k} 가 인구보다 많다")
        X[i, layout.S] -= k
        X[i, comp] += k
    return X
