"""지역별 인구. 표(국가별 통계) 또는 격자(GeoTIFF)에서 만든다. 없는 값은 NaN 으로 남기고 출처를 기록한다."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import shapely

from .boundaries import RegionGeometry


def from_worldbank_csv(path: str | Path, regions: RegionGeometry, year: int) -> tuple[np.ndarray, dict]:
    """World Bank SP.POP.TOTL (datahub 사본 형식: Country Name, Country Code, Year, Value).

    지역 id(ISO3)와 연도가 일치하는 값만 쓴다. 나머지는 NaN 이며 meta['missing'] 에 남긴다.
    """
    table: dict[tuple[str, int], float] = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                table[(row["Country Code"], int(row["Year"]))] = float(row["Value"])
            except (KeyError, ValueError):
                continue
    pop = np.array([table.get((rid, year), np.nan) for rid in regions.ids])
    missing = [rid for rid, v in zip(regions.ids, pop) if np.isnan(v)]
    years = sorted({y for (_, y) in table})
    return pop, {"source": f"World Bank SP.POP.TOTL via {Path(path).name}", "year": year,
                 "available_years": [years[0], years[-1]] if years else [], "missing": missing}


def from_attribute(regions: RegionGeometry, key: str, year_key: str | None = None) -> tuple[np.ndarray, dict]:
    """경계 파일의 속성 값(예: Natural Earth POP_EST). 보조 출처로만 쓴다."""
    pop = np.array([float(a.get(key)) if a.get(key) not in (None, "", -99) else np.nan for a in regions.attrs])
    years = sorted({a.get(year_key) for a in regions.attrs if year_key and a.get(year_key) is not None})
    return pop, {"source": f"{regions.source} attribute {key}", "years": years,
                 "missing": [rid for rid, v in zip(regions.ids, pop) if np.isnan(v)]}


def combine(primary: tuple[np.ndarray, dict], fallback: tuple[np.ndarray, dict]) -> tuple[np.ndarray, np.ndarray, dict]:
    """primary 가 NaN 인 곳만 fallback 으로 채운다. 지역별 출처 색인(0 = primary, 1 = fallback, -1 = 없음)을 반환한다."""
    p, pm = primary
    f, fm = fallback
    src = np.where(~np.isnan(p), 0, np.where(~np.isnan(f), 1, -1))
    out = np.where(src == 0, p, np.where(src == 1, f, np.nan))
    return out, src, {"primary": pm, "fallback": fm}


def from_raster(path: str | Path, regions: RegionGeometry) -> tuple[np.ndarray, dict]:
    """인구 수 격자(예: WorldPop ppp, GPW count)의 지역별 합.

    규칙: 셀 중심이 지역 안에 있으면 그 셀 값을 모두 더한다 (nodata 와 음수는 제외).
    1 km 격자와 시도 이상 크기의 지역에서는 경계 셀 할당 오차가 작다. 그 크기는 meta 의 경계 셀 비율로 기록한다.
    """
    import rasterio
    from rasterio.windows import from_bounds

    sums = np.full(regions.K, np.nan)
    boundary_share = np.full(regions.K, np.nan)
    with rasterio.open(path) as ds:
        nodata = ds.nodata
        for k, g in enumerate(regions.geoms):
            minx, miny, maxx, maxy = g.bounds
            win = from_bounds(minx, miny, maxx, maxy, transform=ds.transform).round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height)) if win.width > 0 else win
            arr = ds.read(1, window=win, masked=False).astype(float)
            if arr.size == 0:
                sums[k] = 0.0
                continue
            tr = ds.window_transform(win)
            rows, cols = np.indices(arr.shape)
            xs = tr.c + (cols + 0.5) * tr.a
            ys = tr.f + (rows + 0.5) * tr.e
            inside = shapely.contains_xy(g, xs, ys)
            valid = np.isfinite(arr) & (arr >= 0)
            if nodata is not None:
                valid &= arr != nodata
            sums[k] = float(arr[inside & valid].sum())
            edge = shapely.contains_xy(g.boundary.buffer(abs(tr.a)), xs, ys) & valid
            tot = arr[inside & valid].sum()
            boundary_share[k] = float(arr[edge & inside].sum() / tot) if tot > 0 else 0.0
        meta = {"source": f"raster {Path(path).name}", "crs": str(ds.crs), "res": list(ds.res),
                "rule": "cell-center in polygon", "boundary_cell_share": boundary_share.tolist()}
    return sums, meta
