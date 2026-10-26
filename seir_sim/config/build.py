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
from .schema import Config


def load_config(path: str | Path) -> Config:
    with open(path, encoding="utf-8") as fh:
        return Config.model_validate(yaml.safe_load(fh))


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
    raise NotImplementedError("regions.source = 'dataset' 은 1-D 단계에서 구현한다 (미구현)")


def build_scenario(cfg: Config) -> Scenario:
    regions = build_regions(cfg)
    d = cfg.disease
    if cfg.environment.series_path is not None:
        raise NotImplementedError("환경 시계열 입력은 1-D 단계에서 구현한다 (미구현)")
    names = list(regions.names)
    periods = [{"start": p.start, "end": p.end, "value": p.value,
                "regions": None if p.regions is None else [names.index(n) for n in p.regions]}
               for p in cfg.interventions]
    drivers = Drivers(regions.K, cfg.environment.g, None, InterventionSchedule(regions.K, periods))

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

    seeds: dict[int, float] = {}
    comps = {s.compartment for s in cfg.initial.seeds}
    if len(comps) != 1:
        raise ValueError("현재는 모든 초기 감염자를 같은 구획에 심는다")
    for s in cfg.initial.seeds:
        seeds[regions.index(s.region)] = seeds.get(regions.index(s.region), 0.0) + s.count
    X0 = initial_state(system.layout, regions.population, seeds, comps.pop())

    dfe = analysis.disease_free_state(system)
    derived = {
        "c0": c0,
        "R0_reference": c0 * base.P1 * base.T1 / base.gamma,
        "R0_network_t0": analysis.reproduction_number(system, dfe, 0.0),
        "rho_ref": system.rho_ref,
        "regions_synthetic": regions.synthetic,
    }
    return Scenario(cfg, system, X0, derived)
