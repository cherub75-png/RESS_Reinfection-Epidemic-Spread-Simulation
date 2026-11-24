"""인플루엔자: FluNet 통합 규칙, 미래 자료 누설 검사, 시간순 구간 보정 (합성 자료로 정확한 기댓값을 아는 경우)."""

import numpy as np
import pandas as pd
import pytest

from seir_sim.forecast import flu as FL
from seir_sim.forecast.metrics import QUANTILES
from seir_sim.surveillance import flunet as F

COLS = F.COLS


def _raw(tmp_path, rows):
    df = pd.DataFrame(rows, columns=COLS)
    p = tmp_path / "f.csv"
    df.to_csv(p, index=False)
    return p


def test_flunet_rules(tmp_path):
    base = ["KOR", "Korea", "SENTINEL", None, "NH", "Z", None, None, None, None, None]
    rows = []
    for k, (spec, a, b, allp, neg) in enumerate([(100, 5, 1, 6, 94), (100, 5, 1, 6, 94),     # 완전 중복 (R1)
                                                 (3, 5, 0, 5, None),                         # 검사 < 양성 (R3: 무효)
                                                 (50, None, None, None, 50),                 # 양성 비어 있고 음성 = 검사 -> 0
                                                 (50, None, None, None, 40),                 # 양성 비어 있고 음성 != 검사 -> 결측
                                                 (0, 0, 0, 0, 0)]):                          # 검사 0 -> 결측
        r = list(base)
        r[3] = str(pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=[0, 0, 2, 3, 4, 5][k]))[:10]
        r[6], r[7], r[8], r[9], r[10] = spec, a, b, allp, neg
        rows.append(r)
    d = F.load_flunet(_raw(tmp_path, rows))
    assert d.attrs["exact_duplicates_removed"] == 1 and len(d) == 5
    d = d.set_index("week")
    assert d.loc["2024-01-01", "tests"] == 100 and d.loc["2024-01-01", "pos"] == 6
    assert np.isnan(d.loc["2024-01-15", "tests"])                    # 검사 3 < 양성 5
    assert d.loc["2024-01-22", "pos"] == 0 and d.loc["2024-01-22", "tests"] == 50
    assert np.isnan(d.loc["2024-01-29", "pos"]) and np.isnan(d.loc["2024-01-29", "tests"])
    assert np.isnan(d.loc["2024-02-05", "tests"])
    assert F.logit_positivity([15], [3], 20)[0] != F.logit_positivity([15], [3], 20)[0]   # 검사 < 20 이면 NaN
    assert F.logit_positivity([100], [9], 20)[0] == pytest.approx(np.log(9.5 / 91.5))


def _synthetic_df(n_weeks=520, series=("AAA|SENTINEL", "BBB|SENTINEL"), seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2012-01-02", periods=n_weeks, freq="7D")
    rows = []
    for k, s in enumerate(series):
        c, src = s.split("|")
        p = 0.05 + 0.25 * np.clip(np.sin(2 * np.pi * (np.arange(n_weeks) / 52.18 + 0.3 * k)), 0, None) ** 3
        n = rng.integers(80, 200, n_weeks)
        x = rng.binomial(n, p)
        rows += [{"series": s, "country": c, "iso3": c, "source": src, "name": c, "hemisphere": "NH", "itz": "Z",
                  "week": w, "tests": float(a), "pos": float(b)} for w, a, b in zip(weeks, n, x)]
    return pd.DataFrame(rows)


def test_features_do_not_use_future_data():
    """기점 주 i 뒤의 자료를 바꿔도 주 i 의 특성·기준 모델 예측이 같아야 한다."""
    df = _synthetic_df()
    a = FL.FluData(df, ["AAA|SENTINEL", "BBB|SENTINEL"], start="2012-01-02", lat={"AAA": 40, "BBB": -30})
    i = 400
    cut = a.weeks[i]
    df2 = df.copy()
    late = df2["week"] > cut
    df2.loc[late, "pos"] = df2.loc[late, "tests"]                     # 미래를 모두 100% 양성으로
    b = FL.FluData(df2, ["AAA|SENTINEL", "BBB|SENTINEL"], start="2012-01-02", lat={"AAA": 40, "BBB": -30})
    for h in FL.HORIZONS:
        fa, fb = a.features(i, h).drop(columns=["series", "week"]), b.features(i, h).drop(columns=["series", "week"])
        pd.testing.assert_frame_equal(fa, fb)
    for m in ("persistence", "trend"):
        np.testing.assert_array_equal(a.baseline(0, i, m), b.baseline(0, i, m))
    np.testing.assert_array_equal(a.seasonal(1, i), b.seasonal(1, i))
    ta, tb = FL.feature_table(a), FL.feature_table(b)
    o = a.weeks[i]
    tra = ta[(ta["target_week"] <= o) & ta["target"].notna()].reset_index(drop=True)
    trb = tb[(tb["target_week"] <= o) & tb["target"].notna()].reset_index(drop=True)
    pd.testing.assert_frame_equal(tra, trb)                           # 학습 행도 미래 자료와 무관


def test_seasonal_excludes_covid_gap_and_needs_history():
    df = _synthetic_df()
    a = FL.FluData(df, ["AAA|SENTINEL", "BBB|SENTINEL"], start="2012-01-02")
    assert a.seasonal(0, 10) is None                                  # 과거 절기 없음
    assert a.seasonal(0, 300).shape == (4, QUANTILES.size)


def test_conformal_adjust_restores_nominal_coverage():
    """너무 좁은 분위수(오차 sd 의 절반)를 지난 52주 오차로 보정하면 90% 포함률이 0.9 근처로 돌아온다."""
    rng = np.random.default_rng(1)
    rows = []
    origins = pd.date_range("2020-01-06", periods=150, freq="7D")
    from scipy.stats import norm
    for o in origins:
        for s in range(20):
            for h in (1, 2):
                mu = rng.normal()
                truth_z = mu + rng.normal()
                q = mu + 0.5 * norm.ppf(QUANTILES)                        # 너무 좁음
                rows.append({"origin": o, "target_week": o + pd.Timedelta(weeks=h), "h": h, "truth": truth_z,
                             **{f"q{k}": q[k] for k in range(QUANTILES.size)}})
    fc = pd.DataFrame(rows)
    ident = lambda v: v                                                    # noqa: E731
    out = FL.conformal_adjust(fc, ident, ident, window_weeks=52, min_rows=300)
    late = out["origin"] >= origins[60]
    lo, hi = out.loc[late, "q1"], out.loc[late, "q7"]
    cov = ((out.loc[late, "truth"] >= lo) & (out.loc[late, "truth"] <= hi)).mean()
    raw = ((fc.loc[late, "truth"] >= fc.loc[late, "q1"]) & (fc.loc[late, "truth"] <= fc.loc[late, "q7"])).mean()
    assert raw < 0.65 and 0.87 < cov < 0.93, (raw, cov)
    early = out["origin"] < origins[16]                                    # 보정 표본 부족 (16주 x 20계열 < 300... 경계)
    assert (out.loc[out["origin"] == origins[0], "cal_n"] == 0).all()       # 첫 기점: 과거 없음 -> 보정 안 함
    del early
    # 보정은 기점 이전 정답만 쓴다: 기점 o 이후 정답을 바꿔도 o 의 보정 결과가 같다
    fc2 = fc.copy()
    o = origins[100]
    fc2.loc[fc2["target_week"] > o, "truth"] += 10
    out2 = FL.conformal_adjust(fc2, ident, ident)
    a = out[out["origin"] == o][[f"q{k}" for k in range(9)]].to_numpy()
    b = out2[out2["origin"] == o][[f"q{k}" for k in range(9)]].to_numpy()
    np.testing.assert_allclose(a, b)


def test_baseline_matches_bruteforce_loop():
    """미리 계산한 오차로 만든 기준 모델 분위수 = 과거 기점을 하나씩 도는 정의 그대로의 계산."""
    from scipy.special import expit
    df = _synthetic_df()
    a = FL.FluData(df, ["AAA|SENTINEL", "BBB|SENTINEL"], start="2012-01-02")
    for method in ("persistence", "trend"):
        for i in (60, 250, 480):
            got = a.baseline(1, i, method)
            zf, zt = a.zf[:, 1], a.zt[:, 1]
            want = []
            for h in FL.HORIZONS:
                p = a._point(zf, i, h, method)
                err = [zt[j + h] - a._point(zf, j, h, method) for j in range(1, i - h + 1)
                       if np.isfinite(a._point(zf, j, h, method)) and np.isfinite(zt[j + h])]
                err = np.asarray(err)
                if method == "persistence":
                    err = np.concatenate([err, -err])
                want.append(expit(p + np.quantile(err, QUANTILES)))
            np.testing.assert_allclose(got, np.array(want), rtol=0, atol=1e-12)


def test_operational_origin_skips_partly_reported_week():
    """기점 = 계열 절반 이상이 보고한 가장 최근 주의 전 주 (그 주는 덜 보고되어 있음)."""
    from seir_sim.forecast.flu_operational import operational_origin
    df = _synthetic_df(n_weeks=60, series=("AAA|SENTINEL", "BBB|SENTINEL", "CCC|SENTINEL", "DDD|SENTINEL"))
    last = df["week"].max()
    df.loc[(df["week"] == last) & (df["series"] != "AAA|SENTINEL"), "tests"] = np.nan       # 마지막 주는 1/4 만 보고
    prev = last - pd.Timedelta(weeks=1)
    assert operational_origin(df, sorted(df["series"].unique())) == prev - pd.Timedelta(weeks=1)
