"""1.4절 방정식을 문서 그대로 반복문으로 옮긴 참조 구현 (사건 목록과 독립).

사건 목록에서 만든 drift 가 이 식과 일치하는지 검사하는 데만 쓴다.
"""

import numpy as np

from seir_sim.model.functions import susceptibility, transmissibility


def reference_rhs(p, regions, h_values, g, u, X, layout):
    K, M = regions.K, p.M
    C, om = regions.contact, regions.mobility
    S = X[:, layout.S]
    E = {n: X[:, layout.E(n)] for n in range(1, M + 1)}
    I = {n: X[:, layout.I(n)] for n in range(1, M + 1)}
    RP = {n: X[:, layout.RP(n)] for n in range(1, M + 1)}
    RW = {n: X[:, layout.RW(n)] for n in range(1, M + 1)}

    def P(n):
        return float(susceptibility(n, p.P1, p.Pmin, p.alpha))

    def T(n):
        return float(transmissibility(n, p.T1, p.beta))

    def f(n):
        return float(p.f(np.array([n]))[0])

    def m(n):
        return min(n + 1, M)

    N = S + sum(E[n] + I[n] + RP[n] + RW[n] for n in range(1, M + 1))
    c = p.c0 * h_values * (1 - u)
    Lam = np.zeros(K)
    for i in range(K):
        acc = 0.0
        for j in range(K):
            if N[j] > 0:
                acc += C[i, j] * sum(T(k) * I[k][j] for k in range(1, M + 1)) / N[j]
        Lam[i] = g[i] * c[i] * acc

    def mob(Xc):
        out = np.zeros(K)
        for i in range(K):
            out[i] = sum(om[j, i] * Xc[j] - om[i, j] * Xc[i] for j in range(K))
        return out

    dX = np.zeros_like(X)
    dX[:, layout.S] = -p.P1 * Lam * S + mob(S)
    for n in range(1, M + 1):
        inflow = (p.P1 * S if n == 1 else 0.0) + sum(
            P(l + 1) * RP[l] + p.P1 * RW[l] for l in range(1, M + 1) if m(l) == n)
        dX[:, layout.E(n)] = Lam * inflow - p.sigma * E[n] + mob(E[n])
        dX[:, layout.I(n)] = p.sigma * E[n] - p.gamma * I[n] + mob(I[n])
        dX[:, layout.RP(n)] = ((1 - f(n)) * p.gamma * I[n] - (p.lam + P(n + 1) * Lam) * RP[n]
                               + mob(RP[n]))
        dX[:, layout.RW(n)] = p.lam * RP[n] - p.P1 * Lam * RW[n] + mob(RW[n])
    dX[:, layout.D] = p.gamma * sum(f(n) * I[n] for n in range(1, M + 1))
    return dX
