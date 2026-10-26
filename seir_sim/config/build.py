"""설정(Config)을 모형 객체(ReactionSystem, 초기 상태)로 바꾼다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from ..model import analysis
from ..model.drivers import Drivers, InterventionSchedule
from ..model.params import EpiParams
from ..model.reactions import ReactionSystem
from ..model.regions import RegionSet
from ..model.state import initial_state
from ..data.climate import daily_series
from ..data.dataset import RegionDataset
from .schema import Config


def load_config(path: str | Path) -> Config:
    """YAML 설정을 읽는다. 상대 경로(regions.path)는 설정 파일 위치 기준이다."""
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw.setdefault("meta", {})["_config_dir"] = str(Path(path).resolve().parent)
    return Config.model_validate(raw)


@dataclass
class Scenario:
    config: Config
    system: ReactionSystem
    X0: np.ndarray
    derived: dict          # 유도된 값 (c0, 두 기준의 R0 등). 실행 기록에 저장한다.


def build_regions(cfg: Config) -> RegionSet:
    r = cfg.regions
    if r.source == "synthetic_single":
        if r.population is None:
            raise ValueError("synthetic_single 에는 population 이 필요하다")
        return RegionSet.single(r.population, r.density)
    if r.source == "synthetic_random":
        if r.K is None:
            raise ValueError("synthetic_random 에는 K 가 필요하다")
        return RegionSet.synthetic_random(r.K, np.random.default_rng(r.seed), r.total_population,
                                          r.mobility_scale, r.self_contact)
    if r.path is None:
        raise ValueError("regions.source = dataset 에는 path 가 필요하다")
    return load_dataset(cfg).to_region_set()


def load_dataset(cfg: Config) -> RegionDataset:
    path = Path(cfg.regions.path)
    if not path.is_absolute() and cfg.meta.get("_config_dir"):
        path = Path(cfg.meta["_config_dir"]) / path
    return RegionDataset.load(path)


def build_scenario(cfg: Config) -> Scenario:
    regions = build_regions(cfg)
    d = cfg.disease
    environment = None
    if cfg.environment.source == "dataset":
        if cfg.regions.source != "dataset":
            raise ValueError("environment.source = dataset 은 regions.source = dataset 일 때만 쓸 수 있다")
        ds = load_dataset(cfg)
        if ds.tavg is None:
            raise ValueError("지역 데이터셋에 기후 자료(tavg, rh)가 없다 (기후 자료 미확보)")
        environment = daily_series(ds.tavg, ds.rh, cfg.initial.start_date, int(np.ceil(cfg.simulation.days)),
                                   {"dataset": str(cfg.regions.path)})
    names = list(regions.names)
    periods = [{"start": p.start, "end": p.end, "value": p.value,
                "regions": None if p.regions is None else [names.index(n) for n in p.regions]}
               for p in cfg.interventions]
    drivers = Drivers(regions.K, cfg.environment.g, environment, InterventionSchedule(regions.K, periods))

    base = EpiParams(sigma=d.sigma, gamma=d.gamma, c0=1.0, P1=d.P1, T1=d.T1, Pmin=d.Pmin,
                     alpha=d.alpha, beta=d.beta, lam=d.lam, f1=d.f1, phi_spec=d.phi, M=d.M)
    system = ReactionSystem(base, regions, drivers, cfg.contact_model.h, cfg.contact_model.rho_ref)

    tr = d.transmission
    if tr.c0 is not None:
        c0 = tr.c0
    elif tr.r0_reference == "reference":
        c0 = analysis.c0_reference(tr.R0, base)
    else:
        c0 = analysis.c0_network(tr.R0, system)
    system = system.with_params(c0=c0)

    for s in cfg.initial.seeds:
        if s.region not in regions.names:
            raise ValueError(f"초기 감염 지역 {s.region!r} 이 지역 목록에 없다 (예: {list(regions.names)[:8]})")
    seeds = [(regions.index(s.region), s.count, s.compartment or cfg.initial.seed_compartment)
             for s in cfg.initial.seeds]
    X0 = initial_state(system.layout, regions.population, seeds)

    derived = {"c0": c0, "c0_basis": "given" if tr.c0 is not None else tr.r0_reference,
               **analysis.r0_report(system), "rho_ref": system.rho_ref,
               "regions_synthetic": regions.synthetic,
               "regions_provenance": regions.provenance,
               "g_status": cfg.environment.status, "g_spec": dict(cfg.environment.g)}
    if derived.get("R0_network_dominated_by_small_population"):
        import warnings
        warnings.warn("지역망 R0 의 주 고유모드가 인구 비율 "
                      f"{derived['R0_network_dominant_population_share']:.3f} 인 지역({derived['R0_network_dominant_regions'][:5]})"
                      "에 몰려 있다. network 기준으로 c0 를 정하면 대부분 지역의 R0 가 목표보다 낮아질 수 있다 "
                      "(docs/DECISIONS.md D-008).", stacklevel=2)
    return Scenario(cfg, system, X0, derived)
