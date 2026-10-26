"""항공 이동: OpenFlights 공항·노선 -> 지역 간 1인당 이동률 omega.

OpenFlights 노선은 "항공사-출발 공항-도착 공항" 쌍의 목록이며 승객 수가 없다 (2014년 기준).
따라서 omega 는 다음 명시적 가정으로만 만든다.
  1) 지역 쌍의 상대 이동량은 노선 수에 비례한다: R_ij = i 공항 -> j 공항 노선 수 (codeshare 제외, i != j)
  2) 양방향 이동량이 같다: F_ij = F_ji = trips_per_day * (R_ij + R_ji) / sum(R + R^T)
  3) omega_ij = F_ij / N_i
가정 2) 때문에 omega_ij N_i = omega_ji N_j 이고, 무감염 상태에서 지역 인구가 변하지 않는다 (1-B 발견 사항).
trips_per_day 는 "하루 전체 지역 간 이동 횟수" 이며 자료가 아니라 사용자가 정하는 규모 가정이다.
실제 승객 OD 자료가 생기면 R 대신 그 값을 쓴다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
import shapely.ops

from .boundaries import RegionGeometry


@dataclass
class Airports:
    ids: np.ndarray        # OpenFlights airport id
    iata: list[str]
    lon: np.ndarray
    lat: np.ndarray
    country: list[str]


def _num(v):
    return None if v in ("\\N", "", None) else v


def read_airports(path: str | Path) -> Airports:
    ids, iata, lon, lat, country = [], [], [], [], []
    with open(path, encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 8 or _num(row[0]) is None:
                continue
            try:
                la, lo = float(row[6]), float(row[7])
            except ValueError:
                continue
            ids.append(int(row[0]))
            iata.append(row[4])
            lat.append(la)
            lon.append(lo)
            country.append(row[3])
    return Airports(np.array(ids), iata, np.array(lon), np.array(lat), country)


def read_routes(path: str | Path, exclude_codeshare: bool = True) -> tuple[np.ndarray, dict]:
    """[(출발 공항 id, 도착 공항 id)] 배열. id 가 없는 노선과 codeshare 노선은 뺀다."""
    pairs, n_all, n_noid, n_code = [], 0, 0, 0
    with open(path, encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 8:
                continue
            n_all += 1
            s, d = _num(row[3]), _num(row[5])
            if s is None or d is None:
                n_noid += 1
                continue
            if exclude_codeshare and row[6] == "Y":
                n_code += 1
                continue
            pairs.append((int(s), int(d)))
    return np.array(pairs, dtype=np.int64).reshape(-1, 2), {
        "routes_total": n_all, "dropped_missing_airport_id": n_noid, "dropped_codeshare": n_code}


def assign_points(regions: RegionGeometry, lon: np.ndarray, lat: np.ndarray,
                  snap_km: float = 30.0) -> tuple[np.ndarray, dict]:
    """각 점이 들어 있는 지역 색인 (없으면 -1).

    경계 다각형 밖에 있는 점(해안 공항 등)은 snap_km 안의 가장 가까운 지역에 넣는다.
    경계가 겹치면 먼저 나온 지역에 넣는다.
    """
    from .geo import haversine_km
    out = np.full(lon.size, -1, dtype=np.int64)
    for k, g in enumerate(regions.geoms):
        free = out < 0
        if not free.any():
            break
        inside = shapely.contains_xy(g, lon[free], lat[free])
        out[np.flatnonzero(free)[inside]] = k
    n_inside = int((out >= 0).sum())
    snapped = 0
    if snap_km > 0:
        tree = shapely.STRtree(regions.geoms)
        for q in np.flatnonzero(out < 0):
            pt = shapely.Point(lon[q], lat[q])
            k = tree.nearest(pt)
            if k is None:
                continue
            near = shapely.ops.nearest_points(regions.geoms[k], pt)[0]
            if haversine_km(lon[q], lat[q], near.x, near.y) <= snap_km:
                out[q] = k
                snapped += 1
    return out, {"points_inside": n_inside, "points_snapped": snapped, "snap_km": snap_km,
                 "points_unassigned": int((out < 0).sum())}


def route_matrix(regions: RegionGeometry, airports: Airports, routes: np.ndarray) -> tuple[np.ndarray, dict]:
    reg_of, ameta = assign_points(regions, airports.lon, airports.lat)
    pos = {aid: i for i, aid in enumerate(airports.ids)}
    K = regions.K
    R = np.zeros((K, K))
    unmatched = intra = outside = 0
    for s, d in routes:
        if s not in pos or d not in pos:
            unmatched += 1
            continue
        i, j = reg_of[pos[s]], reg_of[pos[d]]
        if i < 0 or j < 0:
            outside += 1
            continue
        if i == j:
            intra += 1
            continue
        R[i, j] += 1
    meta = {"airports_in_regions": int((reg_of >= 0).sum()), "airports_total": int(airports.ids.size),
            "airport_assignment": ameta,
            "routes_used": int(R.sum()), "routes_unmatched_airport": unmatched,
            "routes_endpoint_outside_regions": outside, "routes_within_one_region": intra}
    return R, meta


def symmetric_air_mobility(R: np.ndarray, population: np.ndarray, trips_per_day: float) -> tuple[np.ndarray, dict]:
    """가정 1)~3) 으로 omega 를 만든다. trips_per_day <= 0 이면 omega = 0."""
    K = R.shape[0]
    if trips_per_day <= 0 or R.sum() == 0:
        return np.zeros((K, K)), {"trips_per_day": trips_per_day, "note": "항공 이동 없음"}
    S = R + R.T
    F = trips_per_day * S / S.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        om = np.where(population[:, None] > 0, F / population[:, None], 0.0)
    np.fill_diagonal(om, 0.0)
    out = om.sum(axis=1)
    return om, {"trips_per_day": trips_per_day, "assumption": "flux proportional to route count, symmetric",
                "max_out_rate_per_day": float(out.max()), "median_out_rate_per_day": float(np.median(out)),
                "high_out_rate_regions_gt_5pct_per_day": int((out > 0.05).sum())}
