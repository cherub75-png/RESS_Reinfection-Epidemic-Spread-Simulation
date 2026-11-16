// 브라우저 엔진(site/src/engine.js) 과 Python FastODE 의 결과 비교. 사용: node site/test/engine_vs_python.mjs
// 기준: site/test/reference_KOR.json (scripts/build_static_site.py 가 만듦), 자료: site/dist/data/KOR_admin1.json
import { createRequire } from "module";
import { readFileSync } from "fs";
const require = createRequire(import.meta.url);
const SEIR = require("../src/engine.js");
const ref = JSON.parse(readFileSync(new URL("./reference_KOR.json", import.meta.url)));
const ds = JSON.parse(readFileSync(new URL("../dist/data/KOR_admin1.json", import.meta.url)));
const meta = JSON.parse(readFileSync(new URL("../dist/data/meta.json", import.meta.url)));
const p = { ...meta.disease_defaults, R0: ref.request.R0 };
const md = SEIR.buildModel(ds, p, { eta: ref.request.eta, useMobility: true, useCommuting: true });
const k = ds.ids.indexOf("KR-11");
const mine = SEIR.initialState(md, ds.population, [{ k, I: 10, E: 5 }], 0.1);
let x0diff = 0; for (let q = 0; q < mine.length; q++) x0diff = Math.max(x0diff, Math.abs(mine[q] - ref.X0[q]));
console.log(`초기 상태 최대 차이 ${x0diff.toFixed(3)}명 (초기 면역을 반올림 전/후 인구로 계산한 차이)`);
const x0 = Float64Array.from(ref.X0);                     // 엔진만 비교하려고 Python 의 초기 상태를 그대로 쓴다
const x = SEIR.simulate(md, x0, 180, (d, gc) => { for (let i = 0; i < md.K; i++) gc[i] = md.baseC[i] * (1 - (d >= 30 && d < 90 ? 0.3 : 0)); }, null, 4);
const s = SEIR.summarize(md, x);
let worst = 0;
for (let i = 0; i < md.K; i++) {
  for (const [a, b] of [[s.I[i], ref.I_end[i]], [s.D[i], ref.D_end[i]], [s.S[i], ref.S_end[i]]]) worst = Math.max(worst, Math.abs(a - b) / Math.max(1, Math.abs(b)));
}
const ok = Math.abs(md.c0 - ref.c0) < 1e-12 && worst < 1e-8;
console.log(`c0 JS ${md.c0} / Python ${ref.c0}, 최대 상대 차이 ${worst.toExponential(2)} -> ${ok ? "일치" : "불일치"}`);
process.exit(ok ? 0 : 1);
