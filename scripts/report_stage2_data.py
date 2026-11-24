"""2단계 자료 품질 보고서: 12개국 국가 단위 + 대한민국 17개 시도.

사용법: python -I scripts/report_stage2_data.py
출력:   docs/reports/2_data_quality.md, .json, docs/figures/2_kor_cases_sources.png
모든 수치는 data_raw/ 의 원자료(SHA-256 은 data_raw/manifest.json)에서 계산한다. 원자료 값은 바꾸지 않는다.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seir_sim.surveillance import quality as Q   # noqa: E402
from seir_sim.surveillance import sources as S   # noqa: E402

R = ROOT / "data_raw"
SIDO = ["11", "26", "27", "28", "29", "30", "31", "41", "42", "43", "44", "45", "46", "47", "48", "49", "50"]


def best_lag(a: pd.Series, b: pd.Series, lags=range(-3, 4)) -> dict:
    """b 를 k 일 밀었을 때 a 와의 일별 상관이 가장 큰 k (일별 발생 수)."""
    out = {}
    for k in lags:
        j = pd.concat([a.rename("a"), b.shift(k).rename("b")], axis=1).dropna()
        out[k] = float(j.a.corr(j.b)) if len(j) > 30 else np.nan
    k = max(out, key=lambda x: -np.inf if np.isnan(out[x]) else out[x])
    j = pd.concat([a.rename("a"), b.shift(k).rename("b")], axis=1).dropna()
    return {"best_lag_days": int(k), "corr_at_best": out[k], "corr_lag0": out[0],
            "exact_match_frac_at_best": float((j.a == j.b).mean())}


def countries():
    out = {}
    jc = R / "jhu_csse_global" / "time_series_covid19_confirmed_global.csv"
    jd = R / "jhu_csse_global" / "time_series_covid19_deaths_global.csv"
    owid = R / "owid_covid" / "owid-covid-data.csv"
    ox = R / "oxcgrt_national" / "OxCGRT_compact_national_v1.csv"
    for iso3, (iso2, _) in S.COUNTRIES.items():
        j = S.jhu_country(jc, jd, iso3)
        o = S.owid_country(owid, iso3)
        gpath = R / ("gc19od_kr" if iso2 == "KR" else "gc19od_countries") / f"{iso2}.csv"
        g = S.gc19od_location(gpath)
        x = S.oxcgrt_country(ox, iso3)
        rec = {
            "jhu_new_cases": Q.series_qc(j.new_cases), "jhu_new_deaths": Q.series_qc(j.new_deaths),
            "owid_new_cases": Q.series_qc(o.new_cases), "owid_new_deaths": Q.series_qc(o.new_deaths),
            "gc_new_confirmed": Q.series_qc(g.new_confirmed) if "new_confirmed" in g else None,
            "cmp_cum_cases_jhu_vs_gc": Q.compare_series(j.cum_cases, g.cumulative_confirmed) if "cumulative_confirmed" in g else None,
            "cmp_cum_cases_jhu_vs_owid": Q.compare_series(j.cum_cases, o.new_cases.fillna(0).cumsum()),
            "lag_daily_cases_jhu_vs_gc": best_lag(j.new_cases, g.new_confirmed) if "new_confirmed" in g else None,
            "hosp_patients_days": int(o.hosp_patients.notna().sum()), "icu_patients_days": int(o.icu_patients.notna().sum()),
            "new_tests_days": int(o.new_tests.notna().sum()),
            "people_vaccinated_first": str(o.people_vaccinated.dropna().index.min().date()) if o.people_vaccinated.notna().any() else None,
            "oxcgrt_stringency_days": int(x.StringencyIndex_Average.notna().sum()),
            "oxcgrt_range": [str(x.index.min().date()), str(x.index.max().date())],
            "gc_weather_days": int(g.average_temperature_celsius.notna().sum()) if "average_temperature_celsius" in g else 0,
            "gc_mobility_days": int(g.mobility_workplaces.notna().sum()) if "mobility_workplaces" in g else 0,
            "population_owid": float(o.population.dropna().iloc[-1]) if o.population.notna().any() else None,
            "population_gc": float(g.population.dropna().iloc[0]) if g.population.notna().any() else None,
        }
        out[iso3] = rec
    return out


def korea_sido():
    nat = S.gc19od_location(R / "gc19od_kr" / "KR.csv")
    jhu = S.jhu_country(R / "jhu_csse_global" / "time_series_covid19_confirmed_global.csv",
                        R / "jhu_csse_global" / "time_series_covid19_deaths_global.csv", "KOR")
    frames, rows = {}, []
    for c in SIDO:
        g = S.gc19od_location(R / "gc19od_kr" / f"KR_{c}.csv")
        frames[c] = g
        q = Q.series_qc(g.new_confirmed)
        rows.append({"key": f"KR_{c}", "name": str(g.subregion1_name.iloc[0]), "population": float(g.population.iloc[0]),
                     "area_sq_km": float(g.area_sq_km.iloc[0]),
                     "cases_first": q.get("first_date"), "cases_last": q.get("last_date"), "cases_total": q.get("total"),
                     "cases_negative_days": q.get("n_negative"),
                     "weather_days": int(g.average_temperature_celsius.notna().sum()),
                     "rh_days": int(g.relative_humidity.notna().sum())})
    # 날짜별로 값이 있는 시도만 더한다 (빈 값 = 그 시도의 보고 없음). 모든 시도가 비면 빈 값.
    sido_sum = pd.concat([f.new_confirmed for f in frames.values()], axis=1).sum(axis=1, min_count=1)
    start, end = "2020-01-24", "2020-09-09"
    s = sido_sum.loc[start:end]
    natc = nat.new_confirmed.loc[start:end]
    pop_sum = sum(r["population"] for r in rows)
    wb = {}
    with open(R / "wb_population" / "population.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["Country Code"] == "KOR" and r["Year"] in ("2019", "2020", "2021"):
                wb[r["Year"]] = float(r["Value"])
    # Natural Earth 시도 id 와 대응 (KR_11 <-> KR-11)
    import json as js
    ne = js.load(open(R / "ne_admin1_10m" / "ne_10m_admin_1_states_provinces.geojson"))
    ne_ids = sorted(f["properties"]["iso_3166_2"] for f in ne["features"] if f["properties"].get("adm0_a3") == "KOR")
    gc_ids = sorted("KR-" + c for c in SIDO)
    return {
        "sido": rows,
        "period_with_sido_cases": [start, end],
        "sum_sido_cases": float(s.sum()), "national_cases_gc_same_period": float(natc.sum()),
        "national_cases_jhu_same_period": float(jhu.new_cases.loc[start:end].sum()),
        "sido_sum_over_national_gc": float(s.sum() / natc.sum()),
        "daily_corr_sido_sum_vs_national_gc": float(pd.concat([s, natc], axis=1).dropna().corr().iloc[0, 1]),
        "population_sum_sido_gc": pop_sum, "population_national_gc": float(nat.population.iloc[0]),
        "population_worldbank": wb,
        "id_match_natural_earth": {"missing_in_ne": sorted(set(gc_ids) - set(ne_ids)),
                                   "extra_in_ne": sorted(set(ne_ids) - set(gc_ids))},
    }, sido_sum, nat, jhu


def figure(sido_sum, nat, jhu, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from seir_sim.viz.plots import INK, INK_2, SURFACE, _font, _style
    ko = _font()
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.2), dpi=150, facecolor=SURFACE)
    ax = axes[0]
    _style(ax)
    ax.plot(jhu.new_cases.loc[:"2022-09-13"], color="#2a78d6", lw=1.0, label="JHU (KCDC 발표 누적의 차분)")
    ax.plot(nat.new_confirmed, color="#eb6834", lw=1.0, alpha=0.8, label="Google Open Data (국가)")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_title("대한민국 일별 확진 (출처별, 원자료)" if ko else "Korea daily cases by source", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)
    ax = axes[1]
    _style(ax)
    a, b = sido_sum.loc["2020-01-24":"2020-09-09"], nat.new_confirmed.loc["2020-01-24":"2020-09-09"]
    ax.plot(b, color="#eb6834", lw=1.2, label="국가 (Google)")
    ax.plot(a, color="#1baf7a", lw=1.2, label="17개 시도 합 (Google, 원출처 Wikipedia 집계)")
    ax.set_title("시도 합 vs 국가 (2020-01-24 ~ 2020-09-09)" if ko else "Sum of provinces vs national", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main():
    rep = {"countries": countries()}
    kr, sido_sum, nat, jhu = korea_sido()
    rep["korea_sido"] = kr
    man = json.loads((R / "manifest.json").read_text())
    rep["inputs"] = {k: {"status": v["status"], "version": v["version"], "retrieved_utc": v["retrieved_utc"],
                         "files": [{"path": f.get("path"), "sha256": f.get("sha256")} for f in v["files"]]}
                     for k, v in man.items() if k in ("owid_covid", "jhu_csse_global", "oxcgrt_national", "gc19od_kr",
                                                      "gc19od_countries", "wb_population", "ne_admin1_10m")}
    out = ROOT / "docs" / "reports"
    (out / "2_data_quality.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str))
    figure(sido_sum, nat, jhu, ROOT / "docs" / "figures" / "2_kor_cases_sources.png")

    L = ["# 2단계 자료 품질 보고 (자동 생성: scripts/report_stage2_data.py)", "",
         "원자료는 바꾸지 않았다. 출처·SHA-256: `docs/DATA_SOURCES.md`, `data_raw/manifest.json`.", "",
         "## 1. 국가별 일별 확진 (JHU CSSE: KCDC 등 각국 발표의 누적 차분)", "",
         "| 국가 | 기간 | 음수일 | 0 비율 | 주간 보고 | 급증일 | 요일 비 (월~일) | OWID 주간 보고 | JHU↔Google 누적 중앙 차이 | JHU↔Google 최적 지연 (상관) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for iso3, r in rep["countries"].items():
        q, qo = r["jhu_new_cases"], r["owid_new_cases"]
        wr = " ".join("-" if v is None else f"{v:.2f}" for v in q["weekday_ratio"].values())
        cg = r["cmp_cum_cases_jhu_vs_gc"]
        lg = r["lag_daily_cases_jhu_vs_gc"]
        L.append(f"| {iso3} | {q['first_date']}~{q['last_date']} | {q['n_negative']} | {q['zero_frac']:.2f} | "
                 f"{'예' if q['weekly_reporting'] else '아니오'} | {q['n_spikes']} | {wr} | {'예' if qo['weekly_reporting'] else '아니오'} | "
                 f"{(cg or {}).get('median_rel_diff', float('nan')):.3f} | "
                 f"{lg['best_lag_days'] if lg else '-'} ({(lg or {}).get('corr_at_best', float('nan')):.2f}) |")
    L += ["", "## 2. 국가별 보조 자료 (일수)", "",
          "| 국가 | 입원 | 중환자 | 검사 | 첫 백신 | OxCGRT 정책 | Google 기상 | Google 이동 | 인구 (OWID) | 인구 (Google) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for iso3, r in rep["countries"].items():
        L.append(f"| {iso3} | {r['hosp_patients_days']} | {r['icu_patients_days']} | {r['new_tests_days']} | {r['people_vaccinated_first']} | "
                 f"{r['oxcgrt_stringency_days']} | {r['gc_weather_days']} | {r['gc_mobility_days']} | "
                 f"{r['population_owid']:.4g} | {r['population_gc']:.4g} |")
    k = rep["korea_sido"]
    L += ["", "## 3. 대한민국 시도 (Google Open Data; 시도 확진의 원출처는 Wikipedia 의 KCDC 브리핑 집계 = 2차 자료)", "",
          f"- 시도 확진이 있는 기간: {k['period_with_sido_cases'][0]} ~ {k['period_with_sido_cases'][1]} (그 뒤로는 시도 확진 없음)",
          f"- 같은 기간 17개 시도 합 {k['sum_sido_cases']:.0f} 명 / 국가 {k['national_cases_gc_same_period']:.0f} 명 "
          f"(비 {k['sido_sum_over_national_gc']:.3f}, 일별 상관 {k['daily_corr_sido_sum_vs_national_gc']:.3f}). "
          "차이는 시도에 배정되지 않은 검역(해외 유입) 확진으로 추정되나, 원자료에 범주가 없어 확인하지 못했다.",
          f"- 인구: 시도 합 {k['population_sum_sido_gc']:.0f}, 국가(Google) {k['population_national_gc']:.0f}, "
          f"World Bank {', '.join(f'{y}: {v:.0f}' for y, v in k['population_worldbank'].items())}",
          f"- Natural Earth 시도 id 대응: 없는 id {k['id_match_natural_earth']['missing_in_ne']}, 남는 id {k['id_match_natural_earth']['extra_in_ne']}",
          "", "| 키 | 이름 | 인구 (Google) | 면적 km² | 확진 합 | 확진 기간 | 기상 일수 | 상대습도 일수 |", "|---|---|---|---|---|---|---|---|"]
    for r in k["sido"]:
        L.append(f"| {r['key']} | {r['name']} | {r['population']:.0f} | {r['area_sq_km']:.0f} | {r['cases_total']:.0f} | "
                 f"{r['cases_first']}~{r['cases_last']} | {r['weather_days']} | {r['rh_days']} |")
    L += ["", "그림: `docs/figures/2_kor_cases_sources.png`"]
    (out / "2_data_quality.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore")
    main()
