"""인플루엔자 seir 보조 비교 (규약 7절): 정해진 계열 x 4주 간격 기점, 기점마다 26주 창으로 다시 적합.

사용법: python -I scripts/run_flu_seir.py [--workers 4]
출력: outputs/flu/seir_forecasts.parquet, outputs/flu/seir_fits.json
"""

import argparse
import json
import multiprocessing as mp
import os
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
SUBSET = ["KOR|SENTINEL", "USA|SENTINEL", "NOR|NONSENTINEL", "ESP|SENTINEL", "JPN|SENTINEL", "SGP|SENTINEL",
          "AUS|NOTDEFINED", "CHL|NONSENTINEL", "BRA|NONSENTINEL", "ZAF|SENTINEL"]
FIRST_ORIGIN, LAST_ORIGIN = "2022-10-03", "2026-09-21"


def one(args):
    os.environ["OMP_NUM_THREADS"] = "1"
    warnings.simplefilter("ignore")
    sys.path.insert(0, str(ROOT))
    from seir_sim.forecast.metrics import QUANTILES
    from seir_sim.inference.flu_seir import WINDOW_WEEKS, FluPositivityModel
    series, origin, x, n, pop, truth = args
    m = FluPositivityModel(pop, x, n)
    fr = m.fit()
    n_future = np.nanmedian(n[-4:])
    info = {"series": series, "origin": str(origin.date()), "success": fr["success"], "hessian_pd": fr["hessian_pd"],
            "n_iter": fr["n_iter"], "wall_s": round(fr["wall_s"], 1), "window_weeks": WINDOW_WEEKS}
    if not np.isfinite(n_future):
        return [], info
    S = m.predictive(fr, n_future, n_samples=300, seed=0)
    q = np.quantile(S, QUANTILES, axis=0).T
    rows = [{"series": series, "origin": origin, "h": h, "target_week": origin + pd.Timedelta(weeks=h), "truth": truth[h - 1],
             "method": "seir", **{f"q{k}": float(q[h - 1, k]) for k in range(QUANTILES.size)}} for h in (1, 2, 3, 4)]
    return rows, info


def main():
    from seir_sim.forecast import flu as FL  # noqa: F401
    from seir_sim.inference.flu_seir import WINDOW_WEEKS
    from seir_sim.surveillance import flunet as F
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.perf_counter()
    df = F.load_flunet(ROOT / "data_raw" / "who_flunet" / "VIW_FNT.csv")
    sel = set(F.select_series(df))
    subset = [s for s in SUBSET if s in sel]
    dropped = [s for s in SUBSET if s not in sel]
    meta = F.series_meta(df)
    wb = pd.read_csv(ROOT / "data_processed" / "tables" / "wb_population_api.csv")
    wb = wb.sort_values("Year").groupby("Country Code").last()
    origins = pd.date_range(FIRST_ORIGIN, LAST_ORIGIN, freq="28D")
    jobs = []
    for s in subset:
        T, X = F.wide(df, [s], "2022-01-03", str(df["week"].max().date()))
        P = F.positivity(T[s].to_numpy(), X[s].to_numpy(), F.MIN_TESTS_TARGET)
        pop = float(wb.loc[meta.loc[s, "iso3"], "Value"])
        for o in origins:
            i = T.index.get_loc(o)
            sl = slice(i - WINDOW_WEEKS + 1, i + 1)
            truth = [P[i + h] if i + h < len(P) else np.nan for h in (1, 2, 3, 4)]
            jobs.append((s, o, X[s].to_numpy()[sl], T[s].to_numpy()[sl], pop, truth))
    rows, infos = [], []
    with ProcessPoolExecutor(a.workers, mp_context=mp.get_context("forkserver")) as ex:
        for k, (r, info) in enumerate(ex.map(one, jobs), 1):
            rows += r
            infos.append(info)
            if k % 20 == 0 or k == len(jobs):
                print(f"seir {k}/{len(jobs)} ({time.perf_counter() - t0:.0f}초)", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT / "seir_forecasts.parquet")
    (OUT / "seir_fits.json").write_text(json.dumps({"subset": subset, "dropped_by_selection": dropped, "fits": infos,
                                                    "wall_seconds": round(time.perf_counter() - t0, 1)}, indent=1, ensure_ascii=False))
    ok = np.mean([i["success"] for i in infos]) if infos else float("nan")
    print(f"완료: 적합 {len(infos)}, 수렴 {ok:.2f}, 빠짐 {dropped}")


if __name__ == "__main__":
    main()
