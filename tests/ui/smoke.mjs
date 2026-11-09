// UI 연기 시험 (Playwright, Node). 사용: node tests/ui/smoke.mjs [기본 http://127.0.0.1:8765] [스크린샷 폴더]
// 서버를 먼저 띄운다: python -m seir_sim.web   (KOR_admin1, world_countries 데이터셋이 저장소에 활성화되어 있어야 한다)
// 접근성 점검: 환경 변수 AXE_PATH 에 axe-core 의 axe.min.js 경로를 주면 WCAG 2 A/AA 규칙으로 검사한다 (없으면 건너뜀).
import { createRequire } from "module";
import { existsSync } from "fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const SHOTS = process.argv[3] || null;
const AXE = process.env.AXE_PATH && existsSync(process.env.AXE_PATH) ? process.env.AXE_PATH : null;
const errors = [];
const check = (cond, msg) => { if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; } else console.log("ok:", msg); };
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false }); };
const openAll = (page) => page.evaluate(() => document.querySelectorAll(".ws-right details").forEach((d) => (d.open = true)));
// 실행 단추를 누르고 새 작업이 시작된 것을 확인한 뒤 (이전 작업의 표시와 섞이지 않게) 끝날 때까지 기다린다
const runAndWait = async (page) => {
  const old = await page.evaluate(() => WS.job);
  await page.click("#run-btn");
  await page.waitForFunction((o) => WS.job && WS.job !== o, old, { timeout: 120000 });
  await waitBadge(page, "최종");
};
// 최종 평균이 보인 뒤 결과 저장이 끝나 작업이 '완료' 가 될 때까지 (상세 단추가 나타남)
const waitBadge = async (page, text, timeout = 240000) => {
  await page.waitForFunction((t) => document.querySelector("#lv-badge").textContent.includes(t), text, { timeout });
  await page.waitForSelector("#rp-detail:not([hidden])", { timeout });
};

async function axeCheck(page, label) {
  if (!AXE) { console.log(`skip: ${label} 접근성 (AXE_PATH 없음)`); return; }
  await page.addScriptTag({ path: AXE });
  const r = await page.evaluate(async () => {
    const res = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] }, resultTypes: ["violations"] });
    return res.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, ex: v.nodes.slice(0, 2).map((x) => x.target.join(" ")) }));
  });
  const bad = r.filter((v) => v.impact === "serious" || v.impact === "critical");
  console.log(`${label} 접근성 위반: ${JSON.stringify(r)}`);
  check(bad.length === 0, `${label}: 접근성 (WCAG 2 A/AA) 심각 위반 없음`);
}

async function frameTiming(page, label) {
  const ms = await page.evaluate(() => {
    const n = WS.data.t_frames.length, t0 = performance.now();
    for (let k = 0; k < 60; k++) wsFrame(k % n);
    return (performance.now() - t0) / 60;
  });
  console.log(`perf: ${label} 지도 한 프레임 갱신 ${ms.toFixed(1)} ms`);
  return ms;
}

const browser = await chromium.launch();
for (const scheme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme, acceptDownloads: true });
  const page = await ctx.newPage();
  // 일부러 낸 입력 오류(422)와 일부러 끊은 네트워크의 자원 실패 로그는 제외
  page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("status of 422") && !m.text().includes("ERR_FAILED")) errors.push(`${scheme}: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`${scheme}: ${e.message} @ ${(e.stack || "").split("\n").slice(0, 3).join(" / ")}`));
  page.on("dialog", (d) => d.accept("UI 시험 메모"));
  await page.goto(BASE + "/");
  check(await page.locator("#tab-home").isVisible(), `${scheme}: 홈 화면`);
  await shot(page, `ui_home_${scheme}`);
  await page.click('#tabs button[data-tab="run"]');
  await page.waitForSelector("#f-dataset option", { state: "attached" });
  check((await page.locator("#f-dataset option").count()) >= 2, `${scheme}: 데이터셋 목록`);
  if (scheme === "light") {
    const K = (await (await page.request.get(BASE + "/api/datasets/KOR_admin1/regions")).json()).ids.length;
    await page.selectOption("#f-dataset", "KOR_admin1");
    await page.waitForFunction((k) => document.querySelectorAll("#ws-map .leaflet-interactive").length === k, K, { timeout: 30000 });
    check(true, `작업 공간 지도 ${K}개 지역 (가운데)`);
    check(await page.locator(".ws-left").isVisible() && await page.locator(".ws-right").isVisible(), "왼쪽 수치 칸·오른쪽 입력 칸");
    const lx = (await page.locator(".ws-left").boundingBox()).x, cx = (await page.locator(".ws-center").boundingBox()).x, rx = (await page.locator(".ws-right").boundingBox()).x;
    check(lx < cx && cx < rx, "배치: 왼쪽 수치 · 가운데 지도 · 오른쪽 입력");
    check((await page.textContent("#input-sources")).includes("경계") && (await page.textContent("#input-sources")).includes("인구"), "입력 자료 출처 표");
    // 지도에서 지역을 눌러 발생 지역 추가
    const before = await page.locator("#f-seeds .row").count();
    await page.locator("#ws-map .leaflet-interactive").nth(5).click({ force: true });
    check((await page.locator("#f-seeds .row").count()) === before + 1, "지도 클릭으로 발생 지역 추가");
    await page.locator("#f-seeds .row button").last().click();
    await openAll(page);
    // 자료 시기: 인구 연도를 바꾸면 그 연도 자료로 다시 만든다
    const years = await page.locator("#p-pop option").allTextContents();
    check(years.some((y) => y.startsWith("2020")), "인구 연도 선택지");
    await page.selectOption("#p-pop", "2020");
    await page.waitForFunction(() => document.querySelector("#input-sources").textContent.includes("2020"), null, { timeout: 60000 });
    check(true, "인구 연도 2020 반영 (입력 자료 표)");
    const bounds = await page.locator("#p-bound option").count();
    check(bounds > 10, `경계 시점 선택지 ${bounds}개`);
    await page.selectOption("#p-bound", "2020-01-01");
    await page.waitForFunction(() => document.querySelectorAll("#ws-map .leaflet-interactive").length === 17, null, { timeout: 60000 });
    check(true, "경계 2020-01-01: 17개 시도 지도");
    await page.click("#p-latest");
    await page.waitForFunction((k) => document.querySelectorAll("#ws-map .leaflet-interactive").length === k, K, { timeout: 60000 });
    check(true, "최신 자료로 되돌리기");
    // 감염병 매개변수: 입력하면 '사용자 입력' 표시
    await page.fill("[name=dz_incubation_days]", "4");
    check((await page.locator("[name=dz_incubation_days] + .tag").textContent()).includes("사용자"), "매개변수 출처 표시 바뀜");
    check((await page.textContent("#dz-derived")).includes("배가 시간"), "R0 와 성장률 관계 안내");
    await page.click("#dz-save");
    await page.waitForTimeout(800);
    check((await page.locator("#dz-presets option").count()) >= 2, "감염병 설정 저장");
    // 매개변수 불확실성
    await page.check("[data-unc=R0]");
    check((await page.inputValue("[data-lo=R0]")) !== "" && (await page.inputValue("[data-hi=R0]")) !== "", "불확실성 범위 시작값");
    await page.fill("[data-lo=R0]", "2.0"); await page.fill("[data-hi=R0]", "3.0");
    await page.fill("input[name=title]", "UI 시험 KOR tau");
    await page.selectOption("select[name=method]", "tau");
    await page.fill("input[name=n_runs]", "4");
    await page.fill("input[name=days]", "120");
    await page.click("#add-int");
    await page.click("#check-btn");
    await page.waitForFunction(() => document.querySelector("#run-msg").textContent.includes("예상 계산 시간"), null, { timeout: 30000 });
    check(true, "점검·예상 계산량");
    const dl = page.waitForEvent("download");
    await page.click("#save-cfg");
    const d = await dl; check((await d.suggestedFilename()).endsWith(".json"), "설정 파일 저장");
    // 실행: ODE 미리보기가 먼저 보이고, 확률 실행이 끝나면 최종으로 바뀐다
    const old0 = await page.evaluate(() => WS.job);
    await page.click("#run-btn");
    await page.waitForFunction((o) => WS.job && WS.job !== o, old0, { timeout: 120000 });
    await page.waitForFunction(() => /미리보기|확률|최종/.test(document.querySelector("#lv-badge").textContent), null, { timeout: 120000 });
    check(true, `실행 중 갱신 표시: ${await page.textContent("#lv-badge")}`);
    await waitBadge(page, "최종");
    check((await page.locator("#lv-tiles .tile").count()) === 8, "왼쪽 수치 타일 8개");
    await page.click("#ws-play"); await page.waitForTimeout(300); await page.click("#ws-play");
    await page.fill("#ws-slider", "40"); await page.dispatchEvent("#ws-slider", "input");
    check((await page.textContent("#ws-time")).includes("일"), "시간 막대");
    check((await page.textContent("#lv-day")).includes("일째"), "왼쪽 날짜 표시");
    check((await page.textContent("#ws-legend")).includes("10만 명당"), "감염자 수 색 범례");
    await page.locator("#ws-map .leaflet-interactive").first().click({ force: true });
    check(await page.locator("#lv-region").count() === 1, "지역을 누르면 왼쪽에 지역 수치");
    await frameTiming(page, `대한민국 ${K}개 지역`);
    await shot(page, `ui_workspace_${scheme}`);
    await axeCheck(page, "작업 공간");
    // 네트워크 오류: 서버 요청을 끊으면 오류 문구를 보여 준다
    await page.route("**/api/**", (r) => r.abort());
    await page.click("#check-btn");
    await page.waitForFunction(() => document.querySelector("#run-msg").textContent.includes("서버에 연결할 수 없다"), null, { timeout: 10000 });
    check(true, "네트워크 오류 메시지");
    await page.unroute("**/api/**");
    // 상세 결과
    await page.click("#rp-detail");
    await page.waitForSelector("#result-view:not([hidden])", { timeout: 30000 });
    await page.waitForSelector("#ts-chart svg path", { timeout: 30000 });
    await page.waitForFunction((k) => document.querySelectorAll("#map .leaflet-interactive").length === k, K, { timeout: 30000 });
    check((await page.locator("#rv-regions tbody tr").count()) === K, `지역 표 ${K}행`);
    check((await page.locator("#rv-params tr").count()) > 10, "매개변수 출처 표");
    check((await page.textContent("#rv-warnings")).includes("매개변수 불확실성"), "불확실성 반영 안내");
    for (const layer of ["E", "D", "first", "arrival", "I"]) { await page.selectOption("#map-layer", layer); await page.waitForTimeout(150); }
    await page.selectOption("#map-scale", "abs");
    check((await page.textContent("#map-legend")).includes("명"), "절대 인원 범례");
    await page.check("#map-flows"); await page.waitForTimeout(800);
    check((await page.textContent("#map-def")).includes("실측"), "이동망 표시와 설명");
    await page.locator("#rv-regions tbody tr").first().click();
    await page.waitForSelector("#region-detail:not([hidden]) svg", { timeout: 10000 });
    check(true, "지역 상세 그래프");
    for (const k of ["new", "cum", "RD", "region", "I"]) { await page.selectOption("#chart-kind", k); await page.waitForTimeout(150); }
    await page.locator("#ts-chart svg").scrollIntoViewIfNeeded();
    const box = await page.locator("#ts-chart svg").boundingBox();
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    check(await page.locator("#ts-chart .tooltip:not([hidden])").count() === 1, "그래프 툴팁");
    const dl2 = page.waitForEvent("download"); await page.click("#chart-svg"); check((await (await dl2).suggestedFilename()) === "chart.svg", "그래프 SVG 내보내기");
    const dl3 = page.waitForEvent("download"); await page.click("#map-svg"); check((await (await dl3).suggestedFilename()) === "map.svg", "지도 SVG 내보내기");
    await shot(page, `ui_results_${scheme}`);
    // 같은 설정으로 R0 만 바꿔 비교
    await page.click("#rv-reuse");
    await page.waitForTimeout(1500);
    check((await page.inputValue("input[name=title]")) === "UI 시험 KOR tau", "설정 다시 불러오기");
    await openAll(page);
    await page.uncheck("[data-unc=R0]");
    await page.fill("input[name=title]", "UI 시험 KOR tau R0 1.8");
    await page.fill("[name=R0]", "1.8");
    await runAndWait(page);
    await page.click('#tabs button[data-tab="results"]');
    await page.click("#refresh-jobs"); await page.waitForTimeout(800);
    const boxes = page.locator("#jobs-table input[type=checkbox]");
    await boxes.nth(0).check(); await boxes.nth(1).check();
    await page.click("#compare-btn");
    await page.waitForSelector("#compare-chart svg path", { timeout: 20000 });
    check((await page.textContent("#compare-table")).includes("R0="), "비교 표의 다른 설정 열");
    const dl4 = page.waitForEvent("download"); await page.click("#compare-csv"); check((await (await dl4).suggestedFilename()).endsWith(".csv"), "비교 표 CSV");
    // 저장된 결과 이름 바꾸기·삭제 (확인 창은 자동 수락)
    const n0 = await page.locator("#jobs-table tbody tr").count();
    await page.locator("#jobs-table tbody tr").first().locator("button", { hasText: "이름" }).click();
    await page.waitForFunction(() => document.querySelector("#jobs-table tbody").textContent.includes("UI 시험 메모"), null, { timeout: 10000 });
    check(true, "저장된 결과 이름 바꾸기");
    await page.locator("#jobs-table tbody tr").first().locator("button", { hasText: "삭제" }).click();
    await page.waitForFunction((n) => document.querySelectorAll("#jobs-table tbody tr").length === n - 1, n0, { timeout: 10000 });
    check(true, "저장된 결과 삭제");
    // 전 세계 데이터셋: 246개 국가 지도 애니메이션 속도
    await page.click('#tabs button[data-tab="run"]');
    await page.selectOption("#f-dataset", "world_countries");
    await page.waitForFunction(() => document.querySelectorAll("#ws-map .leaflet-interactive").length > 200, null, { timeout: 60000 });
    await openAll(page);
    await page.selectOption("select[name=method]", "ode");
    await page.fill("input[name=title]", "UI 시험 전 세계 ODE");
    await page.fill("input[name=days]", "200");
    await runAndWait(page);
    const nW = await page.locator("#ws-map .leaflet-interactive").count();
    const msW = await frameTiming(page, `전 세계 ${nW}개 국가`);
    check(msW < 150, `전 세계 지도 프레임 갱신 ${msW.toFixed(0)} ms (< 150 ms)`);
    await shot(page, `ui_world_${scheme}`);
    // 서버 입력 검증 메시지
    await page.selectOption("#f-dataset", "KOR_admin1");
    await page.waitForFunction((k) => document.querySelectorAll("#ws-map .leaflet-interactive").length === k, K, { timeout: 30000 });
    await page.fill("#f-seeds .row input", "100000000");
    await page.click("#run-btn");
    await page.waitForFunction(() => document.querySelector("#run-msg").textContent.includes("입력 오류"), null, { timeout: 20000 });
    check(true, "서버 입력 오류 메시지 표시");
    await page.fill("#f-seeds .row input", "10");
  }
  for (const tab of ["validation", "data", "sources", "help", "latest", "results"]) {
    await page.click(`#tabs button[data-tab="${tab}"]`);
    await page.waitForTimeout(1200);
    check(await page.locator(`#tab-${tab}`).isVisible(), `${scheme}: ${tab} 탭`);
    await shot(page, `ui_${tab}_${scheme}`);
  }
  check((await page.locator("#src-table tr").count()) > 5, `${scheme}: 자료 출처·갱신 표`);
  check((await page.locator("#ds-content table").count()) >= 1, `${scheme}: 데이터 관리 표`);
  if (scheme === "dark") { await page.click('#tabs button[data-tab="run"]'); await page.waitForTimeout(800); await axeCheck(page, "어두운 화면 작업 공간"); }
  await page.setViewportSize({ width: 390, height: 800 });
  for (const tab of ["run", "results", "sources"]) {
    await page.click(`#tabs button[data-tab="${tab}"]`); await page.waitForTimeout(400);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(over <= 1, `${scheme}: 좁은 화면 ${tab} 가로 넘침 없음 (${over}px)`);
  }
  await shot(page, `ui_mobile_${scheme}`);
  await ctx.close();
}
await browser.close();
check(errors.length === 0, `콘솔 오류 없음 ${errors.join(" | ")}`);
