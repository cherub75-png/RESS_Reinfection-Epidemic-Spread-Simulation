"""4~5단계: 예측 지표, 기준 모델, ML 특성의 누설 검사, SEIR 순차 재추정 (모두 합성 자료)."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from seir_sim.forecast import baselines as B
from seir_sim.forecast import metrics as Mx
from seir_sim.forecast.seir import RollingSpec, rolling_country, weekly_from_daily
from seir_sim.forecast.targets import history, origins, rolling7, truth, weekly
from seir_sim.inference.calibrate import FitSpec, SingleRegionModel
from seir_sim.ml.features import FEATURES, daily_features, origin_rows, training_rows
from seir_sim.model.params import EpiParams
from seir_sim.surveillance.observed import build_weekly

Q = Mx.QUANTILES


# --------------------------------------------------------------------- 지표

def test_wis_point_mass_equals_absolute_error():
    """모든 분위수가 한 점 m 이면 WIS = |y - m| (Bracher et al. 2021 의 성질)."""
    y = np.array([3.0, 10.0, 7.0])
    m = np.array([5.0, 5.0, 7.0])
    qv = np.repeat(m[:, None], Q.size, axis=1)
    np.testing.assert_allclose(Mx.wis(y, qv)["wis"], np.abs(y - m), rtol=1e-12)


def test_wis_components_sum_and_hand_example():
    qv = np.array([[1, 2, 3, 4, 5, 6, 7, 8, 9]], float)
    y = np.array([12.0])
    w = Mx.wis(y, qv)
    assert w["wis"][0] == pytest.approx(w["dispersion"][0] + w["overprediction"][0] + w["underprediction"][0])
    # 손 계산: 0.5|12-5| + sum_k a/2 [(u-l) + 2/a (12-u)]
    terms = [(0.05, 1, 9), (0.1, 2, 8), (0.2, 3, 7), (0.5, 4, 6)]
    tot = 0.5 * 7 + sum(a / 2 * ((u - l) + 2 / a * (12 - u)) for a, l, u in terms)
    assert w["wis"][0] == pytest.approx(tot / 4.5)


def test_wis_equals_twice_mean_pinball_loss():
    """WIS = (2 / (2K + 1)) sum_tau PL_tau(y, q_tau), PL_tau = (1{y <= q} - tau)(q - y) (Bracher et al. 2021).
    분위수 수준이 0..1 에 고르게 촘촘하면 2 mean PL -> CRPS 이다. 여기 9개 수준은 꼬리에 몰려 있어 WIS < CRPS 이므로
    WIS 는 같은 분위수 집합끼리만 비교한다."""
    mu, sd, y = 0.0, 1.0, 0.7
    qv = norm.ppf(Q, mu, sd)[None, :]
    pl = ((y <= qv[0]) - Q) * (qv[0] - y)
    assert Mx.wis(np.array([y]), qv)["wis"][0] == pytest.approx(2 * pl.mean(), rel=1e-12)
    taus = np.linspace(0.0005, 0.9995, 1000)
    qd = norm.ppf(taus)
    z = y
    crps = z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi)
    assert 2 * np.mean(((y <= qd) - taus) * (qd - y)) == pytest.approx(crps, rel=2e-3)


def test_crps_samples_matches_closed_form():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (1, 20000))
    y = 0.7
    z = y
    crps = z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi)
    assert Mx.crps_samples(np.array([y]), X)[0] == pytest.approx(crps, abs=0.01)


def test_coverage_and_mase_scale():
    qv = np.tile(np.arange(1, 10, dtype=float), (3, 1))
    y = np.array([0.5, 5.0, 9.5])
    np.testing.assert_array_equal(Mx.coverage(y, qv, 0.05), [0, 1, 0])
    h = pd.Series([10.0, 12, 9, 15, 15, 11])
    assert Mx.mase_scale(h) == pytest.approx(np.mean([2, 3, 6, 0, 4]))


def test_peak_errors():
    idx = pd.date_range("2021-01-03", periods=12, freq="7D")
    v = np.array([10, 20, 80, 300, 900, 400, 100, 40, 20, 10, 10, 10], float)
    s = pd.Series(v, index=idx)
    pk = Mx.observed_peaks(s)
    assert list(pk) == [idx[4]]
    e = Mx.peak_errors(idx[2], np.array([300, 800, 500, 200.0]), s, pk)
    assert e["weeks_before_peak"] == 2 and e["timing_error_weeks"] == 0     # 예측 정점 2주차 = 관측 2주차
    assert e["log_size_ratio"] == pytest.approx(np.log1p(800) - np.log1p(900))
    assert Mx.peak_errors(idx[6], np.ones(4), s, pk) is None


# --------------------------------------------------------------------- 대상과 기준 모델

def _daily(n=400, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    lam = 200 * np.exp(np.sin(t / 40.0) * 2)
    return pd.Series(rng.poisson(lam).astype(float), index=pd.date_range("2020-01-22", periods=n))


def test_weekly_targets_and_history():
    d = _daily()
    w = weekly(d)
    assert np.all(w.index.dayofweek == 6)
    e = w.index[5]
    assert w.iloc[5] == d.loc[e - pd.Timedelta(days=6): e].sum()
    o = w.index[10]
    np.testing.assert_array_equal(truth(w, o), w.iloc[11:15].to_numpy())
    assert history(w, o).index[-1] == o
    d2 = d.copy()
    d2.iloc[30] = np.nan
    d2.iloc[60] = -1e6
    w2 = weekly(d2)
    assert w2.isna().sum() >= 2                     # 결측이 있는 주와 음수 합 주는 NaN
    ow = build_weekly(d2, "cases", "SYN", "syn")
    assert ow.n == int(w2.notna().sum())
    np.testing.assert_allclose(ow.y, w2.dropna().to_numpy())


def test_origins_are_same_weekday():
    o = origins("2020-07-05", "2022-12-25", 2)
    assert o[0] == pd.Timestamp("2020-07-05") and o[-1] <= pd.Timestamp("2022-12-25")
    assert np.all(np.diff(o.values).astype("timedelta64[D]").astype(int) == 14)


def test_baselines():
    d = _daily()
    w = weekly(d)
    h = history(w, w.index[30])
    qp = B.baseline_forecast(h, "persistence")
    assert qp.shape == (4, Q.size)
    np.testing.assert_allclose(qp[:, 4], h.iloc[-1], rtol=1e-12)          # 중앙값 = 마지막 값
    assert np.all(np.diff(qp, axis=1) >= 0)
    qt = B.baseline_forecast(h, "trend")
    g = np.log1p(h.iloc[-1]) - np.log1p(h.iloc[-2])
    lv = np.log1p(h.to_numpy())
    err = [lv[i + 1] - (lv[i] + (lv[i] - lv[i - 1]) * 0.75) for i in range(1, h.size - 1)]
    err = np.asarray(err)[np.isfinite(err)]                              # 첫 주(불완전)는 NaN
    assert np.log1p(qt[0, 4]) - lv[-1] == pytest.approx(g * 0.75 + np.median(err), abs=1e-9)
    assert B.baseline_forecast(h, "seasonal52") is None                  # 이력 31주 < 52주
    assert B.baseline_forecast(history(w, w.index[5]), "persistence") is None   # 오차 표본 부족


def test_baselines_ignore_future():
    d = _daily()
    w = weekly(d)
    o = w.index[30]
    a = B.baseline_forecast(history(w, o), "trend")
    w2 = w.copy()
    w2.loc[w2.index > o] *= 50
    np.testing.assert_array_equal(a, B.baseline_forecast(history(w2, o), "trend"))


# --------------------------------------------------------------------- ML 특성 누설 검사

def _panel(n=500, seed=1):
    rng = np.random.default_rng(seed)
    d = _daily(n, seed)
    p = pd.DataFrame(index=d.index)
    p["cases"] = d
    p["deaths"] = rng.poisson(d.rolling(14, min_periods=1).mean().shift(14).fillna(0) * 0.01).astype(float)
    p["stringency"] = np.where(rng.random(n) < 0.1, np.nan, rng.uniform(20, 80, n))
    p["mobility_work"] = rng.normal(-20, 5, n)
    v = np.full(n, np.nan)
    v[350::7] = np.linspace(1, 60, v[350::7].size)
    p["vax_full_per100"] = v
    p.attrs["population"] = 1e7
    return p


def test_features_use_only_past():
    """s 일 이후 자료를 잘라낸 표로 다시 계산해도 s 일의 특성이 같다."""
    p = _panel()
    full = daily_features(p)
    for s in p.index[[60, 200, 377, 420, 499]]:
        cut = p.loc[:s].copy()
        cut.attrs = p.attrs
        part = daily_features(cut)
        pd.testing.assert_series_equal(full.loc[s], part.loc[s], check_names=False)
    assert list(full.columns) == FEATURES


def test_training_rows_targets_observed_by_origin():
    p = _panel()
    f = daily_features(p)
    c7 = rolling7(p["cases"])
    o = p.index[300]
    tr = training_rows(f, c7, o)
    assert len(tr) > 0
    assert np.all(pd.DatetimeIndex(tr["s"]) + pd.to_timedelta(7 * tr["h"], "D") <= o)
    r = tr.iloc[10]
    tgt = np.log1p(c7.loc[r["s"] + pd.Timedelta(days=7 * int(r["h"]))]) - r["lc0"]
    assert r["target"] == pytest.approx(tgt)
    # 기점 뒤 자료를 바꿔도 학습 행이 같다
    p2 = p.copy()
    p2.loc[p2.index > o, "cases"] *= 10
    tr2 = training_rows(daily_features(p2), rolling7(p2["cases"]), o)
    pd.testing.assert_frame_equal(tr, tr2)
    X0 = origin_rows(f, o)
    assert list(X0["h"]) == [1, 2, 3, 4] and np.all(X0.index == o)


def test_ml_quantile_forecast_runs():
    from seir_sim.ml.quantile import ml_forecast
    p = _panel()
    f = daily_features(p)
    o = p.index[400]
    q = ml_forecast(training_rows(f, rolling7(p["cases"]), o), origin_rows(f, o))
    assert q.shape == (4, Q.size) and np.all(np.diff(q, axis=1) >= 0) and np.all(q >= 0)


# --------------------------------------------------------------------- SEIR 순차 재추정

BASE8 = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1, T1=1, Pmin=0.3, alpha=0.5, beta=0.3,
             lam=1 / 180, f1=0.01, M=8)


def test_free_mask_and_warm_start():
    a = SingleRegionModel(EpiParams(**BASE8), 1e7, FitSpec(start="2020-02-01", fit_end="2020-05-01"))
    b = SingleRegionModel(EpiParams(**BASE8), 1e7, FitSpec(start="2020-02-01", fit_end="2020-07-01"))
    th = np.arange(len(a.names), dtype=float)
    w = b.warm_start(a, th)
    for n in a.names:
        assert w[b.idx[n]] == th[a.idx[n]]
    for k in range(a.n_knots, b.n_knots):
        assert w[b.idx[f"z{k}"]] == th[a.n_knots - 1]
    ws = pd.Timestamp("2020-07-01") - pd.Timedelta(days=55)
    fm = b.free_mask(ws, weekday=False)
    lo = b.day_index(ws)
    for k in range(b.n_knots):
        assert fm[b.idx[f"z{k}"]] == ((k + 1) * 14 - 1 >= lo)
    assert not fm[b.idx["log_I0"]] and not fm[b.idx["wc0"]] and fm[b.idx["log_r_c"]]
    assert b.free_mask(None)[b.idx["log_I0"]]


def _synthetic_panel(days=260, seed=4):
    spec = FitSpec(start="2020-02-01", fit_end=str((pd.Timestamp("2020-02-01") + pd.Timedelta(days=days - 1)).date()))
    m = SingleRegionModel(EpiParams(**BASE8), 2e7, spec)
    rt = np.array([2.4, 2.0, 0.9, 0.7, 0.9, 1.2, 1.3, 1.0, 0.8, 0.8, 1.1, 1.3, 1.2, 1.0, 0.9, 0.9, 1.0, 1.0, 1.0])
    th = np.zeros(len(m.names))
    mm = rt[: m.n_knots] / 6.0
    th[: m.n_knots] = np.log(mm / (1 - mm))
    th[m.idx["log_I0"]] = np.log(30)
    th[m.idx["log_delay_c"]] = np.log(5)
    th[m.idx["log_r_c"]] = np.log(30)
    th[m.idx["log_delay_d"]] = np.log(12)
    th[m.idx["log_r_d"]] = np.log(15)
    par = m.unpack(th)
    ex = m.expected(par)
    rng = np.random.default_rng(seed)
    idx = pd.date_range(spec.start, periods=m.days)
    p = pd.DataFrame(index=idx)
    p["cases"] = rng.negative_binomial(30, 30 / (30 + ex["mu_cases"])).astype(float)
    p["deaths"] = rng.negative_binomial(15, 15 / (15 + ex["mu_deaths"])).astype(float)
    p.attrs["population"] = 2e7
    return p, ex


def test_rolling_seir_no_future_leak_and_shapes():
    """두 기점 순차 재추정: 출력 모양, 첫 기점은 전체 추정, 둘째는 창 추정, 기점 뒤 자료를 바꿔도 예측이 같다."""
    p, ex = _synthetic_panel()
    o = pd.DatetimeIndex(["2020-07-05", "2020-07-19"])
    spec = RollingSpec(n_samples=100, window_days=84)
    res = rolling_country("SYN", p, o, spec)
    assert [r["mode"] for r in res] == ["full", "window"]
    for r in res:
        assert np.asarray(r["cases_q"]).shape == (4, Q.size)
        assert r["cases_samples"].shape == (100, 4)
        assert r["success"] and r["hessian_pd"]
    # 예측 중앙값이 참 기댓값의 같은 주 합과 같은 규모 (합성 자료의 참 모형으로 만든 값)
    t = o[1]
    day0 = int((t - pd.Timestamp("2020-02-01")).days) + 1
    true_w = ex["mu_cases"][day0: day0 + 7].sum()
    assert 0.5 < np.asarray(res[1]["cases_q"])[0, 4] / true_w < 2.0
    p2 = p.copy()
    p2.loc[p2.index > o[0], ["cases", "deaths"]] *= 3
    res2 = rolling_country("SYN", p2, o[:1], spec)
    np.testing.assert_array_equal(res2[0]["cases_samples"], res[0]["cases_samples"])


def test_weekly_from_daily():
    x = np.arange(2 * 28).reshape(2, 28).astype(float)
    w = weekly_from_daily(x, 4)
    np.testing.assert_allclose(w[0], [x[0, :7].sum(), x[0, 7:14].sum(), x[0, 14:21].sum(), x[0, 21:28].sum()])


def test_prefix_cache_gives_identical_simulation():
    """고정된 앞 구간을 재사용한 적분이 처음부터 적분한 것과 정확히 같다."""
    p, _ = _synthetic_panel()
    m = SingleRegionModel(EpiParams(**BASE8), 2e7, FitSpec(start="2020-02-01", fit_end="2020-09-30"))
    th = np.random.default_rng(0).normal(0, 0.5, len(m.names))
    th[: m.n_knots] = np.linspace(-1.5, -1.0, m.n_knots)
    th[m.idx["log_I0"]] = np.log(20)
    free = m.free_mask(pd.Timestamp("2020-07-01"), weekday=False)
    m._prefix = None
    full = m.expected(m.unpack(th))
    m.set_prefix(th, free)
    assert m._prefix is not None and m._prefix["day0"] > 0
    th2 = th.copy()
    th2[free] += 0.01                                       # 자유 매개변수만 바꿈 -> 캐시 사용
    a = m.expected(m.unpack(th2))
    m_ref = SingleRegionModel(EpiParams(**BASE8), 2e7, FitSpec(start="2020-02-01", fit_end="2020-09-30"))
    b = m_ref.expected(m_ref.unpack(th2))
    for k in ("infections", "onsets", "deaths_model", "mu_cases", "mu_deaths"):
        np.testing.assert_array_equal(a[k], b[k])
    np.testing.assert_array_equal(m.expected(m.unpack(th))["mu_cases"], full["mu_cases"])
    th3 = th.copy()
    th3[0] += 0.1                                           # 고정 구간이 바뀌면 캐시를 쓰지 않음
    c = m.expected(m.unpack(th3))
    d = m_ref.expected(m_ref.unpack(th3))
    np.testing.assert_array_equal(c["mu_cases"], d["mu_cases"])
