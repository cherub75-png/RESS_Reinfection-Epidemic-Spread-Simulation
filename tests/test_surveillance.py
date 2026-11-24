"""2단계: 감시 자료 로더·품질 점검·관측 구간 규칙.

합성 시계열은 규칙을 검증하기 위한 테스트 입력일 뿐이며 실제 자료로 쓰지 않는다.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seir_sim.surveillance import quality as Q
from seir_sim.surveillance.observed import build_observed

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
needs = pytest.mark.skipif(not (RAW / "jhu_csse_global").exists(), reason="data_raw 의 감염병 자료 없음")


def _s(values, start="2021-01-04"):          # 2021-01-04 = 월요일
    return pd.Series(np.asarray(values, float), index=pd.date_range(start, periods=len(values), freq="D"))


def test_qc_weekday_ratio_and_weekly_detection():
    base = np.array([1.2, 1.1, 1.0, 1.0, 1.0, 0.9, 0.8]) * 100
    daily = _s(np.tile(base, 10))
    q = Q.series_qc(daily)
    assert not q["weekly_reporting"] and q["zero_frac"] == 0
    assert q["weekday_ratio"]["Mon"] == pytest.approx(1.2, abs=0.01)
    assert q["weekday_ratio"]["Sun"] == pytest.approx(0.8, abs=0.01)
    weekly = _s(np.tile([0, 0, 0, 0, 0, 0, 700], 10))
    qw = Q.series_qc(weekly)
    assert qw["weekly_reporting"] and qw["top_weekday_share_of_nonzero"] == 1.0


def test_qc_negative_and_spike():
    v = np.full(40, 50.0)
    v[20] = -30
    v[30] = 2000
    q = Q.series_qc(_s(v))
    assert q["n_negative"] == 1 and q["negative_sum"] == -30
    assert q["n_spikes"] == 1 and q["spike_dates"] == [str(_s(v).index[30].date())]


def test_observed_rules_preserve_totals_and_flag():
    v = np.full(30, 40.0)
    v[10] = 0          # 보고 공백
    v[11] = 80         # 다음 날 몰아서 보고
    v[20] = -5         # 소급 정정
    ob = build_observed(_s(v), "cases", "X", "test")
    lens = ob.window_lengths()
    k = int(np.flatnonzero(ob.start == 10)[0])
    assert lens[k] == 2 and ob.y[k] == 80
    assert ob.flags["gap_windows_merged"] == [str(_s(v).index[10].date())]
    assert ob.flags["negative_days_excluded"] == [str(_s(v).index[20].date())]
    assert 20 not in ob.start and ob.y.sum() == v[v >= 0].sum()


def test_observed_weekly_windows():
    v = np.tile([0, 0, 0, 0, 0, 0, 70.0], 6)
    ob = build_observed(_s(v), "cases", "X", "test")
    assert ob.flags["weekly_reporting"]
    assert np.all(ob.window_lengths() == 7) and np.all(ob.y == 70)


def test_restrict_removes_future_windows():
    ob = build_observed(_s(np.arange(1, 31)), "cases", "X", "test")
    r = ob.restrict(ob.dates[14])
    assert r.n == 15 and r.dates[r.end].max() == ob.dates[14]


def test_compare_series_lagged_identical():
    a = _s(np.arange(100.0))
    c = Q.compare_series(a.cumsum(), a.cumsum())
    assert c["median_rel_diff"] == 0 and c["last_rel_diff"] == 0


@needs
def test_real_korea_sources_and_rules():
    from seir_sim.surveillance import sources as S
    j = S.jhu_country(RAW / "jhu_csse_global/time_series_covid19_confirmed_global.csv",
                      RAW / "jhu_csse_global/time_series_covid19_deaths_global.csv", "KOR")
    ob = build_observed(j.new_cases, "cases", "KOR", "jhu", "2020-01-23", "2023-03-09")
    assert ob.y.sum() == pytest.approx(j.new_cases.loc["2020-01-23":"2023-03-09"].clip(lower=0).sum())
    assert 2.9e7 < ob.y.sum() < 3.2e7                     # 원자료 합 (2023-03-09 누적 30,615,522)
    o = S.owid_country(RAW / "owid_covid/owid-covid-data.csv", "KOR")
    assert Q.series_qc(o.new_cases)["weekly_reporting"]   # OWID 현재 파일은 주간 보고 형식
