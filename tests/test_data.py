"""1-D: 데이터 계층 검증 (합성 기하·격자로 정확한 기댓값을 아는 경우 + 실제 자료가 있으면 점검)."""

from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from seir_sim.data import climate, commuting, mobility
from seir_sim.data import population as popmod
from seir_sim.data.boundaries import RegionGeometry, _build
from seir_sim.data.dataset import RegionDataset
from seir_sim.data.geo import EARTH_RADIUS_KM, area_weighted_center, geodesic_area_km2, haversine_km

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"


def _geo(boxes, names=None):
    items = [({"name": n}, g) for n, g in zip(names or [f"r{i}" for i in range(len(boxes))], boxes)]
    return _build(items, [p["name"] for p, _ in items], [p["name"] for p, _ in items], "synthetic")


# --------------------------------------------------------------------- 지리 계산

def _ellipsoid_band_area_km2(lon1, lon2, lat1, lat2):
    """WGS84 타원체 위 위경도 사각형의 정확한 면적 (authalic q 함수)."""
    a, f = 6378.137, 1 / 298.257223563
    e2 = f * (2 - f)
    e = np.sqrt(e2)

    def q(phi):
        s = np.sin(np.radians(phi))
        return (1 - e2) * (s / (1 - e2 * s * s) - np.log((1 - e * s) / (1 + e * s)) / (2 * e))
    return a * a * np.radians(lon2 - lon1) / 2 * (q(lat2) - q(lat1))


@pytest.mark.parametrize("lat", [0.0, 37.0, 60.0, -75.0])
def test_geodesic_area_matches_exact_ellipsoid_formula(lat):
    """위경도 0.5° 사각형: pyproj 측지 면적 = 타원체 정확식 (상대 1e-4; 사각형 변이 측지선이 아니라 위선이라 생기는 차이 포함)."""
    g = box(10.0, lat, 10.5, lat + 0.5)
    assert geodesic_area_km2(g) == pytest.approx(_ellipsoid_band_area_km2(10.0, 10.5, lat, lat + 0.5), rel=1e-4)


def test_center_handles_antimeridian():
    """날짜변경선 양쪽 조각의 중심은 경도 ±180 근처여야 한다 (평면 평균이면 0 이 되는 오류)."""
    g = MultiPolygon([box(178, -18, 180, -16), box(-180, -18, -178, -16)])
    lon, lat = area_weighted_center(g)
    assert abs(abs(lon) - 180) < 0.5 and lat == pytest.approx(-17, abs=0.1)


def test_haversine_quarter_circumference():
    assert haversine_km(0, 0, 90, 0) == pytest.approx(np.pi / 2 * EARTH_RADIUS_KM, rel=1e-12)


def test_duplicate_ids_are_merged():
    items = [({"name": "A"}, box(0, 0, 2, 2)), ({"name": "A-island"}, box(5, 5, 5.1, 5.1)), ({"name": "B"}, box(3, 0, 4, 1))]
    g = _build(items, ["A", "A", "B"], ["A", "A-island", "B"], "t")
    assert g.ids == ["A", "B"] and g.names == ["A", "B"] and g.merged == {"A": ["A-island"]}
    assert g.area_km2[0] == pytest.approx(geodesic_area_km2(box(0, 0, 2, 2)) + geodesic_area_km2(box(5, 5, 5.1, 5.1)))


# --------------------------------------------------------------------- 인구

def test_worldbank_csv_join(tmp_path):
    f = tmp_path / "pop.csv"
    f.write_text("Country Name,Country Code,Year,Value\nA,AAA,2019,100\nA,AAA,2020,110\nB,BBB,2020,5\n")
    geo = _geo([box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)], ["AAA", "BBB", "CCC"])
    pop, meta = popmod.from_worldbank_csv(f, geo, 2020)
    np.testing.assert_array_equal(pop[:2], [110, 5])
    assert np.isnan(pop[2]) and meta["missing"] == ["CCC"]
    fb = (np.array([np.nan, 7.0, 9.0]), {"m": 1})
    out, src, _ = popmod.combine((pop, meta), fb)
    np.testing.assert_array_equal(out, [110, 5, 9]) and np.testing.assert_array_equal(src, [0, 0, 1])


def _write_raster(path, arr, west, north, res):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="float64", crs="EPSG:4326", transform=from_origin(west, north, res, res),
                       nodata=-9999.0) as ds:
        ds.write(arr, 1)


def test_raster_zonal_sum_exact(tmp_path):
    """셀 중심 규칙: 칸 경계에 맞춘 지역은 정확히 그 칸들의 합이 된다. nodata 는 빠진다."""
    arr = np.arange(100, dtype=float).reshape(10, 10)
    arr[0, 0] = -9999.0
    f = tmp_path / "pop.tif"
    _write_raster(f, arr, 0.0, 10.0, 1.0)
    geo = _geo([box(0, 5, 5, 10), box(5, 0, 10, 5), box(0, 0, 10, 10)])
    sums, meta = popmod.from_raster(f, geo)
    assert sums[0] == pytest.approx(arr[0:5, 0:5].sum() + 9999.0)       # nodata 제외
    assert sums[1] == pytest.approx(arr[5:10, 5:10].sum())
    assert sums[2] == pytest.approx(arr.sum() + 9999.0)
    assert meta["rule"] == "cell-center in polygon"


# --------------------------------------------------------------------- 이동·접촉

def test_point_assignment_and_snap():
    geo = _geo([box(0, 0, 1, 1), box(2, 0, 3, 1)])
    lon = np.array([0.5, 2.5, 1.1, 10.0])
    lat = np.array([0.5, 0.5, 0.5, 10.0])
    reg, meta = mobility.assign_points(geo, lon, lat, snap_km=20.0)
    np.testing.assert_array_equal(reg, [0, 1, 0, -1])        # 1.1 은 0.1° (11km) 밖 -> 0 에 붙임
    assert meta["points_snapped"] == 1 and meta["points_unassigned"] == 1


def test_symmetric_air_mobility_is_balanced_and_scaled():
    R = np.array([[0, 5, 0], [1, 0, 2], [0, 0, 0.0]])
    pop = np.array([1e6, 2e5, 5e5])
    om, meta = mobility.symmetric_air_mobility(R, pop, trips_per_day=1000.0)
    flux = om * pop[:, None]
    np.testing.assert_allclose(flux, flux.T, rtol=1e-12)
    assert flux.sum() == pytest.approx(1000.0)
    np.testing.assert_allclose(flux[0, 1] / flux[1, 2], (5 + 1) / 2)
    assert np.all(np.diag(om) == 0)
    om0, _ = mobility.symmetric_air_mobility(R, pop, 0.0)
    assert not om0.any()


def test_radiation_model_known_values():
    """세 지역이 한 줄(경도 0, 1, 2)에 있을 때 radiation 식을 직접 계산한 값과 같다."""
    pop = np.array([100.0, 200.0, 300.0])
    lon, lat = np.array([0.0, 1.0, 2.0]), np.zeros(3)
    W = commuting.radiation_shares(pop, lon, lat)
    m, n = pop[0], pop
    t01 = m * n[1] / ((m + 0) * (m + n[1] + 0))
    t02 = m * n[2] / ((m + n[1]) * (m + n[2] + n[1]))
    np.testing.assert_allclose(W[0, 1:], np.array([t01, t02]) / (t01 + t02), rtol=1e-12)
    np.testing.assert_allclose(W.sum(axis=1), 1.0)
    C = commuting.contact_matrix(W, 0.1, 0.5)
    np.testing.assert_allclose(C.sum(axis=1), 1.0)
    np.testing.assert_allclose(np.diag(C), 0.95)
    with pytest.raises(ValueError):
        commuting.contact_matrix(W, 2.0, 0.9)


# --------------------------------------------------------------------- 기후

def test_relative_humidity_tetens():
    """20°C 포화수증기압 2.338 kPa (Tetens) -> e = 1.169 kPa 이면 RH = 50%."""
    es = climate.saturation_vapor_pressure_kpa(20.0)
    assert es == pytest.approx(2.3383, rel=1e-3)
    assert climate.relative_humidity(20.0, es / 2) == pytest.approx(50.0, rel=1e-9)
    assert climate.relative_humidity(20.0, 10.0) == 100.0


def test_climate_zonal_mean_and_daily_series(tmp_path):
    import datetime as dt
    arr = np.tile(np.arange(10, dtype=float), (10, 1))        # 경도 방향으로 값이 0..9
    f = tmp_path / "t.tif"
    _write_raster(f, arr, 0.0, 10.0, 1.0)
    geo = _geo([box(0, 0, 2, 10), box(8, 0, 10, 10)])
    v = climate.zonal_mean(f, geo)
    np.testing.assert_allclose(v, [0.5, 8.5], rtol=1e-12)    # 같은 경도대이므로 cos 가중과 무관
    T = np.arange(12)[:, None] * np.ones((1, 2))
    env = climate.daily_series(T, T + 50, dt.date(2020, 1, 30), 3)
    np.testing.assert_allclose(env.temperature[:, 0], [0, 0, 1, 1])   # 1/30, 1/31, 2/1, 2/2


# --------------------------------------------------------------------- 데이터셋 파일

def test_dataset_roundtrip_and_missing_population(tmp_path):
    K = 3
    ds = RegionDataset(["a", "b", "c"], ["A", "B", "C"], np.array([1e5, 2e5, 3e5]), np.array([10.0, 20.0, 30.0]),
                       np.zeros(K), np.zeros(K), np.eye(K), np.zeros((K, K)), {"x": 1}, synthetic=True)
    f = tmp_path / "d.nc"
    ds.save(f)
    back = RegionDataset.load(f)
    assert back.ids == ds.ids and back.names == ds.names and back.synthetic is True
    np.testing.assert_array_equal(back.population, ds.population)
    assert back.provenance == {"x": 1}
    rs = back.to_region_set()
    np.testing.assert_allclose(rs.density, [1e4, 1e4, 1e4])
    ds.population[1] = np.nan
    with pytest.raises(ValueError, match="미확보"):
        ds.to_region_set()


# --------------------------------------------------------------------- 실제 자료 점검 (있을 때만)

needs_raw = pytest.mark.skipif(not (RAW / "manifest.json").exists(), reason="data_raw 없음 (scripts/fetch_data.py)")


@needs_raw
def test_real_world_countries_dataset_quality(tmp_path):
    from seir_sim.data.build import build_world_countries
    d = build_world_countries(RAW / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson",
                              RAW / "wb_population" / "population.csv", 2019,
                              RAW / "openflights" / "airports.dat", RAW / "openflights" / "routes.dat",
                              5e6, 0.002, 0.3)
    q = d.quality()
    assert d.K > 230 and not q["missing_population"]
    assert q["mobility_imbalance_per_day"] < 1e-12 and q["contact_row_sum_max_dev"] < 1e-12
    assert 7.6e9 < d.population.sum() < 7.9e9                  # World Bank 2019 세계 인구 7.78e9
    i = d.ids.index("KOR")
    assert 5.0e7 < d.population[i] < 5.3e7 and 9.5e4 < d.area_km2[i] < 1.05e5
    assert d.provenance["population"]["per_region_source"]["KOR"] == "worldbank"
    assert d.provenance["mobility"]["routes_endpoint_outside_regions"] < 100


@needs_raw
def test_real_korea_admin1_boundaries():
    from seir_sim.data.boundaries import load_admin1
    g = load_admin1(RAW / "ne_admin1_10m" / "ne_10m_admin_1_states_provinces.geojson", "KOR")
    assert g.K == 17 and "KR-11" in g.ids and "KR-50" in g.ids        # 서울, 세종
    seoul = g.area_km2[g.ids.index("KR-11")]
    assert 500 < seoul < 700                                            # 실제 약 605 km^2 (1:10m 일반화)
    assert 1.0e5 > g.area_km2.sum() > 9.0e4
