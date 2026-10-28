"use strict";
// 재감염 SEIR 시뮬레이터 로컬 화면. 외부 서버에 요청하지 않는다 (지도 타일 없음, 경계는 로컬 API 의 GeoJSON).

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
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
  if (a >= 1e6) return nf.format(v / 1e6) + "백만";
  if (a >= 100) return nf.format(Math.round(v));
  if (a >= 1) return nf.format(v);
  return a === 0 ? "0" : Number(v).toPrecision(2);
}
const pct = (v) => (v === null || v === undefined ? "–" : (100 * v).toFixed(1) + "%");
const SERIES = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5"];
const RAMP = ["--ramp-0", "--ramp-1", "--ramp-2", "--ramp-3", "--ramp-4", "--ramp-5", "--ramp-6", "--ramp-7"];
const METHOD_LABEL = { persistence: "지속", trend: "감쇠 추세", seasonal52: "52주 계절", seir: "보정 SEIR", ml: "ML (분위수 GBM)", hybrid: "SEIR+ML 잔차" };
const FIELD = { title: "제목", dataset: "데이터셋", population: "인구", R0: "R0", r0_reference: "R0 기준", reference_region: "기준 지역",
  method: "방법", n_runs: "실행 횟수", n_workers: "작업자 수", days: "기간", start_date: "시작일", seeds: "발생 지역", interventions: "개입",
  eta: "밀도 지수", seed: "난수 시드", count: "I 인원", exposed: "E 인원", region: "지역", start: "시작일", end: "끝일", value: "u", regions: "지역",
  disease: "감염병", incubation_days: "잠복기", infectious_days: "감염 기간", immunity_days: "면역 유지 기간", f1: "치명률",
  initial_immune_fraction: "시작 시 면역 비율", tau_leap_epsilon: "tau ε", sde_dt: "SDE 간격", hybrid_up: "전환 올림", hybrid_down: "전환 내림" };
function fieldName(loc) { return (loc || []).filter((x) => x !== "body").map((x) => (typeof x === "number" ? `${x + 1}번째` : FIELD[x] || x)).join(" ") || "입력"; }
function koMsg(x) {
  const c = x.ctx || {};
  return ({ greater_than: `${c.gt} 보다 커야 한다`, greater_than_equal: `${c.ge} 이상이어야 한다`, less_than: `${c.lt} 보다 작아야 한다`,
    less_than_equal: `${c.le} 이하여야 한다`, missing: "값이 필요하다", extra_forbidden: "허용되지 않는 항목", literal_error: `허용 값: ${c.expected}`,
    string_pattern_mismatch: "형식이 맞지 않는다", too_short: "항목이 너무 적다", too_long: "항목이 너무 많다", int_parsing: "정수가 아니다",
    float_parsing: "숫자가 아니다", value_error: (x.msg || "").replace(/^Value error, /, "") })[x.type] || x.msg;
}
async function api(path, opts = {}) {
  let r;
  try { r = await fetch(path, { headers: { "Content-Type": "application/json", "X-SEIR-Client": "web" }, ...opts }); }
  catch (e) { throw new Error("서버에 연결할 수 없다 (서버가 실행 중인지 확인): " + e.message); }
  let body = null;
  try { body = await r.json(); } catch (_) { /* 본문 없음 */ }
  if (!r.ok) {
    const d = body && body.detail;
    const msg = Array.isArray(d) ? d.map((x) => `${fieldName(x.loc)}: ${koMsg(x)}`).join("; ") : (d || r.statusText);
    throw new Error(msg);
  }
  return body;
}
function download(name, text, type) {
  const a = el("a", { href: URL.createObjectURL(new Blob([text], { type })), download: name });
  document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

// ------------------------------------------------------------------ 테마·탭
let rerenderers = [];
function rerender() { for (const f of rerenderers) { try { f(); } catch (_) { /* 다음 그림 */ } } }
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem("theme", t); } catch (_) { /* 저장 불가 환경 */ }
  rerender();
}
$("#theme").addEventListener("change", (e) => applyTheme(e.target.value));
try { const t = localStorage.getItem("theme") || ""; $("#theme").value = t; if (t) document.documentElement.dataset.theme = t; } catch (_) { /* 없음 */ }
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rerender);

const loaded = {};
function showTab(name) {
  for (const b of $$("#tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
  for (const s of $$("main > section")) s.hidden = s.id !== `tab-${name}`;
  if (!loaded[name]) { loaded[name] = true; ({ home: loadHome, results: loadJobs, validation: loadValidation, latest: initLatest, data: loadDatasets, sources: loadSources })[name]?.(); }
  if (name === "results") setTimeout(() => { if (rerenderMapFit) rerenderMapFit(); }, 50);
  if (name === "run" && seedMap) setTimeout(() => seedMapFit && seedMapFit(), 50);
}
for (const b of $$("#tabs button")) b.addEventListener("click", () => showTab(b.dataset.tab));
for (const b of $$("[data-goto]")) b.addEventListener("click", () => showTab(b.dataset.goto));

// ------------------------------------------------------------------ 선 그래프 (SVG, 십자선·툴팁)
function lineChart(box, o) {
  box.innerHTML = "";
  const W = Math.max(320, box.clientWidth || 600), H = o.height || 280;
  const m = { l: 64, r: o.rightPad || 16, t: 10, b: 34 };
  const xs = o.xs;
  const all = [];
  for (const s of o.series) { for (const v of s.values) if (v !== null && v !== undefined && isFinite(v)) all.push(v);
    if (s.band) for (const b of s.band) for (const v of b) if (v !== null && isFinite(v)) all.push(v); }
  if (o.refLine !== undefined) all.push(o.refLine);
  const logY = !!o.logY;
  const pos = all.filter((v) => !logY || v > 0);
  if (!pos.length) { box.append(el("p", { class: "note" }, "표시할 값이 없다.")); return; }
  let y0 = o.yMin !== undefined ? o.yMin : (logY ? Math.min(...pos) : Math.min(0, ...pos));
  let y1 = Math.max(...pos);
  if (logY) y0 = Math.max(y0, 1e-3);
  if (y1 <= y0) y1 = y0 + 1;
  const xv = xs.map((x) => (x instanceof Date ? x.getTime() : x));
  const x0 = Math.min(...xv), x1 = Math.max(...xv) === x0 ? x0 + 1 : Math.max(...xv);
  const X = (x) => m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r);
  const ly = (v) => (logY ? Math.log10(Math.max(v, y0)) : v);
  const Y = (v) => H - m.b - ((ly(v) - ly(y0)) / (ly(y1) - ly(y0) || 1)) * (H - m.t - m.b);
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H);
  svg.setAttribute("role", "img"); svg.setAttribute("aria-label", o.ariaLabel || "선 그래프");
  const mk = (t, a) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  const ink2 = css("--ink-2"), gridc = css("--grid"), ink3 = css("--ink-3");
  const txt = (x, y, s, anchor) => { const t = mk("text", { x, y, "text-anchor": anchor, fill: ink2, "font-size": 11, "font-family": "sans-serif" }); t.textContent = s; return t; };
  const yt = logY ? (() => { const out = []; for (let p = Math.floor(Math.log10(y0)); p <= Math.ceil(Math.log10(y1)); p++) out.push(10 ** p); return out.filter((v) => v >= y0 * 0.999 && v <= y1 * 1.001); })()
    : Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4);
  for (const v of yt) { svg.append(mk("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: gridc })); svg.append(txt(m.l - 6, Y(v) + 4, (o.yFormat || fmt)(v), "end")); }
  const nx = Math.min(6, xs.length);
  for (let i = 0; i < nx; i++) { const xi = x0 + ((x1 - x0) * i) / Math.max(1, nx - 1); svg.append(txt(X(xi), H - m.b + 16, (o.xFormat || ((v) => fmt(v)))(xs[0] instanceof Date ? new Date(xi) : xi), "middle")); }
  svg.append(mk("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: ink3 }));
  if (o.xLabel) svg.append(txt(W - m.r, H - 2, o.xLabel, "end"));
  if (o.refLine !== undefined) svg.append(mk("line", { x1: m.l, x2: W - m.r, y1: Y(o.refLine), y2: Y(o.refLine), stroke: ink3, "stroke-dasharray": "4 3" }));
  for (const s of o.series) {
    const col = css(s.color);
    if (s.band) {
      const [lo, hi] = s.band; const seg = [];
      for (let i = 0; i < xs.length; i++) if (lo[i] !== null && hi[i] !== null && isFinite(lo[i]) && isFinite(hi[i])) seg.push(i);
      if (seg.length) svg.append(mk("path", { d: seg.map((i, k) => `${k ? "L" : "M"}${X(xv[i])},${Y(hi[i])}`).join("") + seg.slice().reverse().map((i) => `L${X(xv[i])},${Y(lo[i])}`).join("") + "Z", fill: col, "fill-opacity": 0.18, stroke: "none" }));
    }
    if (s.points) { for (let i = 0; i < xs.length; i++) if (s.values[i] !== null && isFinite(s.values[i])) svg.append(mk("circle", { cx: X(xv[i]), cy: Y(s.values[i]), r: 3, fill: col, stroke: css("--surface"), "stroke-width": 1.5 })); continue; }
    let d = "", pen = false;
    for (let i = 0; i < xs.length; i++) { const v = s.values[i]; if (v === null || v === undefined || !isFinite(v) || (logY && v <= 0)) { pen = false; continue; } d += `${pen ? "L" : "M"}${X(xv[i])},${Y(v)}`; pen = true; }
    svg.append(mk("path", { d, fill: "none", stroke: col, "stroke-width": s.width || 2, "stroke-dasharray": s.dash || "", "stroke-linejoin": "round", "stroke-linecap": "round" }));
    if (s.label) { let j = s.values.length - 1; while (j >= 0 && (s.values[j] === null || !isFinite(s.values[j]))) j--;
      if (j >= 0) { const t = txt(X(xv[j]) + 6, Y(s.values[j]) + 4, s.label, "start"); t.setAttribute("fill", css("--ink")); svg.append(t); } }
  }
  const cross = mk("line", { y1: m.t, y2: H - m.b, stroke: ink3, "stroke-width": 1, visibility: "hidden" });
  svg.append(cross);
  const hit = mk("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  svg.append(hit);
  const tip = el("div", { class: "tooltip", hidden: true });
  hit.addEventListener("mousemove", (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const xval = x0 + ((px - m.l) / (W - m.l - m.r)) * (x1 - x0);
    let bi = 0, bd = Infinity;
    xv.forEach((x, i) => { const dd = Math.abs(x - xval); if (dd < bd) { bd = dd; bi = i; } });
    cross.setAttribute("x1", X(xv[bi])); cross.setAttribute("x2", X(xv[bi])); cross.setAttribute("visibility", "visible");
    tip.innerHTML = "";
    tip.append(el("div", { class: "muted" }, (o.xFormat || ((v) => fmt(v)))(xs[bi])));
    for (const s of o.series) {
      let t = `${s.name}: ${(o.yFormat || fmt)(s.values[bi])}`;
      if (s.band) t += ` (${(o.yFormat || fmt)(s.band[0][bi])} – ${(o.yFormat || fmt)(s.band[1][bi])})`;
      tip.append(el("div", {}, el("span", { class: "sw", style: `background:${css(s.color)}` }), t));
    }
    tip.hidden = false;
    const bx = box.getBoundingClientRect();
    let left = ev.clientX - bx.left + 14; if (left > bx.width - 240) left = ev.clientX - bx.left - 250;
    tip.style.left = `${left}px`; tip.style.top = `${ev.clientY - bx.top - 10}px`;
  });
  hit.addEventListener("mouseleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
  box.append(svg, tip);
}
function legend(box, items) {
  box.innerHTML = "";
  for (const it of items) box.append(el("span", {}, el("span", { class: "sw", style: `background:${css(it.color)}${it.dash ? ";opacity:.5" : ""}` }), it.name));
}
function exportSvg(svgEl, name, title) {
  if (!svgEl) return;
  const c = svgEl.cloneNode(true);
  c.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const w = +c.getAttribute("width") || svgEl.clientWidth, h = +c.getAttribute("height") || svgEl.clientHeight;
  const NS = "http://www.w3.org/2000/svg";
  const bg = document.createElementNS(NS, "rect"); bg.setAttribute("width", "100%"); bg.setAttribute("height", "100%"); bg.setAttribute("fill", css("--surface"));
  c.insertBefore(bg, c.firstChild);
  if (title) { const t = document.createElementNS(NS, "text"); t.setAttribute("x", 8); t.setAttribute("y", h - 6); t.setAttribute("font-size", 11); t.setAttribute("fill", css("--ink-2")); t.textContent = title; c.append(t); }
  if (!c.getAttribute("viewBox")) c.setAttribute("viewBox", `0 0 ${w} ${h}`);
  download(name, new XMLSerializer().serializeToString(c), "image/svg+xml");
}

// ------------------------------------------------------------------ 감염병 매개변수 입력
let DEF = null;
const num = (v) => (typeof v === "string" && v.includes("/") ? v.split("/").reduce((a, b) => +a / +b) : +v);
const BASIC = [["incubation_days", "잠복기 (일)", (d) => 1 / num(d.sigma), 0.1], ["infectious_days", "감염 기간 (일)", (d) => 1 / num(d.gamma), 0.1],
  ["immunity_days", "면역 유지 기간 (일, 0 = 소실 없음)", (d) => (num(d.lam) > 0 ? 1 / num(d.lam) : 0), 1], ["f1", "첫 감염 치명률", (d) => num(d.f1), 0.001]];
const ADV = [["P1", "첫 감염 감수성 P1", (d) => num(d.P1), 0.05], ["Pmin", "재감염 감수성 하한 Pmin", (d) => num(d.Pmin), 0.05],
  ["alpha", "감수성 감소 속도 α", (d) => num(d.alpha), 0.05], ["T1", "첫 감염 전파력 T1", (d) => num(d.T1), 0.05],
  ["beta", "전파력 감소 지수 β", (d) => num(d.beta), 0.05], ["phi_delta", "치명률 감소 지수 δ (φ(n) = n^−δ)", (d) => num((d.phi || {}).delta ?? 0.5), 0.05],
  ["M", "감염 횟수 칸 수 M", (d) => num(d.M), 1]];
function paramInput([key, label, defFn, step]) {
  const def = DEF ? defFn(DEF) : null;
  const tag = el("span", { class: "tag asm" }, "기본 가정값");
  const inp = el("input", { type: "number", name: `dz_${key}`, step, placeholder: def === null ? "" : String(+def.toFixed(4)), "data-default": def });
  inp.addEventListener("input", () => { const user = inp.value !== ""; tag.className = `tag ${user ? "user" : "asm"}`; tag.textContent = user ? "사용자 입력" : "기본 가정값"; derived(); });
  return el("label", {}, label, inp, tag);
}
function dzValue(key) { const i = $(`[name=dz_${key}]`); return i && i.value !== "" ? +i.value : null; }
function dzEffective(key) { const i = $(`[name=dz_${key}]`); return i ? (i.value !== "" ? +i.value : +i.dataset.default) : null; }
function derived() {
  const R0 = +$("[name=R0]").value, inc = dzEffective("incubation_days"), inf = dzEffective("infectious_days");
  const P1 = dzEffective("P1"), T1 = dzEffective("T1");
  if (!(R0 > 0 && inc > 0 && inf > 0 && P1 > 0 && T1 > 0)) { $("#dz-derived").textContent = ""; return; }
  const sig = 1 / inc, gam = 1 / inf, kappa = R0 * gam;
  const r = 0.5 * (-(sig + gam) + Math.sqrt((sig - gam) ** 2 + 4 * sig * kappa));
  $("#dz-derived").textContent = `reference 조건(단일 지역, 기준 밀도, 개입 없음, 전원 감수성)에서: c0 = R0·γ/(P1·T1) = ${fmt(R0 * gam / (P1 * T1), 4)}/일, ` +
    `초기 증가율 r = ${fmt(r, 4)}/일` + (r > 0 ? `, 배가 시간 ${fmt(Math.log(2) / r, 1)}일` : " (감소)") + ". 실제 지역망에서는 밀도·이동·개입에 따라 달라진다.";
}
function diseaseRequest() {
  const d = { name: $("[name=dz_name]").value || "사용자 정의", kind: $("[name=dz_kind]").value };
  for (const [k] of [...BASIC, ...ADV]) { const v = dzValue(k); if (v !== null) d[k] = k === "M" ? Math.round(v) : v; }
  return d;
}
function setDisease(d) {
  $("[name=dz_name]").value = d?.name || "사용자 정의"; $("[name=dz_kind]").value = d?.kind || "respiratory";
  for (const [k] of [...BASIC, ...ADV]) { const i = $(`[name=dz_${k}]`); i.value = d && d[k] !== null && d[k] !== undefined ? d[k] : ""; i.dispatchEvent(new Event("input")); }
}
async function loadPresets() {
  const s = $("#dz-presets"); s.innerHTML = ""; s.append(el("option", { value: "" }, "(기본 가정값: COVID 유사)"));
  try { const p = await api("/api/diseases"); for (const n of Object.keys(p)) s.append(el("option", { value: n }, n)); window.__presets = p; } catch (_) { window.__presets = {}; }
}
$("#dz-load").addEventListener("click", () => { const n = $("#dz-presets").value; const p = (window.__presets || {})[n];
  setDisease(p ? p.disease : null); if (p && p.R0) { $("[name=R0]").value = p.R0; derived(); } });
$("#dz-save").addEventListener("click", async () => {
  const note = prompt("근거·출처 메모 (예: 문헌, 추정 방법). 비워 두면 '근거 미기록' 으로 저장된다.", "") ?? null;
  if (note === null) return;
  try { const r = await api("/api/diseases", { method: "POST", body: JSON.stringify({ disease: diseaseRequest(), R0: +$("[name=R0]").value, note: note || "근거 미기록" }) });
    await loadPresets(); $("#dz-presets").value = r.saved; msg(`감염병 설정 '${r.saved}' 저장`); } catch (e) { msg("저장 실패: " + e.message, true); }
});
$("#dz-del").addEventListener("click", async () => { const n = $("#dz-presets").value; if (!n) return;
  try { await api(`/api/diseases/${encodeURIComponent(n)}`, { method: "DELETE" }); await loadPresets(); msg(`'${n}' 삭제`); } catch (e) { msg(e.message, true); } });
function msg(t, err) { const m = $("#run-msg"); m.innerHTML = ""; m.append(el("span", { class: err ? "err" : "" }, t)); }

// ------------------------------------------------------------------ 시나리오 양식
let regionInfo = { ids: [], names: [], population: [] };
let seedMap = null, seedLayer = null, seedMapFit = null, datasetHasClimate = false;
async function initForm() {
  try { const df = await api("/api/defaults"); DEF = df.disease; } catch (_) { DEF = null; }
  $("#dz-basic").append(el("label", {}, "R0", el("input", { type: "number", name: "R0", value: "2.5", step: "0.1", min: "0.1", max: "20", oninput: derived }), el("span", { class: "tag user" }, "사용자 입력")));
  for (const p of BASIC) $("#dz-basic").append(paramInput(p));
  for (const p of ADV) $("#dz-adv").append(paramInput(p));
  derived();
  loadPresets();
  const sel = $("#f-dataset");
  let ds = [];
  try { ds = await api("/api/datasets"); } catch (e) { msg("데이터셋 목록 실패: " + e.message, true); }
  for (const d of ds) {
    const v = d.versions.find((x) => x.version === d.active);
    sel.append(el("option", { value: d.name }, `${d.name} (${d.active || "활성 없음"}, ${v ? v.K : "?"}개 지역${v && v.synthetic ? ", 합성" : ""})`));
  }
  sel.append(el("option", { value: "synthetic_single" }, "합성 단일 지역 (실제 지역 아님)"));
  sel.addEventListener("change", () => onDataset());
  $("#f-basis").addEventListener("change", () => { $("#f-refreg-wrap").hidden = $("#f-basis").value !== "region"; });
  $("#f-climate").addEventListener("change", () => { $("#f-climate-params").hidden = $("#f-climate").value === "none"; });
  $("#add-seed").addEventListener("click", () => addSeed(regionInfo.ids[0], 10, 0));
  $("#add-int").addEventListener("click", () => addInt());
  await onDataset();
}
let dsToken = 0;
async function onDataset(keepRows) {
  const token = ++dsToken;                   // 겹친 호출 중 마지막 것만 화면을 바꾼다
  const name = $("#f-dataset").value;
  $("#f-pop-wrap").hidden = name !== "synthetic_single";
  datasetHasClimate = false;
  if (name === "synthetic_single") { regionInfo = { ids: ["region0"], names: ["합성 지역"], population: [null] }; $("#f-dataset-note").textContent = "합성 단일 지역: 코드 검증용이며 실제 지역이 아니다."; }
  else {
    try {
      const r = await api(`/api/datasets/${name}/regions`);
      if (token !== dsToken) return;
      regionInfo = r;
      const p = r.provenance || {};
      const pop = p.population || {};
      datasetHasClimate = !!p.climate;
      $("#f-dataset-note").innerHTML = "";
      $("#f-dataset-note").append(`${r.ids.length}개 지역 · 경계: ${p.boundaries || "?"} `, el("span", { class: "tag obs" }, "실제 관측"), " · 인구: ",
        `${pop.source || (pop.primary && pop.primary.source) || "?"} `, el("span", { class: "tag " + ((pop.tiers || []).includes("secondary") ? "sec" : "obs") }, (pop.tiers || []).includes("secondary") ? "2차 자료" : "실제 관측"),
        ` · 항공 ${p.assumptions?.air_trips_per_day ?? "?"}회/일, 통근 ${p.assumptions?.commute_fraction ?? "?"}, 접촉 ${p.assumptions?.destination_contact_share ?? "?"} `, el("span", { class: "tag asm" }, "기본 가정값"));
    } catch (e) { $("#f-dataset-note").textContent = "지역 목록 실패: " + e.message; }
  }
  $("#f-climate").disabled = !datasetHasClimate;
  if (!datasetHasClimate) { $("#f-climate").value = "none"; $("#f-climate-params").hidden = true; }
  $("#f-climate-note").textContent = datasetHasClimate ? "기후 효과는 실제 자료로 추정하지 않았다. 켜면 사용자 가정값으로 표시된다 (기후 자료: 2020~2022 월 평균, 관측소 기반)."
    : "이 데이터셋에는 기후 자료가 없다 (미확보). 기후 효과를 켤 수 없다.";
  const ref = $("#f-refreg"); ref.innerHTML = "";
  regionInfo.ids.forEach((id, i) => ref.append(el("option", { value: id }, `${id} ${regionInfo.names[i] || ""}`)));
  if (!keepRows) {
    $("#f-seeds").innerHTML = ""; $("#f-ints").innerHTML = "";
    addSeed(["KR-11", "CHN"].find((x) => regionInfo.ids.includes(x)) || regionInfo.ids[0], 10, 0);
  }
  await drawSeedMap(name, token);
}
async function drawSeedMap(name, token) {
  const box = $("#seed-map");
  if (name === "synthetic_single") { if (seedMap) { seedMap.remove(); seedMap = null; seedLayer = null; } box.innerHTML = "<p class='note' style='padding:8px'>합성 지역은 지도가 없다.</p>"; return; }
  let geo; try { geo = await api(`/api/datasets/${name}/geojson`); } catch (_) { box.textContent = "경계 없음"; return; }
  if (token !== undefined && token !== dsToken) return;
  if (!seedMap) { box.innerHTML = ""; seedMap = L.map(box, { attributionControl: false, zoomSnap: 0.25 }); }
  if (seedLayer) seedLayer.remove();
  const seeded = () => new Set($$("#f-seeds .row select").map((s) => s.value));
  const style = (f) => ({ color: css("--surface"), weight: 1, fillOpacity: 0.85, fillColor: seeded().has(f.id) ? css("--series-2") : css("--ramp-1") });
  seedLayer = L.geoJSON(geo, { style, onEachFeature: (f, layer) => {
    layer.bindTooltip(() => `${esc(f.properties.name)} (${esc(f.id)})<br>인구 ${esc(fmt(f.properties.population))}<br>누르면 발생 지역에 추가`, { sticky: true });
    layer.on("click", () => { if (!seeded().has(f.id)) addSeed(f.id, 10, 0); });
  } }).addTo(seedMap);
  seedMapFit = () => { if (box.clientWidth > 0) { seedMap.invalidateSize(); try { seedMap.fitBounds(seedLayer.getBounds(), { padding: [4, 4] }); } catch (_) { /* 빈 경계 */ } } };
  window.__restyleSeeds = () => seedLayer && seedLayer.setStyle(style);
  seedMapFit();
}
function regionSelect(value, multiple) {
  const s = el("select", multiple ? { multiple: true, size: 3 } : {});
  if (multiple) s.append(el("option", { value: "", selected: !value }, "전체 지역"));
  regionInfo.ids.forEach((id, i) => s.append(el("option", { value: id, selected: multiple ? (value || []).includes(id) : id === value }, `${id} ${regionInfo.names[i] || ""}`)));
  return s;
}
function addSeed(region, count = 10, exposed = 0) {
  const sel = regionSelect(region);
  sel.addEventListener("change", () => window.__restyleSeeds && window.__restyleSeeds());
  const row = el("div", { class: "row" },
    el("label", {}, "지역", sel), el("label", {}, "I (감염 중)", el("input", { type: "number", value: count, min: 0 })),
    el("label", {}, "E (잠복)", el("input", { type: "number", value: exposed, min: 0 })),
    el("button", { type: "button", class: "secondary", onclick: () => { row.remove(); window.__restyleSeeds && window.__restyleSeeds(); } }, "삭제"));
  $("#f-seeds").append(row);
  window.__restyleSeeds && window.__restyleSeeds();
}
function addInt(start = 30, end = 90, value = 0.3, regions = null) {
  const row = el("div", { class: "row" },
    el("label", {}, "시작일", el("input", { type: "number", value: start, min: 0 })), el("label", {}, "끝일", el("input", { type: "number", value: end, min: 1 })),
    el("label", {}, "u (0~1)", el("input", { type: "number", value, min: 0, max: 1, step: 0.05 })),
    el("label", {}, "지역", regionSelect(regions, true)),
    el("button", { type: "button", class: "secondary", onclick: () => row.remove() }, "삭제"));
  $("#f-ints").append(row);
}
function formRequest() {
  const f = $("#scenario-form");
  const v = (n) => f.elements[n].value;
  const req = {
    title: v("title"), dataset: v("dataset"), disease: diseaseRequest(), R0: +$("[name=R0]").value, r0_reference: v("r0_reference"),
    method: v("method"), n_runs: +v("n_runs"), n_workers: +v("n_workers"), days: +v("days"), start_date: v("start_date"), eta: +v("eta"), seed: +v("seed"),
    use_mobility: f.elements.use_mobility.checked, use_commuting: f.elements.use_commuting.checked,
    initial_immune_fraction: +v("immune_pct") / 100, climate: v("climate"),
    climate_a_T: +v("climate_a_T"), climate_a_H: +v("climate_a_H"), climate_T_ref: +v("climate_T_ref"), climate_H_ref: +v("climate_H_ref"),
    tau_leap_epsilon: +v("tau_leap_epsilon"), sde_dt: +v("sde_dt"), hybrid_up: +v("hybrid_up"), hybrid_down: +v("hybrid_down"),
    seeds: $$("#f-seeds .row").map((r) => { const ins = $$("input", r); return { region: $("select", r).value, count: +ins[0].value, exposed: +ins[1].value }; }),
    interventions: $$("#f-ints .row").map((r) => {
      const ins = $$("input", r); const regs = Array.from($("select", r).selectedOptions).map((o) => o.value).filter((x) => x);
      return { start: +ins[0].value, end: +ins[1].value, value: +ins[2].value, regions: regs.length ? regs : null };
    }),
  };
  if (req.dataset === "synthetic_single") req.population = +v("population");
  if (req.r0_reference === "region") req.reference_region = v("reference_region");
  return req;
}
async function fillForm(req) {
  const f = $("#scenario-form");
  if ([...$("#f-dataset").options].some((o) => o.value === req.dataset)) $("#f-dataset").value = req.dataset;
  await onDataset(true);
  $("#f-seeds").innerHTML = ""; $("#f-ints").innerHTML = "";
  const set = (n, val) => { if (val !== undefined && val !== null && f.elements[n]) f.elements[n].value = val; };
  set("title", req.title); set("population", req.population); set("start_date", req.start_date); set("days", req.days);
  set("r0_reference", req.r0_reference); set("method", req.method); set("n_runs", req.n_runs); set("n_workers", req.n_workers);
  set("seed", req.seed); set("eta", req.eta); set("climate", req.climate); set("climate_a_T", req.climate_a_T); set("climate_a_H", req.climate_a_H);
  set("climate_T_ref", req.climate_T_ref); set("climate_H_ref", req.climate_H_ref); set("tau_leap_epsilon", req.tau_leap_epsilon);
  set("sde_dt", req.sde_dt); set("hybrid_up", req.hybrid_up); set("hybrid_down", req.hybrid_down);
  set("immune_pct", req.initial_immune_fraction !== undefined ? Math.round(req.initial_immune_fraction * 100) : 0);
  f.elements.use_mobility.checked = req.use_mobility !== false; f.elements.use_commuting.checked = req.use_commuting !== false;
  $("[name=R0]").value = req.R0 ?? 2.5;
  setDisease(req.disease || null);
  $("#f-refreg-wrap").hidden = req.r0_reference !== "region"; if (req.reference_region) $("#f-refreg").value = req.reference_region;
  $("#f-climate-params").hidden = (req.climate || "none") === "none";
  for (const s of req.seeds || []) addSeed(s.region, s.count, s.exposed || 0);
  for (const i of req.interventions || []) addInt(i.start, i.end, i.value, i.regions);
  derived();
}
// 파일 이름은 ASCII 로 (일부 브라우저가 한글 download 이름을 무시한다). 제목은 파일 안에 그대로 있다.
$("#save-cfg").addEventListener("click", () => download(`scenario_settings_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}.json`, JSON.stringify(formRequest(), null, 1), "application/json"));
$("#load-cfg").addEventListener("change", (e) => { const file = e.target.files[0]; if (!file) return; const r = new FileReader();
  r.onload = async () => { try { await fillForm(JSON.parse(r.result)); msg("설정을 불러왔다. 점검 후 실행한다."); } catch (err) { msg("설정 파일을 읽지 못했다: " + err.message, true); } }; r.readAsText(file); });
const COST = { ok: "짧음", warn: "수 분 이상", heavy: "매우 오래 걸릴 수 있음 (반복 수·기간·방법을 줄이는 것을 권장)" };
$("#check-btn").addEventListener("click", async () => {
  try { const r = await api("/api/scenarios/check", { method: "POST", body: JSON.stringify(formRequest()) });
    msg(`점검 통과. 예상 계산 시간 약 ${fmt(r.estimate.seconds, 0)}초 (${COST[r.estimate.level]}; ${r.estimate.note}).`, r.estimate.level === "heavy"); }
  catch (err) { msg("입력 오류: " + err.message, true); }
});
$("#scenario-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const req = formRequest();
  let res;
  try { res = await api("/api/scenarios", { method: "POST", body: JSON.stringify(req) }); }
  catch (err) { msg("입력 오류: " + err.message, true); return; }
  msg(`실행을 시작했다. 예상 약 ${fmt(res.estimate.seconds, 0)}초 (${COST[res.estimate.level]}).`, res.estimate.level === "heavy");
  trackJob(res.job_id, req.title, (s) => { if (s.state === "done") { loaded.results = false; showTab("results"); viewJob(res.job_id); } });
});
let pollTimer = null;
function trackJob(id, title, onEnd) {
  $("#run-progress").hidden = false; $("#rp-title").textContent = title; $("#rp-bar").style.width = "0";
  $("#rp-cancel").onclick = () => api(`/api/jobs/${id}`, { method: "DELETE" }).catch(() => {});
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    let s; try { s = await api(`/api/jobs/${id}`); } catch (_) { return; }
    $("#rp-bar").style.width = `${Math.round(100 * (s.progress || 0))}%`;
    $("#rp-state").textContent = `${stateLabel(s.state)} ${s.message || ""}`;
    if (["done", "failed", "cancelled", "interrupted"].includes(s.state)) { clearInterval(pollTimer); onEnd && onEnd(s); }
  }, 800);
}
const stateLabel = (s) => ({ queued: "대기", running: "실행 중", done: "완료", failed: "실패", cancelled: "취소됨", interrupted: "중단됨" })[s] || s;

// ------------------------------------------------------------------ 홈
async function loadHome() {
  const t = $("#home-jobs"); t.innerHTML = "";
  let list = []; try { list = await api("/api/jobs"); } catch (_) { /* 없음 */ }
  t.append(el("tr", {}, el("th", {}, "제목"), el("th", {}, "종류"), el("th", {}, "상태"), el("th", {}, "만든 시각 (UTC)")));
  for (const j of list.slice(0, 6)) t.append(el("tr", {}, el("td", {}, el("a", { href: "#", onclick: (e) => { e.preventDefault(); openJob(j); } }, j.title || j.id.slice(0, 8))),
    el("td", {}, ({ scenario: "시나리오", forecast: "최신 예측", dataset: "데이터 갱신", update: "원자료 갱신" })[j.kind] || j.kind), el("td", {}, stateLabel(j.state)),
    el("td", { class: "small muted" }, (j.created_utc || "").replace("T", " ").replace("+00:00", ""))));
  if (!list.length) t.append(el("tr", {}, el("td", { colspan: 4, class: "muted" }, "아직 작업이 없다.")));
}

// ------------------------------------------------------------------ 결과·비교
async function loadJobs() {
  const tb = $("#jobs-table tbody"); tb.innerHTML = "";
  let list = [];
  try { list = await api("/api/jobs"); } catch (e) { tb.append(el("tr", {}, el("td", { colspan: 5, class: "err" }, e.message))); return; }
  if (!list.length) tb.append(el("tr", {}, el("td", { colspan: 5, class: "muted" }, "저장된 작업이 없다.")));
  for (const j of list) {
    const kindLabel = { scenario: "시나리오", forecast: "최신 예측", dataset: "데이터 갱신", update: "원자료 갱신" }[j.kind] || j.kind;
    const cb = j.kind === "scenario" && j.state === "done" ? el("input", { type: "checkbox", value: j.id, "aria-label": "비교 선택" }) : "";
    tb.append(el("tr", {}, el("td", {}, cb), el("td", {}, el("a", { href: "#", onclick: (e) => { e.preventDefault(); openJob(j); } }, j.title || j.id.slice(0, 8))),
      el("td", {}, kindLabel), el("td", { title: j.message || "" }, stateLabel(j.state) + (j.state === "running" ? ` ${Math.round(100 * (j.progress || 0))}%` : "") + (j.state === "failed" ? ` (${j.message || ""})` : "")),
      el("td", { class: "small muted" }, (j.created_utc || "").replace("T", " ").replace("+00:00", ""))));
  }
}
$("#refresh-jobs").addEventListener("click", loadJobs);
function openJob(j) {
  if (j.kind === "scenario") viewJob(j.id);
  else if (j.kind === "forecast") { showTab("latest"); showForecast(j.id); }
  else if (j.kind === "update") showTab("sources");
  else showTab("data");
}

let map = null, geoLayer = null, flowLayer = null, playTimer = null, rerenderMapFit = null;
let R = null;   // 현재 결과 상태 {id, s, geo, names, idx, frame, region}
const LAYER_DEF = {
  I: "감염 중 I: 모형 안의 실제 감염 상태 (관측 확진자 수가 아님), 실행 평균",
  E: "잠복 E: 감염되었으나 아직 전파하지 않는 인원, 실행 평균",
  D: "누적 사망 D: 시작 이후 모형 사망 누적, 실행 평균",
  first: "첫 감염 누적 비율: 한 번 이상 감염된 사람의 비율 (지역 인구 대비), 실행 평균",
  arrival: "도착일: 지역의 감염 중 인원이 처음 1명 이상이 된 날 (실행 간 중앙값). 시간 막대와 무관",
};
function layerValue(i, k) {
  const L = $("#map-layer").value, sc = $("#map-scale").value, fr = R.s.frames, pop = R.s.regions[k].population;
  if (L === "arrival") return R.s.regions[k].arrival_day_median;
  if (L === "first") return fr.first[i][k];
  const v = fr[L][i][k];
  return v === null ? null : (sc === "per100k" ? (v / Math.max(pop, 1)) * 1e5 : v);
}
function layerMax() {
  const L = $("#map-layer").value; let mx = 0;
  if (L === "arrival") { for (const r of R.s.regions) if (r.arrival_day_median !== null) mx = Math.max(mx, r.arrival_day_median); return mx; }
  for (let i = 0; i < R.s.frames.t.length; i++) for (let k = 0; k < R.s.regions.length; k++) { const v = layerValue(i, k); if (v !== null && v > mx) mx = v; }
  return mx;
}
function layerBins(mx) {
  const L = $("#map-layer").value;
  if (!(mx > 0)) return [0];
  if (L === "arrival") return Array.from({ length: 7 }, (_, i) => (mx * (i + 1)) / 8);
  const b = []; for (let i = 7; i >= 1; i--) b.push(mx / 2 ** (i * 1.2)); return b;
}
function colorFor(v, bins) {
  if (v === null || v === undefined || !isFinite(v)) return css("--nodata");
  let k = 0; while (k < bins.length && v > bins[k]) k++;
  if ($("#map-layer").value === "arrival") k = 7 - k;     // 일찍 도착할수록 진하게
  return css(RAMP[Math.max(0, Math.min(k, 7))]);
}
const layerFmt = (v) => { const L = $("#map-layer").value; if (L === "first") return pct(v); if (L === "arrival") return v === null ? "도착 안 함" : `${fmt(v)}일`; return fmt(v); };
const unitLabel = () => ({ first: "", arrival: "" }[$("#map-layer").value] ?? ($("#map-scale").value === "per100k" ? " (10만 명당)" : " (명)"));

async function viewJob(id) {
  showTab("results");
  let s;
  try { s = await api(`/api/jobs/${id}/summary`); } catch (e) { $("#result-view").hidden = false; $("#rv-title").textContent = "결과 없음: " + e.message; return; }
  $("#result-view").hidden = false;
  R = { id, s, geo: null, names: {}, frame: 0, region: null };
  $("#rv-title").textContent = `${s.title} · ${s.method} · ${s.n_runs}회 · ${s.request.dataset}`;
  $("#rv-reuse").onclick = async () => { showTab("run"); await fillForm(s.request); msg("이 결과의 설정을 불러왔다. 바꿀 값만 고친 뒤 실행하면 비교하기 쉽다."); };
  const w = $("#rv-warnings"); w.innerHTML = "";
  w.append(el("div", { class: "warn" }, el("span", { class: "tag sim" }, "시뮬레이션 결과"), ` 가정에 따른 결과이며 예측이 아니다. 감염병 값: ${s.labels.disease_values}. 환경: ${s.labels.environment}.`));
  for (const x of s.warnings) w.append(el("div", { class: "warn" }, x));
  const tiles = $("#rv-tiles"); tiles.innerHTML = "";
  const tile = (k, v) => tiles.append(el("div", { class: "tile" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v)));
  tile("대유행 확률 (최대 I ≥ 1000)", s.n_runs > 1 ? pct(s.outbreak_probability) : (s.outbreak_probability ? "예 (ODE 1회)" : "아니오 (ODE 1회)"));
  tile("정점 I 평균", fmt(s.peak_I_mean));
  tile("정점일 중앙값", `${fmt(s.peak_day_median)}일`);
  tile("첫 감염 누적 (끝, 평균)", pct(s.daily.cum_first_mean[s.daily.cum_first_mean.length - 1] / s.population_total));
  tile("누적 사망 (끝, 평균)", fmt(s.daily.D_mean[s.daily.D_mean.length - 1]));
  tile("계산 시간", `${fmt(s.wall_seconds, 1)}초`);
  paramTable(s); r0Table(s);
  const ex = $("#rv-exports"); ex.innerHTML = "";
  for (const f of ["daily.csv", "regions.csv", "regions_daily.csv", "summary_daily.parquet", "summary_regions.parquet", "summary.json", "config.json", "request.json", "run_record.json", "ensemble.nc"])
    ex.append(el("a", { href: `/api/jobs/${id}/export/${f}`, download: f, class: "secondary", style: "padding:4px 10px;border:1px solid var(--border);border-radius:6px;text-decoration:none;color:var(--ink)" }, f));
  if (s.request.dataset !== "synthetic_single") {
    try { R.geo = await api(`/api/datasets/${s.request.dataset}/geojson`); for (const f of R.geo.features) R.names[f.id] = f.properties.name; } catch (_) { R.geo = null; }
  }
  R.idx = {}; s.regions.forEach((r, k) => (R.idx[r.id] = k));
  regionTable();
  const regSel = el("select", { multiple: true, size: 4, id: "chart-regions", "aria-label": "비교할 지역" });
  s.regions.forEach((r, k) => regSel.append(el("option", { value: k, selected: k < 3 }, `${r.id} ${R.names[r.id] || ""}`)));
  $("#chart-kind").parentElement.querySelector("#chart-regions")?.remove();
  regSel.hidden = $("#chart-kind").value !== "region";
  $("#chart-kind").parentElement.append(regSel);
  regSel.addEventListener("change", drawChart);
  drawMap(); drawChart();
  $("#region-detail").hidden = true;
  rerenderers = [drawChart, drawMap, () => R.region !== null && regionDetail(R.region)];
}
function paramTable(s) {
  const t = $("#rv-params"); t.innerHTML = "";
  t.append(el("tr", {}, el("th", {}, "매개변수"), el("th", { class: "num" }, "값"), el("th", {}, "출처")));
  const d = s.labels.disease || {}, src = s.labels.parameters || {};
  const rows = [["R0 (" + s.request.r0_reference + " 기준)", s.request.R0, "사용자 입력"], ["잠복기 (일) = 1/σ", 1 / d.sigma, src.sigma], ["감염 기간 (일) = 1/γ", 1 / d.gamma, src.gamma],
    ["면역 유지 기간 (일) = 1/λ", d.lam > 0 ? 1 / d.lam : "소실 없음", src.lam], ["첫 감염 치명률 f1", d.f1, src.f1], ["P1", d.P1, src.P1], ["Pmin", d.Pmin, src.Pmin],
    ["α", d.alpha, src.alpha], ["T1", d.T1, src.T1], ["β", d.beta, src.beta], ["φ 지수 δ", (d.phi || {}).delta, src.phi], ["M", d.M, src.M],
    ["시작 시 면역 비율", pct(s.request.initial_immune_fraction), s.request.initial_immune_fraction > 0 ? "사용자 입력" : "기본 가정값"],
    ["지역 간 이동 / 통근", `${s.request.use_mobility ? "켬" : "끔"} / ${s.request.use_commuting ? "켬" : "끔"}`, "사용자 입력"],
    ["기후 효과", s.request.climate === "none" ? "없음 (g = 1)" : `a_T ${s.request.climate_a_T}, a_H ${s.request.climate_a_H}`, s.request.climate === "none" ? "기본 가정값" : "사용자 입력 (가정)"]];
  for (const [k, v, sr] of rows) t.append(el("tr", {}, el("td", {}, k), el("td", { class: "num" }, typeof v === "number" ? fmt(v, Math.abs(v) < 1 ? 4 : 2) : String(v ?? "–")),
    el("td", {}, el("span", { class: "tag " + (String(sr).startsWith("사용자") ? "user" : "asm") }, sr || "기본 가정값"))));
}
function r0Table(s) {
  const r0 = $("#rv-r0"); r0.innerHTML = "";
  const dv = s.derived || {};
  r0.append(el("tr", {}, el("th", {}, "항목"), el("th", { class: "num" }, "값")));
  const add = (k, v) => r0.append(el("tr", {}, el("td", {}, k), el("td", { class: "num" }, v)));
  add("c0 결정 기준", `${dv.c0_basis}${dv.reference_region ? " (" + dv.reference_region + ")" : ""}`);
  add("c0 (1/일)", fmt(dv.c0, 4));
  for (const [k, v] of Object.entries(dv.c0_by_basis || {})) add(`  c0 (${k} 기준)`, v === null ? "계산 불가" : fmt(v, 4));
  add("R0 (reference 조건)", fmt(dv.R0_reference, 3));
  add("R0 (지역망, t0)", fmt(dv.R0_network_t0, 3));
  add("인구가중 평균 고립 R0", fmt(dv.R0_isolated_population_weighted_mean, 3));
  add("고립 R0 > 1 인구 비율", pct(dv.population_share_isolated_R0_gt1));
}
function regionTable() {
  const t = $("#rv-regions"); t.innerHTML = "";
  const cols = [["id", "id"], ["name", "이름"], ["population", "인구"], ["arrival_probability", "도착 확률"], ["arrival_day_median", "도착일 중앙값"],
    ["peak_day", "평균 정점일"], ["attack_mean", "첫 감염 누적 비율"], ["deaths_mean", "누적 사망 (평균)"]];
  let key = "arrival_day_median", asc = true;
  const render = () => {
    t.innerHTML = "";
    const hr = el("tr");
    for (const [k, lab] of cols) hr.append(el("th", { class: k === "id" || k === "name" ? "" : "num", style: "cursor:pointer", onclick: () => { asc = key === k ? !asc : true; key = k; render(); } }, lab + (key === k ? (asc ? " ▲" : " ▼") : "")));
    t.append(el("thead", {}, hr));
    const body = el("tbody");
    const data = R.s.regions.map((r, k) => ({ ...r, name: R.names[r.id] || "", k }));
    data.sort((a, b) => { const x = a[key], y = b[key]; if (x === null) return 1; if (y === null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); });
    for (const r of data) body.append(el("tr", { class: "region-row", onclick: () => regionDetail(r.k) }, el("td", {}, r.id), el("td", {}, r.name), el("td", { class: "num" }, fmt(r.population)),
      el("td", { class: "num" }, pct(r.arrival_probability)), el("td", { class: "num" }, r.arrival_day_median === null ? "–" : fmt(r.arrival_day_median)),
      el("td", { class: "num" }, fmt(r.peak_day)), el("td", { class: "num" }, pct(r.attack_mean)), el("td", { class: "num" }, fmt(r.deaths_mean))));
    t.append(body);
  };
  render();
}
function drawMap() {
  const box = $("#map");
  clearInterval(playTimer); playTimer = null; $("#play-btn").textContent = "재생";
  if (!R || !R.geo) { if (map) { map.remove(); map = null; geoLayer = null; } box.innerHTML = "<p class='note' style='padding:12px'>지도 없음 (합성 지역 또는 경계 자료 없음).</p>"; return; }
  if (!map) { box.innerHTML = ""; map = L.map(box, { attributionControl: true, zoomSnap: 0.25, preferCanvas: false }); map.attributionControl.setPrefix(false); map.attributionControl.addAttribution("경계: Natural Earth (공개 도메인)"); }
  if (geoLayer) geoLayer.remove();
  const fr = R.s.frames;
  const mx = layerMax(), bins = layerBins(mx);
  const style = (f) => ({ color: R.region !== null && R.idx[f.id] === R.region ? css("--ink") : css("--surface"), weight: R.region !== null && R.idx[f.id] === R.region ? 2.5 : 1,
    fillOpacity: 0.9, fillColor: colorFor(R.idx[f.id] !== undefined ? layerValue(R.frame, R.idx[f.id]) : null, bins) });
  geoLayer = L.geoJSON(R.geo, { style, onEachFeature: (f, layer) => {
    layer.bindTooltip(() => { const k = R.idx[f.id]; const v = k === undefined ? null : layerValue(R.frame, k);
      return `${esc(f.properties.name)} (${esc(f.id)})<br>${esc($("#map-layer").selectedOptions[0].text)}${esc(unitLabel())}: ${esc(layerFmt(v))}<br>인구: ${esc(fmt(f.properties.population))}<br>누르면 지역 상세`; }, { sticky: true });
    layer.on("click", () => { if (R.idx[f.id] !== undefined) regionDetail(R.idx[f.id]); });
  } }).addTo(map);
  const fit = () => { if (box.clientWidth > 0 && box.clientHeight > 0) { map.invalidateSize(); try { map.fitBounds(geoLayer.getBounds(), { padding: [8, 8] }); } catch (_) { /* 빈 경계 */ } } };
  fit(); rerenderMapFit = fit; setTimeout(fit, 50);
  const sl = $("#frame-slider"); sl.max = fr.t.length - 1; sl.value = R.frame;
  const setFrame = (i) => { R.frame = i; geoLayer.setStyle(style); $("#frame-label").textContent = `시작 후 ${Math.round(fr.t[i])}일`; sl.value = i; };
  sl.oninput = () => setFrame(+sl.value);
  setFrame(Math.min(R.frame, fr.t.length - 1));
  window.__mapStyle = () => geoLayer && geoLayer.setStyle(style);
  const lg = $("#map-legend"); lg.innerHTML = `${$("#map-layer").selectedOptions[0].text}${unitLabel()}: `;
  const L_ = $("#map-layer").value;
  const edges = [0, ...bins];
  for (let k = 0; k < 8 && k < edges.length; k++) {
    const hi = k + 1 < edges.length ? edges[k + 1] : mx;
    const col = L_ === "arrival" ? RAMP[7 - k] : RAMP[k];
    lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css(col)}` }), ` ≤${layerFmt(hi)}`));
  }
  lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css("--nodata")}` }), L_ === "arrival" ? " 도착 안 함" : " 자료 없음"));
  $("#map-def").textContent = LAYER_DEF[L_] + ". 색은 로그 간격 (작은 값 차이를 보기 위함).";
  $("#play-btn").onclick = () => {
    if (playTimer) { clearInterval(playTimer); playTimer = null; $("#play-btn").textContent = "재생"; return; }
    $("#play-btn").textContent = "멈춤";
    playTimer = setInterval(() => { let i = +sl.value + 1; if (i >= fr.t.length) i = 0; setFrame(i); }, +$("#play-speed").value);
  };
  drawFlows();
}
async function drawFlows() {
  if (flowLayer) { flowLayer.remove(); flowLayer = null; }
  if (!$("#map-flows").checked || !R || !R.geo || !map) return;
  let f; try { f = await api(`/api/datasets/${R.s.request.dataset}/flows?top=30`); } catch (_) { return; }
  const mxf = Math.max(1, ...f.flows.map((x) => x.per_day));
  flowLayer = L.layerGroup(f.flows.map((x) => L.polyline([[x.a_lonlat[1], x.a_lonlat[0]], [x.b_lonlat[1], x.b_lonlat[0]]],
    { color: css("--series-2"), weight: 1 + 4 * Math.sqrt(x.per_day / mxf), opacity: 0.8 })
    .bindTooltip(`${esc(x.a)} ↔ ${esc(x.b)}: 하루 약 ${esc(fmt(x.per_day))}명 (가정 총량 기반, 실측 아님)`))).addTo(map);
  $("#map-def").textContent += ` 이동망: 상위 30개 연결. ${f.note}`;
}
for (const id of ["#map-layer", "#map-scale"]) $(id).addEventListener("change", drawMap);
$("#map-flows").addEventListener("change", drawFlows);
$("#play-speed").addEventListener("change", () => { if (playTimer) { $("#play-btn").click(); $("#play-btn").click(); } });
$("#map-svg").addEventListener("click", () => {
  const svg = map && map.getPanes().overlayPane.querySelector("svg");
  exportSvg(svg, "map.svg", `${R ? R.s.title : ""} · ${$("#map-layer").selectedOptions[0].text}${unitLabel()} · 시작 후 ${R ? Math.round(R.s.frames.t[R.frame]) : 0}일 · 시뮬레이션 결과`);
});
function bandOf(d) { return $("#chart-band").value === "50" ? [d.q25, d.q75] : [d.q05, d.q95]; }
function drawChart() {
  if (!R) return;
  const d = R.s.daily, kind = $("#chart-kind").value, box = $("#ts-chart");
  const rs = $("#chart-regions"); if (rs) rs.hidden = kind !== "region";
  const xf = (v) => `${Math.round(v)}일`;
  let series, note = "";
  if (kind === "I") { series = [{ name: "중앙값", color: "--series-1", values: d.q50, band: bandOf(d) }, { name: "평균", color: "--series-2", values: d.mean, dash: "5 3" }];
    note = `전체 감염 중 인원 (모형 실제 감염). 띠: 실행 간 ${$("#chart-band").value === "50" ? "25–75%" : "5–95%"}.`; }
  else if (kind === "new") { series = [{ name: "일별 신규 첫 감염 (평균)", color: "--series-1", values: d.new_first_mean }]; note = "처음 감염된 사람의 하루 수 (S 감소). 재감염은 포함하지 않는다."; }
  else if (kind === "cum") { series = [{ name: "누적 첫 감염 (평균)", color: "--series-1", values: d.cum_first_mean }]; note = `한 번 이상 감염된 사람의 누적 (전체 인구 ${fmt(R.s.population_total)}명).`; }
  else if (kind === "RD") { series = [{ name: "누적 사망 (평균)", color: "--series-2", values: d.D_mean, band: [d.D_q05, d.D_q95] }];
    note = `누적 사망 (띠: 5–95%). 같은 시점의 회복·면역 상태 R 평균: ${fmt(d.R_mean[d.R_mean.length - 1])}명 (끝). 두 값은 크기가 달라 한 축에 그리지 않는다.`; }
  else {
    const ks = Array.from($("#chart-regions").selectedOptions).map((o) => +o.value).slice(0, 5);
    const fr = R.s.frames;
    series = ks.map((k, j) => ({ name: `${R.s.regions[k].id} ${R.names[R.s.regions[k].id] || ""}`, color: SERIES[j], values: fr.I.map((row) => (row[k] / Math.max(R.s.regions[k].population, 1)) * 1e5) }));
    legend($("#ts-legend"), series); lineChart(box, { xs: fr.t, series, xFormat: xf, ariaLabel: "지역 비교" });
    $("#ts-note").textContent = "지역별 감염 중 I (10만 명당, 실행 평균). 최대 5개 지역 (Ctrl/Shift 로 여러 개 선택)."; return;
  }
  legend($("#ts-legend"), series.flatMap((x) => (x.band ? [x, { name: "구간", color: x.color, dash: true }] : [x])));
  lineChart(box, { xs: d.t, series, xFormat: xf, xLabel: "시작 후 일수", ariaLabel: "시계열" });
  $("#ts-note").textContent = note;
}
for (const id of ["#chart-kind", "#chart-band"]) $(id).addEventListener("change", drawChart);
$("#chart-svg").addEventListener("click", () => exportSvg($("#ts-chart svg"), "chart.svg", `${R ? R.s.title : ""} · ${$("#chart-kind").selectedOptions[0].text} · 시뮬레이션 결과`));
function regionDetail(k) {
  R.region = k; window.__mapStyle && window.__mapStyle();
  const r = R.s.regions[k], fr = R.s.frames;
  $("#region-detail").hidden = false;
  $("#rd-title").textContent = `지역 상세: ${r.id} ${R.names[r.id] || ""}`;
  const series = [{ name: "감염 중 I (평균)", color: "--series-1", values: fr.I.map((x) => x[k]), band: [fr.I_q05.map((x) => x[k]), fr.I_q95.map((x) => x[k])] },
    { name: "잠복 E (평균)", color: "--series-3", values: fr.E.map((x) => x[k]), dash: "5 3" }];
  legend($("#rd-legend"), [...series, { name: "I 5–95%", color: "--series-1", dash: true }]);
  lineChart($("#rd-chart"), { xs: fr.t, series, xFormat: (v) => `${Math.round(v)}일`, height: 220, ariaLabel: "지역 상세" });
  const st = $("#rd-stats"); st.innerHTML = "";
  st.append(el("div", {}, `인구 ${fmt(r.population)} · 도착 확률 ${pct(r.arrival_probability)} · 도착일 중앙값 ${r.arrival_day_median === null ? "–" : fmt(r.arrival_day_median) + "일"} · 평균 정점일 ${fmt(r.peak_day)}일 · 정점 I 평균 ${fmt(r.peak_I_mean)} · 첫 감염 누적 ${pct(r.attack_mean)} · 누적 사망 ${fmt(r.deaths_mean)}`));
}
let lastCompare = null;
$("#compare-btn").addEventListener("click", async () => {
  const ids = $$("#jobs-table input[type=checkbox]:checked").map((c) => c.value).slice(0, 5);
  if (ids.length < 2) { alert("비교할 시나리오를 2개 이상 고른다."); return; }
  const sums = await Promise.all(ids.map((i) => api(`/api/jobs/${i}/summary`)));
  $("#compare-card").hidden = false;
  const draw = () => {
    legend($("#compare-legend"), sums.map((s, k) => ({ name: s.title, color: SERIES[k] })));
    const T = sums.reduce((a, s) => (s.daily.t.length > a.length ? s.daily.t : a), []);
    lineChart($("#compare-chart"), { xs: T, series: sums.map((s, k) => ({ name: s.title, color: SERIES[k], values: T.map((_, i) => (i < s.daily.q50.length ? s.daily.q50[i] : null)) })), xFormat: (v) => `${Math.round(v)}일`, ariaLabel: "시나리오 비교" });
  };
  draw(); rerenderers.push(draw);
  const flat = (o, p = "") => Object.entries(o || {}).flatMap(([k, v]) => (v && typeof v === "object" && !Array.isArray(v) ? flat(v, p + k + ".") : [[p + k, JSON.stringify(v)]]));
  const maps = sums.map((s) => Object.fromEntries(flat(s.request)));
  const keys = [...new Set(maps.flatMap((m) => Object.keys(m)))].filter((k) => k !== "title" && new Set(maps.map((m) => m[k])).size > 1);
  const head = ["시나리오", "다른 설정", "방법", "실행", "대유행 확률", "정점 I 평균", "정점일 중앙값", "첫 감염 누적 (끝)", "누적 사망 (끝)"];
  const rows = sums.map((s, j) => [s.title, keys.map((k) => `${k}=${maps[j][k] ?? "–"}`).join("; ") || "(차이 없음)", s.method, s.n_runs, pct(s.outbreak_probability), fmt(s.peak_I_mean),
    fmt(s.peak_day_median), pct(s.daily.cum_first_mean[s.daily.cum_first_mean.length - 1] / s.population_total), fmt(s.daily.D_mean[s.daily.D_mean.length - 1])]);
  const t = $("#compare-table"); t.innerHTML = "";
  t.append(el("tr", {}, ...head.map((h) => el("th", {}, h))));
  for (const r of rows) t.append(el("tr", {}, ...r.map((c, i) => el("td", { class: i >= 3 ? "num" : "small" }, c))));
  lastCompare = { head, rows };
});
$("#compare-csv").addEventListener("click", () => { if (!lastCompare) return;
  const q = (v) => `"${String(v).replace(/"/g, '""')}"`;
  download("scenario_comparison.csv", "﻿" + [lastCompare.head, ...lastCompare.rows].map((r) => r.map(q).join(",")).join("\n"), "text/csv"); });
// ------------------------------------------------------------------ 예측 검증
const COUNTRIES = ["KOR", "JPN", "NZL", "AUS", "GBR", "DEU", "ITA", "USA", "BRA", "IND", "ZAF", "SWE"];
async function loadValidation() {
  const box = $("#val-content"); box.innerHTML = "";
  let v;
  try { v = await api("/api/validation"); } catch (e) { box.append(el("p", { class: "err" }, e.message)); return; }
  const f = v.forecast;
  if (!f) box.append(el("p", { class: "note" }, "5단계 예측 검증 결과가 아직 없다 (scripts/report_stage5_forecast.py)."));
  else {
    box.append(el("p", { class: "note" }, `기점 ${f.first_origin} ~ ${f.last_origin}, 매 ${f.origins_every_weeks}주, SEIR 구간 ${f.knot_days}일. 공통 비교 행: 확진 ${f.common_set?.cases ?? "–"}, 사망 ${f.common_set?.deaths ?? "–"}.`));
    for (const [varName, title] of [["cases", "확진"], ["deaths", "사망"]]) {
      const byh = f[`${varName}_by_h`]; if (!byh) continue;
      const methods = ["persistence", "trend", "seir", "ml", "hybrid"];
      const hs = [1, 2, 3, 4];
      const card = el("div", { class: "card", style: "margin-bottom:12px" }, el("strong", {}, `${title}: 상대 로그 WIS (지속 예측 = 1, 낮을수록 좋음)`));
      const lg = el("div", { class: "chartlegend" }); const ch = el("div", { class: "chart" });
      card.append(lg, ch);
      const tbl = el("table");
      tbl.append(el("tr", {}, ...["예측 주", "방법", "n", "상대 로그 WIS", "상대 WIS(국가)", "MASE", "50% 포함", "90% 포함", "95% 포함", "로그 편향"].map((h) => el("th", {}, h))));
      for (const h of hs) for (const m of methods) { const r = byh[`${h}|${m}`]; if (!r) continue;
        tbl.append(el("tr", {}, el("td", {}, `${h}주`), el("td", {}, METHOD_LABEL[m]), el("td", { class: "num" }, r.n), el("td", { class: "num" }, fmt(r.rel_wis_log, 3)),
          el("td", { class: "num" }, fmt(r.rel_wis_nat_geo, 3)), el("td", { class: "num" }, fmt(r.mase, 2)), el("td", { class: "num" }, fmt(r.cov50, 2)),
          el("td", { class: "num" }, fmt(r.cov90, 2)), el("td", { class: "num" }, fmt(r.cov95, 2)), el("td", { class: "num" }, fmt(r.bias_log, 3)))); }
      card.append(el("div", { class: "tablewrap" }, tbl));
      box.append(card);
      const draw = () => {
        const ms = ["trend", "seir", "ml", "hybrid"];
        legend(lg, ms.map((m, k) => ({ name: METHOD_LABEL[m], color: SERIES[k] })));
        lineChart(ch, { xs: hs, refLine: 1, rightPad: 110, height: 240, series: ms.map((m, k) => ({ name: METHOD_LABEL[m], color: SERIES[k], label: METHOD_LABEL[m], values: hs.map((h) => byh[`${h}|${m}`]?.rel_wis_log ?? null) })),
          xFormat: (x) => `${Math.round(x)}주`, yFormat: (y) => fmt(y, 2), ariaLabel: `${title} 상대 WIS` });
      };
      draw(); rerenderers.push(draw);
      const bp = f[`${varName}_by_period`];
      if (bp) {
        const t2 = el("table");
        t2.append(el("tr", {}, el("th", {}, "시기 (달력 근사)"), ...methods.map((m) => el("th", { class: "num" }, METHOD_LABEL[m]))));
        const periods = [...new Set(Object.keys(bp).map((k) => k.split("|")[0]))];
        for (const p of periods) t2.append(el("tr", {}, el("td", {}, p), ...methods.map((m) => el("td", { class: "num" }, fmt(bp[`${p}|${m}`]?.rel_wis_log, 3)))));
        box.append(el("div", { class: "card", style: "margin-bottom:12px" }, el("strong", {}, `${title}: 시기별 상대 로그 WIS`), el("div", { class: "tablewrap" }, t2)));
      }
    }
  }
  const c = v.calibration;
  if (c) {
    const t = el("table");
    t.append(el("tr", {}, ...["국가", "수렴", "헤시안 PD", "확진 90% 포함", "확진 PIT KS", "사망 90% 포함"].map((h) => el("th", {}, h))));
    for (const [iso, r] of Object.entries(c.countries)) t.append(el("tr", {}, el("td", {}, iso), el("td", {}, r.success ? "예" : "아니오"), el("td", {}, String(r.hessian_pd)),
      el("td", { class: "num" }, fmt(r.diagnostics?.cases?.coverage90_in_sample, 2)), el("td", { class: "num" }, fmt(r.diagnostics?.cases?.pit_ks_stat, 3)), el("td", { class: "num" }, fmt(r.diagnostics?.deaths?.coverage90_in_sample, 2))));
    box.append(el("div", { class: "card" }, el("strong", {}, `3단계 적합 진단 (${(c.period || []).join(" ~ ")}, 표본 안)`), el("div", { class: "tablewrap" }, t)));
  }
  const cs = $("#vh-country"); cs.innerHTML = ""; COUNTRIES.forEach((x) => cs.append(el("option", { value: x }, x)));
  for (const id of ["#vh-country", "#vh-var", "#vh-method", "#vh-h"]) $(id).addEventListener("change", loadHistory);
  loadHistory();
}
async function loadHistory() {
  const iso = $("#vh-country").value, vr = $("#vh-var").value, m = $("#vh-method").value, h = +$("#vh-h").value;
  let d;
  try { d = await api(`/api/forecast-history?iso3=${iso}&var=${vr}`); } catch (e) { $("#vh-chart").innerHTML = ""; $("#vh-note").textContent = e.message; return; }
  const truthBy = {}; for (const r of d.rows) truthBy[r.target_end] = r.truth;
  if (!d.rows.length) { $("#vh-chart").innerHTML = ""; $("#vh-legend").innerHTML = ""; $("#vh-note").textContent = d.label; return; }
  const rows = d.rows.filter((r) => r.method === m && r.h === h).sort((a, b) => (a.target_end < b.target_end ? -1 : 1));
  const xs = rows.map((r) => new Date(r.target_end));
  const draw = () => {
    legend($("#vh-legend"), [{ name: "관측 (주간 합)", color: "--series-2" }, { name: `${METHOD_LABEL[m]} 중앙값`, color: "--series-1" }, { name: "5–95% 구간", color: "--series-1", dash: true }]);
    lineChart($("#vh-chart"), { xs, logY: true, series: [
      { name: `${METHOD_LABEL[m]} 중앙값`, color: "--series-1", values: rows.map((r) => r.q4), band: [rows.map((r) => r.q1), rows.map((r) => r.q7)] },
      { name: "관측", color: "--series-2", values: rows.map((r) => r.truth), points: true }],
      xFormat: (x) => (x instanceof Date ? x.toISOString().slice(0, 10) : x), ariaLabel: "과거 예측과 관측" });
  };
  draw(); rerenderers.push(draw);
  $("#vh-note").textContent = `${d.label}. 점 = 대상 주의 실제 관측, 선·띠 = ${h}주 전 기점의 예측. 세로축 로그.`;
}

// ------------------------------------------------------------------ 최신 자료 예측
function initLatest() {
  const cs = $("#lf-country"); COUNTRIES.forEach((x) => cs.append(el("option", { value: x }, x)));
  $("#lf-run").addEventListener("click", async () => {
    $("#lf-msg").textContent = "";
    let r; try { r = await api("/api/forecasts", { method: "POST", body: JSON.stringify({ iso3: cs.value }) }); } catch (e) { $("#lf-msg").textContent = e.message; return; }
    $("#lf-progress").hidden = false; $("#lf-bar").style.width = "10%";
    const t = setInterval(async () => {
      const s = await api(`/api/jobs/${r.job_id}`).catch(() => null); if (!s) return;
      $("#lf-msg").textContent = `${stateLabel(s.state)} ${s.message || ""}`;
      if (s.state === "running") $("#lf-bar").style.width = "50%";
      if (["done", "failed", "cancelled", "interrupted"].includes(s.state)) { clearInterval(t); $("#lf-bar").style.width = "100%"; if (s.state === "done") showForecast(r.job_id); }
    }, 1000);
  });
}
async function showForecast(id) {
  const box = $("#lf-result"); box.innerHTML = "";
  let f; try { f = await api(`/api/jobs/${id}/summary`); } catch (e) { box.append(el("p", { class: "err" }, e.message)); return; }
  box.append(el("p", {}, `${f.iso3} · 기점 ${f.origin} · 자료 마지막 날 ${f.data_last_date} · 실행일 ${f.run_date}`));
  for (const w of f.warnings || []) box.append(el("div", { class: "warn" }, w));
  for (const [vr, title] of [["cases", "주간 확진"], ["deaths", "주간 사망"]]) {
    const hist = f.methods._history?.[vr] || {};
    const hd = Object.keys(hist);
    const xs = [...hd, ...f.target_weeks].map((x) => new Date(x));
    const ms = ["seir", "ml", "hybrid", "trend"].filter((m) => f.methods[m]?.[vr]);
    const lg = el("div", { class: "chartlegend" }), ch = el("div", { class: "chart" });
    const card = el("div", { class: "card", style: "margin:12px 0" }, el("strong", {}, `${title}: 관측 (기점까지) 과 4주 예측 (중앙값, 5–95%)`), lg, ch);
    box.append(card);
    const draw = () => {
      legend(lg, [{ name: "관측", color: "--series-5" }, ...ms.map((m, k) => ({ name: METHOD_LABEL[m], color: SERIES[k] }))]);
      const series = [{ name: "관측", color: "--series-5", values: [...hd.map((k) => hist[k]), ...f.target_weeks.map(() => null)] }];
      ms.forEach((m, k) => { const q = f.methods[m][vr]; const pad = hd.map(() => null);
        series.push({ name: METHOD_LABEL[m], color: SERIES[k], values: [...pad, ...q.map((r) => r[4])], band: k === 0 ? [[...pad, ...q.map((r) => r[1])], [...pad, ...q.map((r) => r[7])]] : undefined }); });
      lineChart(ch, { xs, series, logY: true, xFormat: (x) => (x instanceof Date ? x.toISOString().slice(0, 10) : x), ariaLabel: `${title} 예측` });
    };
    draw(); rerenderers.push(draw);
    const t = el("table");
    t.append(el("tr", {}, el("th", {}, "방법"), ...f.target_weeks.map((w) => el("th", { class: "num" }, `${w} 주`))));
    for (const m of ["persistence", "trend", "seir", "ml", "hybrid"]) { const q = f.methods[m]?.[vr]; if (!q) continue;
      t.append(el("tr", {}, el("td", {}, METHOD_LABEL[m]), ...q.map((r) => el("td", { class: "num" }, `${fmt(r[4])} (${fmt(r[1])}–${fmt(r[7])})`)))); }
    card.append(el("div", { class: "tablewrap" }, t));
  }
  if (f.seir_fit) box.append(el("p", { class: "note" }, `SEIR 재추정: 수렴 ${f.seir_fit.success}, 헤시안 양의 정부호 ${f.seir_fit.hessian_pd}, 마지막 구간 R_t ${fmt(f.seir_fit.Rt_last, 2)}${f.seir_fit.Rt_last_capped ? " (상한 도달)" : ""}, 이어 시작한 기점 ${f.seir_fit.resumed_from}. 하이브리드 보정 적용: ${JSON.stringify(f.hybrid_active || {})}`));
}

// ------------------------------------------------------------------ 데이터 관리
async function loadDatasets() {
  const box = $("#ds-content"); box.innerHTML = "";
  let ds; try { ds = await api("/api/datasets"); } catch (e) { box.append(el("p", { class: "err" }, e.message)); return; }
  const up = $("#up-name"); up.innerHTML = "";
  for (const d of ds) {
    up.append(el("option", { value: d.name }, d.name));
    const t = el("table");
    t.append(el("tr", {}, ...["버전", "상태", "등록 (UTC)", "지역", "인구 합", "인구 출처", "검증", "이전 활성 대비", "메모", ""].map((h) => el("th", {}, h))));
    for (const v of d.versions) {
      const val = v.validation;
      const diff = v.diff_vs_active;
      const act = v.version === d.active ? el("strong", { class: "ok" }, "활성") : (val.ok ? el("button", { class: "secondary", onclick: async () => {
        try { await api(`/api/datasets/${d.name}/activate`, { method: "POST", body: JSON.stringify({ version: v.version }) }); loadDatasets(); } catch (e) { alert(e.message); } } }, "활성화") : el("span", { class: "err" }, "활성화 불가"));
      t.append(el("tr", {}, el("td", {}, v.version), el("td", {}, act), el("td", { class: "small" }, (v.registered_utc || "").replace("T", " ").replace("+00:00", "")),
        el("td", { class: "num" }, v.K), el("td", { class: "num" }, fmt(v.population_total)), el("td", { class: "small" }, v.population_source || "–"),
        el("td", { class: "small" }, val.ok ? el("span", { class: "ok" }, "통과") : el("span", { class: "err" }, "실패: " + val.errors.join("; ")), val.warnings.length ? el("div", { class: "muted" }, "경고: " + val.warnings.join("; ")) : ""),
        el("td", { class: "small" }, diff ? `인구 최대 변화 ${diff.population_rel_change_max === null ? "–" : pct(diff.population_rel_change_max)}, 5% 초과 ${diff.population_changed_over_5pct.length}곳, 추가 ${diff.added.length}, 삭제 ${diff.removed.length}` : "–"),
        el("td", { class: "small" }, v.note || ""), el("td", { class: "small muted" }, (v.sha256 || "").slice(0, 10))));
    }
    const card = el("div", { class: "card", style: "margin-bottom:12px" }, el("div", { class: "flex" }, el("strong", {}, d.name), el("span", { class: "note" }, `활성 ${d.active || "없음"} · 이전 활성 ${d.history.join(", ") || "없음"}`), el("span", { class: "spacer" }),
      el("button", { class: "secondary", disabled: !d.history.length, onclick: async () => { try { await api(`/api/datasets/${d.name}/rollback`, { method: "POST" }); loadDatasets(); } catch (e) { alert(e.message); } } }, "이전 활성 버전으로 되돌리기")),
      el("div", { class: "tablewrap" }, t));
    box.append(card);
  }
}
$("#up-file").addEventListener("change", (e) => { const f = e.target.files[0]; if (!f) return; const r = new FileReader(); r.onload = () => ($("#up-text").value = r.result); r.readAsText(f); });
$("#up-btn").addEventListener("click", async () => {
  $("#up-msg").textContent = "";
  let r; try { r = await api(`/api/datasets/${$("#up-name").value}/population-table`, { method: "POST", body: JSON.stringify({ table_text: $("#up-text").value, note: $("#up-note").value }) }); }
  catch (e) { $("#up-msg").innerHTML = ""; $("#up-msg").append(el("span", { class: "err" }, e.message)); return; }
  $("#up-msg").textContent = `점검 통과 (${r.check.rows}행). 새 버전 만드는 중…`;
  const t = setInterval(async () => {
    const s = await api(`/api/jobs/${r.job_id}`).catch(() => null); if (!s) return;
    if (["done", "failed", "cancelled", "interrupted"].includes(s.state)) {
      clearInterval(t);
      if (s.state === "done") { const res = await api(`/api/jobs/${r.job_id}/summary`); $("#up-msg").textContent = `${res.version} 등록 (활성화는 위 표에서). 검증: ${res.validation.ok ? "통과" : "실패"}`; loadDatasets(); }
      else $("#up-msg").textContent = `${stateLabel(s.state)}: ${s.message || ""}`;
    }
  }, 1000);
});

// ------------------------------------------------------------------ 자료 출처·갱신
async function loadSources() {
  let s, u;
  try { [s, u] = await Promise.all([api("/api/sources"), api("/api/updates")]); }
  catch (e) { $("#src-table").innerHTML = ""; $("#src-table").append(el("tr", {}, el("td", { class: "err" }, e.message))); return; }
  const upd = Object.fromEntries(u.datasets.map((x) => [x.id, x]));
  const t = $("#src-table"); t.innerHTML = "";
  t.append(el("tr", {}, ...["id", "종류", "상태", "등급", "출처", "라이선스", "기준 시점", "받은 시각 (UTC)", "마지막 갱신 확인", "주기 (일) · 자동", ""].map((h) => el("th", {}, h))));
  const ids = [...new Set([...s.datasets.map((r) => r.id), ...u.datasets.map((r) => r.id)])];
  for (const id of ids) {
    const r = s.datasets.find((x) => x.id === id) || { id, kind: "", status: upd[id]?.status || "not fetched" };
    const x = upd[id] || {};
    const last = x.last_check ? `${x.last_check.result} (${(x.last_check.checked_utc || "").replace("+00:00", "")})` : "–";
    const iv = el("input", { type: "number", min: 1, max: 3650, value: x.policy?.interval_days ?? "", placeholder: "수동", style: "width:70px", "aria-label": "주기" });
    const au = el("input", { type: "checkbox", checked: !!x.policy?.auto, "aria-label": "자동" });
    const save = el("button", { class: "secondary", onclick: async () => {
      try { await api(`/api/updates/${id}/policy`, { method: "POST", body: JSON.stringify({ interval_days: iv.value ? +iv.value : null, auto: au.checked }) }); save.textContent = "저장됨"; }
      catch (e) { alert(e.message); } } }, "저장");
    const chk = el("button", { class: "secondary", onclick: async () => {
      chk.disabled = true; chk.textContent = "확인 중…";
      try { const j = await api(`/api/updates/${id}/check`, { method: "POST" });
        const timer = setInterval(async () => { const st = await api(`/api/jobs/${j.job_id}`).catch(() => null); if (!st) return;
          if (["done", "failed", "cancelled", "interrupted"].includes(st.state)) { clearInterval(timer); loadSources(); } }, 1500);
      } catch (e) { alert(e.message); chk.disabled = false; chk.textContent = "갱신 확인"; } } }, "갱신 확인");
    t.append(el("tr", {}, el("td", {}, id), el("td", {}, r.kind || ""), el("td", { class: r.status === "ok" ? "ok" : "err" }, r.status === "ok" ? "확보" : `미확보 (${r.status})`),
      el("td", {}, r.tier ? el("span", { class: "tag " + (r.tier === "secondary" ? "sec" : "obs") }, r.tier) : "–"), el("td", { class: "small" }, r.source || ""),
      el("td", { class: "small" }, r.license || x.license || ""), el("td", { class: "small" }, r.time_reference || x.time_reference || ""),
      el("td", { class: "small" }, (r.retrieved_utc || "–").replace("+00:00", "")), el("td", { class: "small" }, last),
      el("td", { class: "small" }, el("span", { class: "flex" }, iv, el("label", { class: "inline" }, au, "자동"), save)), el("td", {}, chk)));
  }
  const lg = $("#upd-log"); lg.innerHTML = "";
  lg.append(el("tr", {}, ...["시각 (UTC)", "자료", "결과", "내용"].map((h) => el("th", {}, h))));
  const lab = { updated: "갱신됨 (이전 판 보관)", unchanged: "변경 없음", failed: "실패 (기존 자료 유지)", unavailable: "받을 주소 없음", changed_not_applied: "변경 있음 (적용 안 함)" };
  for (const x of (u.log || []).slice().reverse().slice(0, 30)) lg.append(el("tr", {}, el("td", { class: "small" }, (x.checked_utc || "").replace("+00:00", "")), el("td", {}, x.id),
    el("td", { class: x.result === "failed" ? "err" : "" }, lab[x.result] || x.result), el("td", { class: "small" }, x.message || "")));
  if (!(u.log || []).length) lg.append(el("tr", {}, el("td", { colspan: 4, class: "muted" }, "아직 갱신 확인 기록이 없다.")));
  const a = $("#asm-table"); a.innerHTML = "";
  a.append(el("tr", {}, ...["이름", "값", "쓰는 곳", "근거", "불확실성"].map((h) => el("th", {}, h))));
  for (const r of s.assumptions) a.append(el("tr", {}, el("td", {}, r.name, " ", el("span", { class: "tag asm" }, "기본 가정값")), el("td", {}, r.value), el("td", { class: "small" }, r.where), el("td", { class: "small" }, r.basis), el("td", { class: "small" }, r.uncertainty)));
}

loadHome(); loaded.home = true;
initForm();
window.addEventListener("resize", () => { clearTimeout(window.__rz); window.__rz = setTimeout(rerender, 200); });
