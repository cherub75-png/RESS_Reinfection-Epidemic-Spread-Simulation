"""화학 랑주뱅 방정식 (1.5절 SDE), Euler-Maruyama.

  dX = sum_j nu_j a_j(X) dt + sum_j nu_j sqrt(a_j(X)) dW_j

한 단계 h 동안 사건 j 의 증분은 inc_j = a_j h + sqrt(a_j h) xi_j (xi_j ~ N(0,1), 서로 독립)이다.
이동은 (i, j, c) 쌍마다 독립 잡음을 둔다. 그래야 원래 방정식의 공분산이 그대로 유지된다.

음수 처리 (1-C 승인: 사건 단위 절단)
  1) inc_j < 0 이면 0 으로 자른다 (사건이 거꾸로 흐르지 않음).
  2) 원천 구획 s 에서 나가는 증분의 합이 X_s 를 넘으면, s 에서 나가는 증분을 모두 X_s / 합 배로 줄인다.
  모든 증분이 한 구획에서 다른 구획으로 옮기기만 하므로 보존이 정확하고(부동소수 반올림 제외), 음수가 생기지 않는다.
  1), 2) 의 횟수와 양은 meta["truncation"] 에 기록한다.
  주의: 1) 은 a_j h 가 작을 때(소규모 수) 평균을 키우는 편향을 만든다. 하이브리드에서는 그 영역을 CTMC 가 맡는다.
"""

from __future__ import annotations

import time

import numpy as np
from numba import njit

from ..model.reactions import ReactionSystem
from ._kernels import force_of_infection
from .ctmc import kernel_args, mobility_args
from .ode import _segments
from .result import DEFAULT_LAST_BIN_WARN, Trajectory, check_last_bin
from .tauleap import _per_capita, _seed, omega_values, seed_from

# stats 색인
S_STEPS, S_NINC, S_NCLIP, S_CLIPMASS, S_NSCALE, S_SCALEMASS, S_FLOW = range(7)


@njit(cache=True)
def _sde_step(x, h, src, dst, kc, K, ncomp, alive_end, indptr, indices, omvals,
              inc, minc, outflow, scale, delta, stats):
    n = x.size
    for s in range(n):
        outflow[s] = 0.0
        delta[s] = 0.0
    sq = np.sqrt(h)
    for j in range(src.size):
        mean = kc[j] * x[src[j]] * h
        v = 0.0
        if mean > 0.0:
            stats[S_NINC] += 1.0
            v = mean + np.sqrt(mean) * np.random.standard_normal()
            if v < 0.0:
                stats[S_NCLIP] += 1.0
                stats[S_CLIPMASS] += -v
                v = 0.0
        inc[j] = v
        outflow[src[j]] += v
    q = 0
    for i in range(K):
        for c in range(alive_end):
            s = i * ncomp + c
            for k in range(indptr[i], indptr[i + 1]):
                mean = omvals[k] * x[s] * h
                v = 0.0
                if mean > 0.0:
                    stats[S_NINC] += 1.0
                    v = mean + np.sqrt(mean) * np.random.standard_normal()
                    if v < 0.0:
                        stats[S_NCLIP] += 1.0
                        stats[S_CLIPMASS] += -v
                        v = 0.0
                minc[q] = v
                q += 1
                outflow[s] += v
    for s in range(n):
        if outflow[s] > x[s]:
            stats[S_NSCALE] += 1.0
            stats[S_SCALEMASS] += outflow[s] - x[s]
            scale[s] = x[s] / outflow[s] if outflow[s] > 0.0 else 0.0
        else:
            scale[s] = 1.0
    for j in range(src.size):
        v = inc[j] * scale[src[j]]
        delta[src[j]] -= v
        delta[dst[j]] += v
        stats[S_FLOW] += v
    q = 0
    for i in range(K):
        for c in range(alive_end):
            s = i * ncomp + c
            for k in range(indptr[i], indptr[i + 1]):
                v = minc[q] * scale[s]
                q += 1
                delta[s] -= v
                delta[indices[k] * ncomp + c] += v
                stats[S_FLOW] += v
    for s in range(n):
        x[s] += delta[s]
        if x[s] < 0.0:              # 비례 축소 뒤 반올림으로 생긴 -1e-16 수준만 해당
            x[s] = 0.0
    stats[S_STEPS] += 1.0


@njit(cache=True)
def _sde_segment(x, t, t_stop, out_times, out, k_out,
                 src, dst, const, susc, region, C, Tn, gc, K, ncomp, I0, M, alive_end,
                 indptr, indices, omvals, dt, lam, kc, inc, minc, outflow, scale, delta, stats):
    n_out = out_times.size
    while True:
        while k_out < n_out and out_times[k_out] <= t + 1e-9:
            out[k_out, :] = x
            k_out += 1
        if t >= t_stop - 1e-12:
            return t_stop, k_out
        target = t_stop
        if k_out < n_out and out_times[k_out] < target:
            target = out_times[k_out]
        if t + dt >= target - 1e-12:
            h = target - t
            t_new = target
        else:
            h = dt
            t_new = t + dt
        force_of_infection(x, K, ncomp, I0, M, alive_end, Tn, C, gc, lam)
        _per_capita(src, const, susc, region, lam, kc)
        _sde_step(x, h, src, dst, kc, K, ncomp, alive_end, indptr, indices, omvals,
                  inc, minc, outflow, scale, delta, stats)
        t = t_new


def simulate_sde(system: ReactionSystem, X0: np.ndarray, days: float, output_dt: float = 1.0,
                 seed=None, dt: float = 0.05, t0: float = 0.0,
                 last_bin_warn: float = DEFAULT_LAST_BIN_WARN) -> Trajectory:
    if np.any(X0 < 0):
        raise ValueError("SDE 초기 상태는 음이 아니어야 한다")
    s32, seed_meta = seed_from(seed)
    shape = X0.shape
    n_out = int(np.floor(days / output_dt + 1e-9)) + 1
    grid = t0 + output_dt * np.arange(n_out)
    out = np.full((n_out, shape[0] * shape[1]), np.nan)
    x = X0.reshape(-1).astype(np.float64).copy()
    src, dst, const, susc, region, C, Tn, K, ncomp, E0, I0, M, alive_end = kernel_args(system)
    _, indptr, indices, _ = mobility_args(system)
    omvals = omega_values(system)
    n = x.size
    lam, kc, inc = np.empty(K), np.empty(src.size), np.empty(src.size)
    minc = np.empty(indices.size * alive_end)
    outflow, scale, delta = np.empty(n), np.empty(n), np.empty(n)
    stats = np.zeros(7)

    _seed(s32)
    t, k_out = t0, 0
    wall = time.perf_counter()
    for a, b in _segments(system, t0, t0 + days):
        gc = np.ascontiguousarray(system.drivers.g(a) * system.contact_rate(a), dtype=float)
        t, k_out = _sde_segment(x, t, b, grid, out, k_out, src, dst, const, susc, region, C, Tn, gc,
                                K, ncomp, I0, M, alive_end, indptr, indices, omvals, float(dt),
                                lam, kc, inc, minc, outflow, scale, delta, stats)
    wall = time.perf_counter() - wall
    X = out.reshape(n_out, *shape)
    pop0 = X0.sum()
    pop = X.reshape(n_out, -1).sum(axis=1)
    ninc = max(stats[S_NINC], 1.0)
    flow = max(stats[S_FLOW], 1e-300)
    meta = {"dt": dt, "steps": int(stats[S_STEPS]), "wall_seconds": wall, **seed_meta,
            "truncation": {"clipped_increment_fraction": stats[S_NCLIP] / ninc,
                           "clipped_mass_over_flow": stats[S_CLIPMASS] / flow,
                           "scaled_source_events": int(stats[S_NSCALE]),
                           "scaled_mass_over_flow": stats[S_SCALEMASS] / flow},
            "max_rel_population_error": float(np.max(np.abs(pop - pop0)) / pop0) if pop0 > 0 else 0.0,
            "min_value": float(X.min())}
    tr = Trajectory(grid, X, system.layout, "sde", meta)
    check_last_bin(tr, last_bin_warn)
    return tr
