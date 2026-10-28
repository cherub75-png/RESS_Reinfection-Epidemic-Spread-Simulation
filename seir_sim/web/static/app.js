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
  if (a >= 1e4) return nf.format(Math.round(v));
  if (a >= 100) return nf.format(Math.round(v));
  return nf.format(v);
}
const pct = (v) => (v === null || v === undefined ? "–" : (100 * v).toFixed(1) + "%");
const SERIES = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5"];
const RAMP = ["--ramp-0", "--ramp-1", "--ramp-2", "--ramp-3", "--ramp-4", "--ramp-5", "--ramp-6", "--ramp-7"];
const METHOD_LABEL = { persistence: "지속", trend: "감쇠 추세", seasonal52: "52주 계절", seir: "보정 SEIR", ml: "ML (분위수 GBM)", hybrid: "SEIR+ML 잔차" };

const FIELD = { title: "제목", dataset: "데이터셋", population: "인구", R0: "R0", r0_reference: "R0 기준", reference_region: "기준 지역",
  method: "방법", n_runs: "실행 횟수", n_workers: "작업자 수", days: "기간", start_date: "시작일", seeds: "초기 감염", interventions: "개입",
  eta: "밀도 지수", seed: "난수 시드", count: "인원", region: "지역", start: "시작일", end: "끝일", value: "u", regions: "지역" };
function fieldName(loc) { return (loc || []).filter((x) => x !== "body").map((x) => (typeof x === "number" ? `${x + 1}번째` : FIELD[x] || x)).join(" ") || "입력"; }
function koMsg(x) {
  const c = x.ctx || {};
  return ({ greater_than: `${c.gt} 보다 커야 한다`, greater_than_equal: `${c.ge} 이상이어야 한다`, less_than: `${c.lt} 보다 작아야 한다`,
    less_than_equal: `${c.le} 이하여야 한다`, missing: "값이 필요하다", extra_forbidden: "허용되지 않는 항목", literal_error: `허용 값: ${c.expected}`,
    string_pattern_mismatch: "형식이 맞지 않는다", too_short: "항목이 너무 적다", too_long: "항목이 너무 많다", int_parsing: "정수가 아니다",
    float_parsing: "숫자가 아니다", value_error: x.msg })[x.type] || x.msg;
}

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json", "X-SEIR-Client": "web" }, ...opts });
  let body = null;
  try { body = await r.json(); } catch (_) { /* 본문 없음 */ }
  if (!r.ok) {
    const d = body && body.detail;
    const msg = Array.isArray(d) ? d.map((x) => `${fieldName(x.loc)}: ${koMsg(x)}`).join("; ") : (d || r.statusText);
    throw new Error(msg);
  }
  return body;
}

// ------------------------------------------------------------------ 테마·탭
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem("theme", t); } catch (_) { /* 저장 불가 환경 */ }
  rerender();
}
let rerenderers = [];
function rerender() { for (const f of rerenderers) { try { f(); } catch (_) { /* 다음 그림 */ } } }
$("#theme").addEventListener("change", (e) => applyTheme(e.target.value));
try { const t = localStorage.getItem("theme") || ""; $("#theme").value = t; if (t) document.documentElement.dataset.theme = t; } catch (_) { /* 없음 */ }
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rerender);

const loaded = {};
function showTab(name) {
  for (const b of $$("#tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
  for (const s of $$("main > section")) s.hidden = s.id !== `tab-${name}`;
  if (!loaded[name]) { loaded[name] = true; ({ results: loadJobs, validation: loadValidation, latest: initLatest, data: loadDatasets, sources: loadSources })[name]?.(); }
  if (name === "results" && map) setTimeout(() => { if (rerenderMapFit) rerenderMapFit(); }, 50);
}
for (const b of $$("#tabs button")) b.addEventListener("click", () => showTab(b.dataset.tab));

// ------------------------------------------------------------------ 선 그래프 (SVG, 십자선·툴팁)
function lineChart(box, o) {
  const draw = () => {
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
    let y0 = o.yMin !== undefined ? o.yMin : (logY ? Math.min(...pos) : Math.min(0, ...pos));
    let y1 = Math.max(...pos, o.yMin !== undefined ? o.yMin + 1e-9 : 1e-9);
    if (logY) { y0 = Math.max(y0, 1e-3); }
    if (y1 <= y0) y1 = y0 + 1;
    const xv = xs.map((x) => (x instanceof Date ? x.getTime() : x));
    const x0 = Math.min(...xv), x1 = Math.max(...xv) === x0 ? x0 + 1 : Math.max(...xv);
    const X = (x) => m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r);
    const ly = (v) => (logY ? Math.log10(Math.max(v, y0)) : v);
    const Y = (v) => H - m.b - ((ly(v) - ly(y0)) / (ly(y1) - ly(y0) || 1)) * (H - m.t - m.b);
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", o.ariaLabel || "선 그래프");
    const mk = (t, a) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
    // 축·격자
    const g = mk("g", { class: "axis" });
    const yt = logY ? (() => { const out = []; for (let p = Math.floor(Math.log10(y0)); p <= Math.ceil(Math.log10(y1)); p++) out.push(10 ** p); return out.filter((v) => v >= y0 * 0.999 && v <= y1 * 1.001); })()
      : Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4);
    for (const v of yt) {
      g.append(mk("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: "gridline" }));
      const t = mk("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }); t.textContent = (o.yFormat || fmt)(v); g.append(t);
    }
    const nx = Math.min(6, xs.length);
    for (let i = 0; i < nx; i++) {
      const xi = x0 + ((x1 - x0) * i) / Math.max(1, nx - 1);
      const t = mk("text", { x: X(xi), y: H - m.b + 16, "text-anchor": "middle" });
      t.textContent = (o.xFormat || ((v) => fmt(v)))(xs[0] instanceof Date ? new Date(xi) : xi); g.append(t);
    }
    g.append(mk("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }));
    if (o.yLabel) { const t = mk("text", { x: 4, y: m.t + 4, "text-anchor": "start" }); t.textContent = ""; g.append(t); }
    if (o.xLabel) { const t = mk("text", { x: W - m.r, y: H - 4, "text-anchor": "end" }); t.textContent = o.xLabel; g.append(t); }
    svg.append(g);
    if (o.refLine !== undefined) svg.append(mk("line", { x1: m.l, x2: W - m.r, y1: Y(o.refLine), y2: Y(o.refLine), stroke: css("--ink-3"), "stroke-dasharray": "4 3", "stroke-width": 1 }));
    // 띠, 선, 점
    for (const s of o.series) {
      const col = css(s.color);
      if (s.band) {
        let d = "", started = false;
        const [lo, hi] = s.band;
        const seg = [];
        for (let i = 0; i < xs.length; i++) if (lo[i] !== null && hi[i] !== null && isFinite(lo[i]) && isFinite(hi[i])) seg.push(i);
        if (seg.length) {
          d = seg.map((i, k) => `${k ? "L" : "M"}${X(xv[i])},${Y(hi[i])}`).join("") + seg.slice().reverse().map((i) => `L${X(xv[i])},${Y(lo[i])}`).join("") + "Z";
          svg.append(mk("path", { d, fill: col, "fill-opacity": s.bandOpacity || 0.18, stroke: "none" }));
        }
        started = started || false;
      }
      if (s.points) {
        for (let i = 0; i < xs.length; i++) if (s.values[i] !== null && isFinite(s.values[i])) svg.append(mk("circle", { cx: X(xv[i]), cy: Y(s.values[i]), r: 3, fill: col, stroke: css("--surface"), "stroke-width": 1.5 }));
        continue;
      }
      let d = "", pen = false;
      for (let i = 0; i < xs.length; i++) {
        const v = s.values[i];
        if (v === null || v === undefined || !isFinite(v) || (logY && v <= 0)) { pen = false; continue; }
        d += `${pen ? "L" : "M"}${X(xv[i])},${Y(v)}`; pen = true;
      }
      svg.append(mk("path", { d, fill: "none", stroke: col, "stroke-width": s.width || 2, "stroke-dasharray": s.dash || "", "stroke-linejoin": "round", "stroke-linecap": "round" }));
      if (s.label) { // 끝 직접 이름표
        let j = s.values.length - 1; while (j >= 0 && (s.values[j] === null || !isFinite(s.values[j]))) j--;
        if (j >= 0) { const t = mk("text", { x: X(xv[j]) + 6, y: Y(s.values[j]) + 4, fill: css("--ink"), "font-size": 11 }); t.textContent = s.label; svg.append(t); }
      }
    }
    // 십자선·툴팁
    const cross = mk("line", { y1: m.t, y2: H - m.b, stroke: css("--ink-3"), "stroke-width": 1, visibility: "hidden" });
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
        const v = s.values[bi];
        let txt = `${s.name}: ${(o.yFormat || fmt)(v)}`;
        if (s.band) txt += ` (${(o.yFormat || fmt)(s.band[0][bi])} – ${(o.yFormat || fmt)(s.band[1][bi])})`;
        tip.append(el("div", {}, el("span", { class: "sw", style: `background:${css(s.color)}` }), txt));
      }
      tip.hidden = false;
      const bx = box.getBoundingClientRect();
      let left = ev.clientX - bx.left + 14; if (left > bx.width - 220) left = ev.clientX - bx.left - 230;
      tip.style.left = `${left}px`; tip.style.top = `${ev.clientY - bx.top - 10}px`;
    });
    hit.addEventListener("mouseleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
    box.append(svg, tip);
  };
  draw();
  return draw;
}
function legend(box, items) {
  box.innerHTML = "";
  for (const it of items) box.append(el("span", {}, el("span", { class: "sw", style: `background:${css(it.color)}${it.dash ? ";opacity:.6" : ""}` }), it.name));
}

// ------------------------------------------------------------------ 시나리오 양식
let regionInfo = { ids: [], names: [] };
async function initForm() {
  const sel = $("#f-dataset");
  let ds = [];
  try { ds = await api("/api/datasets"); } catch (e) { $("#run-msg").textContent = "데이터셋 목록 실패: " + e.message; }
  for (const d of ds) {
    const v = d.versions.find((x) => x.version === d.active);
    sel.append(el("option", { value: d.name }, `${d.name} (${d.active || "활성 없음"}, ${v ? v.K : "?"}개 지역${v && v.synthetic ? ", 합성" : ""})`));
  }
  sel.append(el("option", { value: "synthetic_single" }, "합성 단일 지역 (실제 지역 아님)"));
  try { const df = await api("/api/defaults"); $("#disease-label").textContent = `감염병 매개변수: ${df.disease_label}. σ=${df.disease.sigma}, γ=${df.disease.gamma}, P1=${df.disease.P1}, Pmin=${df.disease.Pmin}, λ=${df.disease.lam}, f1=${df.disease.f1}, M=${df.disease.M}`; } catch (_) { /* 기본 문구 유지 */ }
  sel.addEventListener("change", onDataset);
  $("#f-basis").addEventListener("change", () => { $("#f-refreg-wrap").hidden = $("#f-basis").value !== "region"; });
  $("#add-seed").addEventListener("click", () => addSeed());
  $("#add-int").addEventListener("click", () => addInt());
  await onDataset();
}
async function onDataset() {
  const name = $("#f-dataset").value;
  $("#f-pop-wrap").hidden = name !== "synthetic_single";
  if (name === "synthetic_single") { regionInfo = { ids: ["region0"], names: ["합성 지역"] }; $("#f-dataset-note").textContent = "합성 단일 지역: 코드 검증용이며 실제 지역이 아니다."; }
  else {
    try {
      const r = await api(`/api/datasets/${name}/regions`);
      regionInfo = r;
      const p = r.provenance || {};
      const pop = p.population || {};
      $("#f-dataset-note").textContent = `경계: ${p.boundaries || "?"} · 인구: ${pop.source || (pop.primary && pop.primary.source) || "?"} · 가정: 항공 ${p.assumptions?.air_trips_per_day ?? "?"}회/일, 통근 ${p.assumptions?.commute_fraction ?? "?"}, 접촉 ${p.assumptions?.destination_contact_share ?? "?"}`;
    } catch (e) { $("#f-dataset-note").textContent = "지역 목록 실패: " + e.message; }
  }
  const ref = $("#f-refreg"); ref.innerHTML = "";
  regionInfo.ids.forEach((id, i) => ref.append(el("option", { value: id }, `${id} ${regionInfo.names[i] || ""}`)));
  $("#f-seeds").innerHTML = ""; $("#f-ints").innerHTML = "";
  const pref = ["KR-11", "CHN"].find((x) => regionInfo.ids.includes(x)) || regionInfo.ids[0];
  addSeed(pref, 10);
}
function regionSelect(value, multiple) {
  const s = el("select", multiple ? { multiple: true, size: 3 } : {});
  if (multiple) s.append(el("option", { value: "", selected: true }, "전체 지역"));
  regionInfo.ids.forEach((id, i) => s.append(el("option", { value: id, selected: id === value }, `${id} ${regionInfo.names[i] || ""}`)));
  return s;
}
function addSeed(region, count = 10) {
  const row = el("div", { class: "row" },
    el("label", {}, "지역", regionSelect(region)), el("label", {}, "인원", el("input", { type: "number", value: count, min: 1 })),
    el("button", { type: "button", class: "secondary", onclick: () => row.remove() }, "삭제"));
  $("#f-seeds").append(row);
}
function addInt() {
  const row = el("div", { class: "row" },
    el("label", {}, "시작일", el("input", { type: "number", value: 30, min: 0 })), el("label", {}, "끝일", el("input", { type: "number", value: 90, min: 1 })),
    el("label", {}, "u (0~1)", el("input", { type: "number", value: 0.3, min: 0, max: 1, step: 0.05 })),
    el("label", {}, "지역", regionSelect("", true)),
    el("button", { type: "button", class: "secondary", onclick: () => row.remove() }, "삭제"));
  $("#f-ints").append(row);
}
function formRequest() {
  const f = $("#scenario-form");
  const v = (n) => f.elements[n].value;
  const req = {
    title: v("title"), dataset: v("dataset"), R0: +v("R0"), r0_reference: v("r0_reference"), method: v("method"),
    n_runs: +v("n_runs"), n_workers: +v("n_workers"), days: +v("days"), start_date: v("start_date"), eta: +v("eta"), seed: +v("seed"),
    seeds: $$("#f-seeds .row").map((r) => ({ region: $("select", r).value, count: +$("input", r).value })),
    interventions: $$("#f-ints .row").map((r) => {
      const ins = $$("input", r); const regs = Array.from($("select", r).selectedOptions).map((o) => o.value).filter((x) => x);
      return { start: +ins[0].value, end: +ins[1].value, value: +ins[2].value, regions: regs.length ? regs : null };
    }),
  };
  if (req.dataset === "synthetic_single") req.population = +v("population");
  if (req.r0_reference === "region") req.reference_region = v("reference_region");
  return req;
}
$("#scenario-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#run-msg").textContent = "";
  let res;
  try { res = await api("/api/scenarios", { method: "POST", body: JSON.stringify(formRequest()) }); }
  catch (err) { $("#run-msg").innerHTML = ""; $("#run-msg").append(el("span", { class: "err" }, "입력 오류: " + err.message)); return; }
  trackJob(res.job_id, formRequest().title, (s) => { if (s.state === "done") { loaded.results = false; showTab("results"); viewJob(res.job_id); } });
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

// ------------------------------------------------------------------ 결과·비교
async function loadJobs() {
  const tb = $("#jobs-table tbody"); tb.innerHTML = "";
  let list = [];
  try { list = await api("/api/jobs"); } catch (e) { tb.append(el("tr", {}, el("td", { colspan: 5, class: "err" }, e.message))); return; }
  if (!list.length) tb.append(el("tr", {}, el("td", { colspan: 5, class: "muted" }, "저장된 작업이 없다.")));
  for (const j of list) {
    const kindLabel = { scenario: "시나리오", forecast: "최신 예측", dataset: "데이터 갱신" }[j.kind] || j.kind;
    const cb = j.kind === "scenario" && j.state === "done" ? el("input", { type: "checkbox", value: j.id, "aria-label": "비교 선택" }) : "";
    const tr = el("tr", {}, el("td", {}, cb), el("td", {}, el("a", { href: "#", onclick: (e) => { e.preventDefault(); openJob(j); } }, j.title || j.id.slice(0, 8))),
      el("td", {}, kindLabel), el("td", {}, stateLabel(j.state) + (j.state === "running" ? ` ${Math.round(100 * (j.progress || 0))}%` : "")),
      el("td", { class: "small muted" }, (j.created_utc || "").replace("T", " ").replace("+00:00", "")));
    tb.append(tr);
  }
}
$("#refresh-jobs").addEventListener("click", loadJobs);
function openJob(j) {
  if (j.kind === "scenario") viewJob(j.id);
  else if (j.kind === "forecast") { showTab("latest"); showForecast(j.id); }
  else { showTab("data"); }
}
let map = null, geoLayer = null, playTimer = null;
async function viewJob(id) {
  showTab("results");
  let s;
  try { s = await api(`/api/jobs/${id}/summary`); } catch (e) { $("#result-view").hidden = false; $("#rv-title").textContent = "결과 없음: " + e.message; return; }
  $("#result-view").hidden = false;
  $("#rv-title").textContent = `${s.title} · ${s.method} · ${s.n_runs}회 · ${s.request.dataset}`;
  const w = $("#rv-warnings"); w.innerHTML = "";
  w.append(el("div", { class: "warn" }, `시나리오 결과 (예측 아님). 감염병 값: ${s.labels.disease_values}. 환경: ${s.labels.environment}.`));
  for (const x of s.warnings) w.append(el("div", { class: "warn" }, x));
  const tiles = $("#rv-tiles"); tiles.innerHTML = "";
  const tile = (k, v) => tiles.append(el("div", { class: "tile" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v)));
  tile("대유행 확률 (최대 I ≥ 1000)", s.n_runs > 1 ? pct(s.outbreak_probability) : (s.outbreak_probability ? "예 (ODE 1회)" : "아니오 (ODE 1회)"));
  tile("정점 I 평균", fmt(s.peak_I_mean));
  tile("정점일 중앙값", `${fmt(s.peak_day_median)}일`);
  tile("계산 시간", `${fmt(s.wall_seconds, 1)}초`);
  // 시계열
  const d = s.daily;
  const tsDraw = () => {
    legend($("#ts-legend"), [{ name: "중앙값", color: "--series-1" }, { name: "평균", color: "--series-2" }, { name: "5–95% 구간", color: "--series-1", dash: true }]);
    return lineChart($("#ts-chart"), { xs: d.t, series: [
      { name: "중앙값", color: "--series-1", values: d.q50, band: [d.q05, d.q95] },
      { name: "평균", color: "--series-2", values: d.mean, dash: "5 3" }], xFormat: (v) => `${Math.round(v)}일`, xLabel: "시작 후 일수", ariaLabel: "전체 감염 중 인원 시계열" });
  };
  tsDraw();
  // R0 기준
  const r0 = $("#rv-r0"); r0.innerHTML = "";
  const dv = s.derived || {};
  r0.append(el("tr", {}, el("th", {}, "항목"), el("th", { class: "num" }, "값")));
  const add = (k, v) => r0.append(el("tr", {}, el("td", {}, k), el("td", { class: "num" }, v)));
  add("c0 결정 기준", `${dv.c0_basis}${dv.reference_region ? " (" + dv.reference_region + ")" : ""}`);
  add("c0", fmt(dv.c0, 4));
  for (const [k, v] of Object.entries(dv.c0_by_basis || {})) add(`  c0 (${k} 기준)`, v === null ? "계산 불가" : fmt(v, 4));
  add("R0 (reference 조건)", fmt(dv.R0_reference, 3));
  add("R0 (지역망, t0)", fmt(dv.R0_network_t0, 3));
  add("인구가중 평균 고립 R0", fmt(dv.R0_isolated_population_weighted_mean, 3));
  add("고립 R0 > 1 인구 비율", pct(dv.population_share_isolated_R0_gt1));
  // 내보내기
  const ex = $("#rv-exports"); ex.innerHTML = "";
  for (const f of ["daily.csv", "regions.csv", "summary.json", "run_record.json", "config.json", "ensemble.nc"])
    ex.append(el("a", { class: "secondary", href: `/api/jobs/${id}/export/${f}`, download: f, style: "padding:4px 10px;border:1px solid var(--border);border-radius:6px;text-decoration:none;color:var(--ink)" }, f));
  // 지역 표
  let names = {};
  let geo = null;
  if (s.request.dataset !== "synthetic_single") {
    try { geo = await api(`/api/datasets/${s.request.dataset}/geojson`); for (const f of geo.features) names[f.id] = f.properties.name; } catch (_) { /* 지도 없이 */ }
  }
  regionTable(s.regions, names);
  drawMap(geo, s, names);
  rerenderers = [tsDraw, () => drawMap(geo, s, names)];
}
function regionTable(rows, names) {
  const t = $("#rv-regions"); t.innerHTML = "";
  const cols = [["id", "id"], ["name", "이름"], ["population", "인구"], ["arrival_probability", "도착 확률"], ["arrival_day_median", "도착일 중앙값"],
    ["peak_day", "평균 정점일"], ["attack_mean", "1회 이상 감염 비율"], ["deaths_mean", "사망 (평균)"]];
  let key = "arrival_day_median", asc = true;
  const render = () => {
    t.innerHTML = "";
    const hr = el("tr");
    for (const [k, lab] of cols) hr.append(el("th", { class: k === "id" || k === "name" ? "" : "num", style: "cursor:pointer", onclick: () => { asc = key === k ? !asc : true; key = k; render(); } }, lab + (key === k ? (asc ? " ▲" : " ▼") : "")));
    t.append(el("thead", {}, hr));
    const body = el("tbody");
    const data = rows.map((r) => ({ ...r, name: names[r.id] || "" }));
    data.sort((a, b) => { const x = a[key], y = b[key]; if (x === null) return 1; if (y === null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); });
    for (const r of data) body.append(el("tr", {}, el("td", {}, r.id), el("td", {}, r.name), el("td", { class: "num" }, fmt(r.population)),
      el("td", { class: "num" }, pct(r.arrival_probability)), el("td", { class: "num" }, r.arrival_day_median === null ? "–" : fmt(r.arrival_day_median)),
      el("td", { class: "num" }, fmt(r.peak_day)), el("td", { class: "num" }, pct(r.attack_mean)), el("td", { class: "num" }, fmt(r.deaths_mean))));
    t.append(body);
  };
  render();
}
function binsFor(max) { // 0 과 log 간격 7개 경계 (최댓값 기준)
  if (!(max > 0)) return [0];
  const b = []; for (let i = 7; i >= 1; i--) b.push(max / 2 ** (i * 1.2)); return b;
}
function colorFor(v, bins) {
  if (v === null || v === undefined || !isFinite(v)) return css("--nodata");
  let k = 0; while (k < bins.length && v > bins[k]) k++;
  return css(RAMP[Math.min(k, 7)]);
}
function drawMap(geo, s, names) {
  const box = $("#map");
  clearInterval(playTimer); $("#play-btn").textContent = "재생";
  if (!geo) { box.innerHTML = "<p class='note' style='padding:12px'>지도 없음 (합성 지역 또는 경계 자료 없음).</p>"; if (map) { map.remove(); map = null; } return; }
  if (!map) { box.innerHTML = ""; map = L.map(box, { attributionControl: true, zoomSnap: 0.25 }); map.attributionControl.setPrefix(false); map.attributionControl.addAttribution("경계: Natural Earth (공개 도메인)"); }
  if (geoLayer) geoLayer.remove();
  const fr = s.frames, idx = {};
  s.regions.forEach((r, k) => (idx[r.id] = k));
  const bins = binsFor(fr.max);
  let cur = 0;
  const style = (f) => ({ color: css("--surface"), weight: 1, fillOpacity: 0.9, fillColor: colorFor(idx[f.id] !== undefined ? fr.prevalence_per_100k[cur][idx[f.id]] : null, bins) });
  geoLayer = L.geoJSON(geo, { style, onEachFeature: (f, layer) => layer.bindTooltip(() => {
    const k = idx[f.id]; const v = k === undefined ? null : fr.prevalence_per_100k[cur][k];
    return `${esc(f.properties.name)} (${esc(f.id)})<br>10만 명당 유병: ${esc(fmt(v))}<br>인구: ${esc(fmt(f.properties.population))}`; }, { sticky: true }) }).addTo(map);
  const fit = () => { if (box.clientWidth > 0 && box.clientHeight > 0) { map.invalidateSize(); try { map.fitBounds(geoLayer.getBounds(), { padding: [8, 8] }); } catch (_) { /* 빈 경계 */ } } };
  fit();
  rerenderMapFit = fit;
  const sl = $("#frame-slider"); sl.max = fr.t.length - 1; sl.value = 0;
  const setFrame = (i) => { cur = i; geoLayer.setStyle(style); $("#frame-label").textContent = `${Math.round(fr.t[i])}일`; sl.value = i; };
  sl.oninput = () => setFrame(+sl.value);
  setFrame(0);
  const lg = $("#map-legend"); lg.innerHTML = "10만 명당 유병: ";
  const edges = [0, ...bins];
  for (let k = 0; k < 8 && k < edges.length; k++) lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css(RAMP[k])}` }), ` ≤${fmt(k + 1 < edges.length ? edges[k + 1] : fr.max)}`));
  lg.append(el("span", {}, el("span", { class: "sw", style: `background:${css("--nodata")}` }), " 자료 없음"));
  $("#play-btn").onclick = () => {
    if (playTimer) { clearInterval(playTimer); playTimer = null; $("#play-btn").textContent = "재생"; return; }
    $("#play-btn").textContent = "멈춤";
    playTimer = setInterval(() => { let i = +sl.value + 1; if (i >= fr.t.length) i = 0; setFrame(i); }, 180);
  };
  setTimeout(fit, 50);
}
let rerenderMapFit = null;
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
  draw();
  rerenderers.push(draw);
  const t = $("#compare-table"); t.innerHTML = "";
  t.append(el("tr", {}, ...["시나리오", "방법", "실행", "R0", "기준", "개입 수", "대유행 확률", "정점 I 평균", "정점일 중앙값", "사망 (평균, 끝)"].map((h) => el("th", {}, h))));
  sums.forEach((s) => t.append(el("tr", {}, el("td", {}, s.title), el("td", {}, s.method), el("td", { class: "num" }, s.n_runs), el("td", { class: "num" }, s.request.R0),
    el("td", {}, s.request.r0_reference), el("td", { class: "num" }, s.request.interventions.length), el("td", { class: "num" }, pct(s.outbreak_probability)),
    el("td", { class: "num" }, fmt(s.peak_I_mean)), el("td", { class: "num" }, fmt(s.peak_day_median)), el("td", { class: "num" }, fmt(s.daily.deaths_mean[s.daily.deaths_mean.length - 1])))));
});

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

// ------------------------------------------------------------------ 자료 출처
async function loadSources() {
  let s; try { s = await api("/api/sources"); } catch (e) { $("#src-table").append(el("tr", {}, el("td", { class: "err" }, e.message))); return; }
  const t = $("#src-table"); t.innerHTML = "";
  t.append(el("tr", {}, ...["id", "종류", "상태", "등급", "출처", "라이선스", "버전", "기준 시점", "받은 시각 (UTC)"].map((h) => el("th", {}, h))));
  for (const r of s.datasets) t.append(el("tr", {}, el("td", {}, r.id), el("td", {}, r.kind), el("td", { class: r.status === "ok" ? "ok" : "err" }, r.status === "ok" ? "확보" : `미확보 (${r.status})`),
    el("td", {}, r.tier || "–"), el("td", { class: "small" }, r.source), el("td", { class: "small" }, r.license), el("td", { class: "small" }, r.version), el("td", { class: "small" }, r.time_reference), el("td", { class: "small" }, (r.retrieved_utc || "–").replace("+00:00", ""))));
  const a = $("#asm-table"); a.innerHTML = "";
  a.append(el("tr", {}, ...["이름", "값", "쓰는 곳", "근거", "불확실성"].map((h) => el("th", {}, h))));
  for (const r of s.assumptions) a.append(el("tr", {}, el("td", {}, r.name), el("td", {}, r.value), el("td", { class: "small" }, r.where), el("td", { class: "small" }, r.basis), el("td", { class: "small" }, r.uncertainty)));
}

initForm();
window.addEventListener("resize", () => { clearTimeout(window.__rz); window.__rz = setTimeout(rerender, 200); });
