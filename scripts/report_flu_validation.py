"""인플루엔자 시간순 예측 검증 보고서 (규약: docs/reports/11_influenza_protocol.md).

입력: outputs/flu/forecasts.parquet (scripts/run_flu_validation.py), outputs/flu/seir_forecasts.parquet (scripts/run_flu_seir.py, 선택)
출력: docs/reports/11_influenza_validation.md, .json, docs/figures/11_*.png
지표: 자연 척도 WIS (양성률 %p) 의 지속 예측 대비 비 (상대 WIS), 같은 행 집합에서만 비교.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
QC = [f"q{k}" for k in range(9)]
LABEL = {"persistence": "지속", "trend": "감쇠 추세", "seasonal": "계절 평균", "ml": "ML (분위수 GBM)", "ml_cal": "ML + 구간 보정",
         "ml_noclim": "ML (기후 특성 없음)", "ml_loco_KOR": "ML (대한민국 제외 학습)", "seir": "SEIR (양성률 관측)"}


def score(d: pd.DataFrame) -> pd.DataFrame:
    from seir_sim.forecast import metrics as Mx
    y = 100 * d["truth"].to_numpy()
    q = 100 * d[QC].to_numpy()
    out = d.copy()
    out["wis"] = Mx.wis(y, q)["wis"]
    out["c90"] = Mx.coverage(y, q, 0.1)
    out["c50"] = Mx.coverage(y, q, 0.5)
    out["ae"] = np.abs(y - q[:, 4])
    return out


def common(df: pd.DataFrame, methods: list[str]) -> pd.DataFrame:
    key = ["series", "origin", "h"]
    d = df[df["method"].isin(methods) & np.isfinite(df["truth"])]
    n = d.groupby(key)["method"].nunique()
    keep = n[n == len(methods)].index
    return d.set_index(key).loc[keep].reset_index()


def rel_table(d: pd.DataFrame, methods: list[str], by: list[str]) -> dict:
    out = {}
    for k, g in d.groupby(by):
        m = g.groupby("method")[["wis", "c90", "c50", "ae"]].mean()
        p = m.loc["persistence", "wis"]
        out[k if isinstance(k, tuple) else (k,)] = {"n": int((g["method"] == methods[0]).sum()),
                                                     **{mm: {"rel_wis": float(m.loc[mm, "wis"] / p), "wis": float(m.loc[mm, "wis"]),
                                                             "cov90": float(m.loc[mm, "c90"]), "cov50": float(m.loc[mm, "c50"]),
                                                             "mae": float(m.loc[mm, "ae"])} for mm in methods}}
    return out


def zone(lat: float) -> str:
    if not np.isfinite(lat):
        return "위도 없음"
    return "북반구 온대" if lat >= 23.5 else ("남반구 온대" if lat <= -23.5 else "열대")


def main():
    fc = pd.read_parquet(ROOT / "outputs" / "flu" / "forecasts.parquet")
    run = json.loads((ROOT / "outputs" / "flu" / "run_record.json").read_text())
    sp = ROOT / "outputs" / "flu" / "seir_forecasts.parquet"
    seir = pd.read_parquet(sp) if sp.exists() else None
    fc["h"] = fc["h"].astype(int)
    fc = score(fc)
    fc["zone"] = fc["lat"].map(zone)
    rep = {"run": {k: run[k] for k in ("n_series", "origins", "refit_every_weeks", "climate_features")}, "series": run["series"]}
    main_m = ["persistence", "trend", "seasonal", "ml", "ml_cal"]
    cm = common(fc, main_m)
    rep["main"] = {str(k[0]): v for k, v in rel_table(cm, main_m, ["h"]).items()}
    rep["by_zone"] = {f"{k[0]}|{k[1]}": v for k, v in rel_table(cm, main_m, ["zone", "h"]).items()}
    cl = common(fc, ["persistence", "ml", "ml_noclim"])
    rep["climate_ablation"] = {str(k[0]): v for k, v in rel_table(cl, ["persistence", "ml", "ml_noclim"], ["h"]).items()}
    lo = common(fc[fc["series"] == "KOR|SENTINEL"], ["persistence", "seasonal", "ml", "ml_loco_KOR"])
    rep["loco_KOR"] = {str(k[0]): v for k, v in rel_table(lo, ["persistence", "seasonal", "ml", "ml_loco_KOR"], ["h"]).items()} if len(lo) else {}
    calrows = []
    for h in (1, 2, 3, 4):
        g = cm[cm["h"] == h]
        a, b = g[g["method"] == "ml"], g[g["method"] == "ml_cal"]
        ok = bool(0.85 <= b["c90"].mean() <= 0.95 and b["wis"].mean() <= 1.05 * a["wis"].mean())
        calrows.append({"h": h, "cov90_raw": float(a["c90"].mean()), "cov90_cal": float(b["c90"].mean()),
                        "wis_ratio": float(b["wis"].mean() / a["wis"].mean()), "success": ok})
    rep["calibration"] = calrows
    if seir is not None and len(seir):
        seir["h"] = seir["h"].astype(int)
        s2 = score(seir)
        base = fc[fc["series"].isin(seir["series"].unique()) & fc["origin"].isin(seir["origin"].unique())]
        both = pd.concat([base, s2], ignore_index=True)
        sm = ["persistence", "seasonal", "ml_cal", "seir"]
        cs = common(both, sm)
        rep["seir"] = {str(k[0]): v for k, v in rel_table(cs, sm, ["h"]).items()}
        rep["seir_fits"] = json.loads((ROOT / "outputs" / "flu" / "seir_fits.json").read_text())
        fits = rep["seir_fits"]["fits"]
        rep["seir_fit_summary"] = {"n": len(fits), "success": float(np.mean([f["success"] for f in fits])),
                                   "hessian_pd": float(np.mean([bool(f["hessian_pd"]) for f in fits])),
                                   "mean_wall_s": float(np.mean([f["wall_s"] for f in fits]))}
    (ROOT / "docs" / "reports" / "11_influenza_validation.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str))
    figures(fc, cm)

    o = run["origins"]
    L = ["# 11. 인플루엔자 시간순 예측 검증 (자동 생성: scripts/report_flu_validation.py)", "",
         "규약: `docs/reports/11_influenza_protocol.md` (결과 전에 고정, 변경 기록 포함). 자료: WHO FluNet (2026-11-09 받은 최종판), ERA5 주간 기후.",
         f"계열 {run['n_series']}개 (국가 × 감시 체계), 기점 {o[0]} ~ {o[1]} 매주 ({o[2]}개), 예측 1~4주, ML 은 {run['refit_every_weeks']}주마다 재학습.",
         "자료가 최종판이라 실시간 성능보다 낙관적일 수 있다 (소급 보완을 재현하지 못함). 무작위 분할은 쓰지 않았다.", "",
         "## 1. 전체 (같은 행 집합)", "",
         "| 예측 주 | n | " + " | ".join(f"상대 WIS: {LABEL[m]}" for m in main_m[1:]) + " | 90% 포함: 지속 / 계절 / ML / ML+보정 |",
         "|---|---|" + "---|" * (len(main_m) - 1) + "---|"]
    for h, r in rep["main"].items():
        L.append(f"| {h} | {r['n']} | " + " | ".join(f"{r[m]['rel_wis']:.3f}" for m in main_m[1:]) +
                 f" | {r['persistence']['cov90']:.2f} / {r['seasonal']['cov90']:.2f} / {r['ml']['cov90']:.2f} / {r['ml_cal']['cov90']:.2f} |")
    L += ["", f"지속 예측의 평균 WIS (양성률 %p): " + ", ".join(f"{h}주 {r['persistence']['wis']:.2f}" for h, r in rep["main"].items()) + ".", "",
          "## 2. 지역 묶음별 (상대 WIS, 지속 = 1)", "",
          "| 묶음 | 예측 주 | n | 감쇠 추세 | 계절 평균 | ML | ML + 보정 |", "|---|---|---|---|---|---|---|"]
    for k, r in rep["by_zone"].items():
        z, h = k.split("|")
        if h not in ("1", "4"):
            continue
        L.append(f"| {z} | {h} | {r['n']} | " + " | ".join(f"{r[m]['rel_wis']:.3f}" for m in main_m[1:]) + " |")
    L += ["", "## 3. 예측 구간 보정 (규약 6절)", "",
          "| 예측 주 | 90% 포함 (보정 전 → 후) | WIS 후/전 | 판정 |", "|---|---|---|---|"]
    for r in calrows:
        L.append(f"| {r['h']} | {r['cov90_raw']:.2f} → {r['cov90_cal']:.2f} | {r['wis_ratio']:.3f} | {'성공' if r['success'] else '미달'} |")
    L += ["", "## 4. 기후 특성의 기여 (ERA5; 기점까지의 날씨와 과거 연도 평균만)", "",
          "| 예측 주 | n | 상대 WIS: ML | ML (기후 없음) | ML / ML(기후 없음) |", "|---|---|---|---|---|"]
    for h, r in rep["climate_ablation"].items():
        L.append(f"| {h} | {r['n']} | {r['ml']['rel_wis']:.3f} | {r['ml_noclim']['rel_wis']:.3f} | {r['ml']['wis'] / r['ml_noclim']['wis']:.3f} |")
    if rep["loco_KOR"]:
        L += ["", "## 5. 대한민국 (표본감시) 과 국가 제외 학습", "",
              "| 예측 주 | n | 계절 평균 | ML | ML (대한민국 제외 학습) |", "|---|---|---|---|---|"]
        for h, r in rep["loco_KOR"].items():
            L.append(f"| {h} | {r['n']} | {r['seasonal']['rel_wis']:.3f} | {r['ml']['rel_wis']:.3f} | {r['ml_loco_KOR']['rel_wis']:.3f} |")
    if "seir" in rep:
        fs = rep["seir_fit_summary"]
        L += ["", "## 6. 보조: SEIR (1절 방정식 + 양성률 관측, 규약 7절)", "",
              f"계열 {', '.join(rep['seir_fits']['subset'])} (선택 규칙에서 빠짐: {', '.join(rep['seir_fits']['dropped_by_selection']) or '없음'}), 4주 간격 기점.",
              f"적합 {fs['n']}회: 수렴 {fs['success']:.0%}, 헤시안 양의 정부호 {fs['hessian_pd']:.0%}, 평균 {fs['mean_wall_s']:.0f}초.", "",
              "| 예측 주 | n | 계절 평균 | ML + 보정 | SEIR | 90% 포함 SEIR |", "|---|---|---|---|---|---|"]
        for h, r in rep["seir"].items():
            L.append(f"| {h} | {r['n']} | {r['seasonal']['rel_wis']:.3f} | {r['ml_cal']['rel_wis']:.3f} | {r['seir']['rel_wis']:.3f} | {r['seir']['cov90']:.2f} |")
        L.append("감염병 값은 인플루엔자 가정값이며, 양성률 관측만으로는 감염 규모의 절대값이 잘 식별되지 않는다 (규약 7절).")
    L += ["", "그림: `docs/figures/11_relative_wis.png`, `docs/figures/11_coverage.png`, `docs/figures/11_kor_forecasts.png`"]
    (ROOT / "docs" / "reports" / "11_influenza_validation.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def figures(fc, cm):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from seir_sim.viz.plots import _font
    _font()                                          # 한글 글꼴 (5단계 그림과 같음)
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    hs = [1, 2, 3, 4]
    for m, c in (("trend", "#eda100"), ("seasonal", "#1baf7a"), ("ml", "#2a78d6"), ("ml_cal", "#eb6834")):
        v = [cm[(cm["h"] == h) & (cm["method"] == m)]["wis"].mean() / cm[(cm["h"] == h) & (cm["method"] == "persistence")]["wis"].mean() for h in hs]
        ax[0].plot(hs, v, "o-", color=c, label=LABEL[m])
        cv = [cm[(cm["h"] == h) & (cm["method"] == m)]["c90"].mean() for h in hs]
        ax[1].plot(hs, cv, "o-", color=c, label=LABEL[m])
    ax[0].axhline(1, color="#7a7974", ls="--", lw=1)
    ax[0].set(xlabel="예측 주", ylabel="상대 WIS (지속 = 1)", xticks=hs)
    ax[1].axhline(0.9, color="#7a7974", ls="--", lw=1)
    ax[1].set(xlabel="예측 주", ylabel="90% 구간 포함률", xticks=hs, ylim=(0.4, 1.0))
    ax[0].legend(fontsize=8, frameon=False)
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / "11_relative_wis.png", dpi=130)
    fig.savefig(ROOT / "docs" / "figures" / "11_coverage.png", dpi=130)
    plt.close(fig)
    k = fc[(fc["series"] == "KOR|SENTINEL") & (fc["method"] == "ml_cal")]
    if len(k):
        fig, ax = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
        for a, h in zip(ax, (1, 4)):
            g = k[k["h"] == h].sort_values("target_week")
            a.fill_between(g["target_week"], 100 * g["q1"], 100 * g["q7"], color="#2a78d6", alpha=0.2, label="ML+보정 90% 구간")
            a.plot(g["target_week"], 100 * g["q4"], color="#2a78d6", lw=1.5, label="ML+보정 중앙값")
            a.plot(g["target_week"], 100 * g["truth"], "o", color="#eb6834", ms=3, label="관측 양성률")
            a.set(ylabel="양성률 (%)", title=f"대한민국 표본감시 인플루엔자 양성률: {h}주 전 예측")
            a.spines[["top", "right"]].set_visible(False)
        ax[0].legend(fontsize=8, frameon=False)
        fig.tight_layout()
        fig.savefig(ROOT / "docs" / "figures" / "11_kor_forecasts.png", dpi=130)
        plt.close(fig)


if __name__ == "__main__":
    main()
