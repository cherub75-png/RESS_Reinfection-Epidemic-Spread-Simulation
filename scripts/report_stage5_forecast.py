"""5단계 B: 기준 모델, 국가 공통 ML, 보정 SEIR, SEIR+ML 하이브리드의 시간순 예측 검증.

먼저 scripts/run_stage5_seir.py 로 SEIR 기점별 예측을 만들어 둔다.
사용법: python -I scripts/report_stage5_forecast.py [--workers 4] [--knot 14]
출력:   outputs/stage5/forecasts.parquet (모든 예측), docs/reports/5_forecast_validation.md/.json, docs/figures/5_*.png
규약 (실행 전에 정함): docs/reports/5_protocol.md
"""

import argparse
import json
import multiprocessing as mp
import os
import pickle
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "outputs" / "stage5"
FIRST_ORIGIN, LAST_ORIGIN = "2020-07-05", "2022-12-25"
LOCO = ("KOR",)                    # 국가 제외 학습 비교 대상
CORE = ["persistence", "trend", "seir", "ml", "hybrid"]
ALL_METHODS = ["persistence", "trend", "seasonal52", "seir", "ml", "hybrid"]
VARS = {"cases": "lc0", "deaths": "ld0"}
PERIODS = [("pre-Delta", "2020-07-01", "2021-06-30"), ("Delta(근사)", "2021-07-01", "2021-11-30"),
           ("Omicron(근사)", "2021-12-01", "2023-01-31")]
LABEL = {"persistence": "지속", "trend": "감쇠 추세", "seasonal52": "52주 계절", "seir": "보정 SEIR",
         "ml": "ML (분위수 GBM)", "hybrid": "SEIR+ML 잔차", "ml_loco": "ML (그 나라 제외 학습)"}
G = {}


def _init(knot, every):
    os.environ["OMP_NUM_THREADS"] = "1"
    warnings.simplefilter("ignore")
    sys.path.insert(0, str(ROOT))
    from seir_sim.forecast.targets import origins, rolling7, weekly
    from seir_sim.ml.features import daily_features
    with open(OUT / "panels.pkl", "rb") as f:
        panels = pickle.load(f)
    G["countries"] = list(panels)
    G["feat"] = {c: daily_features(p) for c, p in panels.items()}
    G["s7"] = {"cases": {c: rolling7(p["cases"]) for c, p in panels.items()},
               "deaths": {c: rolling7(p["deaths"]) for c, p in panels.items()}}
    G["weekly"] = {v: {c: weekly(panels[c][v]) for c in panels} for v in VARS}
    G["origins"] = origins(FIRST_ORIGIN, LAST_ORIGIN, every)
    G["seir"] = load_seir(knot, list(panels))


def load_seir(knot, countries):
    out = {}
    for c in countries:
        path = OUT / f"seir_k{knot}_{c}.pkl"
        if not path.exists():
            continue
        with open(path, "rb") as f:
            d = pickle.load(f)
        for r in d["results"]:
            out[(c, pd.Timestamp(r["origin"]))] = r
    return out


def origin_task(t):
    from seir_sim.forecast.baselines import baseline_forecast
    from seir_sim.forecast.metrics import mase_scale
    from seir_sim.forecast.targets import history, truth
    from seir_sim.ml.features import origin_rows, training_rows
    from seir_sim.ml.quantile import fit_hybrid, fit_ml, hybrid_features, hybrid_predict, ml_predict
    t = pd.Timestamp(t)
    rows, info = [], {"origin": str(t.date())}
    for var, base in VARS.items():
        parts = {c: training_rows(G["feat"][c], G["s7"][var][c], t, base=base) for c in G["countries"]}
        train = pd.concat(parts.values())
        models = fit_ml(train)
        info[f"ml_rows_{var}"] = len(train)
        loco = {}
        if var == "cases":                         # 국가 제외 학습: 그 나라 자료 없이 학습한 모형으로 그 나라 예측
            for c in LOCO:
                if c in parts:
                    loco[c] = fit_ml(pd.concat([v for k, v in parts.items() if k != c]))
        hr = []
        for c in G["countries"]:
            for s in G["origins"][G["origins"] < t]:
                r = G["seir"].get((c, s))
                if r is None or f"{var}_q" not in r:
                    continue
                y = truth(G["weekly"][var][c], s)
                X = origin_rows(G["feat"][c], s)
                q = np.asarray(r[f"{var}_q"])
                Xh = hybrid_features(X, q, base)
                Xh["resid"] = np.log1p(y) - np.log1p(q[:, 4])
                ok = (s + pd.to_timedelta(7 * Xh["h"].to_numpy(), "D") <= t) & np.isfinite(y) & np.isfinite(Xh[base].to_numpy())
                hr.append(Xh[ok])
        htrain = pd.concat(hr) if hr else pd.DataFrame()
        hmodels = fit_hybrid(htrain)
        info[f"hybrid_rows_{var}"] = len(htrain)
        for c in G["countries"]:
            hist = history(G["weekly"][var][c], t)
            y = truth(G["weekly"][var][c], t)
            preds = {m: baseline_forecast(hist, m) for m in ("persistence", "trend", "seasonal52")}
            X0 = origin_rows(G["feat"][c], t)
            preds["ml"] = ml_predict(models, X0, base)
            if c in loco:
                preds["ml_loco"] = ml_predict(loco[c], X0, base)
            r = G["seir"].get((c, t))
            seir_q = np.asarray(r[f"{var}_q"]) if (r is not None and f"{var}_q" in r) else None
            preds["seir"] = seir_q
            active = None
            if seir_q is not None and np.isfinite(X0[base]).all():
                preds["hybrid"], active = hybrid_predict(hmodels, X0, seir_q, base)
            scale = mase_scale(hist)
            for m, q in preds.items():
                if q is None:
                    continue
                for h in range(4):
                    row = {"iso3": c, "origin": t, "var": var, "method": m, "h": h + 1,
                           "target_end": t + pd.Timedelta(days=7 * (h + 1)), "truth": y[h], "scale": scale,
                           **{f"q{k}": float(q[h, k]) for k in range(q.shape[1])}}
                    if m == "hybrid":
                        row["hybrid_active"] = bool(active)
                    if m == "seir":
                        row["seir_samples"] = r[f"{var}_samples"][:, h]
                    rows.append(row)
    return rows, info


def score(df: pd.DataFrame) -> pd.DataFrame:
    from seir_sim.forecast import metrics as Mx
    Q = Mx.QUANTILES.size
    qv = df[[f"q{k}" for k in range(Q)]].to_numpy()
    y = df["truth"].to_numpy()
    w = Mx.wis(y, qv)
    wl = Mx.wis(y, qv, log=True)
    df = df.copy()
    df["wis"] = w["wis"]
    df["wis_log"] = wl["wis"]
    for k in ("dispersion", "overprediction", "underprediction"):
        df[f"log_{k}"] = wl[k]
    med = qv[:, 4]
    df["ae"] = np.abs(med - y)
    df["se"] = (med - y) ** 2
    df["ase"] = df["ae"] / df["scale"]
    df["log_err"] = np.log1p(med) - np.log1p(y)
    for a in (0.5, 0.2, 0.1, 0.05):
        df[f"cov{int(round((1 - a) * 100))}"] = Mx.coverage(y, qv, a)
    lo, hi = Mx.interval(qv, 0.1)
    df["width90"] = hi - lo
    df["logwidth90"] = np.log1p(hi) - np.log1p(lo)
    return df


def common(df, methods):
    key = ["iso3", "origin", "var", "h"]
    d = df[df["method"].isin(methods)]
    n = d.groupby(key)["method"].transform("nunique")
    return d[n == len(methods)]


def summarize(d, by):
    g = d.groupby(by)
    out = g.agg(n=("truth", "size"), mae=("ae", "mean"), rmse=("se", lambda x: float(np.sqrt(x.mean()))),
                mase=("ase", "mean"), wis=("wis", "mean"), wis_log=("wis_log", "mean"), cov50=("cov50", "mean"),
                cov90=("cov90", "mean"), cov95=("cov95", "mean"), logwidth90=("logwidth90", "mean"),
                bias_log=("log_err", "mean"))
    return out


def relative(d, by, ref="persistence"):
    """같은 행 집합에서 평균 로그 WIS 의 비 (방법 / 지속), 국가별 자연 척도 WIS 비의 기하평균."""
    s = d.groupby(by + ["method"])["wis_log"].mean().unstack("method")
    rel_log = s.div(s[ref], axis=0)
    nat = d.groupby(by + ["iso3", "method"])["wis"].mean().unstack("method")
    rn = np.log(nat.div(nat[ref], axis=0)).groupby(level=list(range(len(by)))).mean()
    return rel_log, np.exp(rn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--knot", type=int, default=14)
    ap.add_argument("--every", type=int, default=2)
    a = ap.parse_args()
    warnings.simplefilter("ignore")
    from seir_sim.forecast.panel import load_panel
    from seir_sim.surveillance.sources import COUNTRIES
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    panels = {c: load_panel(c) for c in COUNTRIES}
    with open(OUT / "panels.pkl", "wb") as f:
        pickle.dump(panels, f)
    _init(a.knot, a.every)
    missing = [c for c in COUNTRIES if not any(k[0] == c for k in G["seir"])]
    ctx = mp.get_context("forkserver")
    with ProcessPoolExecutor(a.workers, mp_context=ctx, initializer=_init, initargs=(a.knot, a.every)) as ex:
        res = list(ex.map(origin_task, list(G["origins"])))
    rows = [r for rr, _ in res for r in rr]
    infos = [i for _, i in res]
    raw = pd.DataFrame(rows)
    samples = raw.pop("seir_samples") if "seir_samples" in raw else None
    if "hybrid_active" in raw:
        raw["hybrid_active"] = raw["hybrid_active"].astype("boolean")
    raw.to_parquet(OUT / f"forecasts_k{a.knot}.parquet")
    df = score(raw[np.isfinite(raw["truth"])])
    if samples is not None:
        from seir_sim.forecast.metrics import crps_samples
        sm = samples[df.index]
        is_seir = df["method"] == "seir"
        X = np.stack(sm[is_seir].to_numpy())
        df.loc[is_seir, "crps"] = crps_samples(df.loc[is_seir, "truth"].to_numpy(), X)
    report(df, raw, infos, missing, a, time.perf_counter() - t0)


def period_of(dates):
    lab = np.full(len(dates), "", dtype=object)
    for name, s, e in PERIODS:
        lab[(dates >= pd.Timestamp(s)) & (dates <= pd.Timestamp(e))] = name
    return lab


def report(df, raw, infos, missing, a, wall):
    from seir_sim.forecast import metrics as Mx
    rep = {"knot_days": a.knot, "origins_every_weeks": a.every, "first_origin": FIRST_ORIGIN, "last_origin": LAST_ORIGIN,
           "countries_missing_seir": missing, "wall_seconds": wall, "n_rows_scored": int(len(df))}
    df = df.copy()
    df["period"] = period_of(df["target_end"])
    C = common(df, CORE)
    rep["common_set"] = {v: int((C["var"] == v).sum() // len(CORE)) for v in VARS}
    L = ["# 5단계 보고: COVID-19 시간순 예측 검증 (자동 생성: scripts/report_stage5_forecast.py)", "",
         "규약: `docs/reports/5_protocol.md` (실행 전에 정함). 자료: JHU CSSE 일별 확진·사망의 주간 합 (최종판), "
         f"12개국, 기점 {FIRST_ORIGIN} ~ {LAST_ORIGIN} 매 {a.every}주 (일요일), 예측 1~4주 (7·14·21·28일).",
         f"보정 SEIR 구간 길이 {a.knot}일. 전체 실행 {wall / 60:.1f} 분.", "",
         "**주의.** 모든 방법은 기점까지의 자료만 쓴다. 다만 자료가 나중에 정정된 최종판이라 실시간 성능보다 낙관적일 수 있다.",
         "아래 성능은 이 12개국·이 기간의 과거 검증 결과이며, 다른 병원체·국가·시기에서의 예측 정확도를 보장하지 않는다.", ""]
    if missing:
        L += [f"SEIR 예측이 없는 국가 (비교에서 빠짐): {', '.join(missing)}", ""]
    for var in VARS:
        d = C[C["var"] == var]
        if d.empty:
            continue
        rl, rn = relative(d, ["h"])
        sm = summarize(d, ["h", "method"])
        rep[f"{var}_by_h"] = {f"{h}|{m}": {**sm.loc[(h, m)].to_dict(), "rel_wis_log": float(rl.loc[h, m]),
                                           "rel_wis_nat_geo": float(rn.loc[h, m])} for h, m in sm.index}
        L += [f"## {'확진' if var == 'cases' else '사망'}: 공통 비교 집합 (같은 국가·기점·예측 주에서 {len(CORE)}개 방법이 모두 예측한 행)", "",
              "상대 WIS < 1 이면 지속 예측보다 낫다. 상대 로그 WIS = 평균 로그 WIS 의 비 (1차 지표, 규약 참고). "
              "상대 WIS(국가) = 국가별 자연 척도 평균 WIS 비의 기하평균.", "",
              "| 예측 주 | 방법 | n | 상대 로그 WIS | 상대 WIS(국가) | MAE | MASE | 50% 포함 | 90% 포함 | 95% 포함 | 로그 편향 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for h in sorted(d["h"].unique()):
            for m in CORE:
                r = sm.loc[(h, m)]
                L.append(f"| {h} ({7 * h}일) | {LABEL[m]} | {int(r.n)} | {rl.loc[h, m]:.3f} | {rn.loc[h, m]:.3f} | "
                         f"{r.mae:,.0f} | {r.mase:.2f} | {r.cov50:.2f} | {r.cov90:.2f} | {r.cov95:.2f} | {r.bias_log:+.3f} |")
        L.append("")
        # 시기별
        rlp, _ = relative(d, ["period"])
        smp = summarize(d, ["period", "method"])
        rep[f"{var}_by_period"] = {f"{p}|{m}": {**smp.loc[(p, m)].to_dict(), "rel_wis_log": float(rlp.loc[p, m])} for p, m in smp.index}
        L += [f"### 시기별 (대상 주 끝날 기준, 변이 시기는 달력 근사: 국가별 변이 우세 시점 자료는 확보하지 않음)", "",
              "| 시기 | " + " | ".join(LABEL[m] for m in CORE) + " | n (방법당) |", "|---" * (len(CORE) + 2) + "|"]
        for p, _, _ in PERIODS:
            if p in rlp.index:
                L.append(f"| {p} | " + " | ".join(f"{rlp.loc[p, m]:.3f}" for m in CORE) + f" | {int(smp.loc[(p, 'seir')].n)} |")
        L.append("")
        rlc, _ = relative(d, ["iso3"])
        rep[f"{var}_by_country"] = {c: {m: float(rlc.loc[c, m]) for m in CORE} for c in rlc.index}
        L += ["### 국가별 상대 로그 WIS (1~4주 합침)", "", "| 국가 | " + " | ".join(LABEL[m] for m in CORE[1:]) + " |",
              "|---" * len(CORE) + "|"]
        for c in rlc.index:
            L.append(f"| {c} | " + " | ".join(f"{rlc.loc[c, m]:.3f}" for m in CORE[1:]) + " |")
        L.append("")
    # SEIR 표본 CRPS
    s = df[(df["method"] == "seir") & df["crps"].notna()] if "crps" in df else pd.DataFrame()
    if len(s):
        rep["seir_crps_by_var_h"] = {f"{v}|{h}": float(x) for (v, h), x in s.groupby(["var", "h"])["crps"].mean().items()}
    # 52주 계절 단순 예측 (부분 집합)
    S52 = common(df, ["persistence", "seasonal52", "seir", "ml"])
    if len(S52):
        L += ["## 52주 계절 단순 예측 (52주 이력이 있는 기점만; 같은 행에서 비교)", "",
              "| 변수 | 지속 | 52주 계절 | 보정 SEIR | ML | n (방법당) |", "|---|---|---|---|---|---|"]
        for var in VARS:
            d = S52[S52["var"] == var]
            if d.empty:
                continue
            m = d.groupby("method")["wis_log"].mean()
            L.append(f"| {var} | 1.000 | {m['seasonal52'] / m['persistence']:.3f} | {m['seir'] / m['persistence']:.3f} | "
                     f"{m['ml'] / m['persistence']:.3f} | {int((d['method'] == 'seir').sum())} |")
        L.append("")
    # 정점
    L += ["## 정점 시기·크기 (관측 정점이 예측 1~4주 안에 있는 기점)", "",
          "정점 정의 (사전에 정함): 주간 log(1+y) 의 지역 최대 중 양쪽 돌출 log 2 이상, 주 50건 이상.", "",
          "| 변수 | 방법 | 사례 수 | 시기 오차 평균 절대 (주) | 시기 정확 비율 | 크기 log 비 중앙값 | 크기 log 비 평균 절대 |",
          "|---|---|---|---|---|---|---|"]
    pk_rep = {}
    for var in VARS:
        d = C[C["var"] == var]
        for m in CORE:
            errs = []
            for (c, o), g in d[d["method"] == m].groupby(["iso3", "origin"]):
                if len(g) != 4:
                    continue
                w = G["weekly"][var][c]
                e = Mx.peak_errors(o, g.sort_values("h")["q4"].to_numpy(), w, Mx.observed_peaks(w))
                if e:
                    errs.append(e)
            if errs:
                te = np.array([e["timing_error_weeks"] for e in errs])
                ls = np.array([e["log_size_ratio"] for e in errs])
                pk_rep[f"{var}|{m}"] = {"n": len(errs), "mae_timing": float(np.mean(np.abs(te))), "exact": float(np.mean(te == 0)),
                                        "median_log_size": float(np.median(ls)), "mae_log_size": float(np.mean(np.abs(ls)))}
                v = pk_rep[f"{var}|{m}"]
                L.append(f"| {var} | {LABEL[m]} | {v['n']} | {v['mae_timing']:.2f} | {v['exact']:.2f} | {v['median_log_size']:+.2f} | {v['mae_log_size']:.2f} |")
    rep["peaks"] = pk_rep
    L.append("")
    # SEIR 적합 상태
    seir = list(G["seir"].values())
    if seir:
        st = {"n": len(seir), "success": float(np.mean([r["success"] for r in seir])),
              "hessian_pd": float(np.mean([bool(r["hessian_pd"]) for r in seir])),
              "mean_wall_s": float(np.mean([r["wall_s"] for r in seir])),
              "Rt_capped": float(np.mean([r["Rt_last_capped"] for r in seir]))}
        rep["seir_fits"] = st
        L += ["## 보정 SEIR 기점별 재추정 상태", "",
              f"적합 {st['n']}회, 수렴 비율 {st['success']:.2f}, 헤시안 양의 정부호 비율 {st['hessian_pd']:.2f}, "
              f"평균 {st['mean_wall_s']:.1f}초, 마지막 구간 R_t 가 상한(R0_max 의 98%)에 닿은 비율 {st['Rt_capped']:.2f}.", ""]
    h = df[df["method"] == "hybrid"]
    if len(h):
        rep["hybrid_active_fraction"] = float(h["hybrid_active"].mean())
        first = h[h["hybrid_active"]]["origin"].min()
        L += [f"하이브리드 보정이 실제로 적용된 행 비율 {h['hybrid_active'].mean():.2f} (첫 적용 기점 {first.date() if pd.notna(first) else '-'}; "
              "그 전에는 학습 행이 부족해 SEIR 분위수를 그대로 씀).", ""]
    lo = common(df[df["iso3"].isin(LOCO)], ["persistence", "ml", "ml_loco"])
    if len(lo):
        L += ["## 부가: 국가 제외 학습 ML (그 나라 자료 없이 학습 → 그 나라 예측, 확진)", "",
              "| 국가 | 예측 주 | n | 상대 로그 WIS: ML (전체 학습) | ML (그 나라 제외) |", "|---|---|---|---|---|"]
        rep["ml_loco"] = {}
        for (c, h), g in lo.groupby(["iso3", "h"]):
            m_ = g.groupby("method")["wis_log"].mean()
            rep["ml_loco"][f"{c}|{h}"] = {"ml": float(m_["ml"] / m_["persistence"]), "ml_loco": float(m_["ml_loco"] / m_["persistence"])}
            L.append(f"| {c} | {h} | {int((g['method'] == 'ml').sum())} | {m_['ml'] / m_['persistence']:.3f} | {m_['ml_loco'] / m_['persistence']:.3f} |")
        L.append("")
    kc = knot_comparison(df, a.knot)
    if kc:
        rep["knot_comparison"] = kc
        L += ["## 부가: SEIR u(t) 구간 7일 대 14일 (같은 국가·기점·예측 주)", "",
              f"국가 {', '.join(kc['countries'])}, 기점 {kc['n_origins']}개 (7일 실행은 계산량 때문에 4주마다).", "",
              "| 변수 | 예측 주 | n | 로그 WIS 14일 | 로그 WIS 7일 | 비 (7/14) | 90% 포함 14일 | 90% 포함 7일 |", "|---|---|---|---|---|---|---|---|"]
        for r in kc["rows"]:
            L.append(f"| {r['var']} | {r['h']} | {r['n']} | {r['wis_log_k14']:.3f} | {r['wis_log_k7']:.3f} | {r['ratio']:.3f} | "
                     f"{r['cov90_k14']:.2f} | {r['cov90_k7']:.2f} |")
        L.append("")
    rep["train_rows"] = infos
    (ROOT / "docs" / "reports" / f"5_forecast_validation{'' if a.knot == 14 else f'_k{a.knot}'}.json").write_text(
        json.dumps(rep, indent=1, ensure_ascii=False, default=str))
    figures(df, C, a.knot)
    L += ["그림: `docs/figures/5_relative_wis.png`, `docs/figures/5_coverage.png`, `docs/figures/5_kor_forecasts.png`, "
          "`docs/figures/5_by_period.png`"]
    (ROOT / "docs" / "reports" / f"5_forecast_validation{'' if a.knot == 14 else f'_k{a.knot}'}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def knot_comparison(df, knot):
    """seir_k7_*.pkl 이 있으면 같은 (국가, 기점, 변수, 예측 주) 에서 14일 구간 SEIR 과 비교한다."""
    from seir_sim.forecast import metrics as Mx
    if knot != 14:
        return None
    other = load_seir(7, G["countries"])
    if not other:
        return None
    rows = []
    for (c, o), r in other.items():
        for var in VARS:
            if f"{var}_q" not in r:
                continue
            y = np.array([G["weekly"][var][c].get(o + pd.Timedelta(days=7 * h), np.nan) for h in (1, 2, 3, 4)], float)
            q = np.asarray(r[f"{var}_q"])
            for h in range(4):
                rows.append({"iso3": c, "origin": o, "var": var, "h": h + 1, "truth": y[h], **{f"k7_q{k}": q[h, k] for k in range(q.shape[1])}})
    k7 = pd.DataFrame(rows)
    base = df[df["method"] == "seir"][["iso3", "origin", "var", "h", "truth"] + [f"q{k}" for k in range(Mx.QUANTILES.size)]]
    m = base.merge(k7.drop(columns="truth"), on=["iso3", "origin", "var", "h"])
    m = m[np.isfinite(m["truth"])]
    if m.empty:
        return None
    y = m["truth"].to_numpy()
    q14 = m[[f"q{k}" for k in range(Mx.QUANTILES.size)]].to_numpy()
    q7 = m[[f"k7_q{k}" for k in range(Mx.QUANTILES.size)]].to_numpy()
    m["w14"], m["w7"] = Mx.wis(y, q14, log=True)["wis"], Mx.wis(y, q7, log=True)["wis"]
    m["c14"], m["c7"] = Mx.coverage(y, q14, 0.1), Mx.coverage(y, q7, 0.1)
    out = []
    for (var, h), g in m.groupby(["var", "h"]):
        out.append({"var": var, "h": int(h), "n": int(len(g)), "wis_log_k14": float(g["w14"].mean()), "wis_log_k7": float(g["w7"].mean()),
                    "ratio": float(g["w7"].mean() / g["w14"].mean()), "cov90_k14": float(g["c14"].mean()), "cov90_k7": float(g["c7"].mean())})
    return {"countries": sorted(m["iso3"].unique()), "n_origins": int(m["origin"].nunique()), "rows": out}


def figures(df, C, knot):
    if knot != 14:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from seir_sim.viz.plots import CATEGORICAL, INK, INK_2, SURFACE, _font, _style
    _font()
    col = {"seir": CATEGORICAL[0], "ml": CATEGORICAL[1], "hybrid": CATEGORICAL[2], "trend": CATEGORICAL[3]}
    figdir = ROOT / "docs" / "figures"
    # 1) 상대 로그 WIS vs 예측 주
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=150, facecolor=SURFACE, sharey=True)
    for ax, var, title in ((axes[0], "cases", "확진"), (axes[1], "deaths", "사망")):
        _style(ax)
        d = C[C["var"] == var]
        if d.empty:
            continue
        rl, _ = relative(d, ["h"])
        ax.axhline(1.0, color=INK_2, lw=1, ls="--")
        ax.text(4.05, 1.0, "지속 예측", color=INK_2, fontsize=8, va="center")
        for m in ("trend", "seir", "ml", "hybrid"):
            ax.plot(rl.index, rl[m], color=col[m], lw=2, marker="o", ms=5)
            ax.text(4.05, rl[m].iloc[-1], LABEL[m], color=INK, fontsize=8, va="center")
        ax.set_xticks([1, 2, 3, 4], ["1주", "2주", "3주", "4주"])
        ax.set_xlim(0.8, 4.9)
        ax.set_title(f"{title}: 상대 로그 WIS (낮을수록 좋음)", loc="left", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(figdir / "5_relative_wis.png", facecolor=SURFACE)
    plt.close(fig)
    # 2) 포함률
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), dpi=150, facecolor=SURFACE, sharey=True)
    for ax, var, title in ((axes[0], "cases", "확진"), (axes[1], "deaths", "사망")):
        _style(ax)
        d = C[C["var"] == var]
        if d.empty:
            continue
        nominal = [0.5, 0.8, 0.9, 0.95]
        ax.plot([0.45, 1.0], [0.45, 1.0], color=INK_2, lw=1, ls="--")
        for m in ("seir", "ml", "hybrid", "trend"):
            cov = [d[d["method"] == m][f"cov{int(n * 100)}"].mean() for n in nominal]
            ax.plot(nominal, cov, color=col[m], lw=2, marker="o", ms=5)
            ax.text(0.955, cov[-1], LABEL[m], color=INK, fontsize=8, va="center")
        ax.set_xlim(0.45, 1.06)
        ax.set_xlabel("명목 구간 수준", color=INK_2, fontsize=9)
        ax.set_title(f"{title}: 구간 포함률 (점선 = 이상적)", loc="left", color=INK, fontsize=10)
    axes[0].set_ylabel("실제 포함률", color=INK_2, fontsize=9)
    fig.tight_layout()
    fig.savefig(figdir / "5_coverage.png", facecolor=SURFACE)
    plt.close(fig)
    # 3) 대한민국 예측 부채꼴
    w = G["weekly"]["cases"]["KOR"].loc["2020-06-01":"2023-02-01"]
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), dpi=150, facecolor=SURFACE, sharex=True, sharey=True)
    k = df[(df["iso3"] == "KOR") & (df["var"] == "cases")]
    ors = sorted(k["origin"].unique())[::2]
    for ax, m in zip(axes, ("seir", "ml", "hybrid")):
        _style(ax)
        ax.plot(w.index, w.values, color=INK, lw=1.2)
        for o in ors:
            g = k[(k["method"] == m) & (k["origin"] == o)].sort_values("h")
            if len(g) != 4:
                continue
            x = g["target_end"]
            ax.fill_between(x, g["q1"], g["q7"], color=col[m], alpha=0.25, lw=0)
            ax.plot(x, g["q4"], color=col[m], lw=1.5)
        ax.set_yscale("log")
        ax.set_title(f"대한민국 주간 확진: {LABEL[m]} 4주 예측 (중앙값, 90% 구간; 검은 선 = 관측)", loc="left", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(figdir / "5_kor_forecasts.png", facecolor=SURFACE)
    plt.close(fig)
    # 4) 시기별
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), dpi=150, facecolor=SURFACE, sharey=True)
    for ax, var, title in ((axes[0], "cases", "확진"), (axes[1], "deaths", "사망")):
        _style(ax)
        d = C[C["var"] == var]
        if d.empty:
            continue
        rl, _ = relative(d, ["period"])
        order = [p for p, _, _ in PERIODS if p in rl.index]
        ax.axhline(1.0, color=INK_2, lw=1, ls="--")
        for m in ("trend", "seir", "ml", "hybrid"):
            ax.plot(range(len(order)), rl.loc[order, m], color=col[m], lw=2, marker="o", ms=5)
            ax.text(len(order) - 0.95, rl.loc[order[-1], m], LABEL[m], color=INK, fontsize=8, va="center")
        ax.set_xticks(range(len(order)), order)
        ax.set_xlim(-0.2, len(order) + 0.2)
        ax.set_title(f"{title}: 시기별 상대 로그 WIS", loc="left", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(figdir / "5_by_period.png", facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
