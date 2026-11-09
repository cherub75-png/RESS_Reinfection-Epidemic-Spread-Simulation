"""자료 시기 선택: ERA5 월 평균 도구, 작은 지역 기후 평균, 시도 경계, 변형본 (실제 자료가 있을 때)."""

import datetime as dt
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

from seir_sim.data import climate, era5
from seir_sim.data.boundaries import _build

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"


def test_era5_hour_index_and_sampling():
    assert era5.hour_index(dt.datetime(1900, 1, 1)) == 0
    assert era5.hour_index(dt.datetime(2025, 7, 1)) == 1100088          # 자료의 time 좌표와 같은 값 (직접 확인)
    t = era5.sample_times("2024-02", "2024-03", hours=(0, 12))
    assert len(t) == 2 * (29 + 31) and t[0] == dt.datetime(2024, 2, 1) and t[-1] == dt.datetime(2024, 3, 31, 12)
    assert len(era5.sample_times("2024-12", "2025-01", hours=(0,))) == 62


def test_era5_tif_longitude_roll(tmp_path):
    """경도 0..359.75 격자를 -180..180 GeoTIFF 로 돌릴 때 셀이 제자리에 가는지."""
    import rasterio
    lon = np.arange(era5.NLON) * 0.25
    lat = 90 - np.arange(era5.NLAT) * 0.25
    grid = (lon[None, :] * 1000 + lat[:, None]).astype(float)          # 값으로 위치를 알 수 있게
    p = tmp_path / "g.tif"
    era5._write_tif(p, grid)
    with rasterio.open(p) as d:
        a = d.read(1)
        for x, y in [(126.75, 37.5), (-0.25, 51.5), (-179.75, -10.0), (179.75, 0.0)]:
            r, c = d.index(x, y)
            assert a[r, c] == pytest.approx((x % 360) * 1000 + y, abs=1e-2)


def test_zonal_mean_tiny_region_uses_representative_cell(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    arr = np.arange(100, dtype="float32").reshape(10, 10)
    p = tmp_path / "t.tif"
    with rasterio.open(p, "w", driver="GTiff", height=10, width=10, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(0, 10, 1, 1)) as d:
        d.write(arr, 1)
    g = _build([({"n": "big"}, box(2, 2, 4, 4)), ({"n": "tiny"}, box(5.40, 5.40, 5.45, 5.45))], ["big", "tiny"],
               ["big", "tiny"], "synthetic")
    out = climate.zonal_mean(p, g)
    assert out[1] == arr[4, 5]                                          # 셀 하나보다 작은 지역: 대표점 셀
    assert np.isfinite(out[0])


needs_raw = pytest.mark.skipif(not (RAW / "admdongkor_sido").exists(), reason="시도 경계 없음 (scripts/fetch_admdongkor.py)")


@needs_raw
def test_kostat_sido_areas_match_official_scale():
    """SGIS 시도 경계 면적이 실제 규모와 맞는지 (Natural Earth 1:10m 은 광주 133 km² 로 크게 작다)."""
    from seir_sim.data.boundaries import load_kostat_sido
    g = load_kostat_sido(RAW / "admdongkor_sido" / "sido_20200101_light.parquet")
    a = dict(zip(g.ids, g.area_km2))
    assert g.K == 17 and len(set(g.ids)) == 17
    for rid, km2 in {"KR-11": 605, "KR-29": 501, "KR-26": 770, "KR-28": 1067}.items():   # 공식 면적 (대략)
        assert a[rid] == pytest.approx(km2, rel=0.12), (rid, a[rid])
    assert sum(a.values()) == pytest.approx(100_400, rel=0.03)


@needs_raw
def test_kostat_sido_2026_merge_keeps_ids_stable():
    from seir_sim.data.boundaries import load_kostat_sido
    files = sorted((RAW / "admdongkor_sido").glob("sido_2026*_light.parquet"))
    g = load_kostat_sido(files[-1])
    assert "KR-11" in g.ids and "KR-45" in g.ids and len(set(g.ids)) == g.K


@pytest.mark.skipif(not (RAW / "worldpop_kor_r2025a_1km").exists() or not (RAW / "admdongkor_sido").exists(),
                    reason="WorldPop 또는 시도 경계 없음")
def test_worldpop_on_sgis_boundaries_matches_secondary_table():
    """WorldPop 2020 을 SGIS 경계로 합산한 값이 2차 자료 시도 인구표와 크게 다르지 않은지 (중앙 차이 < 3%)."""
    import csv
    from seir_sim.data import population as popmod
    from seir_sim.data.boundaries import load_kostat_sido
    g = load_kostat_sido(RAW / "admdongkor_sido" / "sido_20200101_light.parquet")
    pop, _ = popmod.from_raster(RAW / "worldpop_kor_r2025a_1km" / "kor_pop_2020_CN_1km_R2025A_UA_v1.tif", g)
    tab = ROOT / "data_processed" / "tables" / "KOR_admin1_population_gc19od.csv"
    if not tab.exists():
        pytest.skip("2차 자료 인구표 없음")
    ref = {r["id"]: float(r["population"]) for r in csv.DictReader(open(tab, encoding="utf-8"))}
    rel = np.array([pop[k] / ref[i] - 1 for k, i in enumerate(g.ids)])
    assert np.median(np.abs(rel)) < 0.03 and np.max(np.abs(rel)) < 0.2
