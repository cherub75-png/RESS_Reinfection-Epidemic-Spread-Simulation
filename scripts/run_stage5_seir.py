"""5단계 A: 국가별 보정 SEIR 시간순 예측 (기점마다 그날까지 자료로 재추정). 오래 걸리므로 국가별로 저장하고 이어서 실행할 수 있다.

사용법: python -I scripts/run_stage5_seir.py [--workers 4] [--knot 14] [--countries KOR,JPN,...] [--every 2]
출력:   outputs/stage5/seir_k{knot}_{ISO3}.pkl, outputs/stage5/seir_k{knot}.log
"""

import argparse
import multiprocessing as mp
import pickle
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "outputs" / "stage5"
FIRST_ORIGIN, LAST_ORIGIN = "2020-07-05", "2022-12-25"


def run_one(args):
    warnings.simplefilter("ignore")
    sys.path.insert(0, str(ROOT))
    iso3, knot, every = args
    from seir_sim.forecast.panel import load_panel
    from seir_sim.forecast.seir import RollingSpec, rolling_country, spec_dict
    from seir_sim.forecast.targets import origins
    path = OUT / f"seir_k{knot}_{iso3}.pkl"
    if path.exists():
        return iso3, "exists", 0.0
    logf = open(OUT / f"seir_k{knot}_{iso3}.log", "w")

    def log(msg):
        logf.write(msg + "\n")
        logf.flush()

    t0 = time.perf_counter()
    panel = load_panel(iso3)
    spec = RollingSpec(knot_days=knot)
    res = rolling_country(iso3, panel, origins(FIRST_ORIGIN, LAST_ORIGIN, every), spec, log=log)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump({"iso3": iso3, "spec": spec_dict(spec), "every_weeks": every, "results": res,
                     "population": panel.attrs["population"], "sources": panel.attrs["sources"]}, f)
    tmp.rename(path)
    logf.close()
    return iso3, "done", time.perf_counter() - t0


def main():
    from seir_sim.surveillance.sources import COUNTRIES
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--knot", type=int, default=14)
    ap.add_argument("--every", type=int, default=2)
    ap.add_argument("--countries", default=",".join(COUNTRIES))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cs = a.countries.split(",")
    ctx = mp.get_context("forkserver")
    with ProcessPoolExecutor(a.workers, mp_context=ctx) as ex:
        futs = [ex.submit(run_one, (c, a.knot, a.every)) for c in cs]
        for f in as_completed(futs):
            iso3, status, dt = f.result()
            print(f"{iso3} {status} {dt:.0f}s", flush=True)


if __name__ == "__main__":
    main()
