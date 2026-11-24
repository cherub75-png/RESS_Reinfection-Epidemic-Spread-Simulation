"""확률적 적분기가 공통으로 쓰는 numba 커널.

Python 의 ReactionSystem.force_of_infection / propensities 와 같은 식을 계산한다.
같은지는 tests/test_ctmc.py::test_kernels_match_python 에서 검사한다.
"""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def force_of_infection(x, K, ncomp, I0, M, alive_end, Tn, C, gc, lam_out):
    """Lambda_i = gc_i sum_j C_ij [sum_k T(k) I_{k,j}] / N_j  (N_j = 0 이면 0). x 는 평탄화 상태."""
    ratio = np.zeros(K)
    for j in range(K):
        base = j * ncomp
        N = 0.0
        for c in range(alive_end):
            N += x[base + c]
        if N > 0.0:
            s = 0.0
            for k in range(M):
                s += Tn[k] * x[base + I0 + k]
            ratio[j] = s / N
    for i in range(K):
        acc = 0.0
        for j in range(K):
            acc += C[i, j] * ratio[j]
        lam_out[i] = gc[i] * acc


@njit(cache=True)
def propensities(x, src, const, susc, region, lam, a_out):
    """a_j = (k_j + s_j Lambda_{r_j}) x[src_j]. 합 a0 를 반환한다."""
    a0 = 0.0
    for j in range(src.size):
        v = (const[j] + susc[j] * lam[region[j]]) * x[src[j]]
        a_out[j] = v
        a0 += v
    return a0


@njit(cache=True)
def mobility_propensities(x, K, ncomp, alive_end, out_rate, m_out):
    """지역별 이동 율 out_i N_i. 합을 반환한다."""
    tot = 0.0
    for i in range(K):
        N = 0.0
        b = i * ncomp
        for c in range(alive_end):
            N += x[b + c]
        v = out_rate[i] * N
        m_out[i] = v
        tot += v
    return tot


@njit(cache=True)
def pick_destination(i, u, indptr, indices, cumprob):
    """omega_ij / out_i 확률로 도착지 j 를 고른다 (u in [0,1))."""
    lo, hi = indptr[i], indptr[i + 1]
    for k in range(lo, hi):
        if u < cumprob[k]:
            return indices[k]
    return indices[hi - 1]
