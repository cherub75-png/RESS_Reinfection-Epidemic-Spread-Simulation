"""기후: 월별 격자(예: WorldClim 2.1 tavg, vapr) -> 지역별 월 평균 -> 일 단위 환경 시계열.

- 지역 평균: 셀 중심이 지역 안에 있는 셀의 평균. 위경도 격자는 cos(위도) 로 면적 가중한다.
- 상대습도: WorldClim vapr(수증기압, kPa) 과 기온 T(°C) 에서 Tetens 식으로 계산한다.
    e_s(T) = 0.6108 exp(17.27 T / (T + 237.3))  [kPa],   RH = 100 e / e_s  (0~100 으로 자름)
- 일 단위 시계열: 그 날이 속한 달의 값을 쓴다 (구간별 상수; Drivers 의 정확한 구간 처리와 맞음).
기후평년값(1970-2000)은 특정 연도의 날씨가 아니다. 과거 유행 재현(2단계)에는 ERA5 같은 일별 재분석 자료가 필요하다.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import shapely

from ..model.drivers import EnvironmentSeries
from .boundaries import RegionGeometry


def saturation_vapor_pressure_kpa(T):
    T = np.asarray(T, dtype=float)
    return 0.6108 * np.exp(17.27 * T / (T + 237.3))


def relative_humidity(T, vapor_kpa):
    return np.clip(100.0 * np.asarray(vapor_kpa, float) / saturation_vapor_pressure_kpa(T), 0.0, 100.0)


def zonal_mean(path: str | Path, regions: RegionGeometry, band: int = 1) -> np.ndarray:
    import rasterio
    import rasterio.errors
    from rasterio.windows import Window, from_bounds

    out = np.full(regions.K, np.nan)
    with rasterio.open(path) as ds:
        geographic = ds.crs is None or ds.crs.is_geographic
        for k, g in enumerate(regions.geoms):
            win = from_bounds(*g.bounds, transform=ds.transform).round_offsets().round_lengths()
            try:
                win = win.intersection(Window(0, 0, ds.width, ds.height))
                arr = ds.read(band, window=win).astype(float)
            except rasterio.errors.WindowError:     # 셀 하나보다 작은 지역: 창이 비면 대표점 셀로
                arr = np.empty((0, 0))
            ok = np.zeros(arr.shape, bool)
            if arr.size:
                tr = ds.window_transform(win)
                rows, cols = np.indices(arr.shape)
                xs = tr.c + (cols + 0.5) * tr.a
                ys = tr.f + (rows + 0.5) * tr.e
                ok = shapely.contains_xy(g, xs, ys) & np.isfinite(arr)
                if ds.nodata is not None:
                    ok &= arr != ds.nodata
            if not ok.any():
                c = g.representative_point()        # 지역이 셀보다 작으면 대표점의 셀 값
                r, cidx = ds.index(c.x, c.y)
                if 0 <= r < ds.height and 0 <= cidx < ds.width:
                    v = ds.read(band, window=Window(cidx, r, 1, 1)).astype(float)[0, 0]
                    out[k] = v if (ds.nodata is None or v != ds.nodata) else np.nan
                continue
            w = np.cos(np.radians(ys)) if geographic else np.ones_like(ys)
            out[k] = float(np.sum(arr[ok] * w[ok]) / np.sum(w[ok]))
    return out


def monthly_environment(tavg_paths: list[str | Path], vapr_paths: list[str | Path],
                        regions: RegionGeometry) -> tuple[np.ndarray, np.ndarray, dict]:
    """12개 월 파일 -> (기온 [12, K], 상대습도 [12, K])."""
    if len(tavg_paths) != 12 or len(vapr_paths) != 12:
        raise ValueError("월별 파일이 12개씩 필요하다")
    T = np.stack([zonal_mean(p, regions) for p in tavg_paths])
    E = np.stack([zonal_mean(p, regions) for p in vapr_paths])
    return T, relative_humidity(T, E), {"tavg": [Path(p).name for p in tavg_paths],
                                         "vapr": [Path(p).name for p in vapr_paths],
                                         "rule": "cell-center in polygon, cos(lat) weighted mean; RH from Tetens"}


def daily_series(monthly_T: np.ndarray, monthly_RH: np.ndarray, start_date: dt.date, days: int,
                 provenance: dict | None = None) -> EnvironmentSeries:
    dates = [start_date + dt.timedelta(days=d) for d in range(int(days) + 1)]
    m = np.array([d.month - 1 for d in dates])
    return EnvironmentSeries(np.asarray(monthly_T)[m], np.asarray(monthly_RH)[m], synthetic=False,
                             provenance={"monthly_climatology": True, **(provenance or {})})


def attach_monthly_table(ds, path: str | Path):
    """지역별 월 기후표 (CSV: id, month(1~12), tavg, rh[, source, period, note]) 를 데이터셋에 붙인다 (로컬 파일 입력 경로).

    표에 없는 (지역, 월) 은 NaN (미확보) 이다. 보간하지 않는다. 출처와 기간 열은 provenance 에 남긴다.
    """
    import csv
    from dataclasses import replace
    idx = {r: i for i, r in enumerate(ds.ids)}
    T = np.full((12, ds.K), np.nan)
    RH = np.full((12, ds.K), np.nan)
    sources, periods = set(), set()
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            i = idx.get(row["id"])
            if i is None:
                continue
            m = int(row["month"]) - 1
            if not 0 <= m < 12:
                raise ValueError(f"month 는 1~12: {row}")
            T[m, i] = float(row["tavg"]) if row["tavg"] not in ("", "nan") else np.nan
            RH[m, i] = float(row["rh"]) if row["rh"] not in ("", "nan") else np.nan
            sources.add(row.get("source", ""))
            periods.add(row.get("period", ""))
    if np.any((RH < 0) | (RH > 100)):
        raise ValueError("상대습도는 0~100 이어야 한다")
    prov = {**ds.provenance, "climate": {"table": Path(path).name, "sources": sorted(sources), "periods": sorted(periods),
                                         "missing_cells": int(np.isnan(T).sum() + np.isnan(RH).sum()),
                                         "note": "월별 평균표. 기후평년값이 아닐 수 있음 (periods 참고)"}}
    return replace(ds, tavg=T, rh=RH, provenance=prov)
