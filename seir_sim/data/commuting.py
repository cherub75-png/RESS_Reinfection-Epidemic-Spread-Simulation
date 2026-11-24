"""통근 접촉 C: radiation 모형 (Simini et al. 2012, Nature 484:96) 으로 합성한다.

  T_ij ∝ m_i n_j / ((m_i + s_ij)(m_i + n_j + s_ij)),   s_ij = i 에서 거리 r_ij 안에 있는 인구 (i, j 제외)
  w_ij = T_ij / sum_{k != i} T_ik  (통근 목적지 분포, 행 합 1)

C 는 "i 주민의 접촉 중 j 주민과의 비율" (1.3절) 이다. 다음 두 가정 매개변수로 만든다.
  commute_fraction a_c: 다른 지역으로 통근하는 주민 비율
  destination_contact_share a_s: 통근자의 접촉 중 목적지에서 생기는 비율
  C_ij = a_c a_s w_ij (j != i),   C_ii = 1 - a_c a_s
두 값은 자료가 아니라 가정이며, 실제 통근 자료(인구총조사 OD 등)가 생기면 w 와 a_c 를 그 값으로 바꾼다.
radiation 모형은 매개변수 없이 목적지 분포만 정한다. 거리는 지역 대표 좌표 사이의 대원 거리다.
"""

from __future__ import annotations

import numpy as np

from .geo import distance_matrix_km


def radiation_shares(population: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    m = np.asarray(population, dtype=float)
    K = m.size
    d = distance_matrix_km(np.asarray(lon, float), np.asarray(lat, float))
    W = np.zeros((K, K))
    for i in range(K):
        order = np.argsort(d[i], kind="stable")
        ds, ms = d[i, order], m[order]
        cum = np.concatenate([[0.0], np.cumsum(ms)])
        # s_ij = 거리가 r_ij 보다 엄격히 가까운 지역의 인구 합에서 i 자신을 뺀 값 (j 는 포함되지 않음)
        s = cum[np.searchsorted(ds, d[i], side="left")] - m[i]
        s = np.maximum(s, 0.0)
        denom = (m[i] + s) * (m[i] + m + s)
        with np.errstate(divide="ignore", invalid="ignore"):
            row = np.where(denom > 0, m[i] * m / denom, 0.0)
        row[i] = 0.0
        tot = row.sum()
        if tot > 0:
            W[i] = row / tot
    return W


def contact_matrix(shares: np.ndarray, commute_fraction, destination_contact_share) -> np.ndarray:
    a = np.broadcast_to(np.asarray(commute_fraction, float) * np.asarray(destination_contact_share, float),
                        (shares.shape[0],))
    if np.any((a < 0) | (a > 1)):
        raise ValueError("commute_fraction * destination_contact_share 는 [0, 1] 이어야 한다")
    C = a[:, None] * shares
    np.fill_diagonal(C, 0.0)
    rows = C.sum(axis=1)
    no_dest = rows == 0                       # 목적지가 없는 지역(고립)은 자기 지역만
    C[np.arange(C.shape[0]), np.arange(C.shape[0])] = np.where(no_dest, 1.0, 1.0 - rows)
    return C
