"""P(n, tau) 해석 검증 (docs/MODEL.md 2절).

1) 재감염이 없을 때(Lambda = 0), R^P_l -> R^W_l (율 lambda) 의 감수성 기댓값은
   정확히 P(l+1, tau) 이다. 사건 목록에서 만든 선형 동역학으로 확인한다.
2) Lambda > 0 이면 두 상태 마르코프 모형의 생존확률은 시간가변 위험률 모형
   exp(-int Lambda P(l+1, s) ds) 보다 크거나 같다 (Jensen 부등식). 차이는 Lambda 의 2차이다.
"""

import numpy as np
import pytest

from conftest import make_params
from seir_sim.model import functions as F
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet


def _expm(A):
    """scaling-and-squaring + Taylor 급수 (고유분해 없이, 결함 행렬에도 안전)."""
    norm = np.linalg.norm(A, 1)
    s = max(0, int(np.ceil(np.log2(norm / 0.5))) if norm > 0 else 0)
    B = A / 2.0 ** s
    E, term = np.eye(A.shape[0]), np.eye(A.shape[0])
    for k in range(1, 30):
        term = term @ B / k
        E = E + term
    for _ in range(s):
        E = E @ E
    return E


@pytest.mark.parametrize("M", [1, 3, 4])
def test_mean_susceptibility_equals_P_next_tau(M):
    p = make_params(M=M, lam=1 / 90, alpha=0.8)
    sysm = ReactionSystem(p, RegionSet.single(1e6))
    L = sysm.layout
    # 감염자 0 -> drift 는 상태에 선형. 유한차분으로 행렬을 정확히 얻는다
    base = L.empty()
    A = np.zeros((L.ncomp, L.ncomp))
    for c in range(L.ncomp):
        e = base.copy()
        e[0, c] = 1.0
        A[:, c] = sysm.drift(e, 0.0)[0]
    for l in range(1, M + 1):
        x0 = np.zeros(L.ncomp)
        x0[L.RP(l)] = 1.0
        for tau in (0.0, 10.0, 90.0, 400.0):
            x = _expm(A * tau) @ x0
            mean_susc = float(p.P(l + 1)) * x[L.RP(l)] + p.P1 * x[L.RW(l)]
            expected = F.susceptibility_waning(l + 1, tau, p.P1, p.Pmin, p.alpha, p.lam)
            assert x[L.RP(l)] + x[L.RW(l)] == pytest.approx(1.0, abs=1e-12)
            assert mean_susc == pytest.approx(float(expected), abs=1e-12)


def _markov_survival(Lam, Pn, P1, lam, tau):
    hP, hW = Lam * Pn, Lam * P1
    pP = np.exp(-(lam + hP) * tau)
    if np.isclose(lam + hP, hW):
        pW = lam * tau * np.exp(-hW * tau)
    else:
        pW = lam / (lam + hP - hW) * (np.exp(-hW * tau) - np.exp(-(lam + hP) * tau))
    return pP + pW


def _hazard_survival(Lam, Pn, P1, lam, tau):
    integral = P1 * tau - (P1 - Pn) * (1 - np.exp(-lam * tau)) / lam
    return np.exp(-Lam * integral)


def test_markov_vs_hazard_model_jensen_and_second_order():
    p = make_params()
    Pn, P1, lam = float(p.P(2)), p.P1, p.lam
    tau = 120.0
    diffs = []
    for Lam in (0.02, 0.01, 0.005, 0.002, 0.001, 0.0005):
        sm = _markov_survival(Lam, Pn, P1, lam, tau)
        sh = _hazard_survival(Lam, Pn, P1, lam, tau)
        assert sm >= sh - 1e-15
        diffs.append(sm - sh)
    # 2차 (Lambda tau << 1): Lambda 를 절반으로 하면 차이는 약 1/4
    assert diffs[3] / diffs[4] == pytest.approx(4.0, rel=0.1)
    assert diffs[4] / diffs[5] == pytest.approx(4.0, rel=0.05)
    # P(n+1) = P1 이면 두 모형이 같다
    assert _markov_survival(0.02, P1, P1, lam, tau) == pytest.approx(_hazard_survival(0.02, P1, P1, lam, tau))
