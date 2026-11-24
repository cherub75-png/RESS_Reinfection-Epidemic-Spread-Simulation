"""보정 SEIR 의 시간순 예측: 기점마다 그날까지의 주간 자료로 다시 추정하고 4주 예측 분포를 만든다.

순차 재추정 (계산량 때문에 쓰는 근사; 미래 자료는 쓰지 않는다)
  - 첫 기점: start ~ 기점 전체를 추정 (요일 효과는 주간 합에서 식별되지 않으므로 0 으로 고정).
  - 다음 기점: 앞 기점의 추정값에서 시작한다. 기점 전 window_days 안에 걸치는 R_t·k_f 구간과 관측 매개변수만
    다시 추정하고, 그보다 앞 구간과 I0 는 앞 기점의 값으로 고정한다. 우도도 그 창 안의 관측만 쓴다.
    (고정된 값들은 더 이른 기점, 즉 더 적은 자료로 추정된 것이다.)
  - 불확실성: 자유 매개변수의 라플라스 근사 + 미래 u(t) 의 무작위 걷기 + 주간 NegBin 관측 잡음.
    고정된 매개변수의 불확실성은 빠지므로 구간이 다소 좁을 수 있다 (한계).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from ..inference.calibrate import FitSpec, SingleRegionModel
from ..model.params import EpiParams
from ..surveillance.observed import build_weekly
from .metrics import QUANTILES

BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1, T1=1, Pmin=0.3, alpha=0.5, beta=0.3, lam=1 / 180,
            f1=0.01, M=8)


@dataclass
class RollingSpec:
    start: str = "2020-02-01"
    knot_days: int = 14
    window_days: int = 182
    rho: float = 0.5
    R0_max: float = 6.0
    tau_rw: float = 0.5
    n_samples: int = 300
    horizon_weeks: int = 4
    use_deaths: bool = True
    nsub: int = 4


def weekly_from_daily(x: np.ndarray, weeks: int) -> np.ndarray:
    """[S, 7 * weeks] -> [S, weeks]."""
    return x[:, : 7 * weeks].reshape(x.shape[0], weeks, 7).sum(axis=2)


def rolling_country(iso3: str, panel: pd.DataFrame, origins, spec: RollingSpec = RollingSpec(),
                    base: dict = BASE, seed: int = 0, log=None, resume: dict | None = None) -> list[dict]:
    """resume: 앞선 실행의 마지막 결과 (origin, theta) 에서 이어서 시작한다 (최신 자료 예측용)."""
    pop = panel.attrs["population"]
    oc = build_weekly(panel["cases"], "cases", iso3, "jhu", start=spec.start)
    od = build_weekly(panel["deaths"], "deaths", iso3, "jhu", start=spec.start) if spec.use_deaths else None
    prev_m, prev_th = None, None
    if resume is not None:
        fs = FitSpec(start=spec.start, fit_end=resume["origin"], knot_days=spec.knot_days, rho=spec.rho,
                     R0_max=spec.R0_max, tau_rw=spec.tau_rw, use_deaths=spec.use_deaths, nsub=spec.nsub)
        prev_m, prev_th = SingleRegionModel(EpiParams(**base), pop, fs), np.asarray(resume["theta"], float)
    out = []
    H = spec.horizon_weeks
    for k, t in enumerate(pd.DatetimeIndex(origins)):
        fs = FitSpec(start=spec.start, fit_end=str(t.date()), knot_days=spec.knot_days, rho=spec.rho,
                     R0_max=spec.R0_max, tau_rw=spec.tau_rw, use_deaths=spec.use_deaths, nsub=spec.nsub)
        m = SingleRegionModel(EpiParams(**base), pop, fs)
        t0 = time.perf_counter()
        if prev_m is None:
            th0 = m.initial_theta(oc)
            free = m.free_mask(None, weekday=False)
            fr = m.fit(oc, od, theta0=th0, free=free)
            mode = "full"
        else:
            th0 = m.warm_start(prev_m, prev_th)
            ws = t - pd.Timedelta(days=spec.window_days - 1)
            free = m.free_mask(ws, weekday=False)
            fr = m.fit(oc, od, theta0=th0, free=free, window_start=ws)
            mode = "window"
        pr = m.predictive(fr, horizon=7 * H, n_samples=spec.n_samples, seed=seed + k)
        rng = np.random.default_rng([seed, k, 1])
        res = {"iso3": iso3, "origin": str(t.date()), "mode": mode, "success": fr.success,
               "hessian_pd": fr.hessian_pd, "n_free": int(free.sum()), "n_iter": fr.n_iter,
               "wall_s": time.perf_counter() - t0, "objective": fr.objective}
        res["theta"] = fr.theta.tolist()          # 다음 기점(또는 최신 자료 예측)의 시작값
        res["names"] = list(m.names)
        par = m.unpack(fr.theta)
        res["Rt_last"] = float(par["m"][-1] * spec.R0_max)
        res["Rt_last_capped"] = bool(par["m"][-1] > 0.98)
        for var, key in (("cases", "mu_cases"), ("deaths", "mu_deaths")):
            mu = pr.get(key)
            if mu is None:
                continue
            r = pr["r_c"] if var == "cases" else pr["r_d"]
            mw = weekly_from_daily(mu, H)
            yw = rng.negative_binomial(r[:, None], r[:, None] / (r[:, None] + np.maximum(mw, 1e-10)))
            res[f"{var}_q"] = np.quantile(yw, QUANTILES, axis=0).T.tolist()       # [H, Q]
            res[f"{var}_mean"] = yw.mean(axis=0).tolist()
            res[f"{var}_samples"] = yw.astype(np.int64)
        out.append(res)
        if log:
            log(f"{iso3} {t.date()} {mode} ok={fr.success} pd={fr.hessian_pd} free={free.sum()} "
                f"{res['wall_s']:.1f}s Rt={res['Rt_last']:.2f}")
        prev_m, prev_th = m, fr.theta
    return out


def spec_dict(spec: RollingSpec) -> dict:
    return asdict(spec)
