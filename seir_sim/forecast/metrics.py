"""예측 평가 지표.

- 점 예측(중앙값): MAE, RMSE, MASE (척도 = 기점까지 이력에서 1주 단순 예측의 평균 절대 오차)
- 분포 예측: WIS (Bracher et al. 2021, PLoS Comput Biol 17:e1008618), 표본 CRPS, 구간 포함률·폭
  WIS = (0.5 |y - m| + sum_k (alpha_k / 2) IS_alpha_k) / (K + 0.5),
  IS_alpha = (u - l) + (2/alpha)(l - y) 1{y < l} + (2/alpha)(y - u) 1{y > u}
  WIS = 2 x (분위수별 pinball 손실의 평균) 이다. 분위수 수준이 0..1 에 고르고 촘촘하면 CRPS 로 수렴하지만,
  여기의 9개 수준(구간 4개 + 중앙값)은 꼬리에 몰려 있어 CRPS 보다 작다. 그래서 WIS 는 같은 분위수 집합끼리만 비교한다.
- 로그 척도 WIS: log(1 + y) 와 log(1 + q) 로 계산한다 (규모가 다른 나라·시기를 비교하기 위함;
  Bosse et al. 2023, PLoS Comput Biol 19:e1011393 의 권고).
- 정점: 관측 주간 곡선의 정점 주 앞 1..4주 기점에서 중앙값 경로의 정점 시기·크기 오차
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

QUANTILES = np.array([0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975])
ALPHAS = (0.05, 0.1, 0.2, 0.5)


def _qidx(q: float) -> int:
    i = int(np.argmin(np.abs(QUANTILES - q)))
    assert abs(QUANTILES[i] - q) < 1e-9, q
    return i


def interval(qv: np.ndarray, alpha: float):
    return qv[..., _qidx(alpha / 2)], qv[..., _qidx(1 - alpha / 2)]


def wis(y: np.ndarray, qv: np.ndarray, log: bool = False) -> dict:
    """y [n], qv [n, Q]. 구성 요소 (dispersion, overprediction, underprediction) 도 돌려준다."""
    y = np.asarray(y, float)
    qv = np.asarray(qv, float)
    if log:
        y, qv = np.log1p(np.maximum(y, 0)), np.log1p(np.maximum(qv, 0))
    med = qv[..., _qidx(0.5)]
    disp = np.zeros_like(y)
    over = 0.5 * np.maximum(med - y, 0)
    under = 0.5 * np.maximum(y - med, 0)
    for a in ALPHAS:
        lo, hi = interval(qv, a)
        disp += a / 2 * (hi - lo)
        over += a / 2 * (2 / a) * np.maximum(lo - y, 0)
        under += a / 2 * (2 / a) * np.maximum(y - hi, 0)
    K = len(ALPHAS)
    return {"wis": (disp + over + under) / (K + 0.5), "dispersion": disp / (K + 0.5),
            "overprediction": over / (K + 0.5), "underprediction": under / (K + 0.5)}


def crps_samples(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """표본 CRPS: E|X - y| - 0.5 E|X - X'|. y [n], X [n, S]."""
    X = np.sort(np.asarray(X, float), axis=1)
    S = X.shape[1]
    t1 = np.mean(np.abs(X - np.asarray(y, float)[:, None]), axis=1)
    w = 2 * np.arange(1, S + 1) - S - 1                     # sum_{i<j} |x_j - x_i| = sum_i (2i - S - 1) x_(i)
    t2 = (X * w).sum(axis=1) / S ** 2
    return t1 - t2


def coverage(y, qv, alpha) -> np.ndarray:
    lo, hi = interval(qv, alpha)
    return ((y >= lo) & (y <= hi)).astype(float)


def mase_scale(hist: pd.Series) -> float:
    """기점까지 주간 이력의 1주 단순 예측 평균 절대 오차 (결측 주는 건너뛴다). 0 이면 NaN."""
    v = hist.to_numpy(dtype=float)
    d = np.abs(np.diff(v))
    d = d[np.isfinite(d)]
    if d.size < 4 or d.mean() == 0:
        return np.nan
    return float(d.mean())


def point_metrics(y, med, scale=None) -> dict:
    e = np.asarray(med, float) - np.asarray(y, float)
    out = {"mae": float(np.mean(np.abs(e))), "rmse": float(np.sqrt(np.mean(e ** 2)))}
    if scale is not None:
        out["mase"] = float(np.nanmean(np.abs(e) / np.asarray(scale, float)))
    return out


def observed_peaks(weekly_s: pd.Series, prominence_log: float = np.log(2), min_weekly: float = 50.0) -> pd.DatetimeIndex:
    """관측 주간 곡선 log(1 + y) 의 정점 (양쪽으로 2배 이상 떨어지는 지역 최대, 주 50건 이상). 기준은 사전에 정한 값."""
    s = weekly_s.dropna()
    v = np.log1p(s.to_numpy())
    pk, _ = find_peaks(v, prominence=prominence_log)
    pk = pk[s.to_numpy()[pk] >= min_weekly]
    return s.index[pk]


def peak_errors(origin: pd.Timestamp, median_path: np.ndarray, weekly_s: pd.Series, peaks: pd.DatetimeIndex,
                horizons=(1, 2, 3, 4)):
    """기점 뒤 1..H 주 안에 관측 정점이 있으면 (예측 정점 주 - 관측 정점 주, log(예측 최대 / 관측 정점값)) 을 돌려준다."""
    tgt = [origin + pd.Timedelta(days=7 * h) for h in horizons]
    inside = [p for p in peaks if tgt[0] <= p <= tgt[-1]]
    if not inside:
        return None
    p = inside[0]
    k_obs = tgt.index(p)
    k_pred = int(np.argmax(median_path))
    return {"peak_date": str(p.date()), "weeks_before_peak": k_obs + 1,
            "timing_error_weeks": k_pred - k_obs,
            "log_size_ratio": float(np.log1p(np.max(median_path)) - np.log1p(weekly_s.loc[p]))}
