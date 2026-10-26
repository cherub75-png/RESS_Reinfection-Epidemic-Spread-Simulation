"""행정 경계 -> 지역 단위 i. 국가 단위(Admin 0)와 1급 행정구역(Admin 1)을 같은 형식으로 만든다."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from shapely import unary_union

from .geo import area_weighted_center, geodesic_area_km2, read_geojson


@dataclass
class RegionGeometry:
    ids: list[str]
    names: list[str]
    geoms: list
    area_km2: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    attrs: list[dict] = field(default_factory=list)
    source: str = ""
    merged: dict = field(default_factory=dict)      # id -> 합친 부속 다각형 이름들

    @property
    def K(self) -> int:
        return len(self.ids)

    def subset(self, keep: np.ndarray) -> "RegionGeometry":
        idx = np.flatnonzero(keep)
        return RegionGeometry([self.ids[i] for i in idx], [self.names[i] for i in idx],
                              [self.geoms[i] for i in idx], self.area_km2[idx], self.lon[idx], self.lat[idx],
                              [self.attrs[i] for i in idx], self.source,
                              {k: v for k, v in self.merged.items() if k in {self.ids[i] for i in idx}})


def _build(items, ids, names, source) -> RegionGeometry:
    """같은 id 의 다각형은 하나로 합친다 (예: 본국 코드를 쓰는 작은 부속 영토). 이름·속성은 가장 넓은 것."""
    groups: dict[str, list[int]] = {}
    for k, i in enumerate(ids):
        groups.setdefault(i, []).append(k)
    out_ids, out_names, geoms, attrs, merged = [], [], [], [], {}
    for rid, ks in groups.items():
        areas = [geodesic_area_km2(items[k][1]) for k in ks]
        main = ks[int(np.argmax(areas))]
        g = items[ks[0]][1] if len(ks) == 1 else unary_union([items[k][1] for k in ks])
        if len(ks) > 1:
            merged[rid] = [names[k] for k in ks if k != main]
        out_ids.append(rid)
        out_names.append(names[main])
        geoms.append(g)
        attrs.append(dict(items[main][0]))
    centers = np.array([area_weighted_center(g) for g in geoms]).reshape(-1, 2)
    area = np.array([geodesic_area_km2(g) for g in geoms])
    return RegionGeometry(out_ids, out_names, geoms, area, centers[:, 0], centers[:, 1], attrs, source, merged)


def country_code(props: dict) -> str:
    """Natural Earth 국가 코드. ISO_A3 가 -99 인 경우(예: 일부 영토) ISO_A3_EH, ADM0_A3 순으로 쓴다."""
    for key in ("ISO_A3", "ISO_A3_EH", "ADM0_A3"):
        v = props.get(key)
        if v and v != "-99":
            return v
    raise ValueError(f"국가 코드가 없다: {props.get('NAME')}")


def load_admin0(path: str | Path) -> RegionGeometry:
    """Natural Earth Admin 0 -> 국가 단위 지역. id = ISO 3166-1 alpha-3 (위 규칙)."""
    items = read_geojson(path)
    ids = [country_code(p) for p, _ in items]
    names = [p.get("NAME_EN") or p.get("NAME") for p, _ in items]
    return _build(items, ids, names, f"Natural Earth admin 0: {Path(path).name}")


def load_admin1(path: str | Path, country_a3: str) -> RegionGeometry:
    """Natural Earth Admin 1 에서 한 나라의 1급 행정구역. id = ISO 3166-2 (없으면 adm1_code)."""
    items = [(p, g) for p, g in read_geojson(path) if p.get("adm0_a3") == country_a3]
    if not items:
        raise ValueError(f"{country_a3} 의 1급 행정구역이 없다")
    ids = [p.get("iso_3166_2") if p.get("iso_3166_2") not in (None, "", "-99") else p["adm1_code"] for p, _ in items]
    names = [p.get("name_en") or p.get("name") for p, _ in items]
    return _build(items, ids, names, f"Natural Earth admin 1 ({country_a3}): {Path(path).name}")
