"""관측 모형: 모형의 실제 감염 흐름 -> 보고되는 확진·사망의 기댓값과 우도.

확진 (보고일 d):  mu_c(d) = rho * sum_s ons(d - s) * p_c(s) * w_c(wd(d))
  - ons: 발병 흐름 (E -> I), rho: 보고율 (확진으로 보고되는 감염의 비율)
  - p_c: 발병 -> 보고 지연 분포 (이산화 감마, 평균 delay_c, 변동계수 cv)
  - w_c: 요일 효과 (7개, 기하평균 1)
사망 (보고일 d):  mu_d(d) = sum_s deaths(d - s) * p_d(s) * w_d(wd(d))
  - deaths: 모형의 사망 흐름 (I -> D), p_d: 모형 사망 시점 -> 사망 보고 지연
관측: 구간 k 의 합 y_k ~ NegBin(평균 = 구간 기댓값 합, 크기 r)  (Var = mu + mu^2 / r)
"""

from __future__ import annotations

import numpy as np
from scipy.special import gammaln
from scipy.stats import gamma as gamma_dist


def discretized_gamma(mean: float, cv: float, max_lag: int) -> np.ndarray:
    """P(lag = s), s = 0..max_lag. 구간 [s - 0.5, s + 0.5) (s = 0 은 [0, 0.5)) 의 감마 확률, 합 1 로 정규화."""
    if mean <= 0:
        p = np.zeros(max_lag + 1)
        p[0] = 1.0
        return p
    shape = 1.0 / cv ** 2
    scale = mean / shape
    edges = np.concatenate([[0.0], np.arange(0.5, max_lag + 1.0, 1.0)])
    cdf = gamma_dist.cdf(edges, shape, scale=scale)
    p = np.diff(cdf)
    p = np.append(p, 0.0)[: max_lag + 1] if p.size < max_lag + 1 else p[: max_lag + 1]
    return p / p.sum()


def convolve_causal(x: np.ndarray, pmf: np.ndarray) -> np.ndarray:
    """y(d) = sum_{s=0}^{L} x(d - s) pmf(s)  (d - s < 0 은 0)."""
    return np.convolve(x, pmf)[: x.size]


def weekday_multipliers(log_w6: np.ndarray) -> np.ndarray:
    """6개 자유 매개변수 -> 7개 요일 승수 (log 의 합 0 = 기하평균 1)."""
    lw = np.append(log_w6, -np.sum(log_w6))
    return np.exp(lw)


def window_sums(daily: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    c = np.concatenate([[0.0], np.cumsum(daily)])
    return c[end + 1] - c[start]


def nb_logpmf(y: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    mu = np.maximum(mu, 1e-10)
    return (gammaln(y + r) - gammaln(r) - gammaln(y + 1) + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))


def poisson_logpmf(y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    mu = np.maximum(mu, 1e-10)
    return y * np.log(mu) - mu - gammaln(y + 1)
