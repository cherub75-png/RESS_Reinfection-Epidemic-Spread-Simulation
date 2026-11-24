"""3단계: 관측 모형과 추정기 검증.

모든 자료는 합성(알려진 매개변수로 만든 값)이다. 실제 자료 적합 결과는 docs/reports/3_calibration.md 에 있다.
"""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import nbinom, poisson

from conftest import make_params
from seir_sim.inference import observation as O
from seir_sim.inference.calibrate import FitSpec, SingleRegionModel, fit_diagnostics, numerical_hessian
from seir_sim.inference.fastode import FastODE
from seir_sim.model import analysis as A
from seir_sim.model.drivers import Drivers, InterventionSchedule
from seir_sim.model.params import EpiParams
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet
from seir_sim.model.state import initial_state
from seir_sim.simulate.ode import integrate_ode
from seir_sim.surveillance.observed import build_observed

BASE8 = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1, T1=1, Pmin=0.3, alpha=0.5, beta=0.3,
             lam=1 / 180, f1=0.01, M=8)


# --------------------------------------------------------------------- FastODE

def test_fastode_matches_engine_ode():
    """검증: 추정용 RK4 (하루 4단계) 가 엔진의 DOP853 (rtol 1e-10) 과 같은 해를 준다.
    조건: 4개 지역, 이동, 재감염, 사망, 정수 날짜에서 바뀌는 개입 u (FastODE 의 '하루 안 상수' 가정과 같음).
    흐름 출력의 일관성: 사망 흐름 = D 의 하루 차이, 전체 E 의 변화 = 감염 유입 - 발병 (이동은 전체 합을 보존)."""
    rng = np.random.default_rng(3)
    K = 4
    reg = RegionSet.synthetic_random(K, rng, total_population=4e6, mobility_scale=0.01)
    u = InterventionSchedule(K, [{"start": 20, "end": 60, "value": 0.4, "regions": [0, 1]},
                                 {"start": 45, "end": 120, "value": 0.2, "regions": None}])
    p = make_params(f1=0.02, lam=1 / 90, M=6)
    sysm = ReactionSystem(p, reg, Drivers(K, None, None, u), {"form": "power", "eta": 0.2})
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, reg.population, {0: 20.0})
    days = 200
    tr = integrate_ode(sysm, X0, days, rtol=1e-10, atol=1e-8)

    fo = FastODE(sysm, nsub=4)
    u_days = np.stack([u.at(d + 0.5) for d in range(days)])
    inf, ons, dea, xe = fo.run(X0, fo.gc_from_u(u_days))

    scale = tr.X.max()
    assert np.max(np.abs(xe - tr.X[-1])) / scale < 1e-6
    L = sysm.layout
    D = tr.X[:, :, L.D]
    np.testing.assert_allclose(dea, np.diff(D, axis=0), atol=1e-6 * D.max())
    E = tr.X[:, :, L.E_slice].sum(axis=(1, 2))
    np.testing.assert_allclose(inf.sum(1) - ons.sum(1), np.diff(E), atol=1e-6 * E.max())
    assert np.all(inf >= 0) and np.all(ons >= 0)


# --------------------------------------------------------------------- 관측 함수

@pytest.mark.parametrize("mean,cv", [(4.0, 0.7), (10.0, 0.5), (0.8, 1.0)])
def test_discretized_gamma(mean, cv):
    p = O.discretized_gamma(mean, cv, 40)
    assert p.shape == (41,) and np.all(p >= 0)
    assert p.sum() == pytest.approx(1.0, abs=1e-12)
    # 구간 [s-0.5, s+0.5) 의 대표값 s 를 쓰므로 이산 평균은 연속 평균과 거의 같다 (s = 0 구간만 [0, 0.5))
    assert np.dot(np.arange(41), p) == pytest.approx(mean, abs=0.15)


def test_discretized_gamma_zero_mean_is_identity():
    p = O.discretized_gamma(0.0, 0.5, 10)
    assert p[0] == 1.0 and p[1:].sum() == 0.0


def test_convolve_causal_no_future_leak():
    """d 일의 출력은 d 일 이전 입력에만 의존한다."""
    x = np.zeros(50)
    x[30] = 1.0
    pmf = O.discretized_gamma(5.0, 0.5, 20)
    y = O.convolve_causal(x, pmf)
    assert np.all(y[:30] == 0.0)
    np.testing.assert_allclose(y[30:51], pmf[:20], atol=1e-15)


def test_weekday_multipliers_geometric_mean_one():
    w = O.weekday_multipliers(np.array([0.3, -0.2, 0.1, 0.0, 0.5, -0.4]))
    assert w.shape == (7,)
    assert np.exp(np.mean(np.log(w))) == pytest.approx(1.0, abs=1e-14)


def test_window_sums_brute_force():
    rng = np.random.default_rng(0)
    x = rng.random(60)
    s = np.array([0, 5, 12, 40])
    e = np.array([0, 11, 18, 59])
    ref = np.array([x[a:b + 1].sum() for a, b in zip(s, e)])
    np.testing.assert_allclose(O.window_sums(x, s, e), ref, rtol=1e-13)


def test_likelihoods_match_scipy():
    y = np.array([0, 1, 5, 40, 300])
    mu = np.array([0.5, 2.0, 4.0, 50.0, 250.0])
    r = 7.5
    np.testing.assert_allclose(O.nb_logpmf(y, mu, r), nbinom.logpmf(y, r, r / (r + mu)), rtol=1e-10)
    np.testing.assert_allclose(O.poisson_logpmf(y, mu), poisson.logpmf(y, mu), rtol=1e-10)


def test_numerical_hessian_quadratic():
    A_ = np.array([[3.0, 0.5, 0.0], [0.5, 2.0, -0.3], [0.0, -0.3, 1.0]])
    f = lambda x: 0.5 * x @ A_ @ x + x.sum()
    np.testing.assert_allclose(numerical_hessian(f, np.array([0.2, -0.1, 0.4])), A_, atol=1e-6)


# --------------------------------------------------------------------- 추정기

def _truth(m: SingleRegionModel, rt: np.ndarray) -> np.ndarray:
    th = np.zeros(len(m.names))
    mm = rt[: m.n_knots] / m.spec.R0_max
    th[: m.n_knots] = np.log(mm / (1 - mm))
    th[m.idx["log_I0"]] = np.log(30)
    th[m.idx["log_delay_c"]] = np.log(5)
    th[m.idx["wc0"]: m.idx["wc0"] + 6] = [0.1, 0.05, 0, 0, -0.05, -0.1]
    th[m.idx["log_r_c"]] = np.log(30)
    if m.spec.use_deaths:
        th[m.idx["log_kf0"]: m.idx["log_kf0"] + m.n_kf] = np.log(1.5)
        th[m.idx["log_delay_d"]] = np.log(12)
        th[m.idx["log_r_d"]] = np.log(15)
    return th


def _synthetic_obs(m: SingleRegionModel, th: np.ndarray, seed: int, days: int | None = None):
    par = m.unpack(th)
    ex = m.expected(par, days)
    rng = np.random.default_rng(seed)
    yc = rng.negative_binomial(par["r_c"], par["r_c"] / (par["r_c"] + ex["mu_cases"]))
    dates = pd.date_range(m.spec.start, periods=yc.size)
    oc = build_observed(pd.Series(yc, index=dates), "cases", "SYN", "synthetic")
    od = None
    if m.spec.use_deaths:
        yd = rng.negative_binomial(par["r_d"], par["r_d"] / (par["r_d"] + ex["mu_deaths"]))
        od = build_observed(pd.Series(yd, index=dates), "deaths", "SYN", "synthetic", gap_min_mean=1e9)
    return oc, od


RT = np.array([2.5, 2.2, 1.0, 0.7, 0.8, 1.0, 1.2, 1.1, 0.9, 0.8])


def test_fit_end_blocks_future_observations():
    """검증: fit_end 이후의 관측을 아무리 바꿔도 목적함수가 같다 (시간순 검증의 미래 자료 누설 차단)."""
    spec = FitSpec(start="2020-02-01", fit_end="2020-04-30")
    m = SingleRegionModel(EpiParams(**BASE8), 1e7, spec, horizon_days=60)
    th = _truth(m, RT)
    oc, od = _synthetic_obs(m, th, seed=1, days=m.days)
    m.prepare(oc, od)
    f1 = m.objective(th)
    cut = int((pd.Timestamp(spec.fit_end) - pd.Timestamp(spec.start)).days)
    oc.y[oc.end > cut] *= 100
    od.y[od.end > cut] += 1000
    m.prepare(oc, od)
    assert m.objective(th) == f1
    # 반대로 fit_end 이전 자료를 바꾸면 달라져야 한다 (검사가 무의미하지 않음을 확인)
    oc.y[(oc.end <= cut) & (oc.end > cut - 5)] += 50
    m.prepare(oc, od)
    assert m.objective(th) != f1


def test_window_straddling_fit_end_is_excluded():
    """fit_end 를 걸치는 여러 날 관측 구간은 통째로 뺀다 (부분 합을 쓰면 미래 일부가 섞인다)."""
    spec = FitSpec(start="2020-02-01", fit_end="2020-03-10", use_deaths=False)
    m = SingleRegionModel(EpiParams(**BASE8), 1e7, spec, horizon_days=20)
    dates = pd.date_range(spec.start, periods=m.days)
    y = np.full(m.days, 10.0)
    oc = build_observed(pd.Series(y, index=dates), "cases", "SYN", "synthetic")
    cut = int((pd.Timestamp(spec.fit_end) - pd.Timestamp(spec.start)).days)
    # 마지막 학습일을 포함하는 3일 구간을 하나 만든다
    keep = (oc.end < cut - 1) | (oc.end > cut + 1)
    oc.start = np.append(oc.start[keep], cut - 1)
    oc.end = np.append(oc.end[keep], cut + 1)
    oc.y = np.append(oc.y[keep], 30.0)
    m.prepare(oc, None)
    s, e, _ = m._c
    assert e.max() == cut - 2 and np.all(e < cut - 1)


def test_synthetic_recovery_cases_only():
    """검증: 확진만 있는 합성 자료(140일)에서 R_t 구간값과 관측 매개변수를 되찾는다.
    합격 기준: 수렴, 헤시안 양의 정부호, 참값이 추정값 +- 3 표준오차 안에 드는 매개변수 비율 >= 0.9,
    추정 기대 확진 곡선과 참 곡선의 상대 L1 차이 < 0.1, 표본 안 90% 포함률 0.8 ~ 0.98. 한계: 한 번의 실현값이므로 포함률(빈도 성질)의 검증은 보고서의 반복 실험이 맡는다."""
    spec = FitSpec(start="2020-02-01", fit_end="2020-06-19", use_deaths=False)
    m = SingleRegionModel(EpiParams(**BASE8), 2e7, spec)
    th = _truth(m, RT)
    oc, _ = _synthetic_obs(m, th, seed=7)
    fr = m.fit(oc, None)
    assert fr.success and fr.hessian_pd
    se = fr.se()
    z = np.abs(fr.theta - th) / se
    assert np.mean(z < 3) >= 0.9
    # 이웃한 두 구간의 R_t 는 서로 음의 상관을 가진다 (지연·세대 간격 때문에 바뀐 시점이 약하게 식별됨).
    # 그래서 구간별 R_t 점추정의 절대 오차 대신, 식별되는 양인 기대 확진 곡선을 참값과 비교한다.
    mu_true = m.expected(m.unpack(th), spec.n_fit_days)["mu_cases"]
    mu_est = m.expected(m.unpack(fr.theta), spec.n_fit_days)["mu_cases"]
    assert np.abs(mu_est - mu_true).sum() / mu_true.sum() < 0.1
    d = fit_diagnostics(m, fr)["cases"]
    assert 0.8 <= d["coverage90_in_sample"] <= 0.98


def test_predictive_shapes_and_continuity():
    """예측 표본의 모양, 비음수, 예측 첫 주 평균이 학습 끝 무렵 모형 기댓값과 이어지는지 확인한다."""
    spec = FitSpec(start="2020-02-01", fit_end="2020-05-29", use_deaths=False)
    m = SingleRegionModel(EpiParams(**BASE8), 2e7, spec)
    th = _truth(m, RT)
    oc, _ = _synthetic_obs(m, th, seed=2)
    fr = m.fit(oc, None)
    pr = m.predictive(fr, horizon=14, n_samples=100, seed=0)
    assert pr["cases"].shape == (100, 14) and np.all(pr["cases"] >= 0)
    assert pr["dates"][0] == pd.Timestamp("2020-05-30")
    mu_end = m.expected(m.unpack(fr.theta), spec.n_fit_days)["mu_cases"][-7:].mean()
    assert 0.5 < np.median(pr["mu_cases"][:, :7].mean(1)) / mu_end < 2.0
