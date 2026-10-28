"""9단계: 자료 결측과 보고 편향에 대한 추정 민감도 (대한민국, 3단계와 같은 모형·기간).

  base      : 3단계 적합 (docs/reports/3_calibration.json 의 대한민국 결과를 시작값으로 다시 적합)
  drop10_s  : 관측 구간 10% 를 무작위로 뺀 자료 (시드 3개). 결측이 무작위일 때 추정이 얼마나 흔들리는지.
  report70  : 2021-01-01 부터 확진을 0.7 배로 줄인 자료 (검사 정책 변화로 보고율이 떨어진 상황을 흉내). 실제 자료가 아니라
              실제 자료에 알려진 변형을 가한 민감도 시험이다. 보고율을 고정한 모형이 이를 R_t 변화로 오인하는 정도를 본다.
비교: 14일 구간 R_t 의 차이 (평균 절대, 최대), 치명률 배율, 표본 안 90% 포함률.
출력: docs/reports/9_sensitivity.md, .json
"""

import json
import multiprocessing as mp
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
START, END = "2020-02-01", "2021-10-31"
BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1, T1=1, Pmin=0.3, alpha=0.5, beta=0.3, lam=1 / 180, f1=0.01, M=8)


def run(args):
    warnings.simplefilter("ignore")
    sys.path.insert(0, str(ROOT))
    from seir_sim.inference.calibrate import FitSpec, SingleRegionModel, fit_diagnostics
    from seir_sim.model.params import EpiParams
    from seir_sim.surveillance import sources as S
    from seir_sim.surveillance.observed import ObservedSeries, build_observed
    name, seed, theta0 = args
    j = S.jhu_country(ROOT / "data_raw/jhu_csse_global/time_series_covid19_confirmed_global.csv",
                      ROOT / "data_raw/jhu_csse_global/time_series_covid19_deaths_global.csv", "KOR")
    cases = j.new_cases.copy()
    if name == "report70":
        cases.loc["2021-01-01":] = np.round(cases.loc["2021-01-01":] * 0.7)
    oc = build_observed(cases, "cases", "KOR", "jhu", "2020-01-23", "2023-03-09")
    od = build_observed(j.new_deaths, "deaths", "KOR", "jhu", "2020-01-23", "2023-03-09", gap_min_mean=5)
    if name.startswith("drop10"):
        rng = np.random.default_rng(seed)
        keep_c = rng.random(oc.n) >= 0.1
        keep_d = rng.random(od.n) >= 0.1
        oc = ObservedSeries(oc.variable, oc.location, oc.source, oc.dates, oc.start[keep_c], oc.end[keep_c], oc.y[keep_c], oc.flags)
        od = ObservedSeries(od.variable, od.location, od.source, od.dates, od.start[keep_d], od.end[keep_d], od.y[keep_d], od.flags)
    pop = json.loads((ROOT / "docs/reports/3_calibration.json").read_text())["countries"]["KOR"]["population"]
    m = SingleRegionModel(EpiParams(**BASE), pop, FitSpec(start=START, fit_end=END))
    fr = m.fit(oc, od, theta0=np.array(theta0))
    p = m.unpack(fr.theta)
    d = fit_diagnostics(m, fr)
    return {"name": name, "seed": seed, "success": fr.success, "hessian_pd": fr.hessian_pd, "objective": fr.objective,
            "Rt": (p["m"] * 6.0).tolist(), "k_f": p["k_f"].tolist(), "delay_c": float(p["delay_c"]),
            "cov90_cases": d["cases"]["coverage90_in_sample"], "cov90_deaths": d["deaths"]["coverage90_in_sample"],
            "Rt_se": (fr.se()[: m.n_knots] if fr.cov is not None else np.full(m.n_knots, np.nan)).tolist(),
            "z": fr.theta[: m.n_knots].tolist()}


def main():
    rep3 = json.loads((ROOT / "docs/reports/3_calibration.json").read_text())
    th0 = rep3["countries"]["KOR"]["theta"]
    jobs = [("base", 0, th0), ("drop10", 1, th0), ("drop10", 2, th0), ("drop10", 3, th0), ("report70", 0, th0)]
    with ProcessPoolExecutor(4, mp_context=mp.get_context("forkserver")) as ex:
        res = list(ex.map(run, jobs))
    base = next(r for r in res if r["name"] == "base")
    knots = pd.date_range(START, END, freq="14D")
    rb = np.array(base["Rt"])
    rows = []
    for r in res:
        rt = np.array(r["Rt"])
        d = np.abs(rt - rb)
        after = knots[: rt.size] >= pd.Timestamp("2021-01-01")
        rows.append({**{k: r[k] for k in ("name", "seed", "success", "hessian_pd", "cov90_cases", "cov90_deaths", "delay_c")},
                     "Rt_mean_abs_diff": float(d.mean()), "Rt_max_abs_diff": float(d.max()),
                     "Rt_max_diff_knot": str(knots[int(d.argmax())].date()),
                     "Rt_mean_after_2021_ratio": float(rt[after].mean() / rb[after].mean()),
                     "kf_mean_ratio": float(np.mean(r["k_f"]) / np.mean(base["k_f"]))})
    out = {"results": res, "summary": rows}
    (ROOT / "docs/reports/9_sensitivity.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    L = ["# 9단계: 자료 결측·보고 편향 민감도 (자동 생성: scripts/report_stage9_sensitivity.py)", "",
         f"대한민국, {START} ~ {END}, 3단계와 같은 모형 (보고율 0.5 고정, R0_max 6). 기준 적합과 같은 시작값에서 다시 추정했다.",
         "drop10 은 관측 구간 10% 를 무작위로 뺀 자료, report70 은 2021-01-01 부터 확진을 0.7 배로 바꾼 **변형 자료** (실제 관측이 아니라 민감도 시험용).", "",
         "| 경우 | 시드 | 수렴 | 헤시안 PD | R_t 평균 절대 차이 | R_t 최대 차이 (구간) | 2021년 이후 평균 R_t 비 | 치명률 배율 평균 비 | 확진 90% 포함 | 사망 90% 포함 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['name']} | {r['seed']} | {r['success']} | {r['hessian_pd']} | {r['Rt_mean_abs_diff']:.3f} | "
                 f"{r['Rt_max_abs_diff']:.3f} ({r['Rt_max_diff_knot']}) | {r['Rt_mean_after_2021_ratio']:.3f} | {r['kf_mean_ratio']:.3f} | "
                 f"{r['cov90_cases']:.2f} | {r['cov90_deaths']:.2f} |")
    L += ["", "해석", "",
          "- 무작위 결측 10% 에 대한 R_t 변화가 작으면 (평균 절대 차이가 기준 적합의 표준오차 수준), 추정이 무작위 결측에 안정적이다.",
          "- 보고율이 0.7 배로 떨어진 변형 자료에서 R_t 의 일시적 하락과 치명률 배율 상승이 나타나면, 보고율 고정 모형이 검사 정책 변화를"
          " 전파·치명률 변화로 오인할 수 있다는 뜻이다 (식별 불가 문제, D-011). 실제 검사 정책 변화 시점 자료로 보고율을 따로 다뤄야 한다."]
    base_se = np.nanmean(base["Rt_se"])
    L.append(f"- 참고: 기준 적합의 z(로짓 R_t 비율) 표준오차 평균 {base_se:.3f}.")
    (ROOT / "docs/reports/9_sensitivity.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
