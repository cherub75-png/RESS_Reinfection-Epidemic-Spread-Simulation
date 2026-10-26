"""공통 사건 목록 (1.5절). ODE, SDE, CTMC, tau-leaping, hybrid 가 모두 이것 하나를 쓴다.

1.4절 ODE 의 모든 항은 "한 사람을 구획 src 에서 dst 로 옮기는" 사건 j 이다.
  a_j(X, t) = [ k_j + s_j * Lambda_{r_j}(X, t) ] * X[src_j]
  nu_j      = e_{dst_j} - e_{src_j}
- k_j: 상수 율 (sigma, (1-f)gamma, f gamma, lambda, omega)
- s_j: 감수성 계수 (P_1 또는 P(l+1)). 감염 사건에만 0이 아니다.
- r_j: 감염력 Lambda 를 읽을 지역

사건 종류 (지역 i, n = 1..M)
  INFECT_S   S_i       -> E_{1,i}        s = P_1
  REINF_P    R^P_{l,i} -> E_{m(l),i}     s = P(l+1)
  REINF_W    R^W_{l,i} -> E_{m(l),i}     s = P_1
  PROGRESS   E_{n,i}   -> I_{n,i}        k = sigma
  RECOVER    I_{n,i}   -> R^P_{n,i}      k = (1 - f(n)) gamma
  DIE        I_{n,i}   -> D_i            k = f(n) gamma
  WANE       R^P_{n,i} -> R^W_{n,i}      k = lambda
  MOVE       X_i       -> X_j            k = omega_ij   (D 를 뺀 모든 구획, omega_ij > 0 인 쌍만)

모든 사건이 한 명을 옮기기만 하므로 sum(S, E, I, R^P, R^W, D) 는 구조적으로 보존된다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import functions as F
from .drivers import Drivers
from .params import EpiParams
from .regions import RegionSet
from .state import Layout

KIND_NAMES = ("INFECT_S", "REINF_P", "REINF_W", "PROGRESS", "RECOVER", "DIE", "WANE", "MOVE")
INFECT_S, REINF_P, REINF_W, PROGRESS, RECOVER, DIE, WANE, MOVE = range(len(KIND_NAMES))


@dataclass(frozen=True)
class Channels:
    src: np.ndarray      # 평탄화 색인
    dst: np.ndarray
    const: np.ndarray    # k_j
    susc: np.ndarray     # s_j
    region: np.ndarray   # r_j
    kind: np.ndarray

    def __len__(self):
        return self.src.size


def build_channels(params: EpiParams, regions: RegionSet, layout: Layout) -> Channels:
    M, K, nc = params.M, regions.K, layout.ncomp
    P_next, f_n = params.P_next_by_n, params.f_by_n
    rows: list[tuple[int, int, float, float, int, int]] = []

    def add(i, src_c, dst_c, const, susc, kind, dst_i=None):
        dst_i = i if dst_i is None else dst_i
        rows.append((i * nc + src_c, dst_i * nc + dst_c, const, susc, i, kind))

    for i in range(K):
        add(i, layout.S, layout.E(1), 0.0, params.P1, INFECT_S)
        for l in range(1, M + 1):
            add(i, layout.RP(l), layout.E(params.m(l)), 0.0, float(P_next[l - 1]), REINF_P)
            add(i, layout.RW(l), layout.E(params.m(l)), 0.0, params.P1, REINF_W)
        for n in range(1, M + 1):
            add(i, layout.E(n), layout.I(n), params.sigma, 0.0, PROGRESS)
            add(i, layout.I(n), layout.RP(n), (1.0 - f_n[n - 1]) * params.gamma, 0.0, RECOVER)
            add(i, layout.I(n), layout.D, f_n[n - 1] * params.gamma, 0.0, DIE)
            add(i, layout.RP(n), layout.RW(n), params.lam, 0.0, WANE)

    om = regions.mobility
    for i, j in zip(*np.nonzero(om)):
        for c in range(layout.D):          # D 를 뺀 생존 구획
            add(int(i), c, c, float(om[i, j]), 0.0, MOVE, dst_i=int(j))

    a = np.array(rows, dtype=float).reshape(-1, 6)
    return Channels(src=a[:, 0].astype(np.int64), dst=a[:, 1].astype(np.int64),
                    const=a[:, 2].copy(), susc=a[:, 3].copy(),
                    region=a[:, 4].astype(np.int64), kind=a[:, 5].astype(np.int64))


class ReactionSystem:
    """매개변수 + 지역 + 외부 입력 -> 사건 목록과 율 함수."""

    def __init__(self, params: EpiParams, regions: RegionSet, drivers: Drivers | None = None,
                 h_spec: dict | None = None, rho_ref: str | float = "pop_weighted_mean"):
        self.params = params
        self.regions = regions
        self.drivers = drivers or Drivers(regions.K)
        if self.drivers.K != regions.K:
            raise ValueError("drivers 의 지역 수가 regions 와 다르다")
        self.h_spec = h_spec or {"form": "constant"}
        self.rho_ref_mode = rho_ref
        self.rho_ref = regions.rho_ref(rho_ref)
        self.h_values = np.asarray(F.build_h(self.h_spec)(regions.density, self.rho_ref), dtype=float)
        self.layout = Layout(regions.K, params.M)
        self.channels = build_channels(params, regions, self.layout)

    def with_params(self, **kw) -> "ReactionSystem":
        return ReactionSystem(self.params.with_(**kw), self.regions, self.drivers,
                              self.h_spec, self.rho_ref_mode)

    # ---------------------------------------------------------------- 1.3절

    def contact_rate(self, t: float) -> np.ndarray:
        """c_i(t) = c0 h(rho_i) (1 - u_i(t))."""
        return self.params.c0 * self.h_values * (1.0 - self.drivers.u(t))

    def force_of_infection(self, X: np.ndarray, t: float) -> np.ndarray:
        """Lambda_i = g_i c_i sum_j C_ij [sum_k T(k) I_{k,j}] / N_j.  (N_j = 0 이면 그 항은 0)"""
        L = self.layout
        N = L.alive(X)
        Ieff = X[:, L.I_slice] @ self.params.T_by_n
        ratio = np.divide(Ieff, N, out=np.zeros_like(Ieff), where=N > 0)
        return self.drivers.g(t) * self.contact_rate(t) * (self.regions.contact @ ratio)

    # ---------------------------------------------------------------- 1.5절

    def propensities(self, X: np.ndarray, t: float) -> np.ndarray:
        ch = self.channels
        lam = self.force_of_infection(X, t)
        x = X.reshape(-1)
        return (ch.const + ch.susc * lam[ch.region]) * x[ch.src]

    def apply(self, X: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """사건 j 를 counts[j] 번 적용한 새 상태 (counts 는 실수여도 된다: ODE/SDE 증분)."""
        ch, n = self.channels, self.layout.size
        delta = np.bincount(ch.dst, counts, minlength=n) - np.bincount(ch.src, counts, minlength=n)
        return X + delta.reshape(X.shape)

    def drift(self, X: np.ndarray, t: float) -> np.ndarray:
        """dX/dt = sum_j nu_j a_j(X)  — 1.4절 ODE 의 우변."""
        return self.apply(np.zeros_like(X), self.propensities(X, t))
