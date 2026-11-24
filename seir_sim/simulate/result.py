"""모든 적분기(ODE, SDE, CTMC, tau-leaping, hybrid)가 공통으로 쓰는 결과 형식."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

from ..model.state import Layout

DEFAULT_LAST_BIN_WARN = 0.05   # 1-C 결정: 1% -> 5% (오차 약 2e-4 수준)


class LastBinWarning(UserWarning):
    """마지막 감염 횟수 칸(M회 이상)의 점유율이 기준을 넘었다. M 을 늘려야 한다."""


@dataclass
class Trajectory:
    t: np.ndarray            # [T] 일
    X: np.ndarray            # [T, K, ncomp]
    layout: Layout
    method: str
    meta: dict = field(default_factory=dict)

    @property
    def I_by_region(self) -> np.ndarray:
        """[T, K]: I_i(t) = sum_n I_{n,i}(t)."""
        return self.X[:, :, self.layout.I_slice].sum(axis=2)

    @property
    def I_total(self) -> np.ndarray:
        """[T]: I_total(t) = sum_i sum_n I_{n,i}(t)."""
        return self.I_by_region.sum(axis=1)

    def totals(self, sl) -> np.ndarray:
        """[T]: 구획 묶음(slice 또는 색인)의 전체 합."""
        return self.X[:, :, sl].reshape(self.X.shape[0], -1).sum(axis=1)

    @property
    def population_total(self) -> np.ndarray:
        """[T]: sum(모든 구획 + D). 보존되어야 한다."""
        return self.X.reshape(self.X.shape[0], -1).sum(axis=1)

    def last_bin_share(self) -> dict:
        """절단 진단: 마지막 감염 횟수 칸(M회 이상)의 점유율.

        - alive: (E_M + I_M + R^P_M + R^W_M) / N 의 최대값
        - infectious: I_M / I_total 의 최대값. I_total >= max(1e-6 N0, 10) 인 시점만 본다
          (감염자가 몇 명뿐일 때의 확률적 잡음으로 경고가 나지 않게 하려는 것)
        값이 크면 M회를 넘게 감염된 사람이 많다는 뜻이므로 M 을 늘려야 한다 (docs/MODEL.md 3절).
        """
        L, M = self.layout, self.layout.M
        cols = [L.E(M), L.I(M), L.RP(M), L.RW(M)]
        alive = self.X[:, :, L.alive_slice].sum(axis=(1, 2))
        lastbin = self.X[:, :, cols].sum(axis=(1, 2))
        I_M = self.X[:, :, L.I(M)].sum(axis=1)
        It = self.I_total
        ok = It >= max(1e-6 * self.population_total[0], 10.0)
        return {"alive": float(np.max(lastbin / np.where(alive > 0, alive, 1.0))),
                "infectious": float(np.max(I_M[ok] / It[ok])) if ok.any() else 0.0}


def check_last_bin(tr: Trajectory, threshold: float = DEFAULT_LAST_BIN_WARN) -> None:
    """meta 에 절단 진단을 기록하고, 마지막 칸 I 점유율이 threshold 를 넘으면 경고한다."""
    share = tr.last_bin_share()
    tr.meta["last_bin_share"] = share
    tr.meta["last_bin_warn_threshold"] = threshold
    tr.meta["last_bin_warning"] = share["infectious"] > threshold
    if tr.meta["last_bin_warning"]:
        warnings.warn(f"마지막 감염 횟수 칸(M={tr.layout.M}) 의 I 점유율 {share['infectious']:.3f} 가 "
                      f"기준 {threshold} 를 넘는다. M 을 늘려야 결과가 수렴한다.", LastBinWarning,
                      stacklevel=3)
