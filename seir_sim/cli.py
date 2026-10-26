"""명령줄 실행.

  python -m seir_sim info configs/world_countries_2019.yaml
  python -m seir_sim run  configs/world_countries_2019.yaml --out outputs/world --runs 100 --workers 4
  python -m seir_sim run  configs/example_single_region.yaml --out outputs/single --method ode

결과: <out>/ensemble.nc (NetCDF), summary_daily.parquet, summary_regions.parquet, run_record.json, 그림 PNG.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np


def _info(args):
    from .config.build import build_scenario, load_config, load_dataset
    cfg = load_config(args.config)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sc = build_scenario(cfg)
    d = {k: v for k, v in sc.derived.items() if k not in ("regions_provenance", "R0_isolated_by_region")}
    iso = sc.derived["R0_isolated_by_region"]
    vals = np.array(list(iso.values()))
    d["R0_isolated_min_median_max"] = [float(vals.min()), float(np.median(vals)), float(vals.max())]
    out = {"config": args.config, "K": sc.system.regions.K, "M": sc.system.params.M,
           "population_total": float(sc.system.regions.population.sum()), "derived": d,
           "warnings": [str(x.message) for x in w]}
    if cfg.regions.source == "dataset":
        out["dataset_quality"] = {k: v for k, v in load_dataset(cfg).quality().items() if k != "missing_population"}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


def _run(args):
    from .config.build import load_config, load_dataset
    from .ensemble.runner import run_ensemble
    from .viz import plots
    cfg = load_config(args.config)
    if args.days is not None:
        cfg.simulation.days = args.days
    res = run_ensemble(cfg, method=args.method, n_runs=args.runs, n_workers=args.workers,
                       outbreak_threshold=args.outbreak_threshold)
    saved = res.save(args.out)
    out = Path(args.out)
    if not args.no_plots:
        plots.plot_I_total(res, out / "I_total.png")
        plots.plot_region_heatmap(res, out / "regions_heatmap.png")
        if cfg.regions.source == "dataset":
            ds = load_dataset(cfg)
            geoms = None
            if args.outlines:
                from .data.geo import read_geojson
                geoms = [g for _, g in read_geojson(args.outlines)]
            plots.plot_arrival_map(res, ds.lon, ds.lat, ds.population, out / "arrival_map.png", geoms)
    s = res.summary()
    print(json.dumps({"saved": saved, "method": res.method, "runs": int(res.runs.shape[0]),
                      "wall_seconds": round(res.wall_seconds, 2), "outbreak_probability": s["outbreak_probability"],
                      "peak_I_mean": s["peak_I_mean"], "peak_day_median": s["peak_day_median"],
                      "synthetic_regions": bool(res.derived.get("regions_synthetic"))}, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="seir_sim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("info", help="시나리오 점검 (R0 보고, 자료 품질)")
    a.add_argument("config")
    b = sub.add_parser("run", help="앙상블 실행과 저장")
    b.add_argument("config")
    b.add_argument("--out", required=True)
    b.add_argument("--method", choices=["ode", "sde", "ctmc", "tau", "hybrid"], default=None)
    b.add_argument("--runs", type=int, default=None)
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--days", type=float, default=None)
    b.add_argument("--outbreak-threshold", type=float, default=1000.0, help="대유행 판정: max I_total >= 이 값")
    b.add_argument("--outlines", default=None, help="지도 배경 경계 GeoJSON (선택)")
    b.add_argument("--no-plots", action="store_true")
    args = ap.parse_args(argv)
    {"info": _info, "run": _run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
