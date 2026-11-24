"""명령줄 실행.

  python -m seir_sim info configs/world_countries_2019.yaml
  python -m seir_sim run  configs/world_countries_2019.yaml --out outputs/world --runs 100 --workers 4
  python -m seir_sim run  configs/example_single_region.yaml --out outputs/single --method ode
  python -m seir_sim data register --name KOR_admin1 data_processed/KOR_admin1_gc19od.nc --note "..."
  python -m seir_sim data activate --name KOR_admin1 v1      (rollback / list / validate / diff)
  python -m seir_sim forecast --country KOR --out outputs/forecast_KOR.json

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


def _forecast(args):
    from .forecast.operational import latest_forecast
    out = latest_forecast(args.country, args.origin, knot=args.knot, n_samples=args.samples)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "methods"} | {
        "median_weekly_cases": {m: [round(r[4]) for r in v["cases"]] for m, v in out["methods"].items()
                                if not m.startswith("_") and v.get("cases") is not None}}, ensure_ascii=False, indent=1))


def _data(args):
    from .data.dataset import RegionDataset
    from .data.versions import Registry, validate_dataset
    reg = Registry()
    if args.action == "list":
        out = {n: {"active": e["active"], "history": e["history"],
                   "versions": [{k: v[k] for k in ("version", "registered_utc", "K", "population_total", "population_source",
                                                   "synthetic", "note")} | {"ok": v["validation"]["ok"]} for v in e["versions"]]}
               for n, e in reg.list().items()}
    elif args.action == "validate":
        out = validate_dataset(RegionDataset.load(args.target))
    elif args.action == "register":
        out = {"version": reg.register(args.name, args.target, args.note or "")}
    elif args.action == "activate":
        reg.activate(args.name, args.target, force=args.force)
        out = {"active": args.target}
    elif args.action == "rollback":
        out = {"active": reg.rollback(args.name)}
    elif args.action == "periods":
        from .data import periods
        out = periods.options(periods.family(RegionDataset.load(reg.resolve(args.name)).provenance))
    elif args.action == "variant":
        from .data import periods
        path = periods.variant(args.name, population_year=args.population_year, climate_period=args.climate_period,
                               boundary_date=args.boundary_date, log=lambda m: print(m, file=sys.stderr))
        out = {"path": str(path), "use_in_config": {"regions": {"source": "dataset", "path": str(path)}}}
    elif args.action == "climate":
        from .data import era5, periods
        if not (args.start and args.end):
            raise SystemExit("climate: --start YYYY-MM --end YYYY-MM 가 필요하다")
        out = era5.monthly_means(args.start, args.end, periods.CLIMATE / f"era5_{args.start}_{args.end}",
                                 log=lambda m: print(m, file=sys.stderr))
    else:
        out = reg.diff(args.name, None, RegionDataset.load(args.target))
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


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
    c = sub.add_parser("data", help="지역 데이터셋 버전 관리 (list / validate / register / activate / rollback / diff) "
                                    "와 자료 시기 선택 (periods / variant / climate)")
    c.add_argument("action", choices=["list", "validate", "register", "activate", "rollback", "diff", "periods", "variant",
                                      "climate"])
    c.add_argument("--name", help="데이터셋 이름 (예: KOR_admin1)")
    c.add_argument("target", nargs="?", help="validate/register/diff: .nc 파일, activate: 버전 (예: v2)")
    c.add_argument("--note", default=None)
    c.add_argument("--force", action="store_true", help="검증 실패 버전도 활성화 (권장하지 않음)")
    c.add_argument("--population-year", type=int, default=None, help="variant: 인구 기준 연도")
    c.add_argument("--climate-period", default=None, help="variant: 기후 기간 폴더 이름 (예: era5_2025-07_2026-06)")
    c.add_argument("--boundary-date", default=None, help="variant: 경계 시점 YYYY-MM-DD (대한민국 시도)")
    c.add_argument("--start", default=None, help="climate: ERA5 기간 시작 YYYY-MM")
    c.add_argument("--end", default=None, help="climate: ERA5 기간 끝 YYYY-MM (포함)")
    f = sub.add_parser("forecast", help="최신 자료 기점의 4주 예측 (5단계와 같은 방법; 기점 뒤 자료 사용 안 함)")
    f.add_argument("--country", required=True, help="ISO3 (예: KOR)")
    f.add_argument("--origin", default=None, help="기점 날짜 (기본: 자료 마지막 날 이전 일요일)")
    f.add_argument("--knot", type=int, default=14)
    f.add_argument("--samples", type=int, default=300)
    f.add_argument("--out", default=None, help="JSON 저장 경로")
    args = ap.parse_args(argv)
    {"info": _info, "run": _run, "data": _data, "forecast": _forecast}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
