"""YAML 설정 스키마. 모든 상수는 여기에서 이름 있는 매개변수로 지정한다.

율(rate)은 숫자 또는 "1/5.2" 같은 분수 문자열로 쓸 수 있다. eval 은 쓰지 않는다.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

_FRAC = re.compile(r"^\s*([0-9.eE+-]+)\s*/\s*([0-9.eE+-]+)\s*$")


def _parse_number(v):
    if isinstance(v, str):
        m = _FRAC.match(v)
        if m:
            return float(m.group(1)) / float(m.group(2))
        return float(v)
    return v


Num = Annotated[float, BeforeValidator(_parse_number)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- 감염병

class Transmission(Strict):
    """c0 를 직접 주거나 R0 를 준다 (둘 중 하나).

    r0_reference
      - reference: 단일 지역 기준 조건(h=1, g=1, u=0, 이동 없음)의 R0 = c0 P1 T1 / gamma
      - network:   실제 지역망의 t0 시점 다음 세대 행렬 스펙트럼 반지름
    """
    c0: Num | None = None
    R0: Num | None = None
    r0_reference: Literal["reference", "network"] = "reference"

    @model_validator(mode="after")
    def _one(self):
        if (self.c0 is None) == (self.R0 is None):
            raise ValueError("transmission 에는 c0 와 R0 중 정확히 하나를 지정해야 한다")
        return self


class Disease(Strict):
    name: str = "unnamed"
    sigma: Num = Field(gt=0, description="1/잠복기 [1/일]")
    gamma: Num = Field(gt=0, description="1/감염기간 [1/일]")
    transmission: Transmission
    P1: Num = Field(ge=0)
    T1: Num = Field(ge=0)
    Pmin: Num = Field(ge=0)
    alpha: Num = Field(ge=0)
    beta: Num = Field(ge=0)
    lam: Num = Field(ge=0, description="면역 소실 율 [1/일]")
    f1: Num = Field(ge=0, le=1)
    phi: dict = Field(default_factory=lambda: {"form": "power", "delta": 0.5})
    M: int = Field(4, ge=1)
    note: str = ""


# ---------------------------------------------------------------- 지역·환경

class Regions(Strict):
    """source
      - synthetic_single: 단일 합성 지역 (population, density)
      - synthetic_random: 무작위 합성 지역 K개 (seed)
      - dataset:          data 계층이 만든 지역 파일 (1-D 에서 구현)
    """
    source: Literal["synthetic_single", "synthetic_random", "dataset"]
    population: Num | None = None
    density: Num = 1.0
    K: int | None = None
    seed: int = 0
    total_population: Num = 1e6
    mobility_scale: Num = 1e-3
    self_contact: Num = 0.8
    path: str | None = None


class ContactModel(Strict):
    h: dict = Field(default_factory=lambda: {"form": "constant"})
    rho_ref: Num | Literal["pop_weighted_mean"] = "pop_weighted_mean"


class Environment(Strict):
    g: dict = Field(default_factory=lambda: {"form": "constant"})
    series_path: str | None = None


class InterventionPeriod(Strict):
    start: Num
    end: Num
    value: Num = Field(ge=0, le=1)
    regions: list[str] | None = None


# ---------------------------------------------------------------- 초기 조건·실행

class Seed(Strict):
    region: str
    count: Num = Field(gt=0)
    compartment: str = "I1"


class Initial(Strict):
    start_date: dt.date
    seeds: list[Seed]


class Hybrid(Strict):
    """E+I >= threshold_up 이면 tau-leaping, E+I < threshold_down 이면 Gillespie (히스테리시스)."""
    threshold_up: Num = 100
    threshold_down: Num = 50

    @model_validator(mode="after")
    def _order(self):
        if self.threshold_down > self.threshold_up:
            raise ValueError("threshold_down <= threshold_up 이어야 한다")
        return self


class Simulation(Strict):
    days: Num = Field(365, gt=0)
    output_dt: Num = Field(1.0, gt=0)
    method: Literal["ode", "sde", "ctmc", "tau", "hybrid"] = "ode"
    n_runs: int = Field(100, ge=1)
    seed: int = 20260101
    n_workers: int = Field(1, ge=1)
    hybrid: Hybrid = Field(default_factory=Hybrid)
    tau_leap_epsilon: Num = Field(0.03, gt=0, description="Cao-Gillespie-Petzold tau 선택 허용 오차")
    sde_dt: Num = Field(0.05, gt=0)


# ---------------------------------------------------------------- 자료 출처 기록

class DatasetRecord(Strict):
    """외부 자료의 출처 기록.

    role
      - historical_training / historical_validation / historical_test: 과거 자료 (2단계 보정·검증)
      - current_input: 최신 입력 자료 (최종 예측)
    """
    name: str
    role: Literal["historical_training", "historical_validation", "historical_test", "current_input"]
    source: str
    version: str
    license: str
    resolution: str
    time_range: str
    units: str = ""
    url: str = ""
    preprocessing: str = ""
    synthetic: bool = False


class Config(Strict):
    run_mode: Literal["development", "calibration", "forecast"] = "development"
    meta: dict = Field(default_factory=dict)
    disease: Disease
    regions: Regions
    contact_model: ContactModel = Field(default_factory=ContactModel)
    environment: Environment = Field(default_factory=Environment)
    interventions: list[InterventionPeriod] = Field(default_factory=list)
    initial: Initial
    simulation: Simulation = Field(default_factory=Simulation)
    datasets: list[DatasetRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _data_roles(self):
        roles = {d.role for d in self.datasets}
        if self.run_mode == "forecast" and roles - {"current_input"}:
            raise ValueError("forecast 모드에는 current_input 자료만 넣을 수 있다 (과거 관측 자료 혼입 금지)")
        if self.run_mode == "calibration" and "current_input" in roles:
            raise ValueError("calibration 모드에 current_input 자료를 넣을 수 없다 (미래 누설 방지)")
        return self
