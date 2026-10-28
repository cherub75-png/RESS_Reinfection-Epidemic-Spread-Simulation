"""지역 데이터셋 만들기: 경계 + 인구 + 이동 + 접촉 (+ 기후) -> RegionDataset.

같은 함수가 국가 단위(전 세계)와 1급 행정구역(한 나라)을 모두 만든다. 나라별 예외 처리 코드는 두지 않는다.
가정 매개변수(항공 이동 규모, 통근 비율, 목적지 접촉 비율)는 반드시 호출자가 명시한다.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from ..provenance import git_commit
from . import commuting, mobility
from . import population as popmod
from .boundaries import RegionGeometry, load_admin0, load_admin1
from .dataset import RegionDataset

ROOT = Path(__file__).resolve().parent.parent.parent


def _input_record(path: str | Path) -> dict:
    """data_raw/manifest.json 에서 파일의 출처·SHA-256 을 찾는다."""
    path = Path(path).resolve()
    man = ROOT / "data_raw" / "manifest.json"
    if man.exists():
        for did, e in json.loads(man.read_text()).items():
            for f in e.get("files", []):
                if "path" in f and (ROOT / f["path"]).resolve() == path:
                    return {"dataset": did, "file": f["path"], "sha256": f["sha256"], "license": e["license"],
                            "source": e["source"], "version": e["version"], "time_reference": e["time_reference"],
                            "retrieved_utc": e["retrieved_utc"]}
    return {"file": str(path), "note": "manifest 에 없음"}


def _assemble(geo: RegionGeometry, pop: np.ndarray, pop_meta: dict, airports_path, routes_path,
              air_trips_per_day: float, commute_fraction: float, destination_contact_share: float,
              extra: dict) -> RegionDataset:
    keep = np.isfinite(pop) & (pop > 0) & (geo.area_km2 > 0)
    if extra.get("keep_missing_population"):
        keep = (geo.area_km2 > 0) & ~(np.isfinite(pop) & (pop <= 0))
    excluded = [{"id": i, "name": n, "population": (None if not np.isfinite(p) else float(p))}
                for i, n, p, k in zip(geo.ids, geo.names, pop, keep) if not k]
    g = geo.subset(keep)
    pop = pop[keep]
    K = g.K
    prov = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "code_commit": git_commit(ROOT), "boundaries": g.source, "merged_features": g.merged,
            "population": pop_meta,
            "excluded_regions": excluded,
            "assumptions": {"air_trips_per_day": air_trips_per_day, "commute_fraction": commute_fraction,
                            "destination_contact_share": destination_contact_share,
                            "air_flux": "proportional to OpenFlights route count, symmetric (balanced)",
                            "contact": "radiation-model destination shares, C_ij = a_c a_s w_ij"},
            **{k: v for k, v in extra.items() if k != "keep_missing_population"}}
    if np.all(np.isfinite(pop)):
        airports = mobility.read_airports(airports_path)
        routes, rmeta = mobility.read_routes(routes_path)
        R, mmeta = mobility.route_matrix(g, airports, routes)
        om, ometa = mobility.symmetric_air_mobility(R, pop, air_trips_per_day)
        W = commuting.radiation_shares(pop, g.lon, g.lat)
        C = commuting.contact_matrix(W, commute_fraction, destination_contact_share)
        prov["mobility"] = {**rmeta, **mmeta, **ometa, "inputs": [_input_record(airports_path), _input_record(routes_path)]}
    else:
        om = np.full((K, K), np.nan)
        C = np.full((K, K), np.nan)
        prov["mobility"] = {"note": "인구가 미확보라 이동률(omega = 이동량 / 인구)과 radiation 접촉을 계산하지 않음"}
    return RegionDataset(g.ids, g.names, pop.astype(float), g.area_km2, g.lon, g.lat, C, om, prov, synthetic=False)


def build_world_countries(admin0_path, wb_population_csv, year: int, airports_path, routes_path,
                          air_trips_per_day: float, commute_fraction: float,
                          destination_contact_share: float) -> RegionDataset:
    """국가 단위 전 세계. 인구: World Bank (year), 없으면 Natural Earth POP_EST (보조, 지역별로 표시)."""
    geo = load_admin0(admin0_path)
    pop, src, meta = popmod.combine(popmod.from_worldbank_csv(wb_population_csv, geo, year),
                                    popmod.from_attribute(geo, "POP_EST", "POP_YEAR"))
    meta["per_region_source"] = {i: ("worldbank" if s == 0 else "natural_earth_pop_est" if s == 1 else "missing")
                                 for i, s in zip(geo.ids, src)}
    meta["inputs"] = [_input_record(admin0_path), _input_record(wb_population_csv)]
    return _assemble(geo, pop, meta, airports_path, routes_path, air_trips_per_day, commute_fraction,
                     destination_contact_share, {"scope": "world, admin 0", "population_year": year})


def build_admin1(admin1_path, country_a3: str, airports_path, routes_path, air_trips_per_day: float,
                 commute_fraction: float, destination_contact_share: float,
                 population_raster: str | Path | None = None,
                 population_table: str | Path | None = None) -> RegionDataset:
    """한 나라의 1급 행정구역. 인구는 격자 파일 또는 인구표(CSV)에서 만든다. 둘 다 없으면 NaN (미확보) 으로 둔다."""
    geo = load_admin1(admin1_path, country_a3)
    if population_raster is not None and population_table is not None:
        raise ValueError("인구 격자와 인구표 중 하나만 준다")
    if population_raster is not None and Path(population_raster).exists():
        pop, meta = popmod.from_raster(population_raster, geo)
        meta["inputs"] = [_input_record(population_raster)]
    elif population_table is not None:
        pop, meta = popmod.from_table(population_table, geo)
        meta["inputs"] = [_input_record(population_table)]
    else:
        pop = np.full(geo.K, np.nan)
        meta = {"source": "미확보", "reason": f"인구 격자 파일 없음: {population_raster}"}
    meta.setdefault("inputs", [])
    meta["inputs"].append(_input_record(admin1_path))
    return _assemble(geo, pop, meta, airports_path, routes_path, air_trips_per_day, commute_fraction,
                     destination_contact_share, {"scope": f"{country_a3}, admin 1",
                                                 "keep_missing_population": True})
