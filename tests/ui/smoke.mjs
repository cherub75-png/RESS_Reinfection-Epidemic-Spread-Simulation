// UI 연기 시험 (Playwright, Node). 사용: node tests/ui/smoke.mjs [기본 http://127.0.0.1:8765] [스크린샷 폴더]
// 서버를 먼저 띄운다: python -m seir_sim.web   (KOR_admin1 데이터셋이 저장소에 활성화되어 있어야 한다)
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const SHOTS = process.argv[3] || null;
const errors = [];
const check = (cond, msg) => { if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; } else console.log("ok:", msg); };
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

const browser = await chromium.launch();
for (const scheme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: scheme, acceptDownloads: true });
  const page = await ctx.newPage();
  // 일부러 낸 입력 오류(422)의 자원 실패 로그는 제외
  page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("status of 422")) errors.push(`${scheme}: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`${scheme}: ${e.message} @ ${(e.stack || "").split("\n").slice(0, 3).join(" / ")}`));
  page.on("dialog", (d) => d.accept("UI 시험 메모"));
  await page.goto(BASE + "/");
  check(await page.locator("#tab-home").isVisible(), `${scheme}: 홈 화면`);
  await shot(page, `ui_home_${scheme}`);
  await page.click('#tabs button[data-tab="run"]');
  await page.waitForSelector("#f-dataset option", { state: "attached" });
  check((await page.locator("#f-dataset option").count()) >= 2, `${scheme}: 데이터셋 목록`);
  if (scheme === "light") {
    await page.selectOption("#f-dataset", "KOR_admin1");
    await page.waitForLoadState("networkidle");
    await page.waitForSelector("#seed-map .leaflet-interactive", { timeout: 30000 });
    check((await page.locator("#seed-map .leaflet-interactive").count()) === 17, "발생 위치 선택 지도 17개 지역");
    // 지도에서 지역을 눌러 발생 지역 추가
    const before = await page.locator("#f-seeds .row").count();
    await page.locator("#seed-map .leaflet-interactive").nth(5).click({ force: true });
    check((await page.locator("#f-seeds .row").count()) === before + 1, "지도 클릭으로 발생 지역 추가");
    await page.locator("#f-seeds .row button").last().click();
    // 감염병 매개변수: 입력하면 '사용자 입력' 표시
    await page.fill("[name=dz_incubation_days]", "4");
    check((await page.locator("[name=dz_incubation_days] + .tag").textContent()).includes("사용자"), "매개변수 출처 표시 바뀜");
    check((await page.textContent("#dz-derived")).includes("배가 시간"), "R0 와 성장률 관계 안내");
    await page.click("#dz-save");
    await page.waitForTimeout(800);
    check((await page.locator("#dz-presets option").count()) >= 2, "감염병 설정 저장");
    await page.fill("input[name=title]", "UI 시험 KOR ODE");
    await page.click("summary:has-text('계산 설정')");
    await page.selectOption("select[name=method]", "ode");
    await page.fill("input[name=days]", "120");
    await page.click("#add-int");
    await page.click("#check-btn");
    await page.waitForTimeout(800);
    check((await page.textContent("#run-msg")).includes("예상 계산 시간"), "점검·예상 계산량");
    const dl = page.waitForEvent("download");
    await page.click("#save-cfg");
    const d = await dl; check((await d.suggestedFilename()).endsWith(".json"), "설정 파일 저장");
    await page.click("#run-btn");
    await page.waitForSelector("#result-view:not([hidden])", { timeout: 180000 });
    await page.waitForSelector("#ts-chart svg path", { timeout: 30000 });
    await page.waitForSelector("#map .leaflet-interactive", { timeout: 30000 });
    check((await page.locator("#map .leaflet-interactive").count()) === 17, "결과 지도 다각형 17개");
    check((await page.locator("#rv-regions tbody tr").count()) === 17, "지역 표 17행");
    check((await page.locator("#rv-params tr").count()) > 10, "매개변수 출처 표");
    await page.fill("#frame-slider", "60"); await page.dispatchEvent("#frame-slider", "input");
    check((await page.textContent("#frame-label")).includes("일"), "시간 막대");
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
    await page.waitForTimeout(800);
    check((await page.inputValue("input[name=title]")) === "UI 시험 KOR ODE", "설정 다시 불러오기");
    await page.fill("input[name=title]", "UI 시험 KOR ODE R0 1.8");
    await page.fill("[name=R0]", "1.8");
    await page.click("#run-btn");
    await page.waitForSelector("#result-view:not([hidden])", { timeout: 180000 });
    await page.waitForTimeout(1500);
    await page.click("#refresh-jobs"); await page.waitForTimeout(800);
    const boxes = page.locator("#jobs-table input[type=checkbox]");
    await boxes.nth(0).check(); await boxes.nth(1).check();
    await page.click("#compare-btn");
    await page.waitForSelector("#compare-chart svg path", { timeout: 20000 });
    check((await page.textContent("#compare-table")).includes("R0="), "비교 표의 다른 설정 열");
    const dl4 = page.waitForEvent("download"); await page.click("#compare-csv"); check((await (await dl4).suggestedFilename()).endsWith(".csv"), "비교 표 CSV");
    // 서버 입력 검증 메시지
    await page.click('#tabs button[data-tab="run"]');
    await page.fill("#f-seeds .row input", "100000000");
    await page.click("#run-btn"); await page.waitForTimeout(800);
    check((await page.textContent("#run-msg")).includes("입력 오류"), "서버 입력 오류 메시지 표시");
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
