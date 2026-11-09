"""WHO FluNet 주간 인플루엔자 실험실 자료 -> 계열(국가 x 감시 체계)별 주간 검사 수·양성 수·양성률.

통합 규칙 (docs/reports/11_influenza_protocol.md 1절, 결과 전에 고정)
  R1 완전 중복 행은 하나만 남긴다.
  R2 계열 = (COUNTRY_CODE, ORIGIN_SOURCE). 감시 체계를 합치거나 잇지 않는다.
  R3 검사 수 n = SPEC_PROCESSED_NB (결측 아님, > 0, >= INF_ALL 일 때만). 양성 x = INF_ALL.
     n 이 있고 INF_ALL 이 비면, INF_NEGATIVE == n 일 때만 x = 0, 아니면 결측.
  R4 양성률은 특성에는 n >= 10, 정답에는 n >= 20 인 주만 (상수 MIN_TESTS_FEATURE, MIN_TESTS_TARGET).
  R5 주 = ISO 주 (월요일 시작). 영국 4개 지역(X09~X12)의 국가 코드는 GBR 로 기록한다 (기후 특성용).
양성 수는 감염자 수가 아니다: 검사량과 감시 체계에 좌우되는 실험실 확인 건수다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MIN_TESTS_FEATURE = 10
MIN_TESTS_TARGET = 20
UK_PARTS = {"X09": "GBR", "X10": "GBR", "X11": "GBR", "X12": "GBR"}
COLS = ["COUNTRY_CODE", "COUNTRY_AREA_TERRITORY", "ORIGIN_SOURCE", "ISO_WEEKSTARTDATE", "HEMISPHERE", "ITZ",
        "SPEC_PROCESSED_NB", "INF_A", "INF_B", "INF_ALL", "INF_NEGATIVE"]


def load_flunet(path: str | Path) -> pd.DataFrame:
    """정리된 긴 표: series, country, iso3, source, name, hemisphere, itz, week, tests, pos (결측 = NaN)."""
    raw = pd.read_csv(path, usecols=COLS, low_memory=False)
    n_raw = len(raw)
    d = raw.drop_duplicates().copy()                                              # R1
    d["week"] = pd.to_datetime(d["ISO_WEEKSTARTDATE"])
    if not (d["week"].dt.dayofweek == 0).all():
        raise ValueError("ISO 주 시작일이 월요일이 아닌 행이 있다")
    n = d["SPEC_PROCESSED_NB"]
    x = d["INF_ALL"]
    ok = n.notna() & (n > 0) & (x.isna() | (n >= x))                             # R3
    tests = n.where(ok)
    pos = x.where(tests.notna())
    zero = tests.notna() & x.isna() & (d["INF_NEGATIVE"] == tests)
    pos = pos.where(~zero, 0.0)
    pos = pos.where(pos.notna() | zero)
    tests = tests.where(pos.notna())                                              # 양성 수를 모르면 그 주는 쓰지 않음
    out = pd.DataFrame({"series": d["COUNTRY_CODE"] + "|" + d["ORIGIN_SOURCE"], "country": d["COUNTRY_CODE"],
                        "iso3": d["COUNTRY_CODE"].replace(UK_PARTS), "source": d["ORIGIN_SOURCE"],
                        "name": d["COUNTRY_AREA_TERRITORY"], "hemisphere": d["HEMISPHERE"], "itz": d["ITZ"],
                        "week": d["week"], "tests": tests.astype(float), "pos": pos.astype(float)})
    if out.duplicated(["series", "week"]).any():
        raise ValueError("중복 제거 뒤에도 같은 (계열, 주) 가 여러 행이다 (값이 다른 중복)")
    out = out.sort_values(["series", "week"]).reset_index(drop=True)
    out.attrs.update({"rows_raw": n_raw, "rows_after_dedup": len(d), "exact_duplicates_removed": n_raw - len(d),
                      "invalid_tests_rows": int((n.notna() & ~ok).sum())})
    return out


def select_series(df: pd.DataFrame, start: str = "2021-09-27", end: str = "2022-09-19",
                  min_coverage: float = 0.8, min_median_tests: float = 50.0) -> list[str]:
    """시험 직전 1년의 자료 품질만으로 계열을 고른다 (규약 2절과 변경 기록): 검사 수가 있는 주 비율과 주간 검사 수 중앙값."""
    weeks = pd.date_range(start, end, freq="7D")
    w = df[(df["week"] >= weeks[0]) & (df["week"] <= weeks[-1])]
    out = []
    for s, g in w.groupby("series"):
        t = g.set_index("week")["tests"].reindex(weeks)
        if t.notna().mean() >= min_coverage and t.median() >= min_median_tests:
            out.append(s)
    return sorted(out)


def wide(df: pd.DataFrame, series: list[str], start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(검사 수, 양성 수) 의 [주 x 계열] 표. 빠진 주는 NaN."""
    weeks = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="7D")
    if (weeks.dayofweek != 0).any():
        raise ValueError("start 는 월요일이어야 한다")
    d = df[df["series"].isin(series)]
    T = d.pivot(index="week", columns="series", values="tests").reindex(index=weeks, columns=series)
    X = d.pivot(index="week", columns="series", values="pos").reindex(index=weeks, columns=series)
    return T, X


def positivity(tests, pos, min_tests: int):
    """양성률 (검사 수가 min_tests 미만이면 NaN)."""
    t = np.asarray(tests, float)
    x = np.asarray(pos, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = x / t
    return np.where(t >= min_tests, p, np.nan)


def logit_positivity(tests, pos, min_tests: int):
    """logit((x + 0.5) / (n + 1)) (검사 수가 min_tests 미만이면 NaN)."""
    t = np.asarray(tests, float)
    x = np.asarray(pos, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = (x + 0.5) / (t + 1.0)
        z = np.log(p / (1 - p))
    return np.where(t >= min_tests, z, np.nan)


def series_meta(df: pd.DataFrame) -> pd.DataFrame:
    """계열별 이름·국가·반구·전파 구역 (마지막 행 기준)."""
    return df.groupby("series")[["country", "iso3", "source", "name", "hemisphere", "itz"]].last()
