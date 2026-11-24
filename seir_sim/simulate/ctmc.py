"""정확한 CTMC 표본 (1.5절): Gillespie direct method.

  tau = -ln(u1) / a0,   사건 j 를 확률 a_j / a0 로 선택,   X <- X + nu_j

사건 목록과 율은 공통 ReactionSystem 의 것을 그대로 쓴다 (numba 커널로 같은 식을 계산).
g_i(t), u_i(t) 는 구간별 상수이다. 다음 사건 시각이 구간 끝을 넘으면 구간 끝으로 이동한 뒤
새 율로 대기 시간을 다시 뽑는다. 지수분포의 무기억성 때문에 이 방법은 정확하다.

난수: numpy.random.Generator(PCG64, SeedSequence)에서 균등난수를 묶음으로 받아 커널에 넘긴다.
따라서 같은 시드면 같은 경로가 나온다. 사용한 시드는 meta 에 기록한다.
"""

from __future__ import annotations

import time

import numpy as np
from numba import njit

from ..model.reactions import ReactionSystem
from ._kernels import force_of_infection, mobility_propensities, pick_destination, propensities
from .ode import _segments
from .result import DEFAULT_LAST_BIN_WARN, Trajectory, check_last_bin

_DONE, _NEED_RANDOM, _STOPPED = 0, 1, 2


@njit(cache=True)
def _ssa_segment(x, t, t_stop, out_times, out, k_out,
                 src, dst, const, susc, region, C, Tn, gc,
                 K, ncomp, E0, I0, M, alive_end,
                 out_rate, indptr, indices, cumprob,
                 u, u_pos, ei_low, ei_high, a, lam, mob):
    n_out = out_times.size
    events = 0
    check_ei = ei_low >= 0.0 or ei_high < np.inf
    while True:
        if u_pos + 4 > u.size:
            return t, k_out, u_pos, events, _NEED_RANDOM
        if check_ei:
            ei = 0.0
            for i in range(K):
                b = i * ncomp
                for k in range(M):
                    ei += x[b + E0 + k] + x[b + I0 + k]
            if ei <= ei_low or ei >= ei_high:
                return t, k_out, u_pos, events, _STOPPED

        force_of_infection(x, K, ncomp, I0, M, alive_end, Tn, C, gc, lam)
        a_loc = propensities(x, src, const, susc, region, lam, a)
        a0 = a_loc + mobility_propensities(x, K, ncomp, alive_end, out_rate, mob)
        if a0 > 0.0:
            t_next = t - np.log(1.0 - u[u_pos]) / a0
        else:
            t_next = np.inf
        u_pos += 1

        # 상태는 [t, t_next) 동안 일정하다
        if t_next >= t_stop:
            while k_out < n_out and out_times[k_out] <= t_stop:
                out[k_out, :] = x
                k_out += 1
            return t_stop, k_out, u_pos, events, _DONE
        while k_out < n_out and out_times[k_out] < t_next:
            out[k_out, :] = x
            k_out += 1

        target = u[u_pos] * a0          # [0, a0)
        u_pos += 1
        if target < a_loc:
            cum = 0.0
            j = -1
            for jj in range(src.size):
                cum += a[jj]
                if cum > target:
                    j = jj
                    break
            if j < 0:                    # 반올림 대비: 마지막 양의 율
                for jj in range(src.size - 1, -1, -1):
                    if a[jj] > 0.0:
                        j = jj
                        break
            x[src[j]] -= 1.0
            x[dst[j]] += 1.0
        else:
            # 이동: 지역 i (율 out_i N_i), 도착지 j (omega_ij/out_i), 구획 c (X_ic/N_i)
            target -= a_loc
            cum = 0.0
            i = -1
            for ii in range(K):
                cum += mob[ii]
                if cum > target:
                    i = ii
                    break
            if i < 0:
                for ii in range(K - 1, -1, -1):
                    if mob[ii] > 0.0:
                        i = ii
                        break
            jdst = pick_destination(i, u[u_pos], indptr, indices, cumprob)
            u_pos += 1
            b = i * ncomp
            N = 0.0
            for c in range(alive_end):
                N += x[b + c]
            tc = u[u_pos] * N
            u_pos += 1
            cum = 0.0
            cc = -1
            for c in range(alive_end):
                cum += x[b + c]
                if cum > tc:
                    cc = c
                    break
            if cc < 0:
                for c in range(alive_end - 1, -1, -1):
                    if x[b + c] > 0.0:
                        cc = c
                        break
            x[b + cc] -= 1.0
            x[jdst * ncomp + cc] += 1.0
        t = t_next
        events += 1


def _seed_record(seed) -> tuple[np.random.Generator, dict]:
    if isinstance(seed, np.random.Generator):
        return seed, {"seed": "Generator supplied (state not recorded)"}
    ss = seed if isinstance(seed, np.random.SeedSequence) else np.random.SeedSequence(seed)
    return np.random.Generator(np.random.PCG64(ss)), {"seed_entropy": str(ss.entropy),
                                                      "seed_spawn_key": list(ss.spawn_key)}


def kernel_args(system: ReactionSystem):
    ch, L, reg = system.channels, system.layout, system.regions
    return (ch.src, ch.dst, ch.const, ch.susc, ch.region,
            np.ascontiguousarray(reg.contact, dtype=float), np.asarray(system.params.T_by_n, float),
            L.K, L.ncomp, L.E(1), L.I(1), L.M, L.D)


def mobility_args(system: ReactionSystem):
    mb = system.mobility
    return mb.out_rate.astype(float), mb.indptr, mb.indices, mb.cumprob.astype(float)


def simulate_ctmc(system: ReactionSystem, X0: np.ndarray, days: float, output_dt: float = 1.0,
                  seed=None, t0: float = 0.0, stop_EI_at_or_below: float = -1.0,
                  stop_EI_at_or_above: float = np.inf, chunk: int = 1 << 15,
                  last_bin_warn: float = DEFAULT_LAST_BIN_WARN) -> Trajectory:
    """CTMC 경로 하나. 정지 조건(E+I 합)에 걸리면 이후 출력은 NaN 이고 meta['stopped_at'] 에 시각을 남긴다."""
    if not np.allclose(X0, np.round(X0)) or np.any(X0 < 0):
        raise ValueError("CTMC 초기 상태는 음이 아닌 정수여야 한다")
    rng, seed_meta = _seed_record(seed)
    shape = X0.shape
    n_out = int(np.floor(days / output_dt + 1e-9)) + 1
    grid = t0 + output_dt * np.arange(n_out)
    out = np.full((n_out, shape[0] * shape[1]), np.nan)
    x = np.round(X0).reshape(-1).astype(np.float64).copy()
    src, dst, const, susc, region, C, Tn, K, ncomp, E0, I0, M, alive_end = kernel_args(system)
    out_rate, indptr, indices, cumprob = mobility_args(system)
    a = np.empty(src.size)
    lam = np.empty(K)
    mob = np.empty(K)

    u = rng.random(chunk)
    u_pos, k_out, events, stopped_at = 0, 0, 0, None
    t = t0
    wall = time.perf_counter()
    for seg_a, seg_b in _segments(system, t0, t0 + days):
        gc = np.ascontiguousarray(system.drivers.g(seg_a) * system.contact_rate(seg_a), dtype=float)
        while True:
            t, k_out, u_pos, ev, status = _ssa_segment(
                x, t, seg_b, grid, out, k_out, src, dst, const, susc, region, C, Tn, gc,
                K, ncomp, E0, I0, M, alive_end, out_rate, indptr, indices, cumprob, u, u_pos,
                float(stop_EI_at_or_below), float(stop_EI_at_or_above), a, lam, mob)
            events += ev
            if status == _NEED_RANDOM:
                chunk = min(chunk * 2, 1 << 22)
                u = rng.random(chunk)
                u_pos = 0
                continue
            if status == _STOPPED:
                stopped_at = t
            break
        if stopped_at is not None:
            break
    wall = time.perf_counter() - wall

    X = out.reshape(n_out, *shape)
    pop0 = X0.sum()
    valid = ~np.isnan(X).any(axis=(1, 2))
    pop = X[valid].reshape(valid.sum(), -1).sum(axis=1)
    meta = {"events": int(events), "wall_seconds": wall, **seed_meta,
            "stopped_at": stopped_at, "final_state": x.reshape(shape).copy(),
            "max_abs_population_error": float(np.max(np.abs(pop - pop0))) if pop.size else 0.0,
            "min_value": float(np.nanmin(X))}
    tr = Trajectory(grid, X, system.layout, "ctmc", meta)
    if stopped_at is None:
        check_last_bin(tr, last_bin_warn)
    return tr
