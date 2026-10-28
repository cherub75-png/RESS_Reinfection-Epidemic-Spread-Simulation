"""분석용 관측 시계열: 원자료(일별 발생 수)를 "관측 구간" 목록으로 바꾼다.

관측 구간 k 는 날짜 [start_k, end_k] (양 끝 포함) 동안의 발생 합 y_k 이다. 관측 모형은 같은 구간의
모형 발생 합과 y_k 를 비교한다. 원자료 값은 바꾸지 않고, 다음 규칙만 적용한다 (모두 flags 에 기록).

1. 음수 (소급 정정): 그 날은 관측에서 뺀다 (결측). 값을 보간하지 않는다.
2. 보고 공백: 직전 7일 평균이 gap_min_mean 이상인데 0 인 날(최대 3일 연속)과, 그 뒤 첫 양수 날을 한 구간으로 합친다.
   (보고가 없던 날의 발생이 다음 날 몰아서 보고된 것으로 본다)
3. 주간 보고 (quality.series_qc 의 weekly_reporting): 보고일로 끝나는 7일 구간으로 합친다.
4. 결측(NaN): 관측에서 뺀다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .quality import series_qc


@dataclass
class ObservedSeries:
    variable: str
    location: str
    source: str
    dates: pd.DatetimeIndex                 # 연속된 날짜 (모형 시간축)
    start: np.ndarray                       # 구간 시작 색인 (dates 기준)
    end: np.ndarray                         # 구간 끝 색인 (포함)
    y: np.ndarray                           # 구간 관측 합
    flags: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return int(self.y.size)

    def window_lengths(self) -> np.ndarray:
        return self.end - self.start + 1

    def restrict(self, last_date) -> "ObservedSeries":
        """last_date 까지 끝나는 구간만 남긴다 (시간순 검증에서 미래 자료를 막는 데 쓴다)."""
        last = pd.Timestamp(last_date)
        keep = self.dates[self.end] <= last
        return ObservedSeries(self.variable, self.location, self.source, self.dates, self.start[keep],
                              self.end[keep], self.y[keep], {**self.flags, "restricted_to": str(last.date())})

    def to_daily(self) -> pd.Series:
        """1일 구간만 날짜별 값으로, 여러 날 구간은 끝날에 합을 둔 시리즈 (그림·기준 모델용)."""
        s = pd.Series(np.nan, index=self.dates)
        s.iloc[self.end] = self.y
        return s


def build_observed(s: pd.Series, variable: str, location: str, source: str, start=None, end=None,
                   gap_min_mean: float = 20.0) -> ObservedSeries:
    s = s.astype(float)
    if start or end:
        s = s.loc[start:end]
    s = s.asfreq("D")
    dates = s.index
    v = s.to_numpy()
    flags = {"n_days": int(v.size), "rule_version": 1}
    weekly = series_qc(s)["weekly_reporting"]
    flags["weekly_reporting"] = bool(weekly)
    neg = np.flatnonzero(v < 0)
    flags["negative_days_excluded"] = [str(dates[i].date()) for i in neg]
    v = v.copy()
    v[neg] = np.nan

    starts, ends, ys = [], [], []
    if weekly:
        pos = np.flatnonzero(np.nan_to_num(v) > 0)
        prev = -1
        for i in pos:
            lo = max(prev + 1, i - 6)
            seg = v[lo:i + 1]
            if np.isnan(seg).any():
                prev = i
                continue
            starts.append(lo)
            ends.append(i)
            ys.append(float(np.nansum(seg)))
            prev = i
        flags["aggregation"] = "weekly windows ending on reporting days"
    else:
        trailing = pd.Series(v).rolling(7, min_periods=5).mean().shift(1).to_numpy()
        merged = []
        i = 0
        n = v.size
        while i < n:
            if np.isnan(v[i]):
                i += 1
                continue
            if v[i] == 0 and trailing[i] >= gap_min_mean:
                j = i
                while j < n and j - i < 3 and v[j] == 0:
                    j += 1
                if j < n and not np.isnan(v[j]) and v[j] > 0:
                    starts.append(i)
                    ends.append(j)
                    ys.append(float(v[i:j + 1].sum()))
                    merged.append(str(dates[i].date()))
                    i = j + 1
                    continue
            starts.append(i)
            ends.append(i)
            ys.append(float(v[i]))
            i += 1
        flags["gap_windows_merged"] = merged
        flags["aggregation"] = "daily, gap days merged with next positive day"
    return ObservedSeries(variable, location, source, dates, np.array(starts, dtype=np.int64),
                          np.array(ends, dtype=np.int64), np.array(ys), flags)


def build_weekly(s: pd.Series, variable: str, location: str, source: str, start=None, end=None,
                 week_end: str = "SUN") -> ObservedSeries:
    """일별 발생 수를 week_end 요일로 끝나는 7일 합 구간으로 바꾼다 (시간순 예측용).

    - 7일이 모두 있는 주만 쓴다 (NaN 이 하나라도 있으면 그 주는 뺀다).
    - 소급 정정(음수)은 그 주의 합에 그대로 포함한다. 주 합이 음수면 그 주를 뺀다.
    - 주 합은 보고 요일 구성(매일·주 몇 회·주 1회)에 영향을 덜 받으므로 국가 간 보고 방식 차이에 강하다.
    """
    s = s.astype(float)
    if start or end:
        s = s.loc[start:end]
    s = s.asfreq("D")
    dates = s.index
    v = s.to_numpy()
    dow = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}[week_end]
    ends = np.flatnonzero(np.asarray(dates.dayofweek) == dow)
    ends = ends[ends >= 6]
    starts = ends - 6
    c = np.concatenate([[0.0], np.cumsum(np.nan_to_num(v))])
    nan_c = np.concatenate([[0], np.cumsum(np.isnan(v))])
    y = c[ends + 1] - c[starts]
    complete = (nan_c[ends + 1] - nan_c[starts]) == 0
    keep = complete & (y >= 0)
    flags = {"n_days": int(v.size), "aggregation": f"weekly sums ending {week_end}", "rule_version": 1,
             "weeks_incomplete_excluded": int((~complete).sum()),
             "weeks_negative_excluded": [str(dates[e].date()) for e in ends[complete & (y < 0)]],
             "negative_days_included": int(np.sum(v < 0))}
    return ObservedSeries(variable, location, source, dates, starts[keep].astype(np.int64),
                          ends[keep].astype(np.int64), y[keep], flags)
