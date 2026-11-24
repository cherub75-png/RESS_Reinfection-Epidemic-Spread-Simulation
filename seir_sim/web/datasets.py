"""웹: 데이터셋 경계 GeoJSON, 인구표 업로드로 새 버전 만들기 (등록만 하고 활성화는 사용자가 따로 한다)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data_raw"
CACHE = ROOT / "outputs" / "web_cache"
MAX_TABLE_BYTES = 2_000_000


def _scope(prov: dict) -> tuple[str, str | None]:
    sc = str(prov.get("scope", ""))
    if sc.startswith("world"):
        return "admin0", None
    if "admin 1" in sc:
        return "admin1", sc.split(",")[0].strip()
    return "unknown", None


def geojson_for(name: str, version: str | None = None) -> dict:
    """등록 데이터셋 지역의 단순화 경계 (Natural Earth). 캐시한다."""
    import shapely
    from ..data.boundaries import load_admin0, load_admin1
    from ..data.dataset import RegionDataset
    from ..data.versions import Registry
    reg = Registry()
    e = reg.list()[name]
    version = version or e["active"]
    cache = CACHE / f"{name}_{version}.geojson"
    if cache.exists():
        return json.loads(cache.read_text())
    ds = RegionDataset.load(reg.resolve(f"{name}@{version}"))
    kind, a3 = _scope(ds.provenance)
    if ds.provenance.get("boundary_file"):                     # 통계청 SGIS 시도 경계 (admdongkor 시점 파일)
        from ..data.boundaries import load_kostat_sido
        geo = load_kostat_sido(RAW / "admdongkor_sido" / ds.provenance["boundary_file"])
        tol = 0.005
    elif kind == "admin0":
        geo = load_admin0(RAW / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson")
        tol = 0.08
    elif kind == "admin1":
        geo = load_admin1(RAW / "ne_admin1_10m" / "ne_10m_admin_1_states_provinces.geojson", a3)
        tol = 0.01
    else:
        raise ValueError(f"{name}: 경계 출처를 알 수 없다")
    gi = {r: k for k, r in enumerate(geo.ids)}
    feats = []
    for k, rid in enumerate(ds.ids):
        if rid not in gi:
            continue
        g = shapely.simplify(geo.geoms[gi[rid]], tol, preserve_topology=True)
        feats.append({"type": "Feature", "id": rid,
                      "properties": {"id": rid, "name": ds.names[k], "population": float(ds.population[k])
                                     if np.isfinite(ds.population[k]) else None},
                      "geometry": json.loads(shapely.to_geojson(g))})
    out = {"type": "FeatureCollection", "features": feats,
           "properties": {"dataset": name, "version": version, "boundaries": ds.provenance.get("boundaries"),
                          "simplify_tolerance_deg": tol}}
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def check_population_table(text: str) -> dict:
    """업로드한 인구표의 형식 점검 (값을 고치지 않는다)."""
    if len(text.encode()) > MAX_TABLE_BYTES:
        raise ValueError("파일이 너무 크다 (2 MB 이하)")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "id" not in rows[0] or "population" not in rows[0]:
        raise ValueError("id, population 열이 필요하다")
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("중복 id")
    for r in rows:
        v = float(r["population"])
        if not np.isfinite(v) or v <= 0:
            raise ValueError(f"인구 값이 양수가 아니다: {r['id']}")
        if not r.get("source"):
            raise ValueError(f"source 열(출처)이 비어 있다: {r['id']} — 출처 없는 자료는 실제 자료로 등록하지 않는다")
    return {"rows": len(rows), "ids": ids}


def build_and_register(req: dict, job_dir: Path) -> dict:
    """인구표로 새 데이터셋 버전을 만들고 등록한다. 가정 매개변수는 활성 버전의 값을 그대로 쓴다."""
    from ..data.build import build_admin1
    from ..data.dataset import RegionDataset
    from ..data.versions import Registry, validate_dataset
    reg = Registry()
    name = req["name"]
    active = RegionDataset.load(reg.resolve(name))
    kind, a3 = _scope(active.provenance)
    if kind != "admin1":
        raise ValueError("인구표 갱신은 1급 행정구역 데이터셋만 지원한다")
    table = job_dir / "population_table.csv"
    table.write_text(req["table_text"])
    a = active.provenance.get("assumptions", {})
    air = (RAW / "openflights" / "airports.dat", RAW / "openflights" / "routes.dat",
           a["air_trips_per_day"], a["commute_fraction"], a["destination_contact_share"])
    if active.provenance.get("boundary_file"):                  # 통계청 SGIS 시도 경계를 쓰는 버전은 같은 경계로
        from ..data.build import build_kor_sido
        ds = build_kor_sido(RAW / "admdongkor_sido" / active.provenance["boundary_file"], *air, population_table=table)
    else:
        ds = build_admin1(RAW / "ne_admin1_10m" / "ne_10m_admin_1_states_provinces.geojson", a3, *air,
                          population_table=table)
    if active.tavg is not None:
        from dataclasses import replace
        ds = replace(ds, tavg=active.tavg, rh=active.rh,
                     provenance={**ds.provenance, "climate": active.provenance.get("climate")})
    out = job_dir / f"{name}_candidate.nc"
    ds.save(out)
    version = reg.register(name, out, req.get("note") or "웹에서 인구표로 만든 버전")
    entry = [v for v in reg.list()[name]["versions"] if v["version"] == version][0]
    return {"name": name, "version": version, "validation": validate_dataset(ds), "diff_vs_active": entry["diff_vs_active"],
            "note": "등록만 했다. 활성화는 데이터 관리 화면에서 직접 한다."}
