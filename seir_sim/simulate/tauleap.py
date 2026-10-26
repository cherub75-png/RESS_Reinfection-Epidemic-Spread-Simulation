"""이항 tau-leaping (1-C 승인: 방식 (b)).

한 단계 [t, t + tau) 동안 율은 시작 시점 값으로 고정한다. 구획 s 의 사람(x_s 명)마다
"구획을 떠나는 1인당 율" 은 다음과 같다.
  K_s = sum_{j: src_j = s} k_j  +  out_i,   k_j = const_j + susc_j Lambda_{r_j},  out_i = sum_j omega_ij
  떠나는 인원        n_s ~ Binomial(x_s, 1 - exp(-K_s tau))
  사건별 배분        조건부 이항으로 순서대로 (확률 k_j / K_s, 이동은 out_i / K_s)
  이동의 도착지 배분  조건부 이항 (확률 omega_ij / out_i)
떠나는 인원을 단계 시작 시점의 인원에서 뽑으므로 음수가 생기지 않고, 모든 이동이 한 명 단위라 보존이 정확하다.
단계 안에서는 한 사람이 한 번만 움직인다. 이 차이가 O(tau) 의 근사 오차이다.

tau 선택 (Cao, Gillespie & Petzold 2006):
  tau = min_s { max(eps x_s / g, 1) / |mu_s|,  max(eps x_s / g, 1)^2 / sigma2_s }
  mu_s = sum_j nu_sj a_j (이동 포함),  sigma2_s = sum_j nu_sj^2 a_j,  g = 2 (모든 구획에 보수적으로 적용)
그다음 tau_max, 출력 시각, g/u 변화 시각으로 자른다. 기본 eps = 0.01 (1-C: 0.03 은 CTMC 대비 약 1% 체계적 편향).

난수: numba 내부 난수 생성기를 SeedSequence 에서 만든 32비트 시드로 매 실행 초기화한다 (meta 에 기록).
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

G_ORDER = 2.0


@njit(cache=True)
def _seed(s):
    np.random.seed(s)


@njit(cache=True)
def _per_capita(src, const, susc, region, lam, kc):
    for j in range(src.size):
        kc[j] = const[j] + susc[j] * lam[region[j]]


@njit(cache=True)
def select_tau(x, src, dst, kc, ch_mask, K, ncomp, alive_end, out_rate, indptr, indices, omvals,
               mob_mask, eps, mu, s2):
    """CGP tau. ch_mask / mob_mask 로 tau-leap 대상 사건만 고려한다 (하이브리드용)."""
    n = x.size
    for s in range(n):
        mu[s] = 0.0
        s2[s] = 0.0
    for j in range(src.size):
        if not ch_mask[j]:
            continue
        a = kc[j] * x[src[j]]
        mu[src[j]] -= a
        mu[dst[j]] += a
        s2[src[j]] += a
        s2[dst[j]] += a
    for i in range(K):
        for c in range(alive_end):
            s = i * ncomp + c
            if not mob_mask[s] or x[s] <= 0.0:
                continue
            a = out_rate[i] * x[s]
            mu[s] -= a
            s2[s] += a
            for k in range(indptr[i], indptr[i + 1]):
                d = indices[k] * ncomp + c
                b = omvals[k] * x[s]
                mu[d] += b
                s2[d] += b
    tau = np.inf
    for s in range(n):
        bound = max(eps * x[s] / G_ORDER, 1.0)
        if mu[s] != 0.0:
            tau = min(tau, bound / abs(mu[s]))
        if s2[s] > 0.0:
            tau = min(tau, bound * bound / s2[s])
    return tau


@njit(cache=True)
def leap(x, tau, grp_ptr, grp_ch, dst, kc, ch_mask, K, ncomp, alive_end,
         out_rate, indptr, indices, omvals, mob_mask, delta):
    """이항 leap 한 단계. 대상 사건(ch_mask, mob_mask)만 움직인다. 이동 횟수 합을 반환한다."""
    n = x.size
    for s in range(n):
        delta[s] = 0.0
    moved = 0.0
    for i in range(K):
        for c in range(alive_end):
            s = i * ncomp + c
            xs = x[s]
            if xs <= 0.0:
                continue
            Ks = 0.0
            for q in range(grp_ptr[s], grp_ptr[s + 1]):
                j = grp_ch[q]
                if ch_mask[j]:
                    Ks += kc[j]
            mob = out_rate[i] if mob_mask[s] else 0.0
            Ks += mob
            if Ks <= 0.0:
                continue
            nleave = np.random.binomial(int(xs), -np.expm1(-Ks * tau))
            if nleave == 0:
                continue
            moved += nleave
            delta[s] -= nleave
            rem = nleave
            rem_rate = Ks
            for q in range(grp_ptr[s], grp_ptr[s + 1]):
                j = grp_ch[q]
                if not ch_mask[j] or kc[j] <= 0.0:
                    continue
                if rem == 0:
                    break
                p = kc[j] / rem_rate
                m = rem if p >= 1.0 else np.random.binomial(rem, p)
                delta[dst[j]] += m
                rem -= m
                rem_rate -= kc[j]
            if rem > 0:
                if mob <= 0.0:          # 반올림으로 남은 경우: 마지막 대상 사건에 배정
                    for q in range(grp_ptr[s + 1] - 1, grp_ptr[s] - 1, -1):
                        j = grp_ch[q]
                        if ch_mask[j] and kc[j] > 0.0:
                            delta[dst[j]] += rem
                            rem = 0
                            break
                else:
                    rem_w = out_rate[i]
                    hi = indptr[i + 1]
                    for k in range(indptr[i], hi):
                        if rem == 0:
                            break
                        p = omvals[k] / rem_w
                        m = rem if (k == hi - 1 or p >= 1.0) else np.random.binomial(rem, p)
                        delta[indices[k] * ncomp + c] += m
                        rem -= m
                        rem_w -= omvals[k]
    for s in range(n):
        x[s] += delta[s]
    return moved


@njit(cache=True)
def _tau_segment(x, t, t_stop, out_times, out, k_out,
                 src, dst, const, susc, region, C, Tn, gc, K, ncomp, I0, M, alive_end,
                 out_rate, indptr, indices, omvals, grp_ptr, grp_ch,
                 eps, tau_max, lam, kc, mu, s2, delta, ch_mask, mob_mask, stats):
    n_out = out_times.size
    while True:
        while k_out < n_out and out_times[k_out] <= t + 1e-9:
            out[k_out, :] = x
            k_out += 1
        if t >= t_stop - 1e-12:
            return t_stop, k_out
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
        stats[0] += 1.0
        stats[1] = min(stats[1], tau)
        t = t_new


def source_groups(system: ReactionSystem):
    """지역 내 사건을 원천 구획별로 묶은 CSR (grp_ptr[s]:grp_ptr[s+1] 가 구획 s 의 사건들)."""
    src = system.channels.src
    order = np.argsort(src, kind="stable").astype(np.int64)
    counts = np.bincount(src, minlength=system.layout.size)
    grp_ptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    return grp_ptr, order


def omega_values(system: ReactionSystem) -> np.ndarray:
    mb = system.mobility
    vals = np.empty(mb.indices.size)
    for i in range(system.layout.K):
        lo, hi = mb.indptr[i], mb.indptr[i + 1]
        vals[lo:hi] = mb.omega[i, mb.indices[lo:hi]]
    return vals


def seed_from(seed) -> tuple[int, dict]:
    ss = seed if isinstance(seed, np.random.SeedSequence) else np.random.SeedSequence(seed)
    s32 = int(ss.generate_state(1, dtype=np.uint32)[0])
    return s32, {"seed_entropy": str(ss.entropy), "seed_spawn_key": list(ss.spawn_key),
                 "numba_seed_uint32": s32}


def simulate_tau(system: ReactionSystem, X0: np.ndarray, days: float, output_dt: float = 1.0,
                 seed=None, eps: float = 0.01, tau_max: float = 1.0, t0: float = 0.0,
                 last_bin_warn: float = DEFAULT_LAST_BIN_WARN) -> Trajectory:
    if not np.allclose(X0, np.round(X0)) or np.any(X0 < 0):
        raise ValueError("tau-leaping 초기 상태는 음이 아닌 정수여야 한다")
    s32, seed_meta = seed_from(seed)
    shape = X0.shape
    n_out = int(np.floor(days / output_dt + 1e-9)) + 1
    grid = t0 + output_dt * np.arange(n_out)
    out = np.full((n_out, shape[0] * shape[1]), np.nan)
    x = np.round(X0).reshape(-1).astype(np.float64).copy()
    src, dst, const, susc, region, C, Tn, K, ncomp, E0, I0, M, alive_end = kernel_args(system)
    out_rate, indptr, indices, _ = mobility_args(system)
    omvals = omega_values(system)
    grp_ptr, grp_ch = source_groups(system)
    n = x.size
    lam, kc = np.empty(K), np.empty(src.size)
    mu, s2, delta = np.empty(n), np.empty(n), np.empty(n)
    ch_mask = np.ones(src.size, dtype=np.bool_)
    mob_mask = np.ones(n, dtype=np.bool_)
    stats = np.array([0.0, np.inf])

    _seed(s32)
    t, k_out = t0, 0
    wall = time.perf_counter()
    for a, b in _segments(system, t0, t0 + days):
        gc = np.ascontiguousarray(system.drivers.g(a) * system.contact_rate(a), dtype=float)
        t, k_out = _tau_segment(x, t, b, grid, out, k_out, src, dst, const, susc, region, C, Tn, gc,
                                K, ncomp, I0, M, alive_end, out_rate, indptr, indices, omvals,
                                grp_ptr, grp_ch, float(eps), float(tau_max), lam, kc, mu, s2, delta,
                                ch_mask, mob_mask, stats)
    wall = time.perf_counter() - wall
    X = out.reshape(n_out, *shape)
    pop = X.reshape(n_out, -1).sum(axis=1)
    meta = {"steps": int(stats[0]), "min_tau": float(stats[1]), "mean_tau": days / max(stats[0], 1.0),
            "eps": eps, "tau_max": tau_max, "wall_seconds": wall, **seed_meta,
            "max_abs_population_error": float(np.max(np.abs(pop - X0.sum()))),
            "min_value": float(X.min())}
    tr = Trajectory(grid, X, system.layout, "tau", meta)
    check_last_bin(tr, last_bin_warn)
    return tr
