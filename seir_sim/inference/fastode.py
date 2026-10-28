"""추정용 고정 간격 RK4 적분기 (공통 사건 목록과 같은 식, numba).

1.4절 ODE 를 하루 단위 입력 gc[d, i] = g_i(d) c_i(d) 로 적분한다 (하루 안에서는 상수: Drivers 의 구간별 상수와 같음).
상태에 두 누적량을 붙여 하루 단위 흐름을 함께 얻는다.
  inf_i : 감염 유입 (INFECT_S + REINF_P + REINF_W 사건 흐름의 적분)
  ons_i : 발병 (E -> I, PROGRESS 사건 흐름의 적분)
사망은 D 구획의 하루 차이로 얻는다.

엔진의 integrate_ode (DOP853, 적응 간격) 와의 일치는 tests/test_inference.py 에서 확인한다.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from ..model.reactions import INFECT_S, PROGRESS, REINF_P, REINF_W, ReactionSystem
from ..simulate._kernels import force_of_infection
from ..simulate.ctmc import kernel_args, mobility_args
from ..simulate.tauleap import omega_values


@njit(cache=True)
def _rhs(x, gc, src, dst, const, susc, region, C, Tn, K, ncomp, I0, M, alive_end,
         out_rate, indptr, indices, omvals, is_inf, is_ons, lam, dx, finf, fons):
    n = x.size
    for s in range(n):
        dx[s] = 0.0
    for i in range(K):
        finf[i] = 0.0
        fons[i] = 0.0
    force_of_infection(x, K, ncomp, I0, M, alive_end, Tn, C, gc, lam)
    for j in range(src.size):
        a = (const[j] + susc[j] * lam[region[j]]) * x[src[j]]
        dx[src[j]] -= a
        dx[dst[j]] += a
        if is_inf[j]:
            finf[region[j]] += a
        elif is_ons[j]:
            fons[region[j]] += a
    for i in range(K):
        if out_rate[i] == 0.0:
            continue
        for c in range(alive_end):
            s = i * ncomp + c
            v = x[s]
            if v == 0.0:
                continue
            dx[s] -= out_rate[i] * v
            for k in range(indptr[i], indptr[i + 1]):
                dx[indices[k] * ncomp + c] += omvals[k] * v


@njit(cache=True)
def _integrate(x0, gc_days, nsub, src, dst, const, susc, region, C, Tn, K, ncomp, I0, M, alive_end, D,
               out_rate, indptr, indices, omvals, is_inf, is_ons, inf_out, ons_out, death_out, x_end):
    n = x0.size
    x = x0.copy()
    lam = np.empty(K)
    k1, k2, k3, k4, xt = np.empty(n), np.empty(n), np.empty(n), np.empty(n), np.empty(n)
    f1i, f2i, f3i, f4i = np.empty(K), np.empty(K), np.empty(K), np.empty(K)
    f1o, f2o, f3o, f4o = np.empty(K), np.empty(K), np.empty(K), np.empty(K)
    h = 1.0 / nsub
    days = gc_days.shape[0]
    for d in range(days):
        gc = gc_days[d]
        d_before = np.empty(K)
        for i in range(K):
            d_before[i] = x[i * ncomp + D]
            inf_out[d, i] = 0.0
            ons_out[d, i] = 0.0
        for _ in range(nsub):
            _rhs(x, gc, src, dst, const, susc, region, C, Tn, K, ncomp, I0, M, alive_end,
                 out_rate, indptr, indices, omvals, is_inf, is_ons, lam, k1, f1i, f1o)
            for s in range(n):
                xt[s] = x[s] + 0.5 * h * k1[s]
            _rhs(xt, gc, src, dst, const, susc, region, C, Tn, K, ncomp, I0, M, alive_end,
                 out_rate, indptr, indices, omvals, is_inf, is_ons, lam, k2, f2i, f2o)
            for s in range(n):
                xt[s] = x[s] + 0.5 * h * k2[s]
            _rhs(xt, gc, src, dst, const, susc, region, C, Tn, K, ncomp, I0, M, alive_end,
                 out_rate, indptr, indices, omvals, is_inf, is_ons, lam, k3, f3i, f3o)
            for s in range(n):
                xt[s] = x[s] + h * k3[s]
            _rhs(xt, gc, src, dst, const, susc, region, C, Tn, K, ncomp, I0, M, alive_end,
                 out_rate, indptr, indices, omvals, is_inf, is_ons, lam, k4, f4i, f4o)
            for s in range(n):
                x[s] += h / 6.0 * (k1[s] + 2.0 * k2[s] + 2.0 * k3[s] + k4[s])
            for i in range(K):
                inf_out[d, i] += h / 6.0 * (f1i[i] + 2.0 * f2i[i] + 2.0 * f3i[i] + f4i[i])
                ons_out[d, i] += h / 6.0 * (f1o[i] + 2.0 * f2o[i] + 2.0 * f3o[i] + f4o[i])
        for i in range(K):
            death_out[d, i] = x[i * ncomp + D] - d_before[i]
    for s in range(n):
        x_end[s] = x[s]


class FastODE:
    """ReactionSystem 의 사건 목록·매개변수로 하루 단위 흐름을 계산한다. 매개변수가 바뀌면 새로 만든다."""

    def __init__(self, system: ReactionSystem, nsub: int = 4):
        self.system = system
        self.nsub = nsub
        (self.src, self.dst, self.const, self.susc, self.region, self.C, self.Tn,
         self.K, self.ncomp, _, self.I0, self.M, self.alive_end) = kernel_args(system)
        self.out_rate, self.indptr, self.indices, _ = mobility_args(system)
        self.omvals = omega_values(system)
        kind = system.channels.kind
        self.is_inf = np.isin(kind, (INFECT_S, REINF_P, REINF_W))
        self.is_ons = kind == PROGRESS
        self.D = system.layout.D
        self.base_c = system.params.c0 * system.h_values          # c0 h(rho_i)

    def run(self, X0: np.ndarray, gc_days: np.ndarray):
        """gc_days [days, K] = g_i c0 h_i (1 - u_i) 를 날짜별로 준다. (infections, onsets, deaths [days, K], X_end) 반환."""
        days = gc_days.shape[0]
        inf = np.empty((days, self.K))
        ons = np.empty((days, self.K))
        dea = np.empty((days, self.K))
        xe = np.empty(X0.size)
        _integrate(np.ascontiguousarray(X0.reshape(-1), dtype=float), np.ascontiguousarray(gc_days, dtype=float),
                   int(self.nsub), self.src, self.dst, self.const, self.susc, self.region, self.C, self.Tn,
                   self.K, self.ncomp, self.I0, self.M, self.alive_end, self.D, self.out_rate, self.indptr,
                   self.indices, self.omvals, self.is_inf, self.is_ons, inf, ons, dea, xe)
        return inf, ons, dea, xe.reshape(X0.shape)

    def gc_from_u(self, u_days: np.ndarray, g_days: np.ndarray | None = None) -> np.ndarray:
        """u_days [days, K] (0 <= u < 1) -> gc_days."""
        g = 1.0 if g_days is None else g_days
        return g * self.base_c[None, :] * (1.0 - u_days)
