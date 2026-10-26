"""지역 데이터셋 파일 (NetCDF): 시나리오가 읽는 공통 형식. 어느 나라·축척이든 같은 형식이다.

변수
  population[region]            인구 (NaN = 미확보)
  area_km2[region], lon[region], lat[region]
  contact[region, region_to]    C (행 합 1)
  mobility[region, region_to]   omega (1/일)
  tavg[month, region], rh[month, region]  (선택) 월별 기후
속성
  synthetic (0/1), provenance (JSON 문자열): 자료 출처, 기준 연도, 가정 매개변수, 제외 지역, 품질 점검
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..model.regions import RegionSet


@dataclass
class RegionDataset:
    ids: list[str]
    names: list[str]
    population: np.ndarray
    area_km2: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    contact: np.ndarray
    mobility: np.ndarray
    provenance: dict = field(default_factory=dict)
    synthetic: bool = False
    tavg: np.ndarray | None = None
    rh: np.ndarray | None = None

    @property
    def K(self) -> int:
        return len(self.ids)

    @property
    def missing_population(self) -> list[str]:
        return [i for i, v in zip(self.ids, self.population) if not np.isfinite(v)]

    def quality(self) -> dict:
        """자료 점검: 결측, C 행 합, omega 대각·음수, 이동 균형."""
        pop = np.where(np.isfinite(self.population), self.population, 0.0)
        net = self.mobility.T @ pop - self.mobility.sum(axis=1) * pop
        with np.errstate(divide="ignore", invalid="ignore"):
            imb = np.nanmax(np.where(pop > 0, np.abs(net) / pop, 0.0)) if self.K else 0.0
        computed = bool(np.all(np.isfinite(self.mobility)) and np.all(np.isfinite(self.contact)))
        if not computed:
            return {"K": self.K, "missing_population": self.missing_population,
                    "matrices_computed": False, "has_climate": self.tavg is not None}
        return {"K": self.K, "missing_population": self.missing_population, "matrices_computed": True,
                "contact_row_sum_max_dev": float(np.max(np.abs(self.contact.sum(axis=1) - 1))) if self.K else 0.0,
                "mobility_negative": bool(np.any(self.mobility < 0)),
                "mobility_diag_nonzero": bool(np.any(np.diag(self.mobility) != 0)),
                "mobility_imbalance_per_day": float(imb),
                "max_mobility_out_rate_per_day": float(self.mobility.sum(axis=1).max()) if self.K else 0.0,
                "has_climate": self.tavg is not None}

    def save(self, path: str | Path) -> None:
        import xarray as xr
        coords = {"region": self.ids, "region_to": self.ids}
        data = {"name": (("region",), np.array(self.names, dtype=object)),
                "population": (("region",), self.population),
                "area_km2": (("region",), self.area_km2), "lon": (("region",), self.lon),
                "lat": (("region",), self.lat),
                "contact": (("region", "region_to"), self.contact),
                "mobility": (("region", "region_to"), self.mobility)}
        if self.tavg is not None:
            coords["month"] = np.arange(1, 13)
            data["tavg"] = (("month", "region"), self.tavg)
            data["rh"] = (("month", "region"), self.rh)
        ds = xr.Dataset(data, coords=coords,
                        attrs={"synthetic": int(self.synthetic),
                               "provenance": json.dumps(self.provenance, ensure_ascii=False, default=str),
                               "quality": json.dumps(self.quality(), ensure_ascii=False, default=str),
                               "format": "seir_sim region dataset v1"})
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(path, engine="h5netcdf")

    @classmethod
    def load(cls, path: str | Path) -> "RegionDataset":
        import xarray as xr
        with xr.open_dataset(path, engine="h5netcdf") as ds:
            ds = ds.load()
        if ds.attrs.get("format") != "seir_sim region dataset v1":
            raise ValueError(f"지역 데이터셋 형식이 아니다: {path}")
        has_clim = "tavg" in ds
        return cls(ids=[str(v) for v in ds["region"].values], names=[str(v) for v in ds["name"].values],
                   population=ds["population"].values.astype(float), area_km2=ds["area_km2"].values.astype(float),
                   lon=ds["lon"].values.astype(float), lat=ds["lat"].values.astype(float),
                   contact=ds["contact"].values.astype(float), mobility=ds["mobility"].values.astype(float),
                   provenance=json.loads(ds.attrs.get("provenance", "{}")), synthetic=bool(ds.attrs.get("synthetic", 0)),
                   tavg=ds["tavg"].values if has_clim else None, rh=ds["rh"].values if has_clim else None)

    def to_region_set(self, round_population: bool = True) -> RegionSet:
        """모형 입력. 인구가 미확보인 지역이 있으면 멈춘다 (값을 지어내지 않는다)."""
        miss = self.missing_population
        if miss:
            raise ValueError(f"인구가 미확보인 지역이 있어 시나리오를 만들 수 없다: {miss[:10]}"
                             f"{' ...' if len(miss) > 10 else ''} (출처: {self.provenance.get('population', {})})")
        pop = np.round(self.population) if round_population else self.population
        return RegionSet(tuple(self.ids), pop, pop / self.area_km2, self.contact, self.mobility,
                         synthetic=self.synthetic, provenance=self.provenance)
