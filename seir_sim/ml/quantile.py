"""국가 공통 분위수 GBM 과 SEIR 잔차 보정 (하이퍼파라미터는 사전에 정한 값이며 시험 기간으로 조정하지 않는다).

ML 단독:  목표 = log(1 + y_{s,h}) - lc0(s).  분위수 q 마다 HistGradientBoostingRegressor(loss="quantile").
하이브리드: 목표 = log(1 + y_{s,h}) - log(1 + SEIR 중앙값_{s,h}).  특성 = ML 특성 + SEIR 예측 요약.
  학습 자료 = 이전 기점들의 SEIR 예측과, 기점까지 관측이 끝난 대상 (기점 t 에서 s + 7h <= t).
  학습 행이 MIN_HYBRID_ROWS 보다 적으면 보정하지 않고 SEIR 분위수를 그대로 쓴다 (기록 남김).
분위수 교차는 행마다 정렬해 없앤다.
early_stopping 은 끈다 (무작위 검증 분할을 쓰지 않기 위함).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from ..forecast.metrics import QUANTILES
from .features import FEATURES

ML_PARAMS = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=50,
                 l2_regularization=1.0, early_stopping=False, random_state=0)
HYBRID_PARAMS = dict(max_iter=200, learning_rate=0.05, max_leaf_nodes=7, min_samples_leaf=20,
                     l2_regularization=1.0, early_stopping=False, random_state=0)
MIN_ML_ROWS = 200
MIN_HYBRID_ROWS = 150
HYBRID_EXTRA = ["seir_dlog", "seir_logwidth"]


# OpenMP 스레드 수 (기본 1). 다른 계산과 CPU 를 나눠 쓸 때 스레드가 과다하면 학습이 수십 배 느려진다 (9단계 측정).
# 한가한 컴퓨터에서 한 작업만 돌릴 때는 SEIR_SIM_ML_THREADS 로 늘릴 수 있다 (random_state 고정; 스레드 수에 따라
# 부동소수 합산 순서가 달라 아주 작은 차이는 날 수 있다).
ML_THREADS = int(os.environ.get("SEIR_SIM_ML_THREADS", "1"))


def fit_quantile_models(X: pd.DataFrame, y: np.ndarray, params: dict, quantiles=QUANTILES):
    with threadpool_limits(limits=ML_THREADS, user_api="openmp"):
        return [HistGradientBoostingRegressor(loss="quantile", quantile=float(q), **params).fit(X, y) for q in quantiles]


def predict_quantiles(models, X: pd.DataFrame) -> np.ndarray:
    with threadpool_limits(limits=ML_THREADS, user_api="openmp"):
        P = np.column_stack([m.predict(X) for m in models])
    return np.sort(P, axis=1)


def fit_ml(train: pd.DataFrame, quantiles=QUANTILES):
    """train: features.training_rows 를 국가별로 이어 붙인 표. 행이 MIN_ML_ROWS 보다 적으면 None."""
    if len(train) < MIN_ML_ROWS:
        return None
    return fit_quantile_models(train[FEATURES + ["h"]], train["target"].to_numpy(), ML_PARAMS, quantiles)


def ml_predict(models, X0: pd.DataFrame, base: str = "lc0"):
    """X0: 기점 행 (h 별). 반환 [H, Q] 또는 None (기점 값이 결측)."""
    if models is None or not np.isfinite(X0[base]).all():
        return None
    dq = predict_quantiles(models, X0[FEATURES + ["h"]])
    return np.maximum(np.expm1(X0[base].to_numpy()[:, None] + dq), 0.0)


def ml_forecast(train: pd.DataFrame, X0: pd.DataFrame, quantiles=QUANTILES, base: str = "lc0"):
    return ml_predict(fit_ml(train, quantiles), X0, base)


def hybrid_features(X: pd.DataFrame, seir_q: np.ndarray, base: str = "lc0") -> pd.DataFrame:
    """seir_q [n, Q] (SEIR 주간 분위수). seir_dlog = log(1 + 중앙값) - base, seir_logwidth = log((1 + q95)/(1 + q05))."""
    X = X.copy()
    qi = {q: int(np.argmin(np.abs(QUANTILES - q))) for q in (0.05, 0.5, 0.95)}
    X["seir_dlog"] = np.log1p(seir_q[:, qi[0.5]]) - X[base].to_numpy()
    X["seir_logwidth"] = np.log1p(seir_q[:, qi[0.95]]) - np.log1p(seir_q[:, qi[0.05]])
    return X


def fit_hybrid(train: pd.DataFrame, quantiles=QUANTILES):
    """train: 열 FEATURES + h + HYBRID_EXTRA + resid (= log(1+y) - log(1+SEIR 중앙값)). 행이 부족하면 None."""
    if len(train) < MIN_HYBRID_ROWS:
        return None
    cols = FEATURES + ["h"] + HYBRID_EXTRA
    return fit_quantile_models(train[cols], train["resid"].to_numpy(), HYBRID_PARAMS, quantiles)


def hybrid_predict(models, X0: pd.DataFrame, seir_q0: np.ndarray, base: str = "lc0"):
    """반환 ([H, Q], 보정 여부). models 가 None 이면 SEIR 분위수를 그대로 돌려준다."""
    if models is None:
        return seir_q0, False
    cols = FEATURES + ["h"] + HYBRID_EXTRA
    Xh = hybrid_features(X0, seir_q0, base)
    dq = predict_quantiles(models, Xh[cols])
    med = seir_q0[:, int(np.argmin(np.abs(QUANTILES - 0.5)))]
    return np.maximum(np.expm1(np.log1p(med)[:, None] + dq), 0.0), True
