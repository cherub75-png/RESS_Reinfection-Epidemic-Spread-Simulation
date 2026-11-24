// 계산 작업자: 화면을 멈추지 않고 ODE 를 풀고, 계산되는 대로 결과를 보낸다 (실시간 표시).
importScripts("engine.js");

onmessage = (e) => {
  const q = e.data;
  try {
    run(q);
  } catch (err) {
    postMessage({ type: "error", message: String(err && err.message ? err.message : err) });
  }
};

function gcFn(md, q) {
  const K = md.K, u = new Float64Array(K), g = new Float64Array(K);
  return (d, gc) => {
    u.fill(0);
    for (const iv of q.interventions) if (d >= iv.start && d < iv.end) {
      if (iv.regions && iv.regions.length) for (const k of iv.regions) u[k] = Math.max(u[k], iv.value);
      else for (let i = 0; i < K; i++) u[i] = Math.max(u[i], iv.value);
    }
    g.fill(1);
    if (q.climate && q.climate.on) {
      const m = q.monthIdx[d], c = q.climate;
      for (let i = 0; i < K; i++) {
        const T = q.tavg[m][i], H = q.rh[m][i];
        g[i] = Number.isFinite(T) && Number.isFinite(H) ? Math.exp(c.aT * (T - c.Tref) + c.aH * (H - c.Href)) : 1;
      }
    }
    for (let i = 0; i < K; i++) gc[i] = md.baseC[i] * g[i] * (1 - u[i]);
  };
}

function run(q) {
  const days = q.days, ds = q.ds;
  const md = SEIR.buildModel(ds, q.p, q.opt);
  const K = md.K;
  const x0 = SEIR.initialState(md, ds.population, q.seeds, q.immune);
  // 중앙 경로: 지역별 I, E, D 와 전체 S, E, I, D 를 매일 기록하고 일정 간격으로 보낸다
  const I = new Float32Array((days + 1) * K), E = new Float32Array((days + 1) * K), D = new Float32Array((days + 1) * K);
  const tot = { S: new Float64Array(days + 1), E: new Float64Array(days + 1), I: new Float64Array(days + 1), D: new Float64Array(days + 1) };
  const every = Math.max(1, Math.round(days / 45));
  let sent = 0;
  const t0 = Date.now();
  const flush = (upto, final) => {
    postMessage({ type: final ? "central" : "partial", upto, from: sent, K,
      I: I.slice(sent * K, (upto + 1) * K), E: E.slice(sent * K, (upto + 1) * K), D: D.slice(sent * K, (upto + 1) * K),
      S_tot: tot.S.slice(sent, upto + 1), E_tot: tot.E.slice(sent, upto + 1), I_tot: tot.I.slice(sent, upto + 1), D_tot: tot.D.slice(sent, upto + 1),
      c0: md.c0, seconds: (Date.now() - t0) / 1000 });
    sent = upto + 1;
  };
  SEIR.simulate(md, x0, days, gcFn(md, q), (d, x) => {
    const s = SEIR.summarize(md, x);
    for (let i = 0; i < K; i++) { I[d * K + i] = s.I[i]; E[d * K + i] = s.E[i]; D[d * K + i] = s.D[i]; tot.S[d] += s.S[i]; tot.E[d] += s.E[i]; tot.I[d] += s.I[i]; tot.D[d] += s.D[i]; }
    if (d === days) flush(d, true);
    else if (d > 0 && d % every === 0) flush(d, false);
  }, 4);
  // 매개변수 불확실성: 범위 안에서 균등 추출 (재현 가능한 시드), 전체 I 와 D 의 5~95% 띠
  const R = q.draws || 0;
  if (R > 0) {
    const rnd = SEIR.rng(q.seed || 1), Iall = [], Dall = [], drawn = [];
    for (let r = 0; r < R; r++) {
      const p = { ...q.p };
      const d = {};
      for (const [k, lo, hi] of q.ranges) {
        const v = lo + (hi - lo) * rnd();
        d[k] = v;
        if (k === "R0") p.R0 = v;
        else if (k === "incubation") p.sigma = 1 / v;
        else if (k === "infectious") p.gamma = 1 / v;
        else if (k === "immunity") p.lam = v > 0 ? 1 / v : 0;
        else if (k === "f1") p.f1 = v;
      }
      drawn.push(d);
      const m2 = SEIR.buildModel(ds, p, q.opt);
      const xi = SEIR.initialState(m2, ds.population, q.seeds, q.immune);
      const ti = new Float64Array(days + 1), td = new Float64Array(days + 1);
      SEIR.simulate(m2, xi, days, gcFn(m2, q), (dd, x) => { const s = SEIR.summarize(m2, x); for (let i = 0; i < K; i++) { ti[dd] += s.I[i]; td[dd] += s.D[i]; } }, 4);
      Iall.push(ti); Dall.push(td);
      postMessage({ type: "drawProgress", done: r + 1, total: R });
    }
    const band = (arr, qq) => { const out = new Float64Array(days + 1), col = new Float64Array(arr.length);
      for (let d = 0; d <= days; d++) { for (let r = 0; r < arr.length; r++) col[r] = arr[r][d]; col.sort(); const pos = qq * (col.length - 1), lo = Math.floor(pos), hi = Math.ceil(pos); out[d] = col[lo] + (col[hi] - col[lo]) * (pos - lo); }
      return out; };
    postMessage({ type: "bands", I05: band(Iall, 0.05), I95: band(Iall, 0.95), D05: band(Dall, 0.05), D95: band(Dall, 0.95), draws: drawn });
  }
  postMessage({ type: "done", seconds: (Date.now() - t0) / 1000 });
}
