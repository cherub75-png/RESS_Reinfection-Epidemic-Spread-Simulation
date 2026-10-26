"""시간에 따라 변하는 외부 입력: 환경 보정 g_i(t), 방역 개입 u_i(t).

두 입력 모두 구간별 상수(piecewise constant)로 둔다. 변화 시점은 next_change(t) 로 알려 준다.
따라서 CTMC(Gillespie)는 변화 시점마다 멈췄다가 다시 시작하는 방식으로 정확성을 유지할 수 있다.
구간 안에서는 율이 상태에만 의존하기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import functions as F


@dataclass
class EnvironmentSeries:
    """지역별 일 단위 환경 시계열. 값 [d, i] 는 구간 [d, d+1) 동안 적용된다.

    범위 밖의 t 에서는 가장 가까운 끝 값을 쓴다.
    """
    temperature: np.ndarray     # [days, K]
    humidity: np.ndarray        # [days, K]
    synthetic: bool = True
    provenance: dict = field(default_factory=dict)

    def at(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        d = int(np.clip(np.floor(t), 0, self.temperature.shape[0] - 1))
        return self.temperature[d], self.humidity[d]


@dataclass
class InterventionSchedule:
    """u_i(t) in [0, 1]. 구간 [start, end) 동안 value. 겹치는 구간은 뒤의 항목이 덮어쓴다."""
    K: int
    periods: list[dict] = field(default_factory=list)   # {start, end, value, regions: list[int] | None}

    def __post_init__(self):
        for p in self.periods:
            if not (0.0 <= p["value"] <= 1.0):
                raise ValueError("u 값은 [0, 1] 이어야 한다")
            if p["end"] <= p["start"]:
                raise ValueError("u 구간은 start < end 이어야 한다")

    def at(self, t: float) -> np.ndarray:
        u = np.zeros(self.K)
        for p in self.periods:
            if p["start"] <= t < p["end"]:
                idx = slice(None) if p.get("regions") is None else p["regions"]
                u[idx] = p["value"]
        return u

    def breakpoints(self) -> list[float]:
        return sorted({float(p["start"]) for p in self.periods} | {float(p["end"]) for p in self.periods})


class Drivers:
    """g_i(t), u_i(t) 를 제공한다. 기본값은 g = 1, u = 0."""

    def __init__(self, K: int, g_spec: dict | None = None,
                 environment: EnvironmentSeries | None = None,
                 interventions: InterventionSchedule | None = None):
        self.K = K
        self.g_spec = g_spec or {"form": "constant"}
        self._g = F.build_g(self.g_spec)
        self.environment = environment
        self.interventions = interventions or InterventionSchedule(K)
        if self.g_spec["form"] != "constant" and environment is None:
            raise ValueError("g 가 상수가 아니면 환경 시계열(environment)이 필요하다")

    def g(self, t: float) -> np.ndarray:
        if self.environment is None:
            return np.ones(self.K)
        T, H = self.environment.at(t)
        return np.broadcast_to(self._g(T, H), (self.K,)).astype(float)

    def u(self, t: float) -> np.ndarray:
        return self.interventions.at(t)

    def next_change(self, t: float) -> float:
        """t 보다 뒤에서 g 또는 u 가 바뀔 수 있는 가장 이른 시점 (없으면 inf)."""
        cands = [b for b in self.interventions.breakpoints() if b > t]
        if self.environment is not None:
            nd = np.floor(t) + 1.0
            if nd < self.environment.temperature.shape[0]:
                cands.append(nd)
        return min(cands) if cands else np.inf

    @property
    def is_constant(self) -> bool:
        return self.environment is None and not self.interventions.periods
