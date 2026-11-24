"""화학 랑주뱅 방정식 (1.5절 SDE), Euler-Maruyama.

  dX = sum_j nu_j a_j(X) dt + sum_j nu_j sqrt(a_j(X)) dW_j

한 단계 h 동안 사건 j 의 증분은 inc_j = a_j h + sqrt(a_j h) xi_j (xi_j ~ N(0,1), 서로 독립)이다.
이동은 (i, j, c) 쌍마다 독립 잡음을 둔다. 그래야 원래 방정식의 공분산이 그대로 유지된다.

음수 처리 방식 (truncation 인자)
  "flow_limit" (기본, 1-C 2b 결정; docs/DECISIONS.md D-004)
      증분의 부호를 그대로 둔다. 음수 증분은 dst -> src 방향 흐름으로 본다.
      어떤 구획이 음수가 되면, 그 구획에서 나가는 흐름들을 비례로 줄여 정확히 0 이 되게 한다.
      줄인 흐름 때문에 다른 구획이 음수가 되면 같은 처리를 반복한다 (흐름은 줄기만 하므로 끝난다).
      보존이 정확하고, 수정은 0 에 닿는 구획에서만 일어난다.
  "increment_clip" (1-C 에서 승인한 방식 b; 편향이 커서 기본값에서 뺌)
      inc_j < 0 이면 0 으로 자르고, 원천 구획에서 나가는 합이 X_s 를 넘으면 비례로 줄인다.
      a_j h 가 작으면 E[max(0, mu + sqrt(mu) xi)] - mu ~ sqrt(mu / 2 pi) 의 양의 편향이 생긴다.
      단위 시간당 편향은 h -> 0 일 때 sqrt(a / (2 pi h)) 로 발산한다 (CTMC 비교로 확인).
  "state_clip" (지시서 1.5절 원안: 음수 구획을 0 으로 절단)
      보존이 깨진다. 더해진 인구를 meta 에 기록한다.
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

TRUNCATION_MODES = {"flow_limit": 0, "increment_clip": 1, "state_clip": 2}

# stats 색인
S_STEPS, S_NINC, S_NCLIP, S_CLIPMASS, S_NSCALE, S_SCALEMASS, S_FLOW, S_ADDED = range(8)
N_STATS = 8


@njit(cache=True)
def _sde_step(x, h, src, dst, kc, K, ncomp, alive_end, indptr, indices, omvals,
              mode, fr, to, amt, sc, net, outsum, insum, fac, stats):
    """Euler-Maruyama 한 단계. 모든 증분을 (from, to, amount >= 0) 흐름으로 바꾼 뒤 방식에 따라 처리한다."""
    n = x.size
    nf = 0
    for j in range(src.size):
        mean = kc[j] * x[src[j]] * h
        if mean <= 0.0:
            continue
        stats[S_NINC] += 1.0
        v = mean + np.sqrt(mean) * np.random.standard_normal()
        if v < 0.0 and mode == 1:
            stats[S_NCLIP] += 1.0
            stats[S_CLIPMASS] += -v
            v = 0.0
        if v >= 0.0:
            fr[nf] = src[j]
            to[nf] = dst[j]
            amt[nf] = v
        else:
            fr[nf] = dst[j]
            to[nf] = src[j]
            amt[nf] = -v
        nf += 1
    for i in range(K):
        for c in range(alive_end):
            s = i * ncomp + c
            for k in range(indptr[i], indptr[i + 1]):
                mean = omvals[k] * x[s] * h
                if mean <= 0.0:
                    continue
                stats[S_NINC] += 1.0
                d = indices[k] * ncomp + c
                v = mean + np.sqrt(mean) * np.random.standard_normal()
                if v < 0.0 and mode == 1:
                    stats[S_NCLIP] += 1.0
                    stats[S_CLIPMASS] += -v
                    v = 0.0
                if v >= 0.0:
                    fr[nf] = s
                    to[nf] = d
                    amt[nf] = v
                else:
                    fr[nf] = d
                    to[nf] = s
                    amt[nf] = -v
                nf += 1
    for f in range(nf):
        sc[f] = 1.0

    if mode == 0 or mode == 1:
        # 음수가 되는 구획의 나가는 흐름을 비례로 줄인다 (mode 1 은 이미 증분이 >= 0).
        # 반올림 수준의 초과(상대 1e-12)는 무시한다. 100회 안에 끝나지 않으면 초과 구획의 나가는 흐름을
        # 0 으로 만든다. 흐름은 줄기만 하므로 반드시 끝난다.
        it = 0
        while True:
            for s in range(n):
                outsum[s] = 0.0
                insum[s] = 0.0
            for f in range(nf):
                a = amt[f] * sc[f]
                outsum[fr[f]] += a
                insum[to[f]] += a
            bad = False
            for s in range(n):
                avail = x[s] + insum[s]
                if outsum[s] - avail > 1e-12 * (outsum[s] + avail + 1.0):
                    fac[s] = avail / outsum[s] if it < 100 else 0.0
                    bad = True
                else:
                    fac[s] = 1.0
            if not bad:
                break
            for f in range(nf):
                fs = fac[fr[f]]
                if fs < 1.0:
                    stats[S_SCALEMASS] += amt[f] * sc[f] * (1.0 - fs)
                    sc[f] *= fs
            stats[S_NSCALE] += 1.0
            it += 1
    for s in range(n):
        net[s] = 0.0
    for f in range(nf):
        a = amt[f] * sc[f]
        net[fr[f]] -= a
        net[to[f]] += a
        stats[S_FLOW] += a
    for s in range(n):
        x[s] += net[s]
        if x[s] < 0.0:
            stats[S_ADDED] += -x[s]   # mode 2: 절단으로 더한 인구, mode 0/1: 반올림 수준이어야 한다
            x[s] = 0.0
    stats[S_STEPS] += 1.0


@njit(cache=True)
def _sde_segment(x, t, t_stop, out_times, out, k_out,
                 src, dst, const, susc, region, C, Tn, gc, K, ncomp, I0, M, alive_end,
                 indptr, indices, omvals, dt, mode, lam, kc, fr, to, amt, sc, net, outsum, insum,
                 fac, stats):
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
                  mode, fr, to, amt, sc, net, outsum, insum, fac, stats)
        t = t_new


def simulate_sde(system: ReactionSystem, X0: np.ndarray, days: float, output_dt: float = 1.0,
                 seed=None, dt: float = 0.05, t0: float = 0.0, truncation: str = "flow_limit",
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
    if truncation not in TRUNCATION_MODES:
        raise ValueError(f"truncation 은 {list(TRUNCATION_MODES)} 중 하나여야 한다")
    mode = TRUNCATION_MODES[truncation]
    lam, kc = np.empty(K), np.empty(src.size)
    nf_max = src.size + indices.size * alive_end
    fr, to = np.empty(nf_max, np.int64), np.empty(nf_max, np.int64)
    amt, sc = np.empty(nf_max), np.empty(nf_max)
    net, outsum, insum, fac = np.empty(n), np.empty(n), np.empty(n), np.empty(n)
    stats = np.zeros(N_STATS)

    _seed(s32)
    t, k_out = t0, 0
    wall = time.perf_counter()
    for a, b in _segments(system, t0, t0 + days):
        gc = np.ascontiguousarray(system.drivers.g(a) * system.contact_rate(a), dtype=float)
        t, k_out = _sde_segment(x, t, b, grid, out, k_out, src, dst, const, susc, region, C, Tn, gc,
                                K, ncomp, I0, M, alive_end, indptr, indices, omvals, float(dt), mode,
                                lam, kc, fr, to, amt, sc, net, outsum, insum, fac, stats)
    wall = time.perf_counter() - wall
    X = out.reshape(n_out, *shape)
    pop0 = X0.sum()
    pop = X.reshape(n_out, -1).sum(axis=1)
    ninc = max(stats[S_NINC], 1.0)
    flow = max(stats[S_FLOW], 1e-300)
    meta = {"dt": dt, "steps": int(stats[S_STEPS]), "wall_seconds": wall, **seed_meta,
            "truncation": {"mode": truncation,
                           "clipped_increment_fraction": stats[S_NCLIP] / ninc,
                           "clipped_mass_over_flow": stats[S_CLIPMASS] / flow,
                           "limiting_passes": int(stats[S_NSCALE]),
                           "limited_mass_over_flow": stats[S_SCALEMASS] / flow,
                           "zero_clamp_added_mass": stats[S_ADDED],
                           "zero_clamp_added_over_population": stats[S_ADDED] / max(X0.sum(), 1e-300)},
            "max_rel_population_error": float(np.max(np.abs(pop - pop0)) / pop0) if pop0 > 0 else 0.0,
            "min_value": float(X.min())}
    tr = Trajectory(grid, X, system.layout, "sde", meta)
    check_last_bin(tr, last_bin_warn)
    return tr
