"""ERA5 재분석 자료 -> 기간별 월 평균 기온·수증기압 격자 (GeoTIFF) -> 지역별 월 기후표.

자료: ECMWF ERA5 (Copernicus Climate Change Service) 의 Google ARCO-ERA5 사본 (Zarr v3, 0.25°, 1시간 간격).
  https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3
  - 시간 색인 i = 1900-01-01 00UTC 이후 시간 수 (자료의 time 좌표와 같음). 청크 하나 = 한 시각의 전 지구 721 x 1440 격자.
  - 확정 ERA5 의 마지막 날은 Zarr 속성 valid_time_stop (그 뒤는 예비판 ERA5T 이므로 쓰지 않는다).
ERA5 는 관측을 동화한 재분석(모델) 자료다. 관측소 값 그 자체가 아니다.

월 평균 정의 (WorldClim 경로와 같은 정의):
  - 기온 T: 표본 시각의 2 m 기온 평균 (°C).
  - 수증기압 e: 2 m 이슬점 Td 에서 e = e_s(Td) (Tetens, kPa) 의 평균.
  - 상대습도는 지역 평균 단계에서 RH = 100 e / e_s(T) 로 계산한다 (climate.monthly_environment).
  - 표본: 기본 매일 00, 06, 12, 18 UTC (하루 4회). 기간에 여러 해가 있으면 같은 달끼리 모두 평균한다 (기간 기후값).
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

BASE = "https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
NLAT, NLON = 721, 1440
EPOCH = dt.datetime(1900, 1, 1)


def hour_index(t: dt.datetime) -> int:
    return int((t - EPOCH).total_seconds() // 3600)


def _get(url: str, tries: int = 4) -> bytes:
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception:                      # 네트워크 오류: 잠시 뒤 다시 (정책 차단 403 도 여기서 끝내 실패로 남는다)
            if k == tries - 1:
                raise
            time.sleep(2 ** k)
    raise RuntimeError("unreachable")


def dataset_attrs() -> dict:
    meta = json.loads(_get(f"{BASE}/.zmetadata"))["metadata"]
    return meta.get(".zattrs", {})


def _field(var: str, i: int) -> np.ndarray:
    import numcodecs
    raw = numcodecs.Blosc().decode(_get(f"{BASE}/{var}/{i}.0.0"))
    a = np.frombuffer(raw, dtype="<f4")
    if a.size != NLAT * NLON:
        raise ValueError(f"{var}[{i}] 크기 {a.size} (기대 {NLAT * NLON})")
    return a.reshape(NLAT, NLON)


def sample_times(start: str, end: str, hours=(0, 6, 12, 18), day_step: int = 1) -> list[dt.datetime]:
    """start, end = 'YYYY-MM' (양 끝 달 포함)."""
    y0, m0 = map(int, start.split("-"))
    y1, m1 = map(int, end.split("-"))
    d, last = dt.date(y0, m0, 1), dt.date(y1 + (m1 == 12), m1 % 12 + 1, 1)
    out = []
    while d < last:
        out += [dt.datetime(d.year, d.month, d.day, h) for h in hours]
        d += dt.timedelta(days=day_step)
    return out


def monthly_means(start: str, end: str, out_dir: str | Path, hours=(0, 6, 12, 18), day_step: int = 1,
                  workers: int = 16, log=print) -> dict:
    """기간의 달력 월별 평균 T(°C)·e(kPa) 격자를 GeoTIFF 로 쓴다: era5_tavg_MM.tif, era5_vapr_MM.tif (MM = 01..12).

    기간에 없는 달은 파일을 만들지 않는다 (미확보). 확정 ERA5 범위 밖의 시각은 거부한다.
    """
    from .climate import saturation_vapor_pressure_kpa
    attrs = dataset_attrs()
    stop = dt.datetime.fromisoformat(attrs["valid_time_stop"]) + dt.timedelta(hours=23)
    begin = dt.datetime.fromisoformat(attrs["valid_time_start"])
    times = sample_times(start, end, hours, day_step)
    bad = [t for t in times if t < begin or t > stop]
    if bad:
        raise ValueError(f"확정 ERA5 범위({attrs['valid_time_start']} ~ {attrs['valid_time_stop']}) 밖의 시각이 있다: {bad[0]} …")
    sT = np.zeros((12, NLAT, NLON))
    sE = np.zeros((12, NLAT, NLON))
    n = np.zeros(12, int)

    def one(t):
        i = hour_index(t)
        T = _field("2m_temperature", i).astype(float) - 273.15
        E = saturation_vapor_pressure_kpa(_field("2m_dewpoint_temperature", i).astype(float) - 273.15)
        return t.month - 1, T, E

    t0 = time.perf_counter()
    with ThreadPoolExecutor(workers) as ex:
        for k, (m, T, E) in enumerate(ex.map(one, times), 1):
            sT[m] += T
            sE[m] += E
            n[m] += 1
            if k % 100 == 0 or k == len(times):
                log(f"ERA5 {k}/{len(times)} 시각 ({time.perf_counter() - t0:.0f}초)")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for m in range(12):
        if n[m] == 0:
            continue
        for name, s in (("tavg", sT[m] / n[m]), ("vapr", sE[m] / n[m])):
            p = out / f"era5_{name}_{m + 1:02d}.tif"
            _write_tif(p, s)
            files[f"{name}_{m + 1:02d}"] = p.name
    prov = {"source": "ERA5 (ECMWF / Copernicus C3S), Google ARCO-ERA5 사본", "url": BASE,
            "dataset_last_updated": attrs.get("last_updated"), "valid_time_stop": attrs.get("valid_time_stop"),
            "period": f"{start} ~ {end}", "hours_utc": list(hours), "day_step": day_step,
            "samples_per_month": {f"{m + 1:02d}": int(n[m]) for m in range(12)},
            "variables": {"tavg": "2m_temperature 평균 (°C)", "vapr": "e_s(2m_dewpoint_temperature) 평균 (kPa, Tetens)"},
            "kind": "재분석 (관측 동화 모델 자료, 관측소 값 아님)", "license": "Copernicus licence (출처 표시: Contains modified Copernicus Climate Change Service information)",
            "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "files": files,
            "wall_seconds": round(time.perf_counter() - t0, 1)}
    (out / "provenance.json").write_text(json.dumps(prov, indent=1, ensure_ascii=False))
    return prov


def _write_tif(path: Path, grid: np.ndarray) -> None:
    """ERA5 격자 (위도 90 -> -90, 경도 0 -> 359.75) 를 경도 -180 ~ 180 으로 돌려 GeoTIFF (EPSG:4326) 로 쓴다."""
    import rasterio
    from rasterio.transform import from_origin
    g = np.roll(grid, NLON // 2, axis=1).astype("float32")          # 경도 180..359.75 를 앞으로 -> -180..179.75
    tr = from_origin(-180.125, 90.125, 0.25, 0.25)                    # 셀 중심이 격자점에 오도록
    with rasterio.open(path, "w", driver="GTiff", height=NLAT, width=NLON, count=1, dtype="float32",
                       crs="EPSG:4326", transform=tr, compress="deflate") as ds:
        ds.write(g, 1)


def region_table(period_dir: str | Path, regions, ids: list[str], out_csv: str | Path) -> dict:
    """기간 폴더의 월 격자 -> 지역별 월 기후표 CSV (id, month, tavg, rh, source, period). 없는 달은 쓰지 않는다."""
    import csv
    from .climate import relative_humidity, zonal_mean
    d = Path(period_dir)
    prov = json.loads((d / "provenance.json").read_text())
    rows = []
    for m in range(1, 13):
        ft, fv = d / f"era5_tavg_{m:02d}.tif", d / f"era5_vapr_{m:02d}.tif"
        if not (ft.exists() and fv.exists()):
            continue
        T = zonal_mean(ft, regions)
        RH = relative_humidity(T, zonal_mean(fv, regions))
        for k, rid in enumerate(ids):
            rows.append({"id": rid, "month": m, "tavg": "" if not np.isfinite(T[k]) else round(float(T[k]), 3),
                         "rh": "" if not np.isfinite(RH[k]) else round(float(RH[k]), 3),
                         "source": "ERA5 재분석 (Google ARCO-ERA5), 셀 중심 포함·cos(위도) 가중 평균",
                         "period": prov["period"]})
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "month", "tavg", "rh", "source", "period"])
        w.writeheader()
        w.writerows(rows)
    return {"rows": len(rows), "months": sorted({r["month"] for r in rows}), "period": prov["period"]}


# ------------------------------------------------------------------ 지역별 주간 계열 (예측 특성용)
def cell_weights(regions) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ERA5 0.25° 격자 셀 -> 지역 대응 (셀 번호, 지역 번호, cos 위도 가중치). 셀 중심이 지역 안에 있는 셀,
    하나도 없으면 대표점에서 가장 가까운 셀 하나 (zonal_mean 과 같은 규칙)."""
    import shapely
    lat = 90.0 - 0.25 * np.arange(NLAT)
    lon = 0.25 * np.arange(NLON)
    lon180 = ((lon + 180.0) % 360.0) - 180.0
    cells, regs, wts = [], [], []
    for k, g in enumerate(regions.geoms):
        x0, y0, x1, y1 = g.bounds
        ri = np.flatnonzero((lat >= y0 - 0.25) & (lat <= y1 + 0.25))
        ci = np.flatnonzero((lon180 >= x0 - 0.25) & (lon180 <= x1 + 0.25))
        found = False
        if ri.size and ci.size:
            R, C = np.meshgrid(ri, ci, indexing="ij")
            inside = shapely.contains_xy(g, lon180[C], lat[R])
            if inside.any():
                r, c = R[inside], C[inside]
                cells.append(r * NLON + c)
                regs.append(np.full(r.size, k))
                wts.append(np.cos(np.radians(lat[r])))
                found = True
        if not found:
            p = g.representative_point()
            r = int(np.argmin(np.abs(lat - p.y)))
            c = int(np.argmin(np.abs(((lon180 - p.x + 180.0) % 360.0) - 180.0)))
            cells.append(np.array([r * NLON + c]))
            regs.append(np.array([k]))
            wts.append(np.array([np.cos(np.radians(lat[r]))]))
    return np.concatenate(cells), np.concatenate(regs), np.concatenate(wts)


def _field_or_none(var: str, i: int):
    try:
        return _field(var, i)
    except Exception:                    # 아직 없는 시각 (확정·예비판 범위 밖) 은 결측
        return None


def weekly_region_series(regions, ids: list[str], start_week: str, end_week: str, hours=(0, 12),
                         workers: int = 16, log=print) -> "pd.DataFrame":
    """지역별 ISO 주(월요일 시작) 평균 2 m 기온 T(°C), 수증기압 e(kPa), 절대습도 AH(g/m³).

    AH = 2166.8 e / (T + 273.15) (e = e_s(이슬점), Tetens). 표본: 매일 hours (UTC) 시각.
    확정 ERA5 마지막 날 뒤는 ERA5T 예비판이다 (era5t_samples 로 표시). 예비판도 없는 시각은 빠진다.
    """
    import pandas as pd

    from .climate import saturation_vapor_pressure_kpa
    attrs = dataset_attrs()
    stop = dt.datetime.fromisoformat(attrs["valid_time_stop"]) + dt.timedelta(hours=23)
    stop_t = dt.datetime.fromisoformat(attrs.get("valid_time_stop_era5t", attrs["valid_time_stop"])) + dt.timedelta(hours=23)
    cells, regs, w = cell_weights(regions)
    K = len(ids)
    wsum = np.bincount(regs, weights=w, minlength=K)
    weeks = pd.date_range(start_week, end_week, freq="7D")
    if (weeks.dayofweek != 0).any():
        raise ValueError("start_week 는 월요일이어야 한다")
    times = [dt.datetime(d.year, d.month, d.day, h) for d in pd.date_range(weeks[0], weeks[-1] + pd.Timedelta(days=6)) for h in hours]
    times = [t for t in times if t <= stop_t]
    sT = np.zeros((len(weeks), K))
    sE = np.zeros((len(weeks), K))
    n = np.zeros(len(weeks), int)
    nt = np.zeros(len(weeks), int)
    w0 = weeks[0].to_pydatetime()

    def one(t):
        i = hour_index(t)
        a, b = _field_or_none("2m_temperature", i), _field_or_none("2m_dewpoint_temperature", i)
        if a is None or b is None:
            return t, None, None
        T = a.ravel()[cells].astype(float) - 273.15
        E = saturation_vapor_pressure_kpa(b.ravel()[cells].astype(float) - 273.15)
        return t, np.bincount(regs, weights=w * T, minlength=K) / wsum, np.bincount(regs, weights=w * E, minlength=K) / wsum

    import time as _time
    t0 = _time.perf_counter()
    with ThreadPoolExecutor(workers) as ex:
        for k, (t, T, E) in enumerate(ex.map(one, times), 1):
            if T is not None:
                j = (t - w0).days // 7
                sT[j] += T
                sE[j] += E
                n[j] += 1
                nt[j] += t > stop
            if k % 500 == 0 or k == len(times):
                log(f"ERA5 주간 {k}/{len(times)} 시각 ({_time.perf_counter() - t0:.0f}초)")
    rows = []
    for j, wk in enumerate(weeks):
        if n[j] == 0:
            continue
        T, E = sT[j] / n[j], sE[j] / n[j]
        for k, rid in enumerate(ids):
            rows.append((wk, rid, T[k], E[k], 2166.8 * E[k] / (T[k] + 273.15), int(n[j]), int(nt[j])))
    out = pd.DataFrame(rows, columns=["week", "id", "tavg", "vapr", "ah", "samples", "era5t_samples"])
    out.attrs.update({"source": "ERA5 (Google ARCO-ERA5)", "url": BASE, "hours_utc": list(hours),
                      "valid_time_stop": attrs["valid_time_stop"], "valid_time_stop_era5t": attrs.get("valid_time_stop_era5t"),
                      "dataset_last_updated": attrs.get("last_updated"), "rule": "셀 중심 포함, cos(위도) 가중",
                      "wall_seconds": round(_time.perf_counter() - t0, 1)})
    return out
