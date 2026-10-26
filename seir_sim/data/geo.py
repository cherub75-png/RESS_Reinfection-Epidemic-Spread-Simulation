"""지리 계산: GeoJSON 읽기, 측지 면적, 대표 좌표, 대원 거리. 특정 국가와 무관하다."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon, shape

GEOD = Geod(ellps="WGS84")
EARTH_RADIUS_KM = 6371.0088      # 평균 반지름 (IUGG)


def read_geojson(path: str | Path) -> list[tuple[dict, object]]:
    """[(properties, shapely geometry)] 를 반환한다. 기하가 없는 항목은 건너뛴다."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = []
    for f in data["features"]:
        if f.get("geometry") is None:
            continue
        out.append((f["properties"], shape(f["geometry"])))
    return out


def geodesic_area_km2(geom) -> float:
    """WGS84 타원체 위의 면적 [km^2]."""
    area, _ = GEOD.geometry_area_perimeter(geom)
    return abs(area) / 1e6


def _parts(geom):
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    raise TypeError(f"다각형이 아니다: {geom.geom_type}")


def area_weighted_center(geom) -> tuple[float, float]:
    """조각별 중심을 3차원 단위벡터로 바꿔 면적 가중 평균한 (경도, 위도).

    날짜변경선(±180°)에 걸친 지역(예: 피지, 러시아 동부)도 평면 평균의 오류 없이 계산된다.
    """
    v = np.zeros(3)
    for p in _parts(geom):
        c = p.centroid
        lon, lat = np.radians(c.x), np.radians(c.y)
        w = geodesic_area_km2(p)
        v += w * np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    if not np.any(v):
        c = geom.representative_point()
        return float(c.x), float(c.y)
    lon = np.degrees(np.arctan2(v[1], v[0]))
    lat = np.degrees(np.arctan2(v[2], np.hypot(v[0], v[1])))
    return float(lon), float(lat)


def haversine_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def distance_matrix_km(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    return haversine_km(lon[:, None], lat[:, None], lon[None, :], lat[None, :])
