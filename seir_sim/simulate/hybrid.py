"""하이브리드: 정확한 CTMC + 이항 tau-leaping (1.5절, 1-C 승인 분할 방식).

지역 i 의 상태(mode)는 E+I_i = sum_n (E_{n,i} + I_{n,i}) 로 정한다. 히스테리시스를 둔다.
  exact -> leap : E+I_i >= threshold_up   (기본 100)
  leap  -> exact: E+I_i <  threshold_down (기본 50)
  처음 상태: E+I_i < threshold_up 이면 exact

사건 분할
  - 감염 관련 사건 (INFECT_S, REINF_P, REINF_W, PROGRESS, RECOVER, DIE 와 E·I 구획의 이동):
      exact 지역이면 CTMC(Gillespie), leap 지역이면 이항 tau-leap
  - S·R 만 관련된 사건 (WANE 과 S, R^P, R^W 구획의 이동): 항상 이항 tau-leap
    (인원이 많아 정확한 모의가 불필요하게 비싸고, 소멸 확률에 영향을 주지 않는다)

한 단계 [t, t + tau)
  1) tau 선택: leap 대상 사건만 보고 CGP 방식 (eps), tau_max, 출력 시각, g/u 변화 시각으로 자른다.
  2) leap 대상 사건을 단계 시작 상태로 한 번에 적용한다.
  3) exact 대상 사건을 같은 구간에서 Gillespie 로 진행한다. 율은 사건마다 다시 계산한다.
     leap 지역의 감염자는 2) 의 결과 값으로 고정된다 (tau-leap 과 같은 차수의 근사).
  leap 이 먼저 단계 시작 인원에서 빼고, CTMC 는 남아 있는 사람만 옮기므로 음수가 생기지 않고 보존이 정확하다.
  상태 전환은 단계 끝에서만 판정한다.
"""

from __future__ import annotations

import time

import numpy as np
from numba import njit

from ..model.reactions import WANE, ReactionSystem
from ._kernels import force_of_infection, pick_destination
from .ctmc import kernel_args, mobility_args
from .ode import _segments
from .result import DEFAULT_LAST_BIN_WARN, Trajectory, check_last_bin
from .tauleap import _per_capita, _seed, leap, omega_values, seed_from, select_tau, source_groups

# stats 색인
H_STEPS, H_EXACT_EVENTS, H_SWITCH_UP, H_SWITCH_DOWN, H_MIN_TAU, H_EXACT_REGION_STEPS = range(6)


@njit(cache=True)
def _region_ei(x, i, ncomp, E0, I0, M):
    b = i * ncomp
    s = 0.0
    for k in range(M):
        s += x[b + E0 + k] + x[b + I0 + k]
    return s


@njit(cache=True)
def _update_modes(x, exact, K, ncomp, E0, I0, M, up, down, stats):
    changed = False
    for i in range(K):
        ei = _region_ei(x, i, ncomp, E0, I0, M)
        if exact[i] and ei >= up:
            exact[i] = False
            changed = True
            stats[H_SWITCH_UP] += 1.0
        elif (not exact[i]) and ei < down:
            exact[i] = True
            changed = True
            stats[H_SWITCH_DOWN] += 1.0
    return changed


@njit(cache=True)
def _build_masks(exact, region, is_epi, comp_is_ei, K, ncomp, alive_end, ch_mask, mob_mask, ex_idx):
    """leap 마스크와 exact 사건 목록. exact 사건 수를 반환한다."""
    n_ex = 0
    for j in range(region.size):
        if is_epi[j] and exact[region[j]]:
            ch_mask[j] = False
            ex_idx[n_ex] = j
            n_ex += 1
        else:
            ch_mask[j] = True
    for i in range(K):
        for c in range(alive_end):
            mob_mask[i * ncomp + c] = not (comp_is_ei[c] and exact[i])
    return n_ex


@njit(cache=True)
def _ssa_exact(x, t, t_end, ex_idx, n_ex, src, dst, const, susc, region, C, Tn, gc,
               K, ncomp, E0, I0, M, alive_end, exact, comp_is_ei, out_rate, indptr, indices, cumprob,
               lam, a, mob):
    """exact 사건만 [t, t_end) 동안 Gillespie 로 진행한다. 사건 수를 반환한다."""
    events = 0
    any_exact = False
    for i in range(K):
        if exact[i]:
            any_exact = True
            break
    if not any_exact:
        return 0
    while True:
        force_of_infection(x, K, ncomp, I0, M, alive_end, Tn, C, gc, lam)
        a_loc = 0.0
        for q in range(n_ex):
            j = ex_idx[q]
            v = (const[j] + susc[j] * lam[region[j]]) * x[src[j]]
            a[q] = v
            a_loc += v
        a_mob = 0.0
        for i in range(K):
            v = 0.0
            if exact[i] and out_rate[i] > 0.0:
                v = out_rate[i] * _region_ei(x, i, ncomp, E0, I0, M)
            mob[i] = v
            a_mob += v
        a0 = a_loc + a_mob
        if a0 <= 0.0:
            return events
        t = t - np.log(1.0 - np.random.random()) / a0
        if t >= t_end:
            return events
        target = np.random.random() * a0
        if target < a_loc:
            cum = 0.0
            jq = -1
            for q in range(n_ex):
                cum += a[q]
                if cum > target:
                    jq = q
                    break
            if jq < 0:
                for q in range(n_ex - 1, -1, -1):
                    if a[q] > 0.0:
                        jq = q
                        break
            j = ex_idx[jq]
            x[src[j]] -= 1.0
            x[dst[j]] += 1.0
        else:
            target -= a_loc
            cum = 0.0
            ii = -1
            for i in range(K):
                cum += mob[i]
                if cum > target:
                    ii = i
                    break
            if ii < 0:
                for i in range(K - 1, -1, -1):
                    if mob[i] > 0.0:
                        ii = i
                        break
            jd = pick_destination(ii, np.random.random(), indptr, indices, cumprob)
            b = ii * ncomp
            tot = _region_ei(x, ii, ncomp, E0, I0, M)
            tc = np.random.random() * tot
            cum = 0.0
            cc = -1
            for c in range(alive_end):
                if comp_is_ei[c]:
                    cum += x[b + c]
                    if cum > tc:
                        cc = c
                        break
            if cc < 0:
                for c in range(alive_end - 1, -1, -1):
                    if comp_is_ei[c] and x[b + c] > 0.0:
                        cc = c
                        break
            x[b + cc] -= 1.0
            x[jd * ncomp + cc] += 1.0
        events += 1


@njit(cache=True)
def _hybrid_segment(x, t, t_stop, out_times, out, k_out,
                    src, dst, const, susc, region, C, Tn, gc, K, ncomp, E0, I0, M, alive_end,
                    out_rate, indptr, indices, cumprob, omvals, grp_ptr, grp_ch,
                    eps, tau_max, up, down, exact, is_epi, comp_is_ei, ch_mask, mob_mask, ex_idx,
                    lam, kc, mu, s2, delta, a_ex, mob, ei_low, ei_high, stats):
    n_out = out_times.size
    n_ex = _build_masks(exact, region, is_epi, comp_is_ei, K, ncomp, alive_end, ch_mask, mob_mask, ex_idx)
    check_ei = ei_low >= 0.0 or ei_high < np.inf
    while True:
        while k_out < n_out and out_times[k_out] <= t + 1e-9:
            out[k_out, :] = x
            k_out += 1
        if check_ei:
            ei = 0.0
            for i in range(K):
                ei += _region_ei(x, i, ncomp, E0, I0, M)
            if ei <= ei_low or ei >= ei_high:
                return t, k_out, True
        if t >= t_stop - 1e-12:
            return t_stop, k_out, False
        if _update_modes(x, exact, K, ncomp, E0, I0, M, up, down, stats):
            n_ex = _build_masks(exact, region, is_epi, comp_is_ei, K, ncomp, alive_end,
                                ch_mask, mob_mask, ex_idx)
        force_of_infection(x, K, ncomp, I0, M, alive_end, Tn, C, gc, lam)
        _per_capita(src, const, susc, region, lam, kc)
        tau = select_tau(x, src, dst, kc, ch_mask, K, ncomp, alive_end, out_rate, indptr, indices,
                         omvals, mob_mask, eps, mu, s2)
        tau = min(tau, tau_max)
        target = t_stop
        if k_out < n_out and out_times[k_out] < target:
            target = out_times[k_out]
        if t + tau >= target - 1e-12:
            tau = target - t
            t_new = target
        else:
            t_new = t + tau
        leap(x, tau, grp_ptr, grp_ch, dst, kc, ch_mask, K, ncomp, alive_end,
             out_rate, indptr, indices, omvals, mob_mask, delta)
        stats[H_EXACT_EVENTS] += _ssa_exact(x, t, t_new, ex_idx, n_ex, src, dst, const, susc, region,
                                            C, Tn, gc, K, ncomp, E0, I0, M, alive_end, exact, comp_is_ei,
                                            out_rate, indptr, indices, cumprob, lam, a_ex, mob)
        stats[H_STEPS] += 1.0
        stats[H_MIN_TAU] = min(stats[H_MIN_TAU], tau)
        for i in range(K):
            if exact[i]:
                stats[H_EXACT_REGION_STEPS] += 1.0
        t = t_new


def simulate_hybrid(system: ReactionSystem, X0: np.ndarray, days: float, output_dt: float = 1.0,
                    seed=None, eps: float = 0.01, tau_max: float = 1.0, threshold_up: float = 100.0,
                    threshold_down: float = 50.0, t0: float = 0.0, stop_EI_at_or_below: float = -1.0,
                    stop_EI_at_or_above: float = np.inf,
                    last_bin_warn: float = DEFAULT_LAST_BIN_WARN) -> Trajectory:
    if not np.allclose(X0, np.round(X0)) or np.any(X0 < 0):
        raise ValueError("하이브리드 초기 상태는 음이 아닌 정수여야 한다")
    if threshold_down > threshold_up:
        raise ValueError("threshold_down <= threshold_up 이어야 한다")
    s32, seed_meta = seed_from(seed)
    L = system.layout
    shape = X0.shape
    n_out = int(np.floor(days / output_dt + 1e-9)) + 1
    grid = t0 + output_dt * np.arange(n_out)
    out = np.full((n_out, shape[0] * shape[1]), np.nan)
    x = np.round(X0).reshape(-1).astype(np.float64).copy()
    src, dst, const, susc, region, C, Tn, K, ncomp, E0, I0, M, alive_end = kernel_args(system)
    out_rate, indptr, indices, cumprob = mobility_args(system)
    omvals = omega_values(system)
    grp_ptr, grp_ch = source_groups(system)
    n = x.size
    is_epi = system.channels.kind != WANE
    comp_is_ei = np.zeros(ncomp, dtype=np.bool_)
    comp_is_ei[L.E_slice] = True
    comp_is_ei[L.I_slice] = True
    ei0 = X0[:, L.E_slice].sum(axis=1) + X0[:, L.I_slice].sum(axis=1)
    exact = (ei0 < threshold_up).astype(np.bool_)
    ch_mask = np.ones(src.size, dtype=np.bool_)
    mob_mask = np.ones(n, dtype=np.bool_)
    ex_idx = np.zeros(src.size, dtype=np.int64)
    lam, kc = np.empty(K), np.empty(src.size)
    mu, s2, delta = np.empty(n), np.empty(n), np.empty(n)
    a_ex, mob = np.empty(src.size), np.empty(K)
    stats = np.array([0.0, 0.0, 0.0, 0.0, np.inf, 0.0])

    _seed(s32)
    t, k_out, stopped_at = t0, 0, None
    wall = time.perf_counter()
    for a, b in _segments(system, t0, t0 + days):
        gc = np.ascontiguousarray(system.drivers.g(a) * system.contact_rate(a), dtype=float)
        t, k_out, stopped = _hybrid_segment(
            x, t, b, grid, out, k_out, src, dst, const, susc, region, C, Tn, gc, K, ncomp, E0, I0, M,
            alive_end, out_rate, indptr, indices, cumprob, omvals, grp_ptr, grp_ch, float(eps),
            float(tau_max), float(threshold_up), float(threshold_down), exact, is_epi, comp_is_ei,
            ch_mask, mob_mask, ex_idx, lam, kc, mu, s2, delta, a_ex, mob,
            float(stop_EI_at_or_below), float(stop_EI_at_or_above), stats)
        if stopped:
            stopped_at = t
            break
    wall = time.perf_counter() - wall
    X = out.reshape(n_out, *shape)
    valid = ~np.isnan(X).any(axis=(1, 2))
    pop = X[valid].reshape(valid.sum(), -1).sum(axis=1)
    meta = {"steps": int(stats[H_STEPS]), "exact_events": int(stats[H_EXACT_EVENTS]),
            "switches_to_leap": int(stats[H_SWITCH_UP]), "switches_to_exact": int(stats[H_SWITCH_DOWN]),
            "min_tau": float(stats[H_MIN_TAU]),
            "exact_region_step_fraction": float(stats[H_EXACT_REGION_STEPS] / max(stats[H_STEPS] * K, 1.0)),
            "eps": eps, "tau_max": tau_max, "threshold_up": threshold_up, "threshold_down": threshold_down,
            "wall_seconds": wall, **seed_meta, "stopped_at": stopped_at,
            "final_state": x.reshape(shape).copy(),
            "max_abs_population_error": float(np.max(np.abs(pop - X0.sum()))) if pop.size else 0.0,
            "min_value": float(np.nanmin(X))}
    tr = Trajectory(grid, X, system.layout, "hybrid", meta)
    if stopped_at is None:
        check_last_bin(tr, last_bin_warn)
    return tr
