"""인플루엔자 최신 자료 예측 (docs/reports/11_influenza_protocol.md 8절).

기점 = 선택 계열의 절반 이상이 검사 수를 보고한 가장 최근 주의 바로 전 주 (그 주는 덜 보고되어 있음).
기점 뒤의 자료는 쓰지 않는다. 방법: persistence, seasonal, ml_cal (검증과 같은 ML·같은 보정 규칙).
구간 보정의 보정 표본 = 검증 실행(outputs/flu/forecasts.parquet)의 ml 예측 중 기점 전 52주, 대상 주 <= 기점인 것.
seir (보조) 는 규약 7절 계열에만, 요청할 때 계산한다 (적합 1회 약 20초).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from ..surveillance import flunet as F
from . import flu as FL
from .metrics import QUANTILES

ROOT = Path(__file__).resolve().parents[2]
QC = [f"q{k}" for k in range(QUANTILES.size)]


def operational_origin(df: pd.DataFrame, series: list[str]) -> pd.Timestamp:
    n = df[df["series"].isin(series) & df["tests"].notna()].groupby("week")["series"].nunique()
    latest = n[n >= len(series) / 2].index.max()
    return latest - pd.Timedelta(weeks=1)


def latest_flu_forecast(with_seir: bool = False, log=lambda m: None) -> dict:
    from ..data.boundaries import load_admin0
    from ..ml.quantile import ML_PARAMS, fit_quantile_models, predict_quantiles
    raw = ROOT / "data_raw" / "who_flunet" / "VIW_FNT.csv"
    man = json.loads((ROOT / "data_raw" / "manifest.json").read_text()).get("who_flunet", {})
    df = F.load_flunet(raw)
    series = F.select_series(df)
    origin = operational_origin(df, series)
    data_last = df["week"].max()
    df = df[df["week"] <= origin]                                               # 기점 뒤 자료는 쓰지 않는다
    geo = load_admin0(ROOT / "data_raw" / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson")
    lat = dict(zip(geo.ids, geo.lat))
    cp = ROOT / "data_processed" / "climate" / "era5_weekly_countries.parquet"
    climate = pd.read_parquet(cp) if cp.exists() else None
    if climate is not None:
        climate = climate[climate["week"] <= origin]
    log(f"기점 {origin.date()}, 계열 {len(series)}개: 특성 만들기")
    data = FL.FluData(df, series, start="2009-01-05", end=str(origin.date()), lat=lat, climate=climate)
    tab = FL.feature_table(data, climate=climate is not None)
    cols = FL.feature_list(climate is not None)
    train = tab[(tab["target_week"] <= origin) & tab["target"].notna()]
    log(f"ML 학습 ({len(train)}행)")
    models = fit_quantile_models(train[cols], train["target"].to_numpy(), ML_PARAMS)
    X = tab[tab["week"] == origin]
    Z = predict_quantiles(models, X[cols])
    delta, cal_n = _calibration_shift(origin)
    i = data.index(origin)
    out = {"kind": "influenza_latest_forecast", "origin": str(origin.date()), "data_last_week": str(data_last.date()),
           "retrieved_utc": man.get("retrieved_utc"), "source": "WHO FluNet (GISRS)", "run_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "target_weeks": [str((origin + pd.Timedelta(weeks=h)).date()) for h in FL.HORIZONS], "quantiles": QUANTILES.tolist(),
           "calibration": {"rows": cal_n, "applied": bool(delta is not None)}, "climate_features": climate is not None,
           "warnings": [], "series": []}
    if delta is None:
        out["warnings"].append("구간 보정 표본이 부족해 ML 구간을 보정하지 않았다 (검증 실행 결과 필요).")
    if climate is not None and climate["era5t_samples"].max() > 0:
        out["warnings"].append("최근 기후 특성에 ERA5T 예비판 자료가 들어 있다.")
    for k, s in enumerate(series):
        m = data.meta.loc[s]
        hist_w = data.weeks[max(0, i - 103): i + 1]
        hist = data.pt[max(0, i - 103): i + 1, k]
        tests = data.tests[:, k]
        med8 = np.nanmedian(tests[max(0, i - 8): i]) if i > 0 else np.nan
        warn = []
        if not np.isfinite(tests[i]):
            warn.append("기점 주 자료 없음")
        elif np.isfinite(med8) and tests[i] < 0.5 * med8:
            warn.append("기점 주 미완성 가능 (검사 수가 직전 8주 중앙값의 50% 미만)")
        row = {"series": s, "name": m["name"], "iso3": m["iso3"], "source": m["source"], "hemisphere": m["hemisphere"],
               "last_tests": None if not np.isfinite(tests[i]) else float(tests[i]),
               "history": {"weeks": [str(w.date()) for w in hist_w], "positivity": [None if not np.isfinite(v) else float(v) for v in hist]},
               "methods": {}, "warnings": warn}
        for name in ("persistence", "seasonal"):
            q = data.seasonal(k, i) if name == "seasonal" else data.baseline(k, i, name)
            if q is not None:
                row["methods"][name] = q.tolist()
        xr = X[X["series"] == s]
        if len(xr):
            zz = Z[np.flatnonzero((X["series"] == s).to_numpy())]
            order = np.argsort(xr["h"].to_numpy())
            zz = zz[order]
            row["methods"]["ml"] = expit(zz).tolist()
            if delta is not None:
                zc = np.sort(zz + np.array([delta[h] for h in FL.HORIZONS]), axis=1)
                row["methods"]["ml_cal"] = expit(zc).tolist()
        out["series"].append(row)
    if with_seir:
        _add_seir(out, df, data, origin, log)
    vp = ROOT / "docs" / "reports" / "11_influenza_validation.json"
    if vp.exists():
        v = json.loads(vp.read_text())
        out["validation"] = {h: {m: v["main"][h][m]["rel_wis"] for m in ("seasonal", "ml", "ml_cal")} | {"n": v["main"][h]["n"]}
                             for h in v["main"]}
    return out


def _calibration_shift(origin: pd.Timestamp, window_weeks: int = 52, min_rows: int = 300):
    """예측 주별 분위수 이동 delta[h] (logit 척도). 검증 실행의 ml 예측 중 기점 전 52주·대상 주 <= 기점인 것."""
    p = ROOT / "outputs" / "flu" / "forecasts.parquet"
    if not p.exists():
        return None, 0
    fc = pd.read_parquet(p)
    fc = fc[(fc["method"] == "ml") & np.isfinite(fc["truth"])]
    cal = fc[(fc["origin"] < origin) & (fc["origin"] >= origin - pd.Timedelta(weeks=window_weeks)) & (fc["target_week"] <= origin)]
    to_z = lambda v: logit(np.clip(v, 1e-3, 1 - 1e-3))                    # noqa: E731
    delta, n = {}, {}
    for h in FL.HORIZONS:
        c = cal[cal["h"] == h]
        n[h] = len(c)
        if len(c) < min_rows:
            return None, n
        zt, Zq = to_z(c["truth"].to_numpy()), to_z(c[QC].to_numpy())
        delta[h] = np.array([np.quantile(zt - Zq[:, j], QUANTILES[j]) for j in range(QUANTILES.size)])
    return delta, n


def _add_seir(out: dict, df: pd.DataFrame, data, origin, log):
    from ..inference.flu_seir import WINDOW_WEEKS, FluPositivityModel
    subset = ["KOR|SENTINEL", "USA|SENTINEL", "NOR|NONSENTINEL", "ESP|SENTINEL", "JPN|SENTINEL", "SGP|SENTINEL",
              "AUS|NOTDEFINED", "CHL|NONSENTINEL", "BRA|NONSENTINEL", "ZAF|SENTINEL"]
    wb = pd.read_csv(ROOT / "data_processed" / "tables" / "wb_population_api.csv").sort_values("Year").groupby("Country Code").last()
    i = data.index(origin)
    for row in out["series"]:
        s = row["series"]
        if s not in subset:
            continue
        k = data.series.index(s)
        x, n = data.pos[i - WINDOW_WEEKS + 1: i + 1, k], data.tests[i - WINDOW_WEEKS + 1: i + 1, k]
        log(f"SEIR {s}")
        m = FluPositivityModel(float(wb.loc[row["iso3"], "Value"]), x, n)
        fr = m.fit()
        S = m.predictive(fr, np.nanmedian(n[-4:]), n_samples=300)
        row["methods"]["seir"] = np.quantile(S, QUANTILES, axis=0).T.tolist()
        row["seir_fit"] = {"success": fr["success"], "hessian_pd": fr["hessian_pd"]}
