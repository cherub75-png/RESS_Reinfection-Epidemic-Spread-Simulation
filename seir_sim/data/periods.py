"""자료 시기 선택: 경계 시점 · 인구 연도 · 기후 기간을 골라 지역 데이터셋 변형본을 만든다.

같은 데이터셋이라도 "언제의" 지리·인구·기후를 쓰는지가 결과를 바꾼다. 기본은 확보한 가장 최신 자료이며, 사용자가 다른
시기를 고를 수 있다. 확보하지 못한 시기는 고를 수 없게 표시한다 (값을 지어내거나 보간하지 않는다).

데이터셋 묶음 (provenance.scope 로 구분)
  world : 국가 단위. 경계 Natural Earth (한 판), 인구 World Bank WDI 연도별 (1960 ~ 최신), 기후 ERA5 기간.
  KOR   : 대한민국 시도. 경계 통계청 SGIS 시점 파일 (1975 ~ 현재), 인구 WorldPop R2025A 연도별 (2015 ~ 2030;
          받은 해 이후는 전망), 기후 ERA5 기간.
이동 규모·통근·접촉 비율은 원본 데이터셋의 가정값을 그대로 쓴다 (provenance.assumptions).
변형본은 data_processed/variants/ 에 캐시한다 (같은 선택이면 다시 만들지 않는다). 저장소(registry)에 등록하지 않는
파생 파일이며, 출처는 파일의 provenance 에 남는다.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data_raw"
CLIMATE = ROOT / "data_processed" / "climate"
VARIANTS = ROOT / "data_processed" / "variants"
WB_TABLE = ROOT / "data_processed" / "tables" / "wb_population_api.csv"
WB_MIRROR = RAW / "wb_population" / "population.csv"
WP_DIR = RAW / "worldpop_kor_r2025a_1km"
SIDO_DIR = RAW / "admdongkor_sido"
AIRPORTS, ROUTES = RAW / "openflights" / "airports.dat", RAW / "openflights" / "routes.dat"
WP_RELEASE_YEAR = 2025          # WorldPop R2025A 발표 연도: 이보다 뒤 연도는 전망치로 표시하고 기본값으로 쓰지 않는다


def family(prov: dict) -> str:
    sc = str(prov.get("scope", ""))
    if sc.startswith("world"):
        return "world"
    if sc.startswith("KOR"):
        return "KOR"
    return "other"


# ------------------------------------------------------------------ 선택지
def _wb_table() -> Path:
    return WB_TABLE if WB_TABLE.exists() else WB_MIRROR


def population_options(fam: str) -> list[dict]:
    today = dt.date.today().year
    if fam == "world":
        p = _wb_table()
        if not p.exists():
            return []
        import pandas as pd
        years = sorted(pd.read_csv(p, usecols=["Year"])["Year"].unique().tolist())
        src = "World Bank WDI 공식 API" if p == WB_TABLE else "World Bank WDI (datahub 사본)"
        return [{"value": int(y), "label": f"{y}", "source": src, "kind": "compiled",
                 "note": "최신 연도 값은 추정치일 수 있음" if y >= today - 1 else ""} for y in years]
    if fam == "KOR":
        out = []
        for f in sorted(WP_DIR.glob("kor_pop_*_CN_1km_R2025A_UA_v1.tif")):
            y = int(re.search(r"kor_pop_(\d{4})_", f.name).group(1))
            out.append({"value": y, "label": f"{y}", "source": "WorldPop R2025A 1 km (UN 총량 조정)", "kind": "model_estimate",
                        "note": f"전망 (자료 발표 {WP_RELEASE_YEAR}년 이후)" if y > WP_RELEASE_YEAR else "모델 추정"})
        return out
    return []


def boundary_options(fam: str) -> list[dict]:
    if fam == "KOR":
        out = []
        for f in sorted(SIDO_DIR.glob("sido_*_light.parquet")):
            d = re.search(r"sido_(\d{8})_", f.name).group(1)
            out.append({"value": f"{d[:4]}-{d[4:6]}-{d[6:]}", "label": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                        "source": "통계청 SGIS 행정동 경계 기반 (admdongkor)", "file": f.name})
        return out
    if fam == "world":
        return [{"value": "natural_earth", "label": "Natural Earth (받은 판)", "source": "Natural Earth admin 0", "file": None}]
    return []


def climate_options() -> list[dict]:
    out = []
    for d in sorted(CLIMATE.glob("era5_*")):
        p = d / "provenance.json"
        if not p.exists():
            continue
        prov = json.loads(p.read_text())
        months = [m for m, n in prov["samples_per_month"].items() if n > 0]
        out.append({"value": d.name, "label": f"ERA5 {prov['period']}", "source": prov["source"], "kind": "reanalysis",
                    "months": len(months), "note": "" if len(months) == 12 else f"{len(months)}개 달만 있음 (나머지 달 미확보)"})
    return out


def options(fam: str) -> dict:
    pops, bounds, clim = population_options(fam), boundary_options(fam), climate_options()
    return {"family": fam, "population": pops, "boundaries": bounds, "climate": clim,
            "latest": {"population": latest_population_year(fam),
                       "boundaries": bounds[-1]["value"] if bounds else None,
                       "climate": _latest_full_climate(clim)}}


def _latest_full_climate(clim: list[dict]):
    full = [c for c in clim if c["months"] == 12]
    if not full:
        return None
    return max(full, key=lambda c: c["value"].split("_")[-1])["value"]


def latest_population_year(fam: str) -> int | None:
    """전망치가 아닌 가장 최근 연도 (올해와 자료 발표 연도를 넘지 않음)."""
    cap = min(dt.date.today().year, WP_RELEASE_YEAR) if fam == "KOR" else dt.date.today().year
    ys = [o["value"] for o in population_options(fam) if o["value"] <= cap]
    return max(ys) if ys else None


# ------------------------------------------------------------------ 변형본
def _key(name: str, boundary, year, climate) -> str:
    safe = lambda v: re.sub(r"[^A-Za-z0-9_.-]", "", str(v)) if v is not None else "base"
    return f"{name}__b{safe(boundary)}__p{safe(year)}__c{safe(climate)}"


def variant(name: str, version: str | None = None, population_year: int | None = None,
            climate_period: str | None = None, boundary_date: str | None = None, log=lambda m: None) -> Path:
    """선택한 시기의 데이터셋 파일 경로. 모두 None 이면 저장소의 원본 파일."""
    from .dataset import RegionDataset
    from .versions import Registry, validate_dataset
    reg = Registry()
    spec = f"{name}@{version}" if version else name
    base_path = reg.resolve(spec)
    if population_year is None and climate_period is None and boundary_date is None:
        return base_path
    base = RegionDataset.load(base_path)
    fam = family(base.provenance)
    if fam == "other":
        raise ValueError(f"{name}: 시기 선택을 지원하지 않는 데이터셋 (scope={base.provenance.get('scope')})")
    VARIANTS.mkdir(parents=True, exist_ok=True)
    out = VARIANTS / f"{_key(name, boundary_date, population_year, climate_period)}.nc"
    if out.exists():
        return out
    a = base.provenance.get("assumptions", {})
    air = (AIRPORTS, ROUTES, float(a["air_trips_per_day"]), float(a["commute_fraction"]), float(a["destination_contact_share"]))
    geo = None
    if fam == "world":
        from .boundaries import load_admin0
        from .build import build_world_countries
        year = population_year or base.provenance.get("population_year")
        log(f"전 세계 데이터셋 만들기: 인구 {year}")
        ds = build_world_countries(RAW / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson", _wb_table(), int(year), *air)
        if climate_period:
            geo = load_admin0(RAW / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson")
    else:
        from .boundaries import load_kostat_sido
        from .build import build_kor_sido
        bfile = _boundary_file(boundary_date)
        year = population_year or latest_population_year("KOR")
        raster = WP_DIR / f"kor_pop_{year}_CN_1km_R2025A_UA_v1.tif"
        if not raster.exists():
            raise ValueError(f"{year} 년 WorldPop 인구 격자가 없다 (미확보). 고를 수 있는 연도: "
                             f"{[o['value'] for o in population_options('KOR')]}")
        log(f"대한민국 시도 데이터셋 만들기: 경계 {bfile.name}, 인구 WorldPop {year}")
        ds = build_kor_sido(bfile, *air, population_raster=raster)
        geo = load_kostat_sido(bfile)
    if climate_period:
        ds = _attach_climate(ds, geo, climate_period, log)
    ds.provenance["period_selection"] = {"base": spec, "boundary_date": boundary_date, "population_year": population_year,
                                         "climate_period": climate_period,
                                         "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    v = validate_dataset(ds)
    if not v["ok"]:
        raise ValueError(f"변형본 검증 실패: {v['errors']}")
    ds.provenance["validation"] = v
    ds.save(out)
    _write_geojson(out.with_suffix(".geojson"), ds, geo if geo is not None else None, fam)
    return out


def _boundary_file(boundary_date: str | None) -> Path:
    files = sorted(SIDO_DIR.glob("sido_*_light.parquet"))
    if not files:
        raise ValueError("시도 경계 파일이 없다 (scripts/fetch_admdongkor.py)")
    if boundary_date is None:
        return files[-1]
    want = boundary_date.replace("-", "")
    older = [f for f in files if re.search(r"sido_(\d{8})_", f.name).group(1) <= want]
    if not older:
        raise ValueError(f"{boundary_date} 이전의 경계 파일이 없다 (가장 이른 판: {files[0].name})")
    return older[-1]


def _attach_climate(ds, geo, period: str, log):
    from dataclasses import replace

    from . import era5
    from .climate import attach_monthly_table
    d = CLIMATE / period
    if not (d / "provenance.json").exists():
        raise ValueError(f"기후 기간 {period} 이 없다. 고를 수 있는 기간: {[c['value'] for c in climate_options()]}")
    ids = set(ds.ids)
    g = geo.subset(np.array([i in ids for i in geo.ids]))       # 표는 id 로 붙이므로 순서는 상관없다
    tmp = VARIANTS / f"_climate_{period}_{g.K}.csv"
    log(f"ERA5 {period} 지역 평균 계산")
    era5.region_table(d, g, g.ids, tmp)
    ds2 = attach_monthly_table(replace(ds), tmp)
    ds2.provenance["climate"]["era5_provenance"] = json.loads((d / "provenance.json").read_text())
    tmp.unlink(missing_ok=True)
    return ds2


def _write_geojson(path: Path, ds, geo, fam: str) -> None:
    import shapely
    if geo is None:
        from .boundaries import load_admin0
        geo = load_admin0(RAW / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson")
    tol = 0.08 if fam == "world" else 0.005
    gi = {r: k for k, r in enumerate(geo.ids)}
    feats = []
    for k, rid in enumerate(ds.ids):
        if rid not in gi:
            continue
        g = shapely.simplify(geo.geoms[gi[rid]], tol, preserve_topology=True)
        feats.append({"type": "Feature", "id": rid,
                      "properties": {"id": rid, "name": ds.names[k],
                                     "population": float(ds.population[k]) if np.isfinite(ds.population[k]) else None},
                      "geometry": json.loads(shapely.to_geojson(g))})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats,
                                "properties": {"boundaries": ds.provenance.get("boundaries")}}, ensure_ascii=False))
