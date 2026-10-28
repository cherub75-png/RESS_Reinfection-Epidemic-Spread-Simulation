// UI 연기 시험 (Playwright, Node). 사용: node tests/ui/smoke.mjs [기본 http://127.0.0.1:8765] [스크린샷 폴더]
// 서버를 먼저 띄운다: python -m seir_sim.web
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const SHOTS = process.argv[3] || null;
const errors = [];
const check = (cond, msg) => { if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; } else console.log("ok:", msg); };

const browser = await chromium.launch();
for (const scheme of ["light", "dark"]) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: scheme });
  // 일부러 낸 입력 오류(422)의 자원 실패 로그는 제외
  page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("status of 422")) errors.push(`${scheme}: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`${scheme}: ${e.message} @ ${(e.stack || "").split("\n").slice(0, 4).join(" / ")}`));
  page.on("response", (r) => { if (r.status() === 404) errors.push(`${scheme}: 404 ${r.url()}`); });
  await page.goto(BASE + "/");
  await page.waitForSelector("#f-dataset option", { state: "attached" });
  check((await page.locator("#f-dataset option").count()) >= 2, `${scheme}: 데이터셋 목록`);
  if (scheme === "light") {
    // 대한민국 시도, ODE 로 빠르게 실행
    await page.selectOption("#f-dataset", "KOR_admin1");
    await page.waitForTimeout(500);
    await page.fill("input[name=title]", "UI 시험 KOR ODE");
    await page.selectOption("select[name=method]", "ode");
    await page.fill("input[name=days]", "120");
    await page.click("#add-int");
    await page.click("#run-btn");
    await page.waitForSelector("#result-view:not([hidden])", { timeout: 180000 });
    await page.waitForSelector("#ts-chart svg path", { timeout: 30000 });
    await page.waitForSelector("#map .leaflet-interactive", { timeout: 30000 });
    const nPoly = await page.locator("#map .leaflet-interactive").count();
    check(nPoly === 17, `지도 다각형 17개 (실제 ${nPoly})`);
    check((await page.locator("#rv-regions tbody tr").count()) === 17, "지역 표 17행");
    await page.fill("#frame-slider", "60");
    await page.dispatchEvent("#frame-slider", "input");
    check((await page.textContent("#frame-label")).includes("일"), "시간 슬라이더");
    // 툴팁
    const box = await page.locator("#ts-chart svg").boundingBox();
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    check(await page.locator("#ts-chart .tooltip:not([hidden])").count() === 1, "그래프 툴팁");
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/ui_results_${scheme}.png`, fullPage: true });
    // 두 번째 시나리오로 비교
    await page.click('#tabs button[data-tab="run"]');
    await page.fill("input[name=title]", "UI 시험 KOR ODE R0 1.8");
    await page.fill("input[name=R0]", "1.8");
    await page.click("#run-btn");
    await page.waitForSelector("#result-view:not([hidden])", { timeout: 180000 });
    await page.waitForTimeout(1500);
    await page.click("#refresh-jobs");
    await page.waitForTimeout(800);
    const boxes = page.locator("#jobs-table input[type=checkbox]");
    check((await boxes.count()) >= 2, "비교 선택 상자");
    await boxes.nth(0).check(); await boxes.nth(1).check();
    await page.click("#compare-btn");
    await page.waitForSelector("#compare-chart svg path", { timeout: 20000 });
    check(await page.locator("#compare-table tr").count() >= 3, "비교 표");
    // 입력 오류 표시
    await page.click('#tabs button[data-tab="run"]');
    await page.fill("#f-seeds .row input", "100000000");       // 서버 검증 상한 (1e7) 초과
    await page.click("#run-btn");
    await page.waitForTimeout(800);
    check((await page.textContent("#run-msg")).includes("입력 오류"), "서버 입력 오류 메시지 표시");
    await page.fill("#f-seeds .row input", "10");
  }
  for (const tab of ["validation", "data", "sources", "help", "latest"]) {
    await page.click(`#tabs button[data-tab="${tab}"]`);
    await page.waitForTimeout(1200);
    check(await page.locator(`#tab-${tab}`).isVisible(), `${scheme}: ${tab} 탭`);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/ui_${tab}_${scheme}.png`, fullPage: true });
  }
  check((await page.locator("#src-table tr").count()) > 5, `${scheme}: 자료 출처 표`);
  check((await page.locator("#ds-content table").count()) >= 1, `${scheme}: 데이터 관리 표`);
  // 휴대폰 폭에서 가로 넘침 없음
  await page.setViewportSize({ width: 390, height: 800 });
  await page.click('#tabs button[data-tab="run"]');
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check(over <= 1, `${scheme}: 좁은 화면 가로 넘침 없음 (${over}px)`);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ui_mobile_${scheme}.png`, fullPage: true });
  await page.close();
}
await browser.close();
check(errors.length === 0, `콘솔 오류 없음 ${errors.join(" | ")}`);
