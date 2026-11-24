"""인플루엔자 보조 비교 모형 (docs/reports/11_influenza_protocol.md 7절, 결과 전에 고정).

1절 방정식, 단일 지역. 감염병 값은 인플루엔자 **가정값** (잠복 1.5일, 감염 4일, 면역 소실 1/365 일⁻¹, 치명률 0,
재감염 구조 P·T·M 은 1단계 기본값), R0_max = 4 (u = 0 의 기준 R0, reference 기준).
창: 기점 주 끝에서 182일 (26주) 전부터. 추정 (벌점 우도, L-BFGS-B, 라플라스 근사):
  z_k (14일 구간 u, R_t = R0_max sigmoid(z_k), 무작위 걷기 sd 0.5), 창 시작 I0 (log N(log(1e-5 N), 3²)),
  창 시작 감수성 비율 s0 (logit N(logit 0.6, 1²); 나머지는 보호 상태 R^P_1), 관측 척도 c (log N(log 1e-3, 2²)),
  과산포 κ (log N(log 100, 1.5²)).
관측: 주간 양성 x_w ~ BetaBinomial(n_w, 평균 p_w, 농도 κ), p_w = inc_w / (inc_w + c), inc_w = 그 주 발병(E -> I) / N.
  양성률 = 인플루엔자 환자 / (인플루엔자 + 다른 원인 호흡기 환자) 의 근사이며, 감염 규모의 절대값은 c 와 함께 움직여 잘 식별되지 않는다.
예측: 마지막 구간 z 에서 무작위 걷기로 이어 가고 (구간당 sd 0.5), 라플라스 표본 + 관측 잡음 (검사 수 = 직전 4주 중앙값 가정).
"""

from __future__ import annotations

import time

import numpy as np
from scipy.optimize import minimize
from scipy.special import betaln, expit, gammaln, logit

from ..model import analysis as A
from ..model.params import EpiParams
from ..model.reactions import ReactionSystem
from ..model.regions import RegionSet
from ..model.state import Layout
from .calibrate import numerical_hessian
from .fastode import FastODE

FLU_PARAMS = dict(sigma=1 / 1.5, gamma=1 / 4.0, c0=1.0, P1=1.0, T1=1.0, Pmin=0.3, alpha=0.5, beta=0.3,
                  lam=1 / 365.0, f1=0.0, M=8)
R0_MAX = 4.0
KNOT_DAYS = 14
TAU_RW = 0.5
WINDOW_WEEKS = 26


def betabinom_logpmf(x, n, p, kappa):
    a, b = p * kappa, (1 - p) * kappa
    return gammaln(n + 1) - gammaln(x + 1) - gammaln(n - x + 1) + betaln(x + a, n - x + b) - betaln(a, b)


class FluPositivityModel:
    def __init__(self, population: float, x: np.ndarray, n: np.ndarray, weeks_horizon: int = 4):
        """x, n: 창의 주간 양성·검사 수 (길이 WINDOW_WEEKS, 검사 수 없는 주는 NaN)."""
        self.N = float(population)
        self.x, self.n = np.asarray(x, float), np.asarray(n, float)
        self.W = self.x.size
        self.ok = np.isfinite(self.x) & np.isfinite(self.n) & (self.n > 0)
        self.days = 7 * self.W
        self.H = weeks_horizon
        base = EpiParams(**FLU_PARAMS)
        reg = RegionSet.single(self.N)
        self.c0 = A.c0_reference(R0_MAX, base.with_(c0=1.0))
        self.system = ReactionSystem(base.with_(c0=self.c0), reg)
        self.fast = FastODE(self.system, nsub=4)
        self.layout = Layout(1, base.M)
        self.base = base
        self.n_knots = int(np.ceil(self.days / KNOT_DAYS))
        self.names = [f"z{k}" for k in range(self.n_knots)] + ["log_I0", "logit_s0", "log_c", "log_kappa"]

    def unpack(self, th, extra_z=None):
        z = th[: self.n_knots]
        if extra_z is not None:
            z = np.concatenate([z, extra_z])
        k = self.n_knots
        return {"z": z, "I0": np.exp(th[k]), "s0": expit(th[k + 1]), "c": np.exp(th[k + 2]), "kappa": np.exp(th[k + 3])}

    def initial_theta(self) -> np.ndarray:
        th = np.zeros(len(self.names))
        th[: self.n_knots] = logit(1.0 / R0_MAX / 0.6)                  # R_t * s0 = 1 근처에서 시작
        k = self.n_knots
        th[k], th[k + 1], th[k + 2], th[k + 3] = np.log(1e-5 * self.N), logit(0.6), np.log(1e-3), np.log(100.0)
        return th

    def weekly_inc(self, par, days):
        L = self.layout
        X0 = L.empty()
        I0 = min(par["I0"], self.N / 100)
        E0 = I0 * self.base.gamma / self.base.sigma
        rest = self.N - I0 - E0
        X0[0, L.S] = par["s0"] * rest
        X0[0, L.RP(1)] = (1 - par["s0"]) * rest
        X0[0, L.I(1)] = I0
        X0[0, L.E(1)] = E0
        k = np.minimum(np.arange(days) // KNOT_DAYS, par["z"].size - 1)
        u = (1.0 - expit(par["z"][k]))[:, None]
        _, ons, _, _ = self.fast.run(X0, self.fast.gc_from_u(u))
        return ons[:, 0].reshape(-1, 7).sum(axis=1) / self.N

    def log_prior(self, th) -> float:
        z = th[: self.n_knots]
        k = self.n_knots
        lp = -0.5 * np.sum(np.diff(z) ** 2) / TAU_RW ** 2
        lp += -0.5 * ((th[k] - np.log(1e-5 * self.N)) / 3.0) ** 2
        lp += -0.5 * ((th[k + 1] - logit(0.6)) / 1.0) ** 2
        lp += -0.5 * ((th[k + 2] - np.log(1e-3)) / 2.0) ** 2
        lp += -0.5 * ((th[k + 3] - np.log(100.0)) / 1.5) ** 2
        return float(lp)

    def objective(self, th) -> float:
        try:
            par = self.unpack(th)
            inc = self.weekly_inc(par, self.days)
            p = np.clip(inc / (inc + par["c"]), 1e-9, 1 - 1e-9)
            ll = betabinom_logpmf(self.x[self.ok], self.n[self.ok], p[self.ok], par["kappa"]).sum()
            v = -(ll + self.log_prior(th))
        except (FloatingPointError, ValueError):
            return 1e30
        return float(v) if np.isfinite(v) else 1e30

    def fit(self, maxiter: int = 3000, hessian: bool = True) -> dict:
        t0 = time.perf_counter()
        th0 = self.initial_theta()
        res = minimize(self.objective, th0, method="L-BFGS-B", options={"maxiter": maxiter, "maxfun": 200000,
                                                                          "ftol": 1e-10, "gtol": 1e-6})
        out = {"theta": res.x, "success": bool(res.success), "message": str(res.message), "objective": float(res.fun),
               "n_iter": int(res.nit), "cov": None, "hessian_pd": None}
        if hessian:
            H = numerical_hessian(self.objective, res.x)
            w = np.linalg.eigvalsh(0.5 * (H + H.T))
            out["hessian_pd"] = bool(w.min() > 0)
            out["cov"] = np.linalg.inv(H) if out["hessian_pd"] else None
        out["wall_s"] = time.perf_counter() - t0
        return out

    def predictive(self, fr: dict, n_future_tests: float, n_samples: int = 300, seed: int = 0) -> np.ndarray:
        """[n_samples, H] 미래 주간 양성률 표본 (관측 잡음 포함, 검사 수 = n_future_tests)."""
        rng = np.random.default_rng(seed)
        days = self.days + 7 * self.H
        n_future = int(np.ceil(days / KNOT_DAYS)) - self.n_knots
        Lc = None
        if fr["cov"] is not None:
            w, V = np.linalg.eigh(0.5 * (fr["cov"] + fr["cov"].T))
            Lc = V * np.sqrt(np.clip(w, 0, None))
        m = max(int(round(n_future_tests)), 1)
        out = np.empty((n_samples, self.H))
        for s in range(n_samples):
            th = fr["theta"] + (Lc @ rng.standard_normal(fr["theta"].size) if Lc is not None else 0.0)
            extra = th[self.n_knots - 1] + np.cumsum(rng.normal(0, TAU_RW, max(n_future, 0)))
            par = self.unpack(th, extra_z=extra)
            inc = self.weekly_inc(par, days)[-self.H:]
            p = np.clip(inc / (inc + par["c"]), 1e-9, 1 - 1e-9)
            q = rng.beta(p * par["kappa"], (1 - p) * par["kappa"])
            out[s] = rng.binomial(m, q) / m
        return out
