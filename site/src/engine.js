// 재감염 SEIR 방정식(작업 지시서 1절)의 브라우저용 ODE 엔진.
// Python seir_sim.inference.fastode (고정 간격 RK4, 하루 nsub 단계, 하루 안에서 g·u 상수) 와 같은 식·같은 순서로 계산한다.
// 일치는 site/test/engine_vs_python.mjs 가 Python 결과와 비교해 확인한다.
// 상태 배치 (지역 i): S, E_1..E_M, I_1..I_M, R^P_1..R^P_M, R^W_1..R^W_M, D  (ncomp = 4M + 2)
(function (root) {
  "use strict";

  function layout(M) {
    return { M, ncomp: 4 * M + 2, S: 0, E: (n) => n, I: (n) => M + n, RP: (n) => 2 * M + n, RW: (n) => 3 * M + n, D: 4 * M + 1 };
  }

  // 1.2절 함수
  const P = (n, p) => p.Pmin + (p.P1 - p.Pmin) * Math.exp(-p.alpha * (n - 1));
  const T = (n, p) => p.T1 * Math.pow(n, -p.beta);
  const f = (n, p) => p.f1 * Math.pow(n, -p.phiDelta);

  // reference 기준 (단일 지역, rho = rho_ref, g = 1, u = 0): R0 = c0 P1 T1 / gamma
  function c0Reference(R0, p) { return (R0 * p.gamma) / (p.P1 * p.T1); }

  // ds: {population[K], density[K], C: 행 우선 K*K, omega: {indptr, indices, values}}, p: 감염병 값, opt: {eta, useMobility, useCommuting}
  function buildModel(ds, p, opt) {
    const K = ds.population.length, M = p.M, L = layout(M), nc = L.ncomp;
    const src = [], dst = [], kc = [], ks = [], reg = [], kind = [];
    const add = (i, a, b, c, s, k) => { src.push(i * nc + a); dst.push(i * nc + b); kc.push(c); ks.push(s); reg.push(i); kind.push(k); };
    const m = (l) => Math.min(l + 1, M);
    for (let i = 0; i < K; i++) {
      add(i, L.S, L.E(1), 0, p.P1, 0);                                   // INFECT_S
      for (let l = 1; l <= M; l++) {
        add(i, L.RP(l), L.E(m(l)), 0, P(l + 1, p), 1);                   // REINF_P: P(l+1)
        add(i, L.RW(l), L.E(m(l)), 0, p.P1, 2);                          // REINF_W
      }
      for (let n = 1; n <= M; n++) {
        add(i, L.E(n), L.I(n), p.sigma, 0, 3);                            // PROGRESS
        add(i, L.I(n), L.RP(n), (1 - f(n, p)) * p.gamma, 0, 4);           // RECOVER
        add(i, L.I(n), L.D, f(n, p) * p.gamma, 0, 5);                     // DIE
        add(i, L.RP(n), L.RW(n), p.lam, 0, 6);                            // WANE
      }
    }
    const Tn = new Float64Array(M);
    for (let n = 1; n <= M; n++) Tn[n - 1] = T(n, p);
    // h(rho) = (rho / rho_ref)^eta, rho_ref = 인구가중 평균 밀도
    let sNr = 0, sN = 0;
    for (let i = 0; i < K; i++) { sNr += ds.population[i] * ds.density[i]; sN += ds.population[i]; }
    const rhoRef = sNr / sN, h = new Float64Array(K);
    for (let i = 0; i < K; i++) h[i] = Math.pow(ds.density[i] / rhoRef, opt.eta);
    const c0 = c0Reference(p.R0, p);
    const C = new Float64Array(K * K);
    if (opt.useCommuting) C.set(ds.C); else for (let i = 0; i < K; i++) C[i * K + i] = 1;
    const out = new Float64Array(K);
    let om = { indptr: new Int32Array(K + 1), indices: new Int32Array(0), values: new Float64Array(0) };
    if (opt.useMobility) {
      om = { indptr: Int32Array.from(ds.omega.indptr), indices: Int32Array.from(ds.omega.indices), values: Float64Array.from(ds.omega.values) };
      for (let i = 0; i < K; i++) for (let k = om.indptr[i]; k < om.indptr[i + 1]; k++) out[i] += om.values[k];
    }
    return { K, M, L, nc, src: Int32Array.from(src), dst: Int32Array.from(dst), kc: Float64Array.from(kc), ks: Float64Array.from(ks),
      reg: Int32Array.from(reg), kind: Int8Array.from(kind), Tn, C, out, om, baseC: Float64Array.from(h, (v) => c0 * v), c0, h, rhoRef };
  }

  // dx = 우변. gc[i] = g_i c0 h_i (1 - u_i)
  function rhs(md, x, gc, dx, lam, ratio) {
    const { K, M, nc, L, src, dst, kc, ks, reg, Tn, C, out, om } = md, aliveEnd = L.D;
    dx.fill(0);
    for (let j = 0; j < K; j++) {
      const b = j * nc; let N = 0, s = 0;
      for (let c = 0; c < aliveEnd; c++) N += x[b + c];
      for (let k = 0; k < M; k++) s += Tn[k] * x[b + 1 + M + k];
      ratio[j] = N > 0 ? s / N : 0;
    }
    for (let i = 0; i < K; i++) { let a = 0; const r = i * K; for (let j = 0; j < K; j++) a += C[r + j] * ratio[j]; lam[i] = gc[i] * a; }
    for (let j = 0; j < src.length; j++) {
      const a = (kc[j] + ks[j] * lam[reg[j]]) * x[src[j]];
      dx[src[j]] -= a; dx[dst[j]] += a;
    }
    for (let i = 0; i < K; i++) {
      if (out[i] === 0) continue;
      for (let c = 0; c < aliveEnd; c++) {
        const v = x[i * nc + c]; if (v === 0) continue;
        dx[i * nc + c] -= out[i] * v;
        for (let k = om.indptr[i]; k < om.indptr[i + 1]; k++) dx[om.indices[k] * nc + c] += om.values[k] * v;
      }
    }
  }

  // 초기 상태: 지역별 인구 N, 발생 [{k, I, E}], 시작 시 면역 비율 (R^P_1 에 둠; 웹 시나리오와 같은 규약)
  function initialState(md, N, seeds, immuneFraction) {
    const x = new Float64Array(md.K * md.nc), L = md.L;
    for (let i = 0; i < md.K; i++) {
      const imm = (immuneFraction || 0) * N[i];
      x[i * md.nc + L.RP(1)] = imm;
      x[i * md.nc + L.S] = N[i] - imm;
    }
    for (const s of seeds) {
      const b = s.k * md.nc;
      x[b + L.I(1)] += s.I; x[b + L.E(1)] += s.E || 0;
      x[b + L.S] -= s.I + (s.E || 0);
      if (x[b + L.S] < 0) throw new Error("초기 감염이 인구보다 많다");
    }
    return x;
  }

  // gcDay(d, gcOut): d 일의 gc 를 채운다. onDay(d, x): 매일 끝 상태 (d = 0 은 초기 상태). nsub: 하루 RK4 단계 수 (Python 과 같은 4)
  function simulate(md, x0, days, gcDay, onDay, nsub) {
    nsub = nsub || 4;
    const n = x0.length, x = Float64Array.from(x0);
    const k1 = new Float64Array(n), k2 = new Float64Array(n), k3 = new Float64Array(n), k4 = new Float64Array(n), xt = new Float64Array(n);
    const lam = new Float64Array(md.K), ratio = new Float64Array(md.K), gc = new Float64Array(md.K);
    const h = 1 / nsub;
    if (onDay && onDay(0, x) === false) return x;
    for (let d = 0; d < days; d++) {
      gcDay(d, gc);
      for (let s = 0; s < nsub; s++) {
        rhs(md, x, gc, k1, lam, ratio);
        for (let q = 0; q < n; q++) xt[q] = x[q] + 0.5 * h * k1[q];
        rhs(md, xt, gc, k2, lam, ratio);
        for (let q = 0; q < n; q++) xt[q] = x[q] + 0.5 * h * k2[q];
        rhs(md, xt, gc, k3, lam, ratio);
        for (let q = 0; q < n; q++) xt[q] = x[q] + h * k3[q];
        rhs(md, xt, gc, k4, lam, ratio);
        for (let q = 0; q < n; q++) x[q] += (h / 6) * (k1[q] + 2 * k2[q] + 2 * k3[q] + k4[q]);
      }
      if (onDay && onDay(d + 1, x) === false) break;
    }
    return x;
  }

  // 상태 요약: 지역별 S, E 합, I 합, D
  function summarize(md, x) {
    const { K, M, nc, L } = md, S = new Float64Array(K), E = new Float64Array(K), I = new Float64Array(K), D = new Float64Array(K), A = new Float64Array(K);
    for (let i = 0; i < K; i++) {
      const b = i * nc; S[i] = x[b]; D[i] = x[b + L.D];
      for (let k = 1; k <= M; k++) { E[i] += x[b + L.E(k)]; I[i] += x[b + L.I(k)]; }
      for (let c = 0; c < L.D; c++) A[i] += x[b + c];
    }
    return { S, E, I, D, alive: A };
  }

  // 재현 가능한 난수 (mulberry32)
  function rng(seed) {
    let a = seed >>> 0;
    return function () { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }

  const api = { layout, buildModel, rhs, initialState, simulate, summarize, c0Reference, rng, P, T, f };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.SEIR = api;
})(typeof self !== "undefined" ? self : this);
