"""단일 지역 보정 (3단계): 방정식은 그대로 두고 시간 변화 개입 u(t), 초기 감염, 관측 매개변수를 추정한다.

모형
  - 1.4절 ODE (단일 지역, 이동 없음). c0 는 "u = 0 일 때의 기준 R0" R0_max 로 정한다 (reference 기준, D-008).
  - u(t): knot_days (기본 14) 일마다 바뀌는 구간별 상수. m_k = 1 - u_k = sigmoid(z_k).
    R_t(전원 감수성) = R0_max * m_k 이다. 백신·변이·행동 효과도 모두 u(t) 에 흡수된다 (방정식에 백신·변이 구획 없음).
  - 초기: start 일에 I_1 = I0, E_1 = I0 * gamma / sigma (나머지 전원 S).
관측 (observation.py)
  - 확진: rho * (발병 * 지연_c) * 요일_c, NegBin(r_c).  rho 는 고정 입력 (식별 불가 → 프로파일로 점검).
  - 사망: k_f(t) * (모형 사망 * 지연_d) * 요일_d, NegBin(r_d). k_f = 치명률 배율 (기준 f1 에 대한 비).
    k_f(t) 는 kf_knot_days (기본 91) 일마다 바뀌는 구간별 상수이고 log 무작위 걷기 (sd tau_kf) 벌점을 둔다.
    방정식의 f(n) 은 시간에 따라 바뀌지 않으므로, 연령 구성·백신에 따른 치명률 변화는 관측 모형에서만 반영한다 (한계).
    사망 흐름을 배율로 다루는 것은 사망이 인구에 비해 매우 작아 되먹임(N 감소)을 무시할 수 있을 때만 정확하다.
사전분포 (벌점; 모두 문서화된 가정)
  - z: 무작위 걷기 z_k - z_{k-1} ~ N(0, tau_rw^2)
  - log 지연 평균: N(log prior_mean, 0.5^2), log r: N(log 20, 1.5^2), 요일 log: N(0, 0.5^2), log I0: N(log 10, 3^2)
추정: 벌점 우도 최소화 (L-BFGS-B, 수치 기울기), 다중 시작점. 불확실성: 라플라스 근사 (수치 헤시안).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit

from ..model import analysis as A
from ..model.params import EpiParams
from ..model.reactions import ReactionSystem
from ..model.regions import RegionSet
from ..model.state import Layout
from ..surveillance.observed import ObservedSeries
from . import observation as O
from .fastode import FastODE


@dataclass
class FitSpec:
    start: str                       # 모형 0일 (날짜)
    fit_end: str                     # 이 날짜까지 끝나는 관측만 쓴다 (포함)
    knot_days: int = 14
    rho: float = 0.5                 # 확진 보고율 (고정 가정)
    R0_max: float = 6.0              # u = 0 의 기준 R0 (고정 가정)
    tau_rw: float = 0.5
    case_delay_prior: float = 4.0    # 발병 -> 확진 보고 평균 (일), 사전 중앙값 (가정)
    death_delay_prior: float = 10.0  # 모형 사망 -> 사망 보고 평균 (일), 사전 중앙값 (가정)
    case_delay_cv: float = 0.7
    death_delay_cv: float = 0.5
    max_lag: int = 40
    use_deaths: bool = True
    kf_knot_days: int = 91
    tau_kf: float = 0.3
    family: str = "negbin"
    nsub: int = 4

    @property
    def n_fit_days(self) -> int:
        return int((pd.Timestamp(self.fit_end) - pd.Timestamp(self.start)).days) + 1


@dataclass
class FitResult:
    theta: np.ndarray
    names: list[str]
    objective: float
    success: bool
    message: str
    n_iter: int
    n_eval: int
    wall_seconds: float
    cov: np.ndarray | None = None
    hessian_pd: bool | None = None
    hessian_min_eig: float | None = None
    multistart_objectives: list = field(default_factory=list)
    free: np.ndarray | None = None

    def params(self, model: "SingleRegionModel") -> dict:
        return model.unpack(self.theta)

    def se(self) -> np.ndarray | None:
        return None if self.cov is None else np.sqrt(np.clip(np.diag(self.cov), 0, None))


class SingleRegionModel:
    def __init__(self, base: EpiParams, population: float, spec: FitSpec, horizon_days: int = 0):
        self.base = base
        self.N = float(population)
        self.spec = spec
        self.start = pd.Timestamp(spec.start)
        self.days = spec.n_fit_days + horizon_days
        reg = RegionSet.single(self.N)
        p = base.with_(c0=1.0)
        self.c0 = A.c0_reference(spec.R0_max, p)
        self.system = ReactionSystem(p.with_(c0=self.c0), reg)
        self.fast = FastODE(self.system, nsub=spec.nsub)
        self.layout = Layout(1, base.M)
        self.n_knots = int(np.ceil(spec.n_fit_days / spec.knot_days))
        self.names = ([f"z{k}" for k in range(self.n_knots)] + ["log_I0", "log_delay_c"]
                      + [f"wc{i}" for i in range(6)] + ["log_r_c"])
        self.n_kf = int(np.ceil(spec.n_fit_days / spec.kf_knot_days))
        if spec.use_deaths:
            self.names += ([f"log_kf{k}" for k in range(self.n_kf)] + ["log_delay_d"]
                           + [f"wd{i}" for i in range(6)] + ["log_r_d"])
        self.idx = {n: i for i, n in enumerate(self.names)}

    # ------------------------------------------------------------------ 매개변수

    def unpack(self, th: np.ndarray, extra_z: np.ndarray | None = None) -> dict:
        z = th[: self.n_knots]
        if extra_z is not None:
            z = np.concatenate([z, extra_z])
        out = {"z": z, "m": expit(z), "I0": np.exp(th[self.idx["log_I0"]]),
               "delay_c": np.exp(th[self.idx["log_delay_c"]]),
               "w_c": O.weekday_multipliers(th[self.idx["wc0"]: self.idx["wc0"] + 6]),
               "r_c": np.exp(th[self.idx["log_r_c"]])}
        if self.spec.use_deaths:
            out.update({"k_f": np.exp(th[self.idx["log_kf0"]: self.idx["log_kf0"] + self.n_kf]),
                        "delay_d": np.exp(th[self.idx["log_delay_d"]]),
                        "w_d": O.weekday_multipliers(th[self.idx["wd0"]: self.idx["wd0"] + 6]),
                        "r_d": np.exp(th[self.idx["log_r_d"]])})
        return out

    def initial_theta(self, obs_c: ObservedSeries) -> np.ndarray:
        th = np.zeros(len(self.names))
        th[: self.n_knots] = logit(np.clip(1.2 / self.spec.R0_max, 1e-3, 0.999))
        k = min(obs_c.n, 14)
        y0 = obs_c.y[:k].sum() / max(obs_c.window_lengths()[:k].sum(), 1) if k else 1.0   # 하루당 평균
        th[self.idx["log_I0"]] = np.log(max(1.0, y0 / max(self.spec.rho, 1e-3) * 3))
        th[self.idx["log_delay_c"]] = np.log(self.spec.case_delay_prior)
        th[self.idx["log_r_c"]] = np.log(20.0)
        if self.spec.use_deaths:
            th[self.idx["log_kf0"]: self.idx["log_kf0"] + self.n_kf] = 0.0
            th[self.idx["log_delay_d"]] = np.log(self.spec.death_delay_prior)
            th[self.idx["log_r_d"]] = np.log(20.0)
        return th

    # ------------------------------------------------------------------ 모형

    def u_days(self, m: np.ndarray, days: int) -> np.ndarray:
        k = np.minimum(np.arange(days) // self.spec.knot_days, m.size - 1)
        return (1.0 - m[k])[:, None]

    def initial_state(self, par: dict) -> np.ndarray:
        L = self.layout
        X0 = L.empty()
        I0 = min(par["I0"], self.N / 10)
        E0 = I0 * self.base.gamma / self.base.sigma
        X0[0, L.S] = self.N - I0 - E0
        X0[0, L.I(1)] = I0
        X0[0, L.E(1)] = E0
        return X0

    def simulate(self, par: dict, days: int | None = None):
        days = days or self.days
        u = self.u_days(par["m"], days)
        pf = getattr(self, "_prefix", None)
        if pf is not None and days > pf["day0"] and par["I0"] == pf["I0"] and np.array_equal(par["z"][: pf["k0"]], pf["z"]):
            # 고정된 앞 구간(I0, z_0..z_{k0-1}) 의 결과를 다시 쓰고 day0 부터만 적분한다 (결과는 처음부터 적분한 것과 같다)
            d0 = pf["day0"]
            inf, ons, dea, _ = self.fast.run(pf["X"], self.fast.gc_from_u(u[d0:]))
            return (np.concatenate([pf["inf"], inf[:, 0]]), np.concatenate([pf["ons"], ons[:, 0]]),
                    np.concatenate([pf["dea"], dea[:, 0]]))
        inf, ons, dea, _ = self.fast.run(self.initial_state(par), self.fast.gc_from_u(u))
        return inf[:, 0], ons[:, 0], dea[:, 0]

    def set_prefix(self, theta: np.ndarray, free: np.ndarray) -> None:
        """I0 와 앞쪽 z 구간이 고정이면, 첫 자유 구간 시작일 day0 까지의 상태와 흐름을 한 번만 계산해 둔다."""
        self._prefix = None
        if free[self.idx["log_I0"]]:
            return
        zf = free[: self.n_knots]
        if not zf.any():
            return
        k0 = int(np.argmax(zf))
        if k0 == 0 or zf[k0:].sum() != zf.size - k0:
            return
        par = self.unpack(theta)
        d0 = k0 * self.spec.knot_days
        inf, ons, dea, X = self.fast.run(self.initial_state(par), self.fast.gc_from_u(self.u_days(par["m"], d0)))
        self._prefix = {"day0": d0, "k0": k0, "z": par["z"][:k0].copy(), "I0": par["I0"], "X": X,
                        "inf": inf[:, 0], "ons": ons[:, 0], "dea": dea[:, 0]}

    def expected(self, par: dict, days: int | None = None):
        days = days or self.days
        inf, ons, dea = self.simulate(par, days)
        wd = np.asarray((self.start + pd.to_timedelta(np.arange(days), "D")).dayofweek)
        pc = O.discretized_gamma(par["delay_c"], self.spec.case_delay_cv, self.spec.max_lag)
        mu_c = self.spec.rho * O.convolve_causal(ons, pc) * par["w_c"][wd]
        mu_d = None
        if self.spec.use_deaths:
            pd_ = O.discretized_gamma(par["delay_d"], self.spec.death_delay_cv, self.spec.max_lag)
            kidx = np.minimum(np.arange(days) // self.spec.kf_knot_days, par["k_f"].size - 1)
            mu_d = par["k_f"][kidx] * O.convolve_causal(dea, pd_) * par["w_d"][wd]
        return {"infections": inf, "onsets": ons, "deaths_model": dea, "mu_cases": mu_c, "mu_deaths": mu_d}

    # ------------------------------------------------------------------ 우도

    def _align(self, obs: ObservedSeries, lo: int = 0):
        off = int((obs.dates[0] - self.start).days)
        s, e = obs.start + off, obs.end + off
        keep = (s >= max(lo, 0)) & (e < self.spec.n_fit_days)
        return s[keep], e[keep], obs.y[keep]

    def day_index(self, date) -> int:
        return int((pd.Timestamp(date) - self.start).days)

    def prepare(self, obs_c: ObservedSeries, obs_d: ObservedSeries | None, window_start=None):
        """fit_end 까지 끝나는 관측만 남긴다. window_start 가 있으면 그날 이후 시작하는 관측만 우도에 넣는다."""
        fit_end = pd.Timestamp(self.spec.fit_end)
        lo = 0 if window_start is None else self.day_index(window_start)
        self._c = self._align(obs_c.restrict(fit_end), lo)
        self._d = self._align(obs_d.restrict(fit_end), lo) if (obs_d is not None and self.spec.use_deaths) else None

    # ------------------------------------------------------------------ 순차 재추정 (시간순 예측용)

    def warm_start(self, prev: "SingleRegionModel", prev_theta: np.ndarray) -> np.ndarray:
        """앞 기점의 추정값으로 시작값을 만든다. 새로 생긴 구간은 마지막 구간 값으로 채운다 (같은 start, knot 간격)."""
        assert prev.start == self.start and prev.spec.knot_days == self.spec.knot_days
        th = np.empty(len(self.names))
        z_last = prev_theta[prev.n_knots - 1]
        kf_last = prev_theta[prev.idx[f"log_kf{prev.n_kf - 1}"]] if prev.spec.use_deaths else 0.0
        for i, n in enumerate(self.names):
            if n in prev.idx:
                th[i] = prev_theta[prev.idx[n]]
            elif n.startswith("z"):
                th[i] = z_last
            elif n.startswith("log_kf"):
                th[i] = kf_last
            else:
                raise KeyError(n)
        return th

    def free_mask(self, window_start=None, weekday: bool = True, I0: bool | None = None) -> np.ndarray:
        """추정할 매개변수. window_start 이전에 끝나는 R_t·k_f 구간과 (기본) I0 는 고정한다.
        weekday=False 면 요일 효과를 0 (승수 1) 으로 고정한다 (주간 합 관측에서는 식별되지 않음)."""
        lo = 0 if window_start is None else self.day_index(window_start)
        free = np.ones(len(self.names), bool)
        kd, kfd = self.spec.knot_days, self.spec.kf_knot_days
        for k in range(self.n_knots):
            free[self.idx[f"z{k}"]] = (k + 1) * kd - 1 >= lo
        if self.spec.use_deaths:
            for k in range(self.n_kf):
                free[self.idx[f"log_kf{k}"]] = (k + 1) * kfd - 1 >= lo
        free[self.idx["log_I0"]] = (lo <= 0) if I0 is None else I0
        if not weekday:
            for key in ("wc", "wd"):
                if f"{key}0" in self.idx:
                    free[self.idx[f"{key}0"]: self.idx[f"{key}0"] + 6] = False
        return free

    def _ll(self, y, mu, r):
        if self.spec.family == "poisson":
            return O.poisson_logpmf(y, mu).sum()
        return O.nb_logpmf(y, mu, r).sum()

    def log_prior(self, th: np.ndarray) -> float:
        sp = self.spec
        z = th[: self.n_knots]
        lp = -0.5 * np.sum(np.diff(z) ** 2) / sp.tau_rw ** 2
        lp += -0.5 * ((th[self.idx["log_delay_c"]] - np.log(sp.case_delay_prior)) / 0.5) ** 2
        lp += -0.5 * ((th[self.idx["log_r_c"]] - np.log(20.0)) / 1.5) ** 2
        lp += -0.5 * np.sum((th[self.idx["wc0"]: self.idx["wc0"] + 6] / 0.5) ** 2)
        lp += -0.5 * ((th[self.idx["log_I0"]] - np.log(10.0)) / 3.0) ** 2
        if sp.use_deaths:
            lp += -0.5 * ((th[self.idx["log_delay_d"]] - np.log(sp.death_delay_prior)) / 0.5) ** 2
            lp += -0.5 * ((th[self.idx["log_r_d"]] - np.log(20.0)) / 1.5) ** 2
            lp += -0.5 * np.sum((th[self.idx["wd0"]: self.idx["wd0"] + 6] / 0.5) ** 2)
            kf = th[self.idx["log_kf0"]: self.idx["log_kf0"] + self.n_kf]
            lp += -0.5 * (kf[0] / 3.0) ** 2 - 0.5 * np.sum(np.diff(kf) ** 2) / sp.tau_kf ** 2
        return float(lp)

    def log_likelihood(self, th: np.ndarray) -> float:
        par = self.unpack(th)
        ex = self.expected(par, self.spec.n_fit_days)
        s, e, y = self._c
        ll = self._ll(y, O.window_sums(ex["mu_cases"], s, e), par["r_c"])
        if self._d is not None:
            s, e, y = self._d
            ll += self._ll(y, O.window_sums(ex["mu_deaths"], s, e), par["r_d"])
        return float(ll)

    def objective(self, th: np.ndarray) -> float:
        try:
            v = -(self.log_likelihood(th) + self.log_prior(th))
        except (FloatingPointError, ValueError):
            return 1e30
        return v if np.isfinite(v) else 1e30

    # ------------------------------------------------------------------ 추정

    def fit(self, obs_c: ObservedSeries, obs_d: ObservedSeries | None = None, theta0=None,
            n_starts: int = 1, seed: int = 0, maxiter: int = 3000, hessian: bool = True,
            free: np.ndarray | None = None, window_start=None) -> FitResult:
        """free: 추정할 매개변수 표시 (나머지는 theta0 값으로 고정). 공분산은 free 부분만 0 이 아니다."""
        self.prepare(obs_c, obs_d, window_start)
        t0 = time.perf_counter()
        th0 = self.initial_theta(obs_c) if theta0 is None else np.asarray(theta0, float).copy()
        free = np.ones(th0.size, bool) if free is None else np.asarray(free, bool)
        self.set_prefix(th0, free)

        def f(x):
            t = th0.copy()
            t[free] = x
            return self.objective(t)

        x0 = th0[free]
        rng = np.random.default_rng(seed)
        best, objs, nit, nfev = None, [], 0, 0
        for k in range(n_starts):
            start = x0 if k == 0 else x0 + rng.normal(0, 0.3, x0.size)
            res = minimize(f, start, method="L-BFGS-B",
                           options={"maxiter": maxiter, "maxfun": 200000, "ftol": 1e-10, "gtol": 1e-6})
            objs.append(float(res.fun))
            nit += res.nit
            nfev += res.nfev
            if best is None or res.fun < best.fun:
                best = res
        theta = th0.copy()
        theta[free] = best.x
        fr = FitResult(theta, list(self.names), float(best.fun), bool(best.success), str(best.message),
                       nit, nfev, time.perf_counter() - t0, multistart_objectives=objs)
        fr.free = free
        if hessian:
            H = numerical_hessian(f, best.x)
            w = np.linalg.eigvalsh(0.5 * (H + H.T))
            fr.hessian_min_eig = float(w.min())
            fr.hessian_pd = bool(w.min() > 0)
            cf = np.linalg.inv(H) if fr.hessian_pd else np.linalg.pinv(H)
            fr.cov = np.zeros((th0.size, th0.size))
            fr.cov[np.ix_(free, free)] = cf
        return fr

    # ------------------------------------------------------------------ 예측

    def predictive(self, fr: FitResult, horizon: int, n_samples: int = 200, seed: int = 0,
                   param_uncertainty: bool = True) -> dict:
        """fit_end 다음 날부터 horizon 일의 확진·사망 예측 표본 (관측 잡음 포함).

        미래 u(t): 마지막 구간 값에서 무작위 걷기로 이어간다 (z 증분 ~ N(0, tau_rw^2) / knot).
        """
        rng = np.random.default_rng(seed)
        days = self.spec.n_fit_days + horizon
        n_future_knots = int(np.ceil(days / self.spec.knot_days)) - self.n_knots
        cases = np.empty((n_samples, horizon))
        deaths = np.empty((n_samples, horizon)) if self.spec.use_deaths else None
        mu_c_all = np.empty((n_samples, horizon))
        mu_d_all = np.empty((n_samples, horizon)) if self.spec.use_deaths else None
        r_c, r_d = np.empty(n_samples), np.empty(n_samples)
        L = None
        if param_uncertainty and fr.cov is not None and fr.hessian_pd:
            w, V = np.linalg.eigh(0.5 * (fr.cov + fr.cov.T))
            L = V * np.sqrt(np.clip(w, 0.0, None))
        for s in range(n_samples):
            th = fr.theta + (L @ rng.standard_normal(fr.theta.size) if L is not None else 0.0)
            if fr.free is not None:
                th[~fr.free] = fr.theta[~fr.free]          # 고정 매개변수는 정확히 그대로 (앞 구간 재사용)
            z_last = th[self.n_knots - 1]
            extra = z_last + np.cumsum(rng.normal(0, self.spec.tau_rw, max(n_future_knots, 0)))
            par = self.unpack(th, extra_z=extra)
            ex = self.expected(par, days)
            mc = ex["mu_cases"][-horizon:]
            mu_c_all[s] = mc
            r_c[s] = par["r_c"]
            cases[s] = rng.negative_binomial(par["r_c"], par["r_c"] / (par["r_c"] + np.maximum(mc, 1e-10)))
            if deaths is not None:
                md = ex["mu_deaths"][-horizon:]
                mu_d_all[s] = md
                r_d[s] = par["r_d"]
                deaths[s] = rng.negative_binomial(par["r_d"], par["r_d"] / (par["r_d"] + np.maximum(md, 1e-10)))
        dates = pd.Timestamp(self.spec.fit_end) + pd.to_timedelta(np.arange(1, horizon + 1), "D")
        # cases/deaths 는 하루 단위 관측 잡음 (일별 관측에 적합했을 때의 뜻). 주간 합에 적합했다면 r 은 주간 합의
        # 분산을 뜻하므로, 주간 예측은 mu 를 주별로 더한 뒤 NegBin(주 합, r) 로 뽑아야 한다 (forecast.seir).
        return {"dates": dates, "cases": cases, "deaths": deaths, "mu_cases": mu_c_all, "mu_deaths": mu_d_all,
                "r_c": r_c, "r_d": r_d if self.spec.use_deaths else None}


def numerical_hessian(f, x: np.ndarray, h: float = 1e-3) -> np.ndarray:
    """중앙 차분 헤시안 (대칭)."""
    n = x.size
    H = np.empty((n, n))
    f0 = f(x)
    E = np.eye(n) * h
    fp = np.array([f(x + E[i]) for i in range(n)])
    fm = np.array([f(x - E[i]) for i in range(n)])
    for i in range(n):
        H[i, i] = (fp[i] - 2 * f0 + fm[i]) / h ** 2
        for j in range(i + 1, n):
            fpp = f(x + E[i] + E[j])
            fmm = f(x - E[i] - E[j])
            H[i, j] = H[j, i] = (fpp - fp[i] - fp[j] + 2 * f0 - fm[i] - fm[j] + fmm) / (2 * h ** 2)
    return H


def _nb_cdf(y, mu, r):
    from scipy.stats import nbinom
    return nbinom.cdf(y, r, r / (r + mu))


def fit_diagnostics(model: SingleRegionModel, fr: FitResult, seed: int = 0) -> dict:
    """표본 안 진단: 무작위화 PIT (균등이면 관측 모형이 맞음), 피어슨 잔차 자기상관, 90% 구간 포함률."""
    from scipy.stats import kstest, nbinom
    rng = np.random.default_rng(seed)
    par = model.unpack(fr.theta)
    ex = model.expected(par, model.spec.n_fit_days)
    out = {}
    for key, data, mu_daily, r in (("cases", model._c, ex["mu_cases"], par["r_c"]),
                                   ("deaths", model._d, ex["mu_deaths"], par.get("r_d"))):
        if data is None or mu_daily is None:
            continue
        s, e, y = data
        mu = O.window_sums(mu_daily, s, e)
        hi = _nb_cdf(y, mu, r)
        lo = np.where(y > 0, _nb_cdf(y - 1, mu, r), 0.0)
        pit = lo + rng.random(y.size) * (hi - lo)
        resid = (y - mu) / np.sqrt(mu + mu ** 2 / r)
        q05 = nbinom.ppf(0.05, r, r / (r + mu))
        q95 = nbinom.ppf(0.95, r, r / (r + mu))
        out[key] = {"n": int(y.size), "obs_total": float(y.sum()), "model_total": float(mu.sum()),
                    "pit_ks_stat": float(kstest(pit, "uniform").statistic),
                    "pit_hist10": np.histogram(pit, bins=10, range=(0, 1))[0].tolist(),
                    "pearson_resid_lag1_autocorr": float(np.corrcoef(resid[:-1], resid[1:])[0, 1]),
                    "coverage90_in_sample": float(np.mean((y >= q05) & (y <= q95)))}
    return out
