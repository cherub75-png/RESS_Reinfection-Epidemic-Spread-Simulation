"""인플루엔자 시간순 예측 검증 (규약: docs/reports/11_influenza_protocol.md, 결과 전에 고정).

방법: persistence, trend, seasonal, ml, ml_cal, ml_noclim, ml_loco_KOR. 기점 2022-10-03 ~ 2026-09-21 매주, 예측 1~4주.
ML 은 4주마다 다시 학습하고 (재학습 기점까지 정답이 알려진 행만), 다음 재학습 전 기점들에 쓴다.
사용법: python -I scripts/run_flu_validation.py [--workers 4]
출력: outputs/flu/forecasts.parquet, docs/reports/11_influenza_validation.md/.json, docs/figures/11_*.png
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
OUT = ROOT / "outputs" / "flu"
FIRST_ORIGIN, LAST_ORIGIN = "2022-10-03", "2026-09-21"
REFIT_EVERY = 4
LOCO = "KOR|SENTINEL"
QC = [f"q{k}" for k in range(9)]
G = {}


def load_inputs():
    from seir_sim.data.boundaries import load_admin0
    from seir_sim.forecast import flu as FL
    from seir_sim.surveillance import flunet as F
    df = F.load_flunet(ROOT / "data_raw" / "who_flunet" / "VIW_FNT.csv")
    series = F.select_series(df)
    geo = load_admin0(ROOT / "data_raw" / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson")
    lat = dict(zip(geo.ids, geo.lat))
    cp = ROOT / "data_processed" / "climate" / "era5_weekly_countries.parquet"
    climate = pd.read_parquet(cp) if cp.exists() else None
    data = FL.FluData(df, series, start="2009-01-05", lat=lat, climate=climate)
    return df, series, data, climate


def _init(path):
    os.environ["OMP_NUM_THREADS"] = "1"
    warnings.simplefilter("ignore")
    sys.path.insert(0, str(ROOT))
    with open(path, "rb") as f:
        G.update(pickle.load(f))


def ml_block(args):
    """재학습 기점 o0 에서 학습한 모형들로 이 블록의 기점들을 예측한다."""
    from seir_sim.forecast import flu as FL
    from seir_sim.ml.quantile import ML_PARAMS, fit_quantile_models, predict_quantiles
    from scipy.special import expit
    o0, origins = args
    tab = G["table"]
    train = tab[(tab["target_week"] <= o0) & tab["target"].notna()]
    out, info = [], {"refit_origin": str(o0.date()), "train_rows": int(len(train))}
    for name, clim, excl in (("ml", True, ()), ("ml_noclim", False, ()), ("ml_loco_KOR", True, (LOCO,))):
        cols = FL.feature_list(clim and G["has_climate"])
        tr = train[~train["series"].isin(excl)]
        models = fit_quantile_models(tr[cols], tr["target"].to_numpy(), ML_PARAMS)
        for o in origins:
            X = tab[tab["week"] == o]
            if name == "ml_loco_KOR":
                X = X[X["series"] == LOCO]
            if X.empty:
                continue
            q = expit(predict_quantiles(models, X[cols]))
            d = X[["series", "week", "h", "target_week", "truth"]].rename(columns={"week": "origin"}).copy()
            d[QC] = q
            d["method"] = name
            out.append(d)
        info[f"{name}_train_rows"] = int(len(tr))
    return pd.concat(out, ignore_index=True), info


def baselines(data, origins):
    rows = []
    for o in origins:
        i = data.index(o)
        for k, s in enumerate(data.series):
            for m in ("persistence", "trend", "seasonal"):
                q = data.seasonal(k, i) if m == "seasonal" else data.baseline(k, i, m)
                if q is None:
                    continue
                for a, h in enumerate((1, 2, 3, 4)):
                    j = i + h
                    rows.append({"series": s, "origin": o, "h": h, "target_week": o + pd.Timedelta(weeks=h),
                                 "truth": data.pt[j, k] if j < len(data.weeks) else np.nan, "method": m,
                                 **{QC[q_]: q[a, q_] for q_ in range(9)}})
    return pd.DataFrame(rows)


def main():
    from scipy.special import expit, logit
    from seir_sim.forecast import flu as FL
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    df, series, data, climate = load_inputs()
    print(f"계열 {len(series)}개, 기후 {'있음' if climate is not None else '없음'}", flush=True)
    origins = pd.date_range(FIRST_ORIGIN, LAST_ORIGIN, freq="7D")
    tab = FL.feature_table(data, climate=climate is not None)
    print(f"특성 표 {len(tab)}행 ({time.perf_counter() - t0:.0f}초)", flush=True)
    path = OUT / "_shared.pkl"
    with open(path, "wb") as f:
        pickle.dump({"table": tab, "has_climate": climate is not None}, f)
    blocks = [(origins[b], list(origins[b: b + REFIT_EVERY])) for b in range(0, len(origins), REFIT_EVERY)]
    with ProcessPoolExecutor(a.workers, mp_context=mp.get_context("forkserver"), initializer=_init, initargs=(str(path),)) as ex:
        fut = ex.map(ml_block, blocks)
        base = baselines(data, origins)
        print(f"기준 모델 {len(base)}행 ({time.perf_counter() - t0:.0f}초)", flush=True)
        parts, infos = [], []
        for k, (d, info) in enumerate(fut, 1):
            parts.append(d)
            infos.append(info)
            print(f"ML 블록 {k}/{len(blocks)} ({time.perf_counter() - t0:.0f}초)", flush=True)
    path.unlink(missing_ok=True)
    ml = pd.concat(parts, ignore_index=True)
    to_z = lambda p: logit(np.clip(p, 1e-3, 1 - 1e-3))                     # noqa: E731
    cal = FL.conformal_adjust(ml[ml["method"] == "ml"], to_z, expit)
    cal["method"] = "ml_cal"
    allf = pd.concat([base, ml, cal.drop(columns=["cal_n"])], ignore_index=True)
    allf = allf.merge(data.meta[["iso3", "hemisphere", "name"]], left_on="series", right_index=True, how="left")
    allf["lat"] = allf["iso3"].map(dict(zip(data.meta["iso3"], data.lat)))
    allf.to_parquet(OUT / "forecasts.parquet")
    cal[["series", "origin", "h", "cal_n"]].to_parquet(OUT / "ml_cal_n.parquet")
    run = {"series": series, "n_series": len(series), "origins": [str(origins[0].date()), str(origins[-1].date()), len(origins)],
           "refit_every_weeks": REFIT_EVERY, "climate_features": climate is not None,
           "climate_provenance": json.loads((ROOT / "data_processed/climate/era5_weekly_countries.json").read_text()) if climate is not None else None,
           "flunet_attrs": df.attrs, "ml_blocks": infos, "wall_seconds": round(time.perf_counter() - t0, 1)}
    (OUT / "run_record.json").write_text(json.dumps(run, indent=1, ensure_ascii=False, default=str))
    print(f"완료 {time.perf_counter() - t0:.0f}초, 예측 {len(allf)}행", flush=True)


if __name__ == "__main__":
    main()
