"""공통 사건 목록 (1.5절). ODE, SDE, CTMC, tau-leaping, hybrid 가 모두 이것 하나를 쓴다.

1.4절 ODE 의 모든 항은 "한 사람을 구획 src 에서 dst 로 옮기는" 사건이다.

(1) 지역 내 사건 j (Channels)
  a_j(X, t) = [ k_j + s_j * Lambda_{r_j}(X, t) ] * X[src_j],   nu_j = e_{dst_j} - e_{src_j}
  - k_j: 상수 율 (sigma, (1-f)gamma, f gamma, lambda)
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

(2) 지역 간 이동 (Mobility)
  1.3절의 M_i[X] 는 (i, j, 구획 c) 마다 율 omega_ij X_{i,c} 인 사건 X_{i,c} -> X_{j,c} 이다 (D 제외).
  같은 분포를 다음과 같이 합쳐서 다룬다 (포아송 과정의 중첩·분할, 1-C 승인).
    지역 i 에서 나가는 사건: 율 out_i * N_i, out_i = sum_j omega_ij
    도착지 j 는 확률 omega_ij / out_i, 구획 c 는 확률 X_{i,c} / N_i 로 고른다.
  CTMC 에서는 분포가 정확히 같다. ODE 에서는 drift 가 행렬 곱 omega^T X - out * X 로 같다.

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

KIND_NAMES = ("INFECT_S", "REINF_P", "REINF_W", "PROGRESS", "RECOVER", "DIE", "WANE")
INFECT_S, REINF_P, REINF_W, PROGRESS, RECOVER, DIE, WANE = range(len(KIND_NAMES))
INFECTION_KINDS = (INFECT_S, REINF_P, REINF_W)


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


@dataclass(frozen=True)
class Mobility:
    """omega 의 CSR 표현. 행 i: 도착지 indices[indptr[i]:indptr[i+1]], 누적확률 cumprob."""
    omega: np.ndarray        # [K, K]
    out_rate: np.ndarray     # [K]  out_i = sum_j omega_ij
    indptr: np.ndarray
    indices: np.ndarray
    cumprob: np.ndarray

    @classmethod
    def from_matrix(cls, omega: np.ndarray) -> "Mobility":
        K = omega.shape[0]
        out = omega.sum(axis=1)
        indptr = np.zeros(K + 1, dtype=np.int64)
        idx, cum = [], []
        for i in range(K):
            js = np.flatnonzero(omega[i] > 0)
            idx.append(js)
            c = np.cumsum(omega[i, js]) / out[i] if js.size else np.zeros(0)
            if c.size:
                c[-1] = 1.0
            cum.append(c)
            indptr[i + 1] = indptr[i] + js.size
        return cls(omega=np.ascontiguousarray(omega, dtype=float), out_rate=out, indptr=indptr,
                   indices=np.concatenate(idx).astype(np.int64) if K else np.zeros(0, np.int64),
                   cumprob=np.concatenate(cum) if K else np.zeros(0))

    @property
    def active(self) -> bool:
        return bool(np.any(self.out_rate > 0))


def build_channels(params: EpiParams, regions: RegionSet, layout: Layout) -> Channels:
    M, K, nc = params.M, regions.K, layout.ncomp
    P_next, f_n = params.P_next_by_n, params.f_by_n
    rows: list[tuple[int, int, float, float, int, int]] = []

    def add(i, src_c, dst_c, const, susc, kind):
        rows.append((i * nc + src_c, i * nc + dst_c, const, susc, i, kind))

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
        self.mobility = Mobility.from_matrix(regions.mobility)

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
        """지역 내 사건 율 a_j."""
        ch = self.channels
        lam = self.force_of_infection(X, t)
        x = X.reshape(-1)
        return (ch.const + ch.susc * lam[ch.region]) * x[ch.src]

    def mobility_propensities(self, X: np.ndarray) -> np.ndarray:
        """지역별 이동(나가는) 사건 율 out_i N_i."""
        return self.mobility.out_rate * self.layout.alive(X)

    def apply(self, X: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """지역 내 사건 j 를 counts[j] 번 적용한 새 상태 (실수 증분도 가능: ODE/SDE)."""
        ch, n = self.channels, self.layout.size
        delta = np.bincount(ch.dst, counts, minlength=n) - np.bincount(ch.src, counts, minlength=n)
        return X + delta.reshape(X.shape)

    def mobility_drift(self, X: np.ndarray) -> np.ndarray:
        """M_i[X_c] = sum_j omega_ji X_{j,c} - out_i X_{i,c}  (D 제외)."""
        D = self.layout.D
        out = np.zeros_like(X)
        if self.mobility.active:
            Xa = X[:, :D]
            out[:, :D] = self.mobility.omega.T @ Xa - self.mobility.out_rate[:, None] * Xa
        return out

    def drift(self, X: np.ndarray, t: float) -> np.ndarray:
        """dX/dt = sum_j nu_j a_j(X) + M[X]  — 1.4절 ODE 의 우변."""
        return self.apply(np.zeros_like(X), self.propensities(X, t)) + self.mobility_drift(X)
