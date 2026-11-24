"""3단계 보고서: 관측 모형과 매개변수 추정의 검증.

  1) 합성 자료 반복 실험: 추정값 편향과 95% 라플라스 구간 포함률 (추정기 검증용, 실제 자료 아님)
  2) 대한민국 (JHU 확진·사망, 2020-02-01 ~ 2021-10-31): 추정, 진단, 보고율 rho 프로파일, 다중 시작점
  3) 추정 u(t) 와 실제 정책(OxCGRT)·이동(Google Community Mobility) 의 상관 (해석 가능성 점검)
  4) 비교국 11개국 같은 기간 적합 (수렴, 진단)

사용법: python -I scripts/report_stage3_calibration.py [--workers 4] [--replicates 20]
출력:   docs/reports/3_calibration.md, .json, docs/figures/3_kor_fit.png
"""

import argparse
import json
import multiprocessing as mp
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

R = ROOT / "data_raw"
START, END = "2020-02-01", "2021-10-31"
BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1, T1=1, Pmin=0.3, alpha=0.5, beta=0.3, lam=1 / 180, f1=0.01, M=8)


def _setup():
    warnings.simplefilter("ignore")
    sys.path.insert(0, str(ROOT))


def load_country(iso3):
    from seir_sim.surveillance import sources as S
    from seir_sim.surveillance.observed import build_observed
    j = S.jhu_country(R / "jhu_csse_global/time_series_covid19_confirmed_global.csv",
                      R / "jhu_csse_global/time_series_covid19_deaths_global.csv", iso3)
    oc = build_observed(j.new_cases, "cases", iso3, "jhu", "2020-01-23", "2023-03-09")
    od = build_observed(j.new_deaths, "deaths", iso3, "jhu", "2020-01-23", "2023-03-09", gap_min_mean=5)
    o = S.owid_country(R / "owid_covid/owid-covid-data.csv", iso3, cols=["population"])
    pop = float(o.population.dropna().iloc[-1])
    return oc, od, pop


def fit_country(args):
    _setup()
    from seir_sim.inference.calibrate import FitSpec, SingleRegionModel, fit_diagnostics
    from seir_sim.model.params import EpiParams
    iso3, rho, theta0 = args
    oc, od, pop = load_country(iso3)
    m = SingleRegionModel(EpiParams(**BASE), pop, FitSpec(start=START, fit_end=END, rho=rho))
    fr = m.fit(oc, od, theta0=theta0)
    p = m.unpack(fr.theta)
    corr = None
    if fr.cov is not None:
        sd = np.sqrt(np.clip(np.diag(fr.cov), 1e-300, None))
        cm = fr.cov / np.outer(sd, sd)
        np.fill_diagonal(cm, 0)
        k = np.unravel_index(np.argmax(np.abs(cm)), cm.shape)
        corr = {"max_abs_corr": float(abs(cm[k])), "pair": [fr.names[k[0]], fr.names[k[1]]]}
    return {"iso3": iso3, "rho": rho, "population": pop, "success": fr.success, "message": fr.message,
            "objective": fr.objective, "n_iter": fr.n_iter, "wall_s": fr.wall_seconds, "hessian_pd": fr.hessian_pd,
            "theta": fr.theta.tolist(), "names": fr.names, "se": (fr.se().tolist() if fr.cov is not None else None),
            "Rt_knots": (p["m"] * 6.0).tolist(), "delay_c": float(p["delay_c"]), "r_c": float(p["r_c"]),
            "k_f": p["k_f"].tolist(), "delay_d": float(p["delay_d"]), "r_d": float(p["r_d"]),
            "w_c": p["w_c"].tolist(), "I0": float(p["I0"]), "diagnostics": fit_diagnostics(m, fr),
            "max_param_corr": corr}


def synthetic_replicate(seed):
    """알려진 매개변수로 만든 합성 관측에서 다시 추정한다 (추정기 검증용)."""
    _setup()
    from seir_sim.inference.calibrate import FitSpec, SingleRegionModel
    from seir_sim.model.params import EpiParams
    from seir_sim.surveillance.observed import build_observed
    spec = FitSpec(start="2020-02-01", fit_end="2020-08-28")
    m = SingleRegionModel(EpiParams(**BASE), 5e7, spec)
    rt = np.array([2.5, 2.3, 1.0, 0.7, 0.8, 0.9, 1.1, 1.3, 1.2, 1.0, 0.9, 0.8, 0.9, 1.0, 1.1])[: m.n_knots]
    th = np.zeros(len(m.names))
    mm = rt / 6.0
    th[: m.n_knots] = np.log(mm / (1 - mm))
    th[m.idx["log_I0"]] = np.log(30)
    th[m.idx["log_delay_c"]] = np.log(5)
    th[m.idx["wc0"]: m.idx["wc0"] + 6] = [0.1, 0.05, 0, 0, -0.05, -0.1]
    th[m.idx["log_r_c"]] = np.log(30)
    th[m.idx["log_kf0"]: m.idx["log_kf0"] + m.n_kf] = np.log(1.5)
    th[m.idx["log_delay_d"]] = np.log(12)
    th[m.idx["log_r_d"]] = np.log(15)
    par = m.unpack(th)
    ex = m.expected(par)
    rng = np.random.default_rng(seed)
    yc = rng.negative_binomial(par["r_c"], par["r_c"] / (par["r_c"] + ex["mu_cases"]))
    yd = rng.negative_binomial(par["r_d"], par["r_d"] / (par["r_d"] + ex["mu_deaths"]))
    dates = pd.date_range(spec.start, periods=m.days)
    oc = build_observed(pd.Series(yc, index=dates), "cases", "SYN", "synthetic")
    od = build_observed(pd.Series(yd, index=dates), "deaths", "SYN", "synthetic", gap_min_mean=1e9)
    fr = m.fit(oc, od)
    se = fr.se()
    return {"seed": seed, "success": fr.success, "pd": fr.hessian_pd, "names": fr.names,
            "true": th.tolist(), "est": fr.theta.tolist(), "se": se.tolist() if se is not None else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--replicates", type=int, default=20)
    a = ap.parse_args()
    _setup()
    from seir_sim.surveillance import sources as S
    t0 = time.perf_counter()
    ctx = mp.get_context("forkserver")
    with ProcessPoolExecutor(a.workers, mp_context=ctx) as ex:
        countries = list(S.COUNTRIES)
        fut_c = {c: ex.submit(fit_country, (c, 0.5, None)) for c in countries}
        fut_s = [ex.submit(synthetic_replicate, s) for s in range(a.replicates)]
        kor = fut_c["KOR"].result()
        th0 = np.array(kor["theta"])
        fut_p = {rho: ex.submit(fit_country, ("KOR", rho, th0)) for rho in (0.2, 0.35, 0.7, 1.0)}
        rng = np.random.default_rng(1)
        fut_m = [ex.submit(fit_country, ("KOR", 0.5, th0 + rng.normal(0, 0.3, th0.size))) for _ in range(3)]
        res_c = {c: f.result() for c, f in fut_c.items()}
        res_s = [f.result() for f in fut_s]
        res_p = {0.5: kor, **{r: f.result() for r, f in fut_p.items()}}
        res_m = [f.result() for f in fut_m]
    wall = time.perf_counter() - t0

    # 1) 합성 반복 실험 요약
    names = res_s[0]["names"]
    T = np.array([r["true"] for r in res_s])
    E = np.array([r["est"] for r in res_s])
    SE = np.array([r["se"] for r in res_s if r["se"] is not None])
    ok = [r["se"] is not None for r in res_s]
    z = (E[ok] - T[ok]) / SE
    groups = {"u(t) 구간값 z_k": [i for i, n in enumerate(names) if n.startswith("z")],
              "초기 감염 log_I0": [names.index("log_I0")], "확진 지연": [names.index("log_delay_c")],
              "확진 과산포": [names.index("log_r_c")], "요일 효과 (확진)": [i for i, n in enumerate(names) if n.startswith("wc")],
              "치명률 배율": [i for i, n in enumerate(names) if n.startswith("log_kf")],
              "사망 지연": [names.index("log_delay_d")], "사망 과산포": [names.index("log_r_d")]}
    syn = {g: {"coverage95": float(np.mean(np.abs(z[:, idx]) < 1.96)), "mean_z": float(np.mean(z[:, idx])),
               "rmse_over_mean_se": float(np.sqrt(np.mean((E[ok][:, idx] - T[ok][:, idx]) ** 2)) / np.mean(SE[:, idx]))}
           for g, idx in groups.items()}
    syn_meta = {"replicates": len(res_s), "converged": int(sum(r["success"] for r in res_s)),
                "hessian_pd": int(sum(bool(r["pd"]) for r in res_s))}

    # 3) u(t) 해석 가능성: 추정 Rt 와 정책·이동
    from seir_sim.surveillance import sources as S2
    interp = {}
    for iso3, r in res_c.items():
        iso2 = S2.COUNTRIES[iso3][0]
        x = S2.oxcgrt_country(R / "oxcgrt_national/OxCGRT_compact_national_v1.csv", iso3)
        g = S2.gc19od_location(R / ("gc19od_kr" if iso2 == "KR" else "gc19od_countries") / f"{iso2}.csv")
        days = pd.date_range(START, END)
        k = np.minimum(np.arange(days.size) // 14, len(r["Rt_knots"]) - 1)
        rt = pd.Series(np.array(r["Rt_knots"])[k], index=days)
        def kn(s):
            return s.reindex(days).groupby(np.arange(days.size) // 14).mean()
        rk = kn(rt)
        st = kn(x.StringencyIndex_Average)
        mob = kn(g.mobility_workplaces) if "mobility_workplaces" in g else None
        interp[iso3] = {"corr_Rt_vs_stringency": float(np.corrcoef(rk[st.notna()], st.dropna())[0, 1]),
                        "corr_Rt_vs_workplace_mobility": (float(pd.concat([rk, mob], axis=1).dropna().corr().iloc[0, 1])
                                                          if mob is not None else None)}

    rep = {"period": [START, END], "wall_seconds": wall, "synthetic": {"meta": syn_meta, "groups": syn},
           "countries": res_c, "rho_profile": {str(k): {"objective": v["objective"], "k_f_mean": float(np.mean(v["k_f"])),
                                                         "I0": v["I0"], "Rt_first": v["Rt_knots"][0]} for k, v in res_p.items()},
           "multistart": [{"objective": r["objective"], "success": r["success"]} for r in res_m] + [{"objective": kor["objective"], "base": True}],
           "interpretation": interp}
    out = ROOT / "docs" / "reports"
    (out / "3_calibration.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str))
    figure(res_c["KOR"], ROOT / "docs" / "figures" / "3_kor_fit.png")

    L = ["# 3단계 보고: 관측 모형과 매개변수 추정 (자동 생성: scripts/report_stage3_calibration.py)", "",
         f"기간 {START} ~ {END}, 확진·사망: JHU CSSE (원출처 각국 보건당국). 고정 가정: sigma = 1/5.2, gamma = 1/7, "
         "R0_max = 6 (u = 0 기준), rho = 0.5 (보고율), 재감염 매개변수는 1단계 가정 값. 모형 설명: `seir_sim/inference/calibrate.py`.",
         f"전체 실행 {wall / 60:.1f} 분 (작업자 {a.workers}).", "",
         "## 1. 추정기 검증: 합성 자료 반복 실험 (실제 자료 아님)", "",
         f"반복 {syn_meta['replicates']}회, 수렴 {syn_meta['converged']}, 헤시안 양의 정부호 {syn_meta['hessian_pd']}.", "",
         "| 매개변수 묶음 | 95% 구간 포함률 | 평균 z (편향) | RMSE / 평균 SE |", "|---|---|---|---|"]
    for g, v in syn.items():
        L.append(f"| {g} | {v['coverage95']:.2f} | {v['mean_z']:+.2f} | {v['rmse_over_mean_se']:.2f} |")
    L += ["", "## 2. 국가별 적합 (같은 모형·같은 기간)", "",
          "| 국가 | 수렴 | 헤시안 PD | 반복 | 시간 s | 확진 PIT KS | 확진 잔차 자기상관 | 확진 90% 포함 | 사망 PIT KS | 사망 90% 포함 | 확진 지연 (일) | 치명률 배율 (처음→끝) | 최대 매개변수 상관 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for iso3, r in res_c.items():
        dc, dd = r["diagnostics"]["cases"], r["diagnostics"].get("deaths", {})
        mc = r["max_param_corr"] or {}
        L.append(f"| {iso3} | {'예' if r['success'] else '아니오'} | {r['hessian_pd']} | {r['n_iter']} | {r['wall_s']:.0f} | "
                 f"{dc['pit_ks_stat']:.3f} | {dc['pearson_resid_lag1_autocorr']:.2f} | {dc['coverage90_in_sample']:.2f} | "
                 f"{dd.get('pit_ks_stat', float('nan')):.3f} | {dd.get('coverage90_in_sample', float('nan')):.2f} | {r['delay_c']:.1f} | "
                 f"{r['k_f'][0]:.2f}→{r['k_f'][-1]:.2f} | {mc.get('max_abs_corr', float('nan')):.2f} ({', '.join(mc.get('pair', []))}) |")
    L += ["", "## 3. 식별 가능성 (대한민국)", "", "보고율 rho 프로파일 (다른 매개변수는 다시 추정):", "",
          "| rho | 목적함수 | 평균 치명률 배율 | 초기 감염 I0 |", "|---|---|---|---|"]
    for k in sorted(rep["rho_profile"], key=float):
        v = rep["rho_profile"][k]
        L.append(f"| {k} | {v['objective']:.2f} | {v['k_f_mean']:.3f} | {v['I0']:.1f} |")
    obj = [rep["rho_profile"][k]["objective"] for k in rep["rho_profile"]]
    L += ["", f"목적함수 범위 {max(obj) - min(obj):.2f} (로그우도 단위). 차이가 2 미만이면 자료로 rho 를 구분할 수 없다는 뜻이다.",
          "치명률 배율은 rho 에 비례해 바뀐다 (확진 대비 사망 비만 식별됨).", "",
          "다중 시작점 (rho = 0.5): 목적함수 " + ", ".join(f"{m['objective']:.2f}" for m in rep["multistart"]), "",
          "## 4. 추정 u(t) 의 해석 가능성 (2주 평균끼리 상관)", "",
          "R_t(전원 감수성) = R0_max (1 - u). 정책이 강하거나 직장 이동이 줄면 R_t 가 낮아야 한다 (음의 상관 / 양의 상관 기대).", "",
          "| 국가 | R_t vs 정책 강도 (OxCGRT) | R_t vs 직장 이동 (Google) |", "|---|---|---|"]
    for iso3, v in interp.items():
        mob = v["corr_Rt_vs_workplace_mobility"]
        L.append(f"| {iso3} | {v['corr_Rt_vs_stringency']:+.2f} | {'-' if mob is None else f'{mob:+.2f}'} |")
    L += ["", "## 5. 한계", "",
          "- 방정식에 백신·변이·연령 구조가 없어 그 효과가 u(t) 와 치명률 배율 k_f(t) 에 흡수된다.",
          "- 해외 유입 항이 없어 유입 비중이 큰 시기(대한민국 2020년 중반)에는 국내 전파로 해석된다.",
          "- rho (보고율) 는 이 자료로 식별되지 않아 고정 가정이다. 혈청 조사 자료가 있으면 추정 가능하다.",
          "", "그림: `docs/figures/3_kor_fit.png`"]
    (out / "3_calibration.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def figure(r, path):
    from seir_sim.inference.calibrate import FitSpec, SingleRegionModel
    from seir_sim.model.params import EpiParams
    from seir_sim.viz.plots import BAND, BLUE, INK, INK_2, SURFACE, _font, _style
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.stats import nbinom
    ko = _font()
    oc, od, pop = load_country("KOR")
    m = SingleRegionModel(EpiParams(**BASE), pop, FitSpec(start=START, fit_end=END))
    m.prepare(oc, od)
    par = m.unpack(np.array(r["theta"]))
    ex = m.expected(par, m.spec.n_fit_days)
    days = pd.date_range(START, END)
    fig, axes = plt.subplots(3, 1, figsize=(9, 8.5), dpi=150, facecolor=SURFACE, sharex=True)
    for ax, key, mu, rr, title in ((axes[0], "c", ex["mu_cases"], par["r_c"], "일별 확진: 관측 vs 모형 기댓값 (90% 관측 구간)"),
                                   (axes[1], "d", ex["mu_deaths"], par["r_d"], "일별 사망: 관측 vs 모형")):
        _style(ax)
        s, e, y = m._c if key == "c" else m._d
        lo = nbinom.ppf(0.05, rr, rr / (rr + mu))
        hi = nbinom.ppf(0.95, rr, rr / (rr + mu))
        ax.fill_between(days, lo, hi, color=BAND, alpha=0.7, lw=0, label="90% 구간")
        ax.plot(days, mu, color=BLUE, lw=1.5, label="모형 기댓값")
        ax.scatter(days[e], y, s=3, color=INK, label="관측 (JHU)", zorder=3)
        ax.set_title(title if ko else key, loc="left", color=INK, fontsize=10)
        ax.legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="upper left")
    ax = axes[2]
    _style(ax)
    k = np.minimum(np.arange(days.size) // 14, len(r["Rt_knots"]) - 1)
    ax.step(days, np.array(r["Rt_knots"])[k], where="post", color=BLUE, lw=1.5, label="추정 R_t (전원 감수성 기준)")
    ax.axhline(1, color=INK_2, lw=0.8, ls="--")
    ax.set_title("추정 R_t = R0_max (1 - u(t))", loc="left", color=INK, fontsize=10)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
