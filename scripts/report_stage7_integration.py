"""7단계 통합 점검: 3단계 추정 결과 -> 엔진 설정 -> 엔진 실행.

1) docs/reports/3_calibration.json 의 대한민국 추정값을 엔진 설정(configs/calibrated/KOR_2020-02-01_2021-10-31.yaml)으로 내보낸다.
2) 엔진 ODE(DOP853) 가 추정용 FastODE 궤적을 재현하는지, 관측 모형을 씌운 기대 확진이 3단계 적합과 같은지 확인한다.
3) 같은 설정을 하이브리드(확률) 엔진으로 30회 돌려 평균이 ODE 와 얼마나 가까운지 본다 (전국 단일 지역, 정수 초기값).
4) 시나리오 예시: 2020-11-15 ~ 2020-12-31 의 u 를 0.1 더 높였다면 (가정) — 예측이 아니라 가정에 따른 결과다.
출력: configs/calibrated/*.yaml, docs/reports/7_integration.md/.json
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")

from seir_sim.config.build import build_scenario                     # noqa: E402
from seir_sim.config.schema import Config                            # noqa: E402
from seir_sim.ensemble.runner import run_ensemble                    # noqa: E402
from seir_sim.inference.calibrate import FitSpec, SingleRegionModel  # noqa: E402
from seir_sim.inference.export import calibrated_config              # noqa: E402
from seir_sim.model.params import EpiParams                          # noqa: E402
from seir_sim.simulate.ode import integrate_ode                      # noqa: E402

START, END = "2020-02-01", "2021-10-31"
BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1, T1=1, Pmin=0.3, alpha=0.5, beta=0.3, lam=1 / 180, f1=0.01, M=8)


def main():
    rep3 = json.loads((ROOT / "docs" / "reports" / "3_calibration.json").read_text())
    kor = rep3["countries"]["KOR"]
    m = SingleRegionModel(EpiParams(**BASE), kor["population"], FitSpec(start=START, fit_end=END, rho=kor["rho"]))
    th = np.array(kor["theta"])
    assert kor["names"] == m.names
    prov = {"source": "docs/reports/3_calibration.json", "country": "KOR", "fit_period": [START, END],
            "objective": kor["objective"], "data": "JHU CSSE daily cases/deaths"}
    cfg_raw = calibrated_config(m, th, "KOR", "OWID population (2022 마지막 값)", prov)
    outdir = ROOT / "configs" / "calibrated"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"KOR_{START}_{END}.yaml"
    head = ("# 3단계 추정 결과로 만든 대한민국 재현 설정 (scripts/report_stage7_integration.py 가 생성)\n"
            "# u(t)·I0 는 추정값, 감염병 매개변수(sigma, gamma, P, T, f, lambda)는 1단계 가정값이다.\n"
            "# 관측 매개변수(보고율·지연·치명률 배율)는 meta.observation 에 기록만 하며 엔진 상태에는 들어가지 않는다.\n")
    path.write_text(head + yaml.safe_dump(cfg_raw, allow_unicode=True, sort_keys=False))
    cfg = Config.model_validate(cfg_raw)
    sc = build_scenario(cfg)
    tr = integrate_ode(sc.system, sc.X0, cfg.simulation.days, rtol=1e-10, atol=1e-8)
    par = m.unpack(th)
    inf, ons, dea, xe = m.fast.run(m.initial_state(par), m.fast.gc_from_u(m.u_days(par["m"], m.spec.n_fit_days)))
    L = m.layout
    rel_state = float(np.max(np.abs(xe - tr.X[-1])) / m.N)
    eng_deaths = np.diff(tr.X[:, 0, L.D])
    rel_deaths = float(np.max(np.abs(eng_deaths - dea[:, 0])) / max(dea.max(), 1))
    # 엔진 궤적에 관측 모형 -> 기대 확진 (발병 흐름은 E 총량 변화 + 감염 유입에서 얻지 않고 FastODE 와 비교만)
    ex = m.expected(par, m.spec.n_fit_days)
    out = {"config": str(path.relative_to(ROOT)), "max_rel_state_error_engine_vs_fastode": rel_state,
           "max_rel_daily_deaths_error": rel_deaths, "model_cases_total": float(ex["mu_cases"].sum()),
           "observed_cases_total_jhu": None}
    from seir_sim.surveillance import sources as S
    j = S.jhu_country(ROOT / "data_raw/jhu_csse_global/time_series_covid19_confirmed_global.csv",
                      ROOT / "data_raw/jhu_csse_global/time_series_covid19_deaths_global.csv", "KOR")
    out["observed_cases_total_jhu"] = float(j["new_cases"].loc[START:END].sum())
    # 3) 하이브리드 30회 (정수 초기값)
    cfg_h = Config.model_validate(calibrated_config(m, th, "KOR", "OWID population", prov, integer_seeds=True,
                                                    method="hybrid", n_runs=30))
    cfg_h.simulation.n_workers = 2
    res = run_ensemble(cfg_h)
    I_ode = tr.I_total
    s = res.summary()
    k = slice(30, None)
    out["hybrid"] = {"runs": 30, "wall_s": res.wall_seconds, "outbreak_probability": s["outbreak_probability"],
                     "median_rel_diff_mean_vs_ode_after_day30": float(np.median(np.abs(s["mean"][k] - I_ode[k]) / np.maximum(I_ode[k], 1))),
                     "extinct_runs": int(np.sum(res.I_total[:, -1] == 0))}
    # 4) 시나리오: 2020-11-15 ~ 2020-12-31 u + 0.1 (가정)
    d0 = (pd.Timestamp("2020-11-15") - pd.Timestamp(START)).days
    d1 = (pd.Timestamp("2021-01-01") - pd.Timestamp(START)).days
    raw = calibrated_config(m, th, "KOR", "OWID population", prov)
    ints = []
    for p in raw["interventions"]:
        a, b = p["start"], p["end"]
        for lo, hi, add in ((a, min(b, d0), 0), (max(a, d0), min(b, d1), 0.1), (max(a, d1), b, 0)):
            if hi > lo:
                ints.append({"start": lo, "end": hi, "value": float(min(1.0, p["value"] + add))})
    raw["interventions"] = ints
    sc2 = build_scenario(Config.model_validate(raw))
    tr2 = integrate_ode(sc2.system, sc2.X0, cfg.simulation.days)
    cum = lambda t: (t.X[0, 0, L.S] - t.X[:, 0, L.S])            # noqa: E731 (첫 감염 누적)
    dates = pd.date_range(START, periods=tr.t.size)
    at = (dates <= pd.Timestamp("2021-03-31"))
    out["scenario_u_plus_0.1_nov_dec_2020"] = {
        "label": "가정에 따른 결과 (예측 아님)",
        "first_infections_to_2021-03-31_base": float(cum(tr)[at][-1]),
        "first_infections_to_2021-03-31_scenario": float(cum(tr2)[at][-1]),
        "deaths_model_to_2021-03-31_base": float(tr.X[at][-1, 0, L.D]),
        "deaths_model_to_2021-03-31_scenario": float(tr2.X[at][-1, 0, L.D])}
    (ROOT / "docs" / "reports" / "7_integration.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    sc_ = out["scenario_u_plus_0.1_nov_dec_2020"]
    L_ = ["# 7단계 통합 점검 (자동 생성: scripts/report_stage7_integration.py)", "",
          f"- 내보낸 설정: `{out['config']}` (u(t) 14일 구간 {len(cfg.interventions)}개, I0 = {par['I0']:.1f})",
          f"- 엔진 ODE(DOP853, rtol 1e-10) 대 추정용 FastODE: 최종 상태 최대 오차 / 인구 = {rel_state:.2e}, 일별 사망 최대 상대 오차 = {rel_deaths:.2e}",
          f"- 관측 모형을 씌운 모형 기대 확진 합 {out['model_cases_total']:,.0f} 명, 같은 기간 JHU 관측 합 {out['observed_cases_total_jhu']:,.0f} 명 (3단계 적합 그대로)",
          f"- 하이브리드 엔진 30회 (정수 초기값, 작업자 2): {out['hybrid']['wall_s']:.1f} 초, 소멸한 실행 {out['hybrid']['extinct_runs']}회, "
          f"30일 이후 평균 I 와 ODE 의 상대 차이 중앙값 {out['hybrid']['median_rel_diff_mean_vs_ode_after_day30']:.3f}",
          "", "## 시나리오 예시 (가정에 따른 결과, 예측 아님)", "",
          "2020-11-15 ~ 2020-12-31 의 u 를 추정값보다 0.1 높였다고 가정하면 (다른 기간은 추정값 그대로):", "",
          "| 지표 (2021-03-31 까지, 모형 값) | 추정 u(t) | 가정 시나리오 |", "|---|---|---|",
          f"| 첫 감염 누적 (모형 실제 감염, 보고율 0.5 가정) | {sc_['first_infections_to_2021-03-31_base']:,.0f} | {sc_['first_infections_to_2021-03-31_scenario']:,.0f} |",
          f"| 모형 사망 (치명률 배율 적용 전) | {sc_['deaths_model_to_2021-03-31_base']:,.0f} | {sc_['deaths_model_to_2021-03-31_scenario']:,.0f} |",
          "", "한계: 전국 단일 지역이다. 시도별 확진은 2020-09-09 까지만 있어 시도별 u(t) 는 추정하지 않았다. "
          "시도 데이터셋(KOR_admin1)에 전국 u(t) 를 똑같이 적용한 실행은 시나리오일 뿐 시도별 재현이 아니다."]
    (ROOT / "docs" / "reports" / "7_integration.md").write_text("\n".join(L_) + "\n")
    print("\n".join(L_))


if __name__ == "__main__":
    main()
