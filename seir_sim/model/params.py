"""감염병 매개변수 객체. ODE, SDE, CTMC, tau-leaping, hybrid 가 모두 이 객체를 공유한다.

단위: 시간은 일(day), 율은 1/일.

| 기호   | 이름    | 단위       | 정의 |
|--------|---------|------------|------|
| sigma  | sigma   | 1/일       | E -> I 율 (1/평균 잠복기) |
| gamma  | gamma   | 1/일       | I 이탈 율(회복 + 사망) (1/평균 감염기간) |
| c0     | c0      | 1/일       | 기준 접촉률 (h=1, u=0 에서 1인당 하루 접촉 수) |
| P1     | P1      | 무차원     | 첫 감염 감수성 = P(1), 그리고 면역 소실 상태(R^W)의 감수성 |
| Pmin   | Pmin    | 무차원     | n -> 무한대 일 때 P(n) 의 극한 |
| alpha  | alpha   | 무차원     | 감수성 감소 지수 |
| T1     | T1      | 무차원     | 첫 감염 전파력 = T(1) |
| beta   | beta    | 무차원     | 전파력 감소 지수 |
| lam    | lambda  | 1/일       | R^P -> R^W 면역 소실 율 |
| f1     | f1      | 무차원     | 첫 감염 치사율 (I 이탈 중 사망 비율) |
| phi    | phi(n)  | 무차원     | 치사율 형태, phi(1) = 1 |
| M      | M       | 정수       | 감염 횟수 칸 수 (마지막 칸은 "M회 이상") |

상호의존성: kappa = c * P1 * T1 (1.3절). 따라서 c0, P1, T1 은 초기 증가율과 R0 만으로는
따로따로 식별되지 않고 곱으로만 식별된다. 2단계의 식별 가능성 분석에서 다룬다.
R0 에서 c0 를 정하는 방법은 analysis.py 를 참고한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import functions as F


@dataclass(frozen=True)
class EpiParams:
    sigma: float
    gamma: float
    c0: float
    P1: float
    T1: float
    Pmin: float
    alpha: float
    beta: float
    lam: float
    f1: float
    phi_spec: dict = field(default_factory=lambda: {"form": "power", "delta": 0.5})
    M: int = 8          # 1-B 수렴 측정으로 4 -> 8 (승인됨)

    def __post_init__(self):
        if int(self.M) != self.M or self.M < 1:
            raise ValueError("M 은 1 이상의 정수여야 한다")
        for name in ("sigma", "gamma", "lam"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} 는 0 이상이어야 한다")
        if self.sigma == 0 or self.gamma == 0:
            raise ValueError("sigma, gamma 는 0보다 커야 한다")
        if self.c0 < 0:
            raise ValueError("c0 는 0 이상이어야 한다")
        if not (0.0 <= self.Pmin <= self.P1):
            raise ValueError("0 <= Pmin <= P1 이어야 한다")
        if self.alpha < 0 or self.beta < 0:
            raise ValueError("alpha, beta 는 0 이상이어야 한다")
        if self.T1 < 0:
            raise ValueError("T1 은 0 이상이어야 한다")
        phi = F.build_phi(self.phi_spec)
        if not np.isclose(float(phi(np.array([1]))[0]), 1.0):
            raise ValueError("phi(1) = 1 이어야 한다")
        fn = self.f1 * phi(np.arange(1, self.M + 1))
        if np.any(fn < 0) or np.any(fn > 1):
            raise ValueError(f"f(n) = f1*phi(n) 은 n=1..M 에서 [0,1] 이어야 한다: {fn}")

    # --- 1.2절 함수의 수치 값 (색인 n = 1..M 을 배열 위치 0..M-1 에 저장)

    def P(self, n) -> np.ndarray:
        return F.susceptibility(n, self.P1, self.Pmin, self.alpha)

    def T(self, n) -> np.ndarray:
        return F.transmissibility(n, self.T1, self.beta)

    def f(self, n) -> np.ndarray:
        return self.f1 * F.build_phi(self.phi_spec)(np.asarray(n))

    @property
    def T_by_n(self) -> np.ndarray:
        """[T(1), ..., T(M)]: I_n 의 전파력."""
        return self.T(np.arange(1, self.M + 1))

    @property
    def f_by_n(self) -> np.ndarray:
        """[f(1), ..., f(M)]: I_n 의 치사율."""
        return self.f(np.arange(1, self.M + 1))

    @property
    def P_next_by_n(self) -> np.ndarray:
        """[P(2), ..., P(M+1)]: R^P_n 의 감수성 P(n+1).

        마지막 칸 R^P_M 에는 P(M+1) 을 쓴다. 이는 M번째 이후 감염의 함수 값을
        n=M 기준으로 고정(freeze)하는 절단과 같은 규약이다 (docs/MODEL.md 3절).
        """
        return self.P(np.arange(2, self.M + 2))

    def m(self, n: int) -> int:
        """m(n) = min(n+1, M): R_n 이 재감염될 때 들어가는 E 칸 번호."""
        return min(n + 1, self.M)

    def with_(self, **kw) -> "EpiParams":
        return replace(self, **kw)

    def as_dict(self) -> dict:
        return {
            "sigma": self.sigma, "gamma": self.gamma, "c0": self.c0,
            "P1": self.P1, "T1": self.T1, "Pmin": self.Pmin,
            "alpha": self.alpha, "beta": self.beta, "lam": self.lam,
            "f1": self.f1, "phi_spec": dict(self.phi_spec), "M": self.M,
        }
