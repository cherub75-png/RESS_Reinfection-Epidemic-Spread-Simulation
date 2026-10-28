"""ML 특성 (기점 s 의 특성은 s 일까지의 자료로만 만든다).

모든 연산은 뒤쪽 창(rolling, shift(+k), 앞 방향 채우기)이다. tests/test_forecast.py 가 "s 이후 자료를 잘라낸 표로
다시 계산해도 같은 값" 임을 확인한다 (누설 검사).

특성 (국가 식별자는 넣지 않는다: 국가 공통 모형이 특정 국가를 외우지 않게 하기 위함)
  lc0..lc3   log(1 + 7일 확진 합) 끝날 s, s-7, s-14, s-21
  gc1..gc3   주간 로그 변화 (lc0-lc1, lc1-lc2, lc2-lc3)
  inc        lc0 - log(인구 / 1e5)          (10만 명당 주간 확진의 로그)
  cum        log(1 + 누적 확진 / 인구 * 1e3) (누적 감염의 대리값; 보고율 차이를 반영하지 못함)
  ld0, gd1   log(1 + 7일 사망 합), 주간 로그 변화
  dinc       ld0 - log(인구 / 1e6)
  dc_ratio   ld0 - lc2 (2주 전 확진 대비 사망)
  string, dstring    OxCGRT 엄격도 (s 까지 마지막 보고값, 최대 7일 앞 방향 채우기), 14일 변화
  mob, dmob          Google 직장 이동 7일 평균 (최소 4일), 14일 변화
  vax                완전 접종 / 100명 (마지막 보고값 앞 방향 채우기; 2020-12-01 이전은 0 = 접종 사업 전,
                     그 뒤 첫 보고 전은 결측)
  h          예측 주 (1..4)
결측은 그대로 둔다 (HistGradientBoosting 이 결측을 직접 다룬다).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..forecast.targets import rolling7

FEATURES = ["lc0", "lc1", "lc2", "lc3", "gc1", "gc2", "gc3", "inc", "cum", "ld0", "gd1", "dinc", "dc_ratio",
            "string", "dstring", "mob", "dmob", "vax"]
VAX_PROGRAMME_START = pd.Timestamp("2020-12-01")


def daily_features(panel: pd.DataFrame) -> pd.DataFrame:
    """각 날짜 s 의 특성 (s 까지 자료만 사용)."""
    pop = panel.attrs["population"]
    c7 = rolling7(panel["cases"])
    d7 = rolling7(panel["deaths"])
    f = pd.DataFrame(index=panel.index)
    lc = np.log1p(c7)
    for k in range(4):
        f[f"lc{k}"] = lc.shift(7 * k)
    f["gc1"], f["gc2"], f["gc3"] = f.lc0 - f.lc1, f.lc1 - f.lc2, f.lc2 - f.lc3
    f["inc"] = f.lc0 - np.log(pop / 1e5)
    cum = panel["cases"].clip(lower=0).fillna(0).cumsum()
    f["cum"] = np.log1p(cum / pop * 1e3)
    ld = np.log1p(d7)
    f["ld0"] = ld
    f["gd1"] = ld - ld.shift(7)
    f["dinc"] = ld - np.log(pop / 1e6)
    f["dc_ratio"] = ld - f.lc2
    st = panel["stringency"].ffill(limit=7)
    f["string"] = st
    f["dstring"] = st - st.shift(14)
    mob = panel["mobility_work"].rolling(7, min_periods=4).mean()
    f["mob"] = mob
    f["dmob"] = mob - mob.shift(14)
    vax = panel["vax_full_per100"].ffill()
    vax[panel.index < VAX_PROGRAMME_START] = 0.0
    f["vax"] = vax
    return f[FEATURES]


def training_rows(feat: pd.DataFrame, c7: pd.Series, origin, first_day="2020-03-01", horizons=(1, 2, 3, 4),
                  base: str = "lc0") -> pd.DataFrame:
    """기점 origin 에 쓸 학습 행: s + 7h <= origin 인 (s, h) (대상이 기점까지 관측된 것만).
    목표 = log(1 + 7일 합(s + 7h)) - base(s).  확진은 c7 = 확진 7일 합, base = lc0; 사망은 사망 7일 합, base = ld0."""
    origin = pd.Timestamp(origin)
    lc = np.log1p(c7)
    rows = []
    for h in horizons:
        s_idx = feat.index[(feat.index >= pd.Timestamp(first_day)) & (feat.index + pd.Timedelta(days=7 * h) <= origin)]
        if s_idx.empty:
            continue
        X = feat.loc[s_idx].copy()
        X["h"] = h
        X["target"] = lc.reindex(s_idx + pd.Timedelta(days=7 * h)).to_numpy() - X[base].to_numpy()
        X["s"] = s_idx
        rows.append(X)
    if not rows:
        return pd.DataFrame(columns=FEATURES + ["h", "target", "s"])
    out = pd.concat(rows)
    return out[np.isfinite(out["target"]) & np.isfinite(out[base])]


def origin_rows(feat: pd.DataFrame, origin, horizons=(1, 2, 3, 4)) -> pd.DataFrame:
    origin = pd.Timestamp(origin)
    X = pd.concat([feat.loc[[origin]].assign(h=h) for h in horizons])
    return X
