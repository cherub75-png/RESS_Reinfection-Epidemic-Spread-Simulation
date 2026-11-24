"""기준 모델 (모두 기점까지의 주간 이력만 쓴다).

점 예측은 log(1 + y) 척도에서 정의한다.
  - persistence:   마지막 주 값을 그대로 이어간다.
  - trend:         마지막 1주 로그 변화 g 를 감쇠해 이어간다. log(1+y_{t+h}) = log(1+y_t) + g sum_{k=1..h} phi^k,
                   phi = 0.75 (사전에 정한 값, 시험 기간 자료로 조정하지 않음)
  - seasonal52:    52주 전 같은 주의 값 (1년 계절 단순 예측). 이력이 52주 + 오차 8개 이상일 때만.
분포: 같은 방법을 과거 기점들에 적용했을 때의 로그 오차 e = log(1+y) - 점 예측 의 경험 분위수를 더한다.
  오차는 기점까지 관측이 끝난 쌍만 쓴다 (확장 창). persistence 는 오차를 대칭화한다 (중앙값 = 마지막 값;
  COVID-19 Forecast Hub 기준 모델과 같은 생각).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import QUANTILES

PHI = 0.75
MIN_ERRORS = 8
METHODS = ("persistence", "trend", "seasonal52")


def _point_log(lv: np.ndarray, i: int, h: int, method: str) -> float:
    """lv = log(1 + 주간 이력), i = 기점 주 색인. NaN 이면 예측 불가."""
    if method == "persistence":
        return lv[i]
    if method == "trend":
        if i < 1:
            return np.nan
        g = lv[i] - lv[i - 1]
        return lv[i] + g * sum(PHI ** k for k in range(1, h + 1))
    if method == "seasonal52":
        j = i + h - 52
        return lv[j] if j >= 0 else np.nan
    raise KeyError(method)


def baseline_forecast(hist: pd.Series, method: str, horizons=(1, 2, 3, 4), quantiles=QUANTILES,
                      min_errors: int = MIN_ERRORS):
    """hist: 기점까지의 주간 합 (마지막 원소 = 기점 주). 반환 [H, Q] 분위수 또는 None (이력 부족)."""
    lv = np.log1p(hist.to_numpy(dtype=float))
    n = lv.size
    i0 = n - 1
    if not np.isfinite(lv[i0]):
        return None
    out = np.empty((len(horizons), quantiles.size))
    for a, h in enumerate(horizons):
        p = _point_log(lv, i0, h, method)
        if not np.isfinite(p):
            return None
        err = []
        for i in range(0, n - h):                 # 과거 기점 i 의 h 주 뒤 관측이 이력 안에 있음
            pi = _point_log(lv, i, h, method)
            if np.isfinite(pi) and np.isfinite(lv[i + h]):
                err.append(lv[i + h] - pi)
        if len(err) < min_errors:
            return None
        err = np.asarray(err)
        if method == "persistence":
            err = np.concatenate([err, -err])
        out[a] = np.expm1(np.maximum(p + np.quantile(err, quantiles), 0.0))
    return out
