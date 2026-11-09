"""COVID-19 5단계 예측의 시간순 구간 보정 재평가 (규약: docs/reports/11_influenza_protocol.md 6절, 결과 전에 고정).

입력: outputs/stage5/forecasts_k14.parquet (재적합 없음). 방법 ml, hybrid, seir 마다, 변수(확진·사망)마다, 예측 주마다
기점 o 의 분위수를 기점이 [o - 52주, o) 이고 대상 주 <= o 인 과거 예측(12개국 모아서)의 log(1 + y) 오차로 옮긴다.
보정 표본 300행 미만이면 보정하지 않는다. 성공 판정 (미리 정함): 90% 포함률 0.85 ~ 0.95, 보정 후 로그 WIS <= 보정 전의 1.05 배.
출력: docs/reports/12_interval_calibration.md, .json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
QC = [f"q{k}" for k in range(9)]


def main():
    from seir_sim.forecast import flu as FL
    from seir_sim.forecast import metrics as Mx
    df = pd.read_parquet(ROOT / "outputs" / "stage5" / "forecasts_k14.parquet")
    df = df[np.isfinite(df["truth"])]
    to_z = lambda y: np.log1p(np.maximum(y, 0))                              # noqa: E731
    from_z = lambda z: np.expm1(z)                                           # noqa: E731
    res = {"rule": {"window_weeks": 52, "min_rows": 300, "scale": "log(1 + 주간 수)", "pooled": "12개국, 변수·방법·예측 주별"}, "rows": []}
    L = ["# 12. COVID-19 예측의 시간순 구간 보정 재평가 (자동 생성: scripts/report_interval_calibration.py)", "",
         "규약: `docs/reports/11_influenza_protocol.md` 6절 (결과 전에 고정). 5단계 예측(`outputs/stage5/forecasts_k14.parquet`)을 다시 적합하지 않고,",
         "기점마다 그 전 52주 동안 정답이 이미 알려진 예측(12개국)의 log(1 + y) 오차로 분위수를 옮겼다. 보정 표본이 300행 미만인 기점은 보정하지 않았다.",
         "평가는 보정이 적용된 행에서 한다 (같은 행에서 보정 전·후와 지속 예측을 비교).", "",
         "| 변수 | 방법 | 예측 주 | n | 90% 포함 (전 → 후) | 50% 포함 (전 → 후) | 로그 WIS (전 → 후) | 후/전 | 상대 로그 WIS (지속=1, 전 → 후) | 판정 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for var in ("cases", "deaths"):
        dv = df[df["var"] == var]
        pers = dv[dv["method"] == "persistence"].set_index(["iso3", "origin", "h"])
        for m in ("ml", "hybrid", "seir"):
            fc = dv[dv["method"] == m].rename(columns={"target_end": "target_week"}).reset_index(drop=True)
            cal = FL.conformal_adjust(fc, to_z, from_z, origin_col="origin", target_col="target_week")
            for h in (1, 2, 3, 4):
                sel = (cal["h"] == h) & (cal["cal_n"] > 0)
                a, b = fc[sel], cal[sel]
                key = list(zip(a["iso3"], a["origin"], a["h"]))
                ok = np.array([k in pers.index for k in key])
                a, b = a[ok], b[ok]
                p = pers.loc[[k for k, o in zip(key, ok) if o]]
                y = a["truth"].to_numpy()
                w_raw = Mx.wis(y, a[QC].to_numpy(), log=True)["wis"].mean()
                w_cal = Mx.wis(y, b[QC].to_numpy(), log=True)["wis"].mean()
                w_p = Mx.wis(y, p[QC].to_numpy(), log=True)["wis"].mean()
                c90 = (Mx.coverage(y, a[QC].to_numpy(), 0.1).mean(), Mx.coverage(y, b[QC].to_numpy(), 0.1).mean())
                c50 = (Mx.coverage(y, a[QC].to_numpy(), 0.5).mean(), Mx.coverage(y, b[QC].to_numpy(), 0.5).mean())
                success = bool(0.85 <= c90[1] <= 0.95 and w_cal <= 1.05 * w_raw)
                r = {"var": var, "method": m, "h": h, "n": int(len(a)), "cov90_raw": c90[0], "cov90_cal": c90[1],
                     "cov50_raw": c50[0], "cov50_cal": c50[1], "wis_log_raw": w_raw, "wis_log_cal": w_cal,
                     "rel_wis_raw": w_raw / w_p, "rel_wis_cal": w_cal / w_p, "success": success}
                res["rows"].append(r)
                L.append(f"| {var} | {m} | {h} | {r['n']} | {c90[0]:.2f} → {c90[1]:.2f} | {c50[0]:.2f} → {c50[1]:.2f} | "
                         f"{w_raw:.3f} → {w_cal:.3f} | {w_cal / w_raw:.3f} | {r['rel_wis_raw']:.3f} → {r['rel_wis_cal']:.3f} | "
                         f"{'성공' if success else '미달'} |")
    n_ok = sum(r["success"] for r in res["rows"])
    L += ["", f"판정 기준 (미리 정함): 보정 후 90% 포함률 0.85 ~ 0.95 이고 보정 후 로그 WIS 가 보정 전의 1.05 배 이하. "
          f"{len(res['rows'])}개 조합 중 {n_ok}개 성공.", "",
          "주의: 보정은 기점 전 52주의 오차 분포가 앞으로도 비슷하다고 가정한다. 유행 양상이 급변하는 시기(예: 변이 교체)에는 보정이 늦게 따라간다."]
    (ROOT / "docs" / "reports" / "12_interval_calibration.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    (ROOT / "docs" / "reports" / "12_interval_calibration.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
