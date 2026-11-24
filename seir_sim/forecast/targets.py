"""예측 대상과 기점 이전 이력.

예측 대상: 기점 t (일요일) 다음 주부터 h = 1..H 주의 주간 합 (월~일).
  y_{t,h} = sum of daily reports on days t + 7(h-1) + 1 .. t + 7h
이력: 기점 t 까지 끝나는 주간 합만 쓴다 (t 이후 자료는 어떤 방법도 보지 않는다).

한계 (모든 방법에 같게 적용): 자료는 최종판(revised vintage)이다. 실시간 예측 당시에는 나중에 정정된 값을
알 수 없었으므로, 이 검증의 성능은 실시간 성능보다 낙관적일 수 있다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (1, 2, 3, 4)


def rolling7(daily: pd.Series) -> pd.Series:
    """끝날 d 의 7일 합 (d-6..d). 7일 중 하나라도 결측이면 NaN. 음수 합은 NaN (소급 정정이 큰 주)."""
    d = daily.astype(float).asfreq("D")
    s = d.rolling(7, min_periods=7).sum()
    return s.where(s >= 0)


def weekly(daily: pd.Series, week_end: str = "SUN") -> pd.Series:
    """주간 합 (week_end 요일로 끝나는 주). 색인 = 주의 마지막 날."""
    s = rolling7(daily)
    dow = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}[week_end]
    return s[s.index.dayofweek == dow]


def origins(first: str, last: str, every_weeks: int = 2) -> pd.DatetimeIndex:
    o = pd.date_range(first, last, freq=f"{every_weeks * 7}D")
    assert np.all(o.dayofweek == o[0].dayofweek)
    return o


def truth(weekly_s: pd.Series, origin, horizons=HORIZONS) -> np.ndarray:
    t = pd.Timestamp(origin)
    idx = [t + pd.Timedelta(days=7 * h) for h in horizons]
    return weekly_s.reindex(idx).to_numpy(dtype=float)


def history(weekly_s: pd.Series, origin) -> pd.Series:
    return weekly_s.loc[: pd.Timestamp(origin)]
