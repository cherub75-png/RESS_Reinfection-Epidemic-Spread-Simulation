"use strict";
// 재감염 SEIR 시뮬레이터 (브라우저 계산판). 계산은 worker.js (engine.js) 가 하고, 이 파일은 화면을 맡는다.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const nf = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });
function fmt(v, d) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (d !== undefined) return Number(v).toFixed(d);
  const a = Math.abs(v);
  if (a >= 1e8) return nf.format(v / 1e8) + "억";
  if (a >= 1e4) return nf.format(v / 1e4) + "만";
  if (a >= 100) return nf.format(Math.round(v));
  if (a >= 1) return nf.format(v);
  return a === 0 ? "0" : Number(v).toPrecision(2);
}
const pct = (v) => (v === null || v === undefined || !isFinite(v) ? "–" : (100 * v).toFixed(1) + "%");
const RAMP = ["--r0", "--r1", "--r2", "--r3", "--r4", "--r5", "--r6", "--r7"];
const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5"];
const getJSON = async (p) => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); };

let META = null;
const DS = {};
async function dataset(name) { if (!DS[name]) DS[name] = await getJSON(`data/${name}.json`); return DS[name]; }

// ------------------------------------------------------------------ 탭
const rendered = {};
function showTab(name) {
  for (const b of $$(".tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
  for (const s of ["sim", "flu", "val", "info"]) $(`#tab-${s}`).hidden = s !== name;
  if (!rendered[name]) { rendered[name] = true; ({ flu: renderFlu, val: renderVal, info: renderInfo })[name]?.(); }
  setTimeout(() => { if (name === "sim") wsFit(); if (name === "flu" && fluMap) fluMap.invalidateSize(); }, 60);
}
for (const b of $$(".tabs button")) b.addEventListener("click", () => showTab(b.dataset.tab));

// ------------------------------------------------------------------ 입력
const PFIELDS = [["p-inc", (d) => 1 / d.sigma], ["p-inf", (d) => 1 / d.gamma], ["p-imm", (d) => (d.lam > 0 ? 1 / d.lam : 0)], ["p-f1", (d) => d.f1],
  ["p-P1", (d) => d.P1], ["p-Pmin", (d) => d.Pmin], ["p-alpha", (d) => d.alpha], ["p-T1", (d) => d.T1], ["p-beta", (d) => d.beta], ["p-delta", (d) => d.phiDelta]];
const UNC = [["R0", "R0", "p-R0"], ["incubation", "잠복기 (일)", "p-inc"], ["infectious", "감염 기간 (일)", "p-inf"], ["immunity", "면역 유지 (일)", "p-imm"], ["f1", "첫 감염 치명률", "p-f1"]];
const val = (id) => +$("#" + id).value;
function params() {
  const d = META.disease_defaults;
  return { ...d, R0: val("p-R0"), sigma: 1 / val("p-inc"), gamma: 1 / val("p-inf"), lam: val("p-imm") > 0 ? 1 / val("p-imm") : 0, f1: val("p-f1"),
    P1: val("p-P1"), Pmin: val("p-Pmin"), alpha: val("p-alpha"), T1: val("p-T1"), beta: val("p-beta"), phiDelta: val("p-delta") };
}
function derived() {
  const p = params();
  if (!(p.R0 > 0 && p.sigma > 0 && p.gamma > 0 && p.P1 > 0 && p.T1 > 0)) { $("#p-derived").textContent = ""; return; }
  const k = p.R0 * p.gamma, r = 0.5 * (-(p.sigma + p.gamma) + Math.sqrt((p.sigma - p.gamma) ** 2 + 4 * p.sigma * k));
  $("#p-derived").textContent = `기준 조건에서 c0 = ${fmt(p.R0 * p.gamma / (p.P1 * p.T1), 4)}/일, 초기 증가율 ${fmt(r, 4)}/일` + (r > 0 ? ` (배가 시간 ${fmt(Math.log(2) / r, 1)}일)` : " (감소)");
}
function regionOptions(ds, value) {
  return ds.ids.map((id, i) => el("option", { value: id, selected: id === value }, `${ds.names[i]} (${id})`));
}
function addSeed(id, I = 10, E = 0) {
  const ds = DS[$("#f-ds").value]; if (!ds) return;
  const sel = el("select", { "aria-label": "발생 지역", onchange: wsRestyle }, ...regionOptions(ds, id));
  const row = el("div", { class: "r" }, el("label", {}, "지역", sel), el("label", {}, "I (감염 중)", el("input", { type: "number", value: I, min: 0 })),
    el("label", {}, "E (잠복)", el("input", { type: "number", value: E, min: 0 })),
    el("button", { type: "button", class: "ghost", "aria-label": "발생 지역 삭제", onclick: () => { row.remove(); wsRestyle(); } }, "삭제"));
  $("#seeds").append(row); wsRestyle();
}
function addInt(start = 30, end = 90, value = 0.3) {
  const ds = DS[$("#f-ds").value];
  const sel = el("select", { "aria-label": "개입 지역" }, el("option", { value: "" }, "모든 지역"), ...regionOptions(ds, null));
  const row = el("div", { class: "r int" }, el("label", {}, "시작일", el("input", { type: "number", value: start, min: 0 })),
    el("label", {}, "끝일", el("input", { type: "number", value: end, min: 1 })), el("label", {}, "u", el("input", { type: "number", value, min: 0, max: 0.99, step: 0.05 })),
    el("label", {}, "지역", sel), el("button", { type: "button", class: "ghost", "aria-label": "개입 삭제", onclick: () => row.remove() }, "삭제"));
  $("#ints").append(row);
}
function initUnc() {
  for (const [k, lab] of UNC) {
    const on = el("input", { type: "checkbox", id: `u-${k}` });
    const lo = el("input", { type: "number", id: `u-${k}-lo`, step: "any", disabled: true, "aria-label": `${lab} 하한` });
    const hi = el("input", { type: "number", id: `u-${k}-hi`, step: "any", disabled: true, "aria-label": `${lab} 상한` });
    on.addEventListener("change", () => {
      lo.disabled = hi.disabled = !on.checked;
      const cur = val(UNC.find((x) => x[0] === k)[2]);
      if (on.checked && lo.value === "" && cur > 0) { lo.value = +(cur * 0.8).toPrecision(3); hi.value = +(cur * 1.2).toPrecision(3); }
      renderSources();
    });
    $("#unc").append(el("div", { class: "unc-row" }, el("label", { class: "check" }, on, lab), el("label", {}, "하한", lo), el("label", {}, "상한", hi)));
  }
}
function ranges() {
  const out = [];
  for (const [k, lab] of UNC) if ($(`#u-${k}`).checked) {
    const lo = +$(`#u-${k}-lo`).value, hi = +$(`#u-${k}-hi`).value;
    if (!(lo < hi) || (k !== "immunity" && k !== "f1" && lo <= 0)) throw new Error(`불확실성 ${lab}: 0 < 하한 < 상한 이어야 한다`);
    out.push([k, lo, hi]);
  }
  return out;
}
function renderSources() {
  const t = $("#input-sources"); t.innerHTML = "";
  const ds = DS[$("#f-ds").value]; if (!ds) return;
  const pv = ds.provenance, a = pv.assumptions || {};
  const row = (k, v, tag, cls) => t.append(el("tr", {}, el("td", {}, k), el("td", {}, v, " ", el("span", { class: "tag " + cls }, tag))));
  const kor = ds.name === "KOR_admin1";
  row("경계", kor ? `통계청 SGIS 시도 경계 (${(pv.boundary_file || "").replace(/^sido_(\d{4})(\d\d)(\d\d).*/, "$1-$2-$3")}, ${ds.K}개 시도)` : `Natural Earth 국가 경계 (${ds.K}개)`, "실제 관측", "obs");
  row("인구", kor ? `WorldPop R2025A ${pv.population_year || 2025} (1 km 격자 합산)` : `World Bank WDI ${pv.population_year || 2025}`, kor ? "자료로 추정" : "실제 관측", kor ? "est" : "obs");
  row("기후", `ERA5 ${(pv.climate_periods || []).join(", ")} 월 평균`, "재분석", "mod");
  row("기후 효과 g", $("#f-clim").checked ? "사용자 가정 계수" : "쓰지 않음 (g = 1)", $("#f-clim").checked ? "사용자 입력" : "기본 가정값", $("#f-clim").checked ? "user" : "asm");
  row("항공 노선", "OpenFlights 노선 구조 (2014-06)", "실제 관측", "obs");
  row("이동 규모", `항공 ${fmt(a.air_trips_per_day)}회/일 · 통근 ${a.commute_fraction} · 접촉 ${a.destination_contact_share}`, "기본 가정값", "asm");
  const d = META.disease_defaults, p = params();
  const changed = ["R0", "sigma", "gamma", "lam", "f1", "P1", "Pmin", "alpha", "T1", "beta", "phiDelta"].filter((k) => Math.abs(p[k] - d[k]) > 1e-9 * Math.max(1, Math.abs(d[k]))).length;
  row("감염병 값", changed ? `${changed}개 사용자 입력, 나머지 COVID 유사 기본값` : "COVID 유사 코드 검증용 기본값", changed ? "사용자 입력" : "기본 가정값", changed ? "user" : "asm");
  let nr = 0; try { nr = ranges().length; } catch (_) { nr = 0; }
  if (nr) row("불확실성", `${nr}개 매개변수 범위, ${val("u-draws")}회`, "사용자 가정", "user");
}
async function onDataset() {
  const name = $("#f-ds").value;
  $("#run-msg").textContent = "지역 자료 불러오는 중…";
  const ds = await dataset(name);
  $("#run-msg").textContent = "";
  $("#seeds").innerHTML = ""; $("#ints").innerHTML = "";
  addSeed(name === "KOR_admin1" ? "KR-11" : "CHN", 10, 0);
  renderSources(); wsLoad(ds);
}

// ------------------------------------------------------------------ 지도 · 왼쪽 수치
const WS = { map: null, layer: null, ds: null, mode: "seed", data: null, frame: 0, timer: null, region: null, bins: null, start: null };
const seeded = () => new Set($$("#seeds .r select").map((s) => s.value));
function wsRestyle() { if (WS.layer) WS.layer.setStyle(wsStyle); }
function wsFit() { const b = $("#ws-map"); if (WS.map && WS.layer && b.clientWidth > 0) { WS.map.invalidateSize(); try { WS.map.fitBounds(WS.layer.getBounds(), { padding: [6, 6] }); } catch (_) { /* 빈 경계 */ } } }
function wsLoad(ds) {
  WS.ds = ds; WS.data = null; WS.idx = {}; ds.ids.forEach((id, k) => (WS.idx[id] = k));
  if (!window.L) { $("#ws-map").textContent = "지도 라이브러리를 불러오지 못했다 (네트워크 확인)."; return; }
  if (!WS.map) { WS.map = L.map("ws-map", { zoomSnap: 0.25, attributionControl: true }); WS.map.attributionControl.setPrefix(false); }
  if (WS.attr) WS.map.attributionControl.removeAttribution(WS.attr);
  WS.attr = ds.name === "KOR_admin1" ? "경계: 통계청 SGIS (공공누리 1유형), admdongkor" : "경계: Natural Earth";
  WS.map.attributionControl.addAttribution(WS.attr);
  if (WS.layer) WS.layer.remove();
  WS.layer = L.geoJSON(ds.geojson, { style: wsStyle, onEachFeature: (f, layer) => {
    layer.bindTooltip(() => wsTip(f), { sticky: true });
    layer.on("click", () => { if (WS.mode === "seed") { if (!seeded().has(f.id)) addSeed(f.id, 10, 0); } else { WS.region = f.id; wsRestyle(); wsRegionInfo(); } });
  } }).addTo(WS.map);
  setMode("seed"); $("#mode-result").disabled = true; $("#ws-play").disabled = true; $("#ws-slider").disabled = true;
  wsFit(); setTimeout(wsFit, 80);
}
function setMode(m) {
  WS.mode = m;
  $("#mode-seed").setAttribute("aria-pressed", String(m === "seed")); $("#mode-result").setAttribute("aria-pressed", String(m === "result"));
  $("#ws-note").textContent = m === "seed" ? "지도를 눌러 발생 지역을 고른다 (주황 = 고른 지역)." : "지역을 누르면 왼쪽에 그 지역 수치가 나온다. 색은 감염자 수 (로그 간격).";
  wsRestyle(); wsLegend();
}
$("#mode-seed").addEventListener("click", () => setMode("seed"));
$("#mode-result").addEventListener("click", () => { if (WS.data) setMode("result"); });
function wsValue(i, k) {
  const d = WS.data, L_ = $("#ws-layer").value, arr = d[L_];
  const v = arr[i * d.K + k];
  return $("#ws-scale").value === "per100k" ? (v / Math.max(WS.ds.population[k], 1)) * 1e5 : v;
}
function wsBins() {
  let mx = 0; const d = WS.data;
  for (let i = 0; i < d.n; i++) for (let k = 0; k < d.K; k++) { const v = wsValue(i, k); if (v > mx) mx = v; }
  const b = []; if (mx > 0) for (let i = 7; i >= 1; i--) b.push(mx / 2 ** (i * 1.2));
  WS.bins = { mx, b };
}
function wsStyle(f) {
  if (WS.mode === "seed" || !WS.data) return { color: css("--surface"), weight: 1, fillOpacity: 0.85, fillColor: seeded().has(f.id) ? css("--seed") : css("--r1") };
  const k = WS.idx[f.id], v = k === undefined ? null : wsValue(WS.frame, k);
  let col = css("--nodata");
  if (v !== null && isFinite(v)) { if (v < 1e-9) col = css("--surface-2"); else { let j = 0; while (j < WS.bins.b.length && v > WS.bins.b[j]) j++; col = css(RAMP[Math.min(j, 7)]); } }
  const sel = WS.region === f.id;
  return { color: sel ? css("--ink") : css("--surface"), weight: sel ? 2.5 : 1, fillOpacity: 0.92, fillColor: col };
}
function wsTip(f) {
  const k = WS.idx[f.id], pop = WS.ds.population[k];
  let t = `${esc(f.properties.name)} (${esc(f.id)})<br>인구 ${esc(fmt(pop))}`;
  if (WS.mode === "seed" || !WS.data) return t + "<br>누르면 발생 지역에 추가";
  const d = WS.data, i = WS.frame;
  return t + `<br>감염 중 I ${esc(fmt(d.I[i * d.K + k]))} (10만 명당 ${esc(fmt(d.I[i * d.K + k] / pop * 1e5))})<br>잠복 E ${esc(fmt(d.E[i * d.K + k]))} · 누적 사망 ${esc(fmt(d.D[i * d.K + k]))}`;
}
function wsLegend() {
  const lg = $("#ws-legend"); lg.innerHTML = "";
  if (WS.mode === "seed" || !WS.data) { lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css("--seed")}` }), "발생 지역"), el("span", {}, el("span", { class: "sw", style: `background:${css("--r1")}` }), "다른 지역")); return; }
  lg.append(`${$("#ws-layer").selectedOptions[0].text} (${$("#ws-scale").value === "per100k" ? "10만 명당" : "명"}):`);
  lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css("--surface-2")}` }), "0"));
  const edges = [0, ...WS.bins.b];
  for (let j = 0; j < 8 && j < edges.length; j++) lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css(RAMP[j])}` }), `≤${fmt(j + 1 < edges.length ? edges[j + 1] : WS.bins.mx)}`));
}
function frame(i) {
  const d = WS.data; if (!d) return;
  WS.frame = i = Math.min(i, d.n - 1); $("#ws-slider").value = i;
  wsRestyle();
  const N = d.Ntot, S = d.S[i], E = d.Et[i], I = d.It[i], D = d.Dt[i], R = N - S - E - I - D, cum = d.S[0] - S, nw = i > 0 ? d.S[i - 1] - S : 0;
  const date = new Date(WS.start.getTime() + i * 864e5).toISOString().slice(0, 10);
  $("#ws-time").textContent = `시작 후 ${i}일 · ${date}`;
  $("#lv-day").innerHTML = ""; $("#lv-day").append(el("b", { class: "big" }, `${i}일째`), date);
  let reached = 0; for (let k = 0; k < d.K; k++) if (d.I[i * d.K + k] + d.E[i * d.K + k] >= 1) reached++;
  const tiles = $("#lv-tiles"); tiles.innerHTML = "";
  const tile = (k, v, s) => tiles.append(el("div", { class: "tile" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v), s ? el("div", { class: "d" }, s) : ""));
  tile("감염 중 I", fmt(I), `인구의 ${pct(I / N)}`); tile("잠복 E", fmt(E)); tile("오늘 신규 첫 감염", fmt(Math.max(0, nw))); tile("누적 첫 감염", fmt(cum), pct(cum / N));
  tile("누적 사망 D", fmt(D)); tile("감염 지역", `${reached} / ${d.K}`, "I + E ≥ 1"); tile("회복·면역 R", fmt(R)); tile("감수성 S", fmt(S));
  spark(i);
  const top = $("#lv-top"); top.innerHTML = "";
  const per = WS.ds.ids.map((id, k) => ({ id, k, v: d.I[i * d.K + k] / Math.max(WS.ds.population[k], 1) * 1e5, n: d.I[i * d.K + k] })).filter((x) => x.n >= 1).sort((a, b) => b.v - a.v).slice(0, 5);
  if (!per.length) top.append(el("li", { class: "muted" }, "아직 없음"));
  for (const x of per) top.append(el("li", { onclick: () => { WS.region = x.id; wsRestyle(); wsRegionInfo(); } }, WS.ds.names[x.k], el("span", {}, fmt(x.v))));
  if (WS.region) wsRegionInfo();
}
function spark(i) {
  const d = WS.data, box = $("#lv-spark"), n = d.It.length, W = 240, H = 76;
  let mx = 1; for (let j = 0; j < n; j++) mx = Math.max(mx, d.It[j], d.band ? d.band.I95[j] : 0);
  const X = (j) => 2 + (j / Math.max(1, d.days)) * (W - 4), Y = (v) => H - 4 - (v / mx) * (H - 16);
  const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "전체 감염 중 인원 추이와 현재 시점");
  const mk = (t, a) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  if (d.band) { let p = ""; for (let j = 0; j <= d.days; j++) p += `${j ? "L" : "M"}${X(j)},${Y(d.band.I95[j])}`; for (let j = d.days; j >= 0; j--) p += `L${X(j)},${Y(d.band.I05[j])}`;
    svg.append(mk("path", { d: p + "Z", fill: css("--s1"), "fill-opacity": 0.18, stroke: "none" })); }
  let p = ""; for (let j = 0; j < n; j++) p += `${j ? "L" : "M"}${X(j)},${Y(d.It[j])}`;
  svg.append(mk("path", { d: p, fill: "none", stroke: css("--s1"), "stroke-width": 1.8 }));
  svg.append(mk("line", { x1: X(i), x2: X(i), y1: 2, y2: H - 2, stroke: css("--s2"), "stroke-width": 1.5 }));
  const t = mk("text", { x: 4, y: 11, "font-size": 10, fill: css("--ink-2") }); t.textContent = `전체 감염 중 I (최대 ${fmt(mx)})${d.band ? " · 띠 5~95%" : ""}`; svg.append(t);
  box.innerHTML = ""; box.append(svg);
}
function wsRegionInfo() {
  const k = WS.idx[WS.region], d = WS.data, box = $("#lv-region"); box.innerHTML = "";
  if (k === undefined || !d) return;
  const i = WS.frame;
  box.append(el("div", { class: "card", style: "margin-top:8px" }, el("strong", {}, `${WS.ds.names[k]} (${WS.region})`),
    el("div", { class: "note" }, `인구 ${fmt(WS.ds.population[k])} · 감염 중 ${fmt(d.I[i * d.K + k])} · 잠복 ${fmt(d.E[i * d.K + k])} · 누적 사망 ${fmt(d.D[i * d.K + k])}`),
    el("button", { type: "button", class: "ghost", onclick: () => { WS.region = null; wsRestyle(); box.innerHTML = ""; } }, "닫기")));
}
function play(on) {
  clearInterval(WS.timer); WS.timer = null;
  if (on === false || (on === undefined && $("#ws-play").textContent === "멈춤")) { $("#ws-play").textContent = "재생"; return; }
  $("#ws-play").textContent = "멈춤";
  WS.timer = setInterval(() => { if (!WS.data) return; let i = WS.frame + 1;
    if (i >= WS.data.n) { if (WS.data.complete) { play(false); return; } i = WS.data.n - 1; }
    frame(i); }, +$("#ws-speed").value);
}
$("#ws-play").addEventListener("click", () => play());
$("#ws-speed").addEventListener("change", () => { if (WS.timer) play(true); });
$("#ws-slider").addEventListener("input", () => { play(false); frame(+$("#ws-slider").value); });
for (const id of ["#ws-layer", "#ws-scale"]) $(id).addEventListener("change", () => { if (WS.data) { wsBins(); wsLegend(); frame(WS.frame); } });

// ------------------------------------------------------------------ 실행 (계산 작업자)
let worker = null;
function runScenario(e) {
  e.preventDefault();
  const ds = WS.ds; if (!ds) return;
  const msg = (t, err) => { $("#run-msg").textContent = t; $("#run-msg").className = "note" + (err ? " err" : ""); };
  let q;
  try {
    const days = Math.round(val("f-days")), p = params();
    if (!(days >= 1 && days <= 730)) throw new Error("기간은 1~730일");
    if (!(p.R0 > 0 && p.sigma > 0 && p.gamma > 0 && p.f1 >= 0 && p.f1 <= 1 && p.Pmin <= p.P1)) throw new Error("감염병 값 확인 (R0·기간 > 0, 0 ≤ 치명률 ≤ 1, Pmin ≤ P1)");
    const seeds = $$("#seeds .r").map((r) => { const ins = $$("input", r); return { k: WS.idx[$("select", r).value], I: +ins[0].value, E: +ins[1].value }; }).filter((s) => s.I + s.E > 0);
    if (!seeds.length) throw new Error("초기 감염자(I) 또는 잠복자(E) 가 1명 이상 필요하다");
    const ints = $$("#ints .r").map((r) => { const ins = $$("input", r), v = $("select", r).value; return { start: +ins[0].value, end: +ins[1].value, value: +ins[2].value, regions: v ? [WS.idx[v]] : null }; });
    for (const iv of ints) if (!(iv.end > iv.start && iv.value >= 0 && iv.value < 1)) throw new Error("개입: 끝일 > 시작일, 0 ≤ u < 1");
    const start = new Date($("#f-start").value + "T00:00:00Z"); if (isNaN(start)) throw new Error("시작일 확인");
    const monthIdx = new Int8Array(days + 1); for (let d = 0; d <= days; d++) monthIdx[d] = new Date(start.getTime() + d * 864e5).getUTCMonth();
    const rg = ranges();
    q = { ds: { population: ds.population, density: ds.density, C: ds.C, omega: ds.omega }, p,
      opt: { eta: val("f-eta"), useMobility: $("#f-mob").checked, useCommuting: $("#f-com").checked }, seeds, immune: val("f-immune") / 100, days,
      interventions: ints, climate: { on: $("#f-clim").checked, aT: val("c-aT"), aH: val("c-aH"), Tref: val("c-Tref"), Href: val("c-Href") },
      tavg: ds.tavg, rh: ds.rh, monthIdx, draws: rg.length ? Math.max(2, Math.min(100, Math.round(val("u-draws")))) : 0, ranges: rg, seed: 20260101 };
    WS.start = start;
  } catch (err) { msg("입력 오류: " + err.message, true); return; }
  if (worker) worker.terminate();
  worker = new Worker("worker.js");
  const K = ds.K, days = q.days;
  WS.data = { K, days, n: 0, I: new Float32Array((days + 1) * K), E: new Float32Array((days + 1) * K), D: new Float32Array((days + 1) * K),
    S: new Float64Array(days + 1), Et: new Float64Array(days + 1), It: new Float64Array(days + 1), Dt: new Float64Array(days + 1),
    Ntot: ds.population.reduce((a, b) => a + b, 0), complete: false, band: null };
  WS.frame = 0; WS.region = null; $("#lv-region").innerHTML = "";
  $("#run-progress").hidden = false; $("#rp-title").textContent = $("#f-title").value || "시나리오"; $("#rp-bar").style.width = "0";
  $("#lv-badge").textContent = "계산 중"; $("#lv-badge").className = "tag asm";
  $("#ws-slider").disabled = false; $("#ws-play").disabled = false; $("#mode-result").disabled = false;
  msg("계산 중… 지도와 왼쪽 수치가 계산되는 대로 바뀐다.");
  let first = true;
  worker.onmessage = (ev) => {
    const m = ev.data, d = WS.data;
    if (m.type === "partial" || m.type === "central") {
      d.I.set(m.I, m.from * K); d.E.set(m.E, m.from * K); d.D.set(m.D, m.from * K);
      d.S.set(m.S_tot, m.from); d.Et.set(m.E_tot, m.from); d.It.set(m.I_tot, m.from); d.Dt.set(m.D_tot, m.from);
      d.n = m.upto + 1; $("#ws-slider").max = d.n - 1;
      $("#rp-bar").style.width = `${Math.round((100 * m.upto) / days * (q.draws ? 0.5 : 1))}%`;
      $("#rp-state").textContent = `${m.upto} / ${days}일 계산 (${m.seconds.toFixed(1)}초)`;
      wsBins();
      if (first) { first = false; setMode("result"); }
      wsLegend();
      if (!WS.timer) frame(d.n - 1);
      if (m.type === "central") { d.complete = true; $("#lv-badge").textContent = q.draws ? "중앙값 경로 완료" : "완료"; $("#lv-badge").className = "tag sim"; }
    } else if (m.type === "drawProgress") {
      $("#rp-bar").style.width = `${Math.round(50 + (50 * m.done) / m.total)}%`; $("#rp-state").textContent = `불확실성 반복 ${m.done} / ${m.total}`;
    } else if (m.type === "bands") {
      d.band = { I05: m.I05, I95: m.I95, D05: m.D05, D95: m.D95 }; frame(WS.frame);
    } else if (m.type === "done") {
      $("#rp-bar").style.width = "100%"; $("#rp-state").textContent = `완료 (${m.seconds.toFixed(1)}초)`;
      $("#lv-badge").textContent = q.draws ? `완료 (${q.draws}회 불확실성)` : "완료"; $("#lv-badge").className = "tag sim";
      msg("완료. 재생 막대로 시점을 옮기거나 지역을 눌러 본다.");
      frame(WS.frame); worker.terminate(); worker = null;
    } else if (m.type === "error") { msg("계산 오류: " + m.message, true); $("#lv-badge").textContent = "오류"; }
  };
  worker.onerror = (er) => { msg("계산 오류: " + (er.message || "작업자 실패"), true); };
  worker.postMessage(q);
}
$("#form").addEventListener("submit", runScenario);

// ------------------------------------------------------------------ 선 그래프 (SVG)
function lineChart(box, o) {
  box.innerHTML = "";
  const W = Math.max(320, box.clientWidth || 600), H = o.height || 260, m = { l: 56, r: 12, t: 10, b: 30 };
  const xs = o.xs.map((x) => (x instanceof Date ? x.getTime() : x)), all = [];
  for (const s of o.series) { for (const v of s.values) if (v !== null && isFinite(v)) all.push(v); if (s.band) for (const b of s.band) for (const v of b) if (v !== null && isFinite(v)) all.push(v); }
  if (!all.length) { box.append(el("p", { class: "note" }, "표시할 값이 없다.")); return; }
  const y0 = o.yMin ?? Math.min(0, ...all), y1 = Math.max(...all) || 1, x0 = Math.min(...xs), x1 = Math.max(...xs) === x0 ? x0 + 1 : Math.max(...xs);
  const X = (x) => m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r), Y = (v) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", o.aria || "선 그래프");
  const mk = (t, a) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  const txt = (x, y, s, an) => { const t = mk("text", { x, y, "text-anchor": an, fill: css("--ink-2"), "font-size": 11 }); t.textContent = s; return t; };
  for (let i = 0; i < 5; i++) { const v = y0 + ((y1 - y0) * i) / 4; svg.append(mk("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: css("--grid") })); svg.append(txt(m.l - 6, Y(v) + 4, (o.yFormat || fmt)(v), "end")); }
  for (let i = 0; i < 5; i++) { const xi = x0 + ((x1 - x0) * i) / 4; svg.append(txt(X(xi), H - m.b + 16, o.xFormat(new Date(xi)), "middle")); }
  for (const s of o.series) {
    const col = css(s.color);
    if (s.band) { const [lo, hi] = s.band, seg = []; for (let i = 0; i < xs.length; i++) if (lo[i] !== null && hi[i] !== null) seg.push(i);
      if (seg.length) svg.append(mk("path", { d: seg.map((i, k) => `${k ? "L" : "M"}${X(xs[i])},${Y(hi[i])}`).join("") + seg.slice().reverse().map((i) => `L${X(xs[i])},${Y(lo[i])}`).join("") + "Z", fill: col, "fill-opacity": 0.18 })); }
    if (s.points) { for (let i = 0; i < xs.length; i++) if (s.values[i] !== null && isFinite(s.values[i])) svg.append(mk("circle", { cx: X(xs[i]), cy: Y(s.values[i]), r: 2.6, fill: col })); continue; }
    let d = "", pen = false; for (let i = 0; i < xs.length; i++) { const v = s.values[i]; if (v === null || !isFinite(v)) { pen = false; continue; } d += `${pen ? "L" : "M"}${X(xs[i])},${Y(v)}`; pen = true; }
    svg.append(mk("path", { d, fill: "none", stroke: col, "stroke-width": 2, "stroke-dasharray": s.dash || "" }));
  }
  box.append(svg);
}
function legend(box, items) { box.innerHTML = ""; for (const it of items) box.append(el("span", {}, el("span", { class: "sw", style: `background:${css(it.color)}${it.faint ? ";opacity:.4" : ""}` }), it.name)); }

// ------------------------------------------------------------------ 인플루엔자 최신 예측
const FLU_LABEL = { persistence: "지속", seasonal: "계절 평균", ml: "ML", ml_cal: "ML + 구간 보정", seir: "SEIR (보조)" };
const FLU_BINS = [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4];
let FLU = null, fluMap = null, fluLayer = null, WORLD = null;
const pp = (v) => (v === null || v === undefined || !isFinite(v) ? "–" : (100 * v).toFixed(1) + "%");
async function renderFlu() {
  try { FLU = await getJSON("data/flu_latest.json"); WORLD = await dataset("world_countries"); } catch (e) { $("#flu-info").textContent = "자료를 불러오지 못했다: " + e.message; return; }
  if (!FLU) { $("#flu-info").textContent = "인플루엔자 예측 결과가 없다."; return; }
  $("#flu-info").innerHTML = "";
  $("#flu-info").append(`기점 주 ${FLU.origin} (그 주까지의 자료만 사용) · 받은 자료의 마지막 주 ${FLU.data_last_week} · 자료 받은 날 ${(FLU.retrieved_utc || "").slice(0, 10)} · 계산 ${FLU.run_utc.slice(0, 10)} · 출처 ${FLU.source}`);
  const sel = $("#flu-series"); sel.innerHTML = "";
  const rows = FLU.series.slice().sort((a, b) => a.name.localeCompare(b.name));
  for (const r of rows) sel.append(el("option", { value: r.series }, `${r.name} · ${r.source}${r.warnings.length ? " ⚠" : ""}`));
  sel.value = (rows.find((r) => r.series === "KOR|SENTINEL") || rows[0]).series;
  sel.addEventListener("change", fluSeries); $("#flu-h").addEventListener("change", fluMapDraw);
  fluSeries(); fluMapDraw();
}
const fluBest = (r) => r.methods.ml_cal || r.methods.ml || null;
function fluSeries() {
  const r = FLU.series.find((x) => x.series === $("#flu-series").value); if (!r) return;
  const NW = 40, hw = r.history.weeks.slice(-NW), hp = r.history.positivity.slice(-NW), tw = FLU.target_weeks;
  const xs = [...hw, ...tw].map((w) => new Date(w)), pad = hw.map(() => null), padT = tw.map(() => null);
  const series = [{ name: "관측 양성률", color: "--s5", values: [...hp, ...padT], points: true }];
  const ms = ["ml_cal", "seasonal", "persistence", "seir"].filter((m) => r.methods[m]);
  ms.forEach((m, k) => { const q = r.methods[m]; series.push({ name: FLU_LABEL[m], color: SERIES[k], dash: m === "ml_cal" ? "" : "5 3", values: [...pad.slice(0, -1), hp.at(-1), ...q.map((x) => x[4])],
    band: m === "ml_cal" ? [[...pad, ...q.map((x) => x[1])], [...pad, ...q.map((x) => x[7])]] : undefined }); });
  legend($("#flu-lg"), [...series.map((s) => ({ name: s.name, color: s.color })), ...(r.methods.ml_cal ? [{ name: "ML+보정 90% 구간", color: SERIES[0], faint: true }] : [])]);
  lineChart($("#flu-chart"), { xs, series, yMin: 0, yFormat: pp, xFormat: (d) => d.toISOString().slice(0, 10), aria: `${r.name} 인플루엔자 양성률` });
  const t = $("#flu-table"); t.innerHTML = "";
  t.append(el("tr", {}, el("th", {}, "방법"), ...tw.map((w) => el("th", { class: "num" }, `${w} 주`))));
  for (const m of ms) t.append(el("tr", {}, el("td", {}, FLU_LABEL[m]), ...r.methods[m].map((q) => el("td", { class: "num" }, `${pp(q[4])} (${pp(q[1])}–${pp(q[7])})`))));
  const w = $("#flu-warn"); w.innerHTML = "";
  for (const x of r.warnings) w.append(el("div", { class: "warn" }, x));
  w.append(el("p", { class: "note" }, "괄호 = 90% 예측 구간. 첫 대상 주는 이미 일부 보고가 시작된 주일 수 있다."));
}
function fluMapDraw() {
  if (!window.L) { $("#flu-map").textContent = "지도 라이브러리를 불러오지 못했다."; return; }
  const h = +$("#flu-h").value, best = {};
  for (const r of FLU.series) { if (!fluBest(r)) continue; const c = best[r.iso3]; if (!c || (r.last_tests || 0) > (c.last_tests || 0)) best[r.iso3] = r; }
  const col = (v) => { if (v === null || v === undefined) return css("--nodata"); let k = 0; while (k < FLU_BINS.length && v > FLU_BINS[k]) k++; return css(RAMP[Math.min(k, 7)]); };
  if (!fluMap) { fluMap = L.map("flu-map", { zoomSnap: 0.25, worldCopyJump: true }); fluMap.attributionControl.setPrefix(false); fluMap.attributionControl.addAttribution("경계: Natural Earth · 자료: WHO FluNet"); fluMap.setView([25, 10], 1.25); }
  if (fluLayer) fluLayer.remove();
  fluLayer = L.geoJSON(WORLD.geojson, { style: (f) => { const r = best[f.id], q = r && fluBest(r); return { color: css("--surface"), weight: 0.6, fillOpacity: 0.9, fillColor: col(q ? q[h][4] : null) }; },
    onEachFeature: (f, layer) => layer.bindTooltip(() => { const r = best[f.id]; if (!r) return `${esc(f.properties.name)}<br>선택된 계열 없음`; const q = fluBest(r);
      return `${esc(f.properties.name)} · ${esc(r.source)}<br>${esc(FLU.target_weeks[h])} 주 예측 ${esc(pp(q[h][4]))} (90% ${esc(pp(q[h][1]))}–${esc(pp(q[h][7]))})`; }, { sticky: true })
      .on("click", () => { if (best[f.id]) { $("#flu-series").value = best[f.id].series; fluSeries(); } }) }).addTo(fluMap);
  const lg = $("#flu-legend"); lg.innerHTML = "예측 양성률:";
  [0, ...FLU_BINS].forEach((e, k) => lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css(RAMP[Math.min(k, 7)])}` }), k < FLU_BINS.length ? `≤${(100 * FLU_BINS[k]).toFixed(0)}%` : `>${(100 * e).toFixed(0)}%`)));
  lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css("--nodata")}` }), "계열 없음"));
  setTimeout(() => fluMap.invalidateSize(), 50);
}

// ------------------------------------------------------------------ 예측 검증
async function renderVal() {
  const box = $("#val"); let v;
  try { v = await getJSON("data/validation.json"); } catch (e) { box.textContent = e.message; return; }
  const tbl = (head, rows) => el("div", { class: "tablewrap" }, el("table", {}, el("tr", {}, ...head.map((h, i) => el("th", { class: i ? "num" : "" }, h))), ...rows.map((r) => el("tr", {}, ...r.map((c, i) => el("td", { class: i ? "num" : "" }, c))))));
  const f = v.flu, hs = ["1", "2", "3", "4"];
  box.append(el("h2", {}, "예측 검증 ", el("span", { class: "tag fc" }, "과거 자료로 잰 성능")),
    el("div", { class: "warn" }, "각 기점에서 그날까지의 자료만으로 만든 예측을 나중의 실제 관측과 비교했다. 숫자는 지속 예측(마지막 값 유지) 대비 오차 점수(WIS) 비로, 1보다 작으면 지속 예측보다 낫다. 자료가 최종판이라 실시간 성능보다 낙관적일 수 있다."),
    el("div", { class: "card valtab" }, el("h3", {}, `인플루엔자 양성률 (WHO FluNet, ${f.run.n_series}개 계열, 기점 ${f.run.origins[0]} ~ ${f.run.origins[1]} 매주)`),
      tbl(["방법", "1주", "2주", "3주", "4주"], [["감쇠 추세", "trend"], ["계절 평균", "seasonal"], ["ML", "ml"], ["ML + 구간 보정", "ml_cal"]].map(([n, k]) => [n, ...hs.map((h) => fmt(f.main[h][k].rel_wis, 3))])),
      tbl(["90% 구간 포함률", "1주", "2주", "3주", "4주"], [["지속", "persistence"], ["ML", "ml"], ["ML + 구간 보정", "ml_cal"]].map(([n, k]) => [n, ...hs.map((h) => fmt(f.main[h][k].cov90, 2))])),
      f.loco_KOR ? el("p", { class: "note" }, `대한민국 표본감시: ML ${hs.map((h) => fmt(f.loco_KOR[h].ml.rel_wis, 2)).join(" / ")}, 대한민국을 빼고 학습한 ML ${hs.map((h) => fmt(f.loco_KOR[h].ml_loco_KOR.rel_wis, 2)).join(" / ")} (1~4주).`) : "",
      f.seir ? el("p", { class: "note" }, `보조 SEIR (8개 계열): ${hs.map((h) => fmt(f.seir[h].seir.rel_wis, 2)).join(" / ")} (1~4주) — 지속 예측보다 나쁘다.`) : ""));
  const cov = v.covid, ms = [["감쇠 추세", "trend"], ["보정 SEIR", "seir"], ["ML", "ml"], ["SEIR + ML", "hybrid"]];
  const relc = (o, h, m) => o[`${h}|${m}`]?.rel_wis_log;
  box.append(el("div", { class: "card valtab" }, el("h3", {}, `COVID-19 주간 확진·사망 (JHU, 12개국, 기점 ${cov.first_origin} ~ ${cov.last_origin}; 로그 척도)`),
    tbl(["방법", "확진 1주", "확진 4주", "사망 1주", "사망 4주"], ms.map(([n, k]) => [n, fmt(relc(cov.cases_by_h, 1, k), 3), fmt(relc(cov.cases_by_h, 4, k), 3), fmt(relc(cov.deaths_by_h, 1, k), 3), fmt(relc(cov.deaths_by_h, 4, k), 3)])),
    el("p", { class: "note" }, "구간 보정 뒤 ML 90% 포함률: " + v.covid_calibration.filter((r) => r.method === "ml").map((r) => `${r.var === "cases" ? "확진" : "사망"} ${r.h}주 ${fmt(r.cov90_raw, 2)}→${fmt(r.cov90_cal, 2)}`).join(", "))));
}

// ------------------------------------------------------------------ 자료·한계
function renderInfo() {
  const box = $("#info"), m = META;
  const lim = ["이 페이지는 결정론적 ODE 로 계산한다. 확률적 방법(하이브리드, CTMC, tau-leaping, SDE)은 Python 판(저장소)에만 있다. 같은 조건에서 이 엔진은 Python 의 RK4 적분기와 상대 차이 5×10⁻¹⁵ 로 일치한다.",
    "감염병 기본값은 COVID 유사 코드 검증용 가정값이다. 새 감염병의 값은 사용자가 근거와 함께 넣어야 한다.",
    "대한민국 시도 인구는 WorldPop 모델 추정이다 (주민등록 인구 아님). 지역 간 이동 규모·통근·접촉 비율은 가정값이다.",
    "방정식에 백신·변이·연령 구조·해외 유입 항이 없다. 기후 효과는 추정하지 않았다 (켜면 사용자 가정).",
    "시나리오는 \"이렇게 가정하면 이렇게 된다\" 는 계산이며 예측이 아니다. 인플루엔자 예측은 계산해 둔 날짜 기준이며 이 페이지가 스스로 갱신하지 않는다."];
  box.append(el("h2", {}, "자료·한계"),
    el("div", { class: "card valtab" }, el("h3", {}, "한계"), el("ul", {}, ...lim.map((t) => el("li", {}, t)))),
    el("div", { class: "card valtab" }, el("h3", {}, "외부 자료"), el("div", { class: "tablewrap" }, el("table", {},
      el("tr", {}, ...["자료", "출처", "라이선스", "기준 시점", "받은 날"].map((h) => el("th", {}, h))),
      ...m.sources.filter((s) => s.status === "ok").map((s) => el("tr", {}, el("td", {}, s.title || s.id), el("td", {}, s.source || ""), el("td", {}, s.license || ""), el("td", {}, s.time_reference || ""), el("td", {}, (s.retrieved_utc || "").slice(0, 10))))))),
    el("div", { class: "card valtab" }, el("h3", {}, "가정값 (자료가 아님)"), el("div", { class: "tablewrap" }, el("table", {},
      el("tr", {}, ...["이름", "값", "근거", "불확실성"].map((h) => el("th", {}, h))),
      ...m.assumptions.map((a) => el("tr", {}, el("td", {}, a.name), el("td", {}, a.value), el("td", {}, a.basis), el("td", {}, a.uncertainty)))))),
    el("p", { class: "note" }, `만든 코드: 저장소 cherub75-png/Epidemic-Spread-Simulation_Claude-Code, 브랜치 claude/global-reinfection-seir-cubnxv, 커밋 ${m.build.commit} · 페이지 생성 ${m.build.built_utc.slice(0, 10)}`));
}

// ------------------------------------------------------------------ 시작
(async () => {
  try { META = await getJSON("data/meta.json"); } catch (e) { $("#run-msg").textContent = "자료를 불러오지 못했다: " + e.message; return; }
  const d = META.disease_defaults;
  for (const [id, fn] of PFIELDS) $("#" + id).value = +fn(d).toPrecision(4);
  for (const id of ["p-R0", ...PFIELDS.map((x) => x[0])]) $("#" + id).addEventListener("input", () => { derived(); renderSources(); });
  derived(); initUnc();
  $("#f-clim").addEventListener("change", () => { $("#clim-params").hidden = !$("#f-clim").checked; renderSources(); });
  $("#f-ds").addEventListener("change", onDataset);
  $("#add-seed").addEventListener("click", () => addSeed(WS.ds.ids[0], 10, 0));
  $("#add-int").addEventListener("click", () => addInt());
  await onDataset();
  addInt(30, 90, 0.3);
  window.addEventListener("resize", () => { clearTimeout(window.__rz); window.__rz = setTimeout(() => { wsFit(); if (WS.data) frame(WS.frame); }, 200); });
})();
