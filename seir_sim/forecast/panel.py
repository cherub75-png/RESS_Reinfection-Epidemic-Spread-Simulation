"""시간순 예측 검증용 국가별 일별 자료 묶음 (모두 실제 공개 자료, 원값 그대로).

열 (출처)
  cases, deaths      : JHU CSSE 누적의 차분 (명/일, 음수 = 소급 정정, 첫날 NaN)
  stringency         : OxCGRT StringencyIndex_Average (0~100, 국가 전체)
  mobility_work      : Google Community Mobility Reports (COVID-19 Open Data 경유) 직장 체류 변화 (%)
  vax_full_per100    : OWID people_fully_vaccinated / population * 100 (보고된 날만, 보간 없음)
  population         : OWID population (상수 1개, attrs)
결측은 결측 그대로 둔다. 특성 계산(ml.features)에서 앞 방향 채우기 등 처리 방식을 명시한다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..surveillance import sources as S

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data_raw"


def load_panel(iso3: str, raw: Path = RAW) -> pd.DataFrame:
    j = S.jhu_country(raw / "jhu_csse_global/time_series_covid19_confirmed_global.csv",
                      raw / "jhu_csse_global/time_series_covid19_deaths_global.csv", iso3)
    o = S.owid_country(raw / "owid_covid/owid-covid-data.csv", iso3, cols=["people_fully_vaccinated", "population"])
    x = S.oxcgrt_country(raw / "oxcgrt_national/OxCGRT_compact_national_v1.csv", iso3, cols=["StringencyIndex_Average"])
    iso2 = S.COUNTRIES[iso3][0]
    gpath = raw / ("gc19od_kr/KR.csv" if iso2 == "KR" else f"gc19od_countries/{iso2}.csv")
    g = S.gc19od_location(gpath)
    pop = float(o["population"].dropna().iloc[-1])
    idx = pd.date_range(j.index.min(), j.index.max(), freq="D")
    df = pd.DataFrame(index=idx)
    df["cases"] = j["new_cases"].reindex(idx)
    df["deaths"] = j["new_deaths"].reindex(idx)
    df["stringency"] = x["StringencyIndex_Average"].reindex(idx)
    df["mobility_work"] = pd.to_numeric(g["mobility_workplaces"], errors="coerce").reindex(idx) if "mobility_workplaces" in g else float("nan")
    df["vax_full_per100"] = (o["people_fully_vaccinated"] / pop * 100).reindex(idx)
    df.attrs.update({"iso3": iso3, "population": pop,
                     "sources": {"cases": "jhu_csse_global", "deaths": "jhu_csse_global", "stringency": "oxcgrt_national",
                                 "mobility_work": f"gc19od:{g.attrs['location']}", "vax_full_per100": "owid_covid",
                                 "population": "owid_covid"}})
    return df
