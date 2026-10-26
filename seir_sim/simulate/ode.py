"""평균장 ODE (1.4절) 적분기.

우변은 공통 사건 목록의 drift(X, t) = sum_j nu_j a_j(X) 이다.
g_i(t), u_i(t) 는 구간별 상수이므로 변화 시점에서 적분을 끊고 새로 시작한다.
각 구간 안에서는 구간 시작 시점의 값을 쓰므로 경계의 불연속이 적분 오차를 만들지 않는다.
"""

from __future__ import annotations

import time

import numpy as np
from scipy.integrate import solve_ivp

from ..model.reactions import ReactionSystem
from .result import DEFAULT_LAST_BIN_WARN, Trajectory, check_last_bin


def _segments(system: ReactionSystem, t0: float, t1: float) -> list[tuple[float, float]]:
    edges = [t0]
    while True:
        nxt = system.drivers.next_change(edges[-1])
        if nxt >= t1:
            break
        edges.append(nxt)
    edges.append(t1)
    return list(zip(edges[:-1], edges[1:]))


def integrate_ode(system: ReactionSystem, X0: np.ndarray, days: float, output_dt: float = 1.0,
                  method: str = "DOP853", rtol: float = 1e-8, atol: float = 1e-6,
                  t0: float = 0.0, last_bin_warn: float = DEFAULT_LAST_BIN_WARN) -> Trajectory:
    shape = X0.shape
    t_end = t0 + days
    n_out = int(np.floor(days / output_dt + 1e-9)) + 1
    grid = t0 + output_dt * np.arange(n_out)

    out = np.empty((n_out, *shape))
    out[0] = X0
    y = X0.reshape(-1).astype(float).copy()
    nfev, n_seg = 0, 0
    wall = time.perf_counter()

    for a, b in _segments(system, t0, t_end):
        n_seg += 1
        t_drv = a                                   # 구간 안에서 g, u 는 상수

        def rhs(t, yy, t_drv=t_drv):
            return system.drift(yy.reshape(shape), t_drv).reshape(-1)

        sel = np.flatnonzero((grid > a) & (grid <= b))
        t_eval = np.unique(np.concatenate([grid[sel], [b]]))
        sol = solve_ivp(rhs, (a, b), y, method=method, t_eval=t_eval, rtol=rtol, atol=atol)
        if not sol.success:
            raise RuntimeError(f"ODE 적분 실패 [{a}, {b}]: {sol.message}")
        nfev += sol.nfev
        for k, tk in enumerate(sol.t):
            m = np.flatnonzero(np.isclose(grid, tk, rtol=0, atol=1e-9))
            if m.size:
                out[m[0]] = sol.y[:, k].reshape(shape)
        y = sol.y[:, -1].copy()

    wall = time.perf_counter() - wall
    pop0 = X0.sum()
    pop = out.reshape(n_out, -1).sum(axis=1)
    meta = {
        "solver": method, "rtol": rtol, "atol": atol, "nfev": int(nfev), "segments": n_seg,
        "wall_seconds": wall,
        "min_value": float(out.min()),
        "max_rel_population_error": float(np.max(np.abs(pop - pop0)) / pop0) if pop0 > 0 else 0.0,
    }
    tr = Trajectory(grid, out, system.layout, "ode", meta)
    check_last_bin(tr, last_bin_warn)
    return tr
