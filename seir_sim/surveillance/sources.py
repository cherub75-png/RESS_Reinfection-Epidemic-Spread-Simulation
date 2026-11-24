"""출처별 로더. 모두 날짜(DatetimeIndex) 를 색인으로 하는 DataFrame 을 돌려주고, attrs 에 출처를 남긴다.

값은 원자료 그대로이다 (단위: 명/일, 누적은 명). 처리하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# 비교 국가 코드표 (ISO3, ISO2, JHU 이름, OxCGRT 코드)
COUNTRIES = {
    "KOR": ("KR", "Korea, South"), "JPN": ("JP", "Japan"), "NZL": ("NZ", "New Zealand"),
    "AUS": ("AU", "Australia"), "GBR": ("GB", "United Kingdom"), "DEU": ("DE", "Germany"),
    "ITA": ("IT", "Italy"), "USA": ("US", "US"), "BRA": ("BR", "Brazil"), "IND": ("IN", "India"),
    "ZAF": ("ZA", "South Africa"), "SWE": ("SE", "Sweden"),
}


def _attrs(df: pd.DataFrame, **kw) -> pd.DataFrame:
    df.attrs.update(kw)
    return df


def jhu_country(confirmed_csv: str | Path, deaths_csv: str | Path, iso3: str) -> pd.DataFrame:
    """JHU CSSE 누적 시계열 -> 국가 일별 (하위 지역 합). new_* 는 누적의 차분 (음수 그대로)."""
    name = COUNTRIES[iso3][1]
    out = {}
    for key, path in (("cases", confirmed_csv), ("deaths", deaths_csv)):
        raw = pd.read_csv(path)
        rows = raw[raw["Country/Region"] == name]
        if rows.empty:
            raise ValueError(f"JHU 에 {name} 가 없다")
        if iso3 in ("GBR",):            # 해외 영토 제외: 본토만
            rows = rows[rows["Province/State"].isna()]
        cum = rows.iloc[:, 4:].sum(axis=0)
        cum.index = pd.to_datetime(cum.index, format="%m/%d/%y")
        out[f"cum_{key}"] = cum.astype(float)
        out[f"new_{key}"] = cum.diff().astype(float)
    df = pd.DataFrame(out)
    return _attrs(df, source="jhu_csse_global", location=iso3, note="new_* = 누적 차분 (첫날 NaN, 음수는 정정)")


OWID_COLS = ["new_cases", "new_deaths", "hosp_patients", "icu_patients", "new_tests", "positive_rate",
             "people_vaccinated", "people_fully_vaccinated", "total_boosters", "stringency_index", "population"]


def owid_country(csv: str | Path, iso3: str, cols=OWID_COLS) -> pd.DataFrame:
    raw = pd.read_csv(csv, usecols=["iso_code", "date", *cols], low_memory=False)
    df = raw[raw["iso_code"] == iso3].drop(columns="iso_code")
    df.index = pd.to_datetime(df.pop("date"))
    return _attrs(df.astype(float), source="owid_covid", location=iso3)


OXCGRT_COLS = ["StringencyIndex_Average", "ContainmentHealthIndex_Average", "GovernmentResponseIndex_Average",
               "C1M_School closing", "C2M_Workplace closing", "C4M_Restrictions on gatherings",
               "C6M_Stay at home requirements", "C8EV_International travel controls", "H6M_Facial Coverings"]


def oxcgrt_country(csv: str | Path, iso3: str, cols=OXCGRT_COLS) -> pd.DataFrame:
    raw = pd.read_csv(csv, usecols=["CountryCode", "Jurisdiction", "Date", *cols], low_memory=False)
    df = raw[(raw["CountryCode"] == iso3) & (raw["Jurisdiction"] == "NAT_TOTAL")].drop(columns=["CountryCode", "Jurisdiction"])
    df.index = pd.to_datetime(df.pop("Date").astype(str), format="%Y%m%d")
    return _attrs(df.astype(float), source="oxcgrt_national", location=iso3)


GC_EPI = ["new_confirmed", "new_deceased", "cumulative_confirmed", "cumulative_deceased", "new_tested"]
GC_WEATHER = ["average_temperature_celsius", "minimum_temperature_celsius", "maximum_temperature_celsius",
              "rainfall_mm", "dew_point", "relative_humidity"]
GC_MOBILITY = ["mobility_retail_and_recreation", "mobility_grocery_and_pharmacy", "mobility_parks",
               "mobility_transit_stations", "mobility_workplaces", "mobility_residential"]
GC_STATIC = ["population", "area_sq_km", "latitude", "longitude", "subregion1_name", "country_name"]


def gc19od_location(csv: str | Path) -> pd.DataFrame:
    """Google COVID-19 Open Data v3 위치별 통합 표. 있는 열만 남긴다."""
    raw = pd.read_csv(csv, low_memory=False)
    keep = [c for c in ["location_key", *GC_EPI, *GC_WEATHER, *GC_MOBILITY, *GC_STATIC] if c in raw.columns]
    df = raw[["date", *keep]].copy()
    df.index = pd.to_datetime(df.pop("date"))
    key = str(df["location_key"].iloc[0])
    return _attrs(df, source="gc19od", location=key)


def first_valid(s: pd.Series):
    v = s.dropna()
    return v.iloc[0] if len(v) else np.nan
