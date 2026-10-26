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

    r0_reference (기본 network)
      - network:   실제 지역망의 t0 시점 다음 세대 행렬 스펙트럼 반지름
      - reference: 단일 지역 기준 조건(h=1, g=1, u=0, 이동 없음)의 R0 = c0 P1 T1 / gamma
    어느 기준으로 c0 를 정하든 두 값과 지역별 고립 R0 를 모두 계산해 실행 기록(derived)에 남긴다.
    """
    c0: Num | None = None
    R0: Num | None = None
    r0_reference: Literal["reference", "network"] = "network"

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
    """환경 보정 g.

    status
      - neutral_default: g = 1 (환경 효과 없음). 실제 자료로 추정하기 전의 기본 상태이며
                         "환경 효과가 없다" 는 추정 결과가 아니다.
      - user_assumption: 사용자가 지정한 가정 계수 (추정값 아님)
      - estimated:       2단계에서 실제 자료로 추정한 계수 (estimate_ref 에 추정 기록을 남긴다)
    추정 전후 비교는 같은 설정에서 environment 블록만 바꿔 실행하면 된다.
    """
    g: dict = Field(default_factory=lambda: {"form": "constant"})
    status: Literal["neutral_default", "user_assumption", "estimated"] = "neutral_default"
    estimate_ref: str | None = None
    series_path: str | None = None

    @model_validator(mode="after")
    def _status(self):
        if self.status == "neutral_default" and self.g.get("form") != "constant":
            raise ValueError("status=neutral_default 이면 g 는 constant (g = 1) 여야 한다")
        if self.status == "estimated" and not self.estimate_ref:
            raise ValueError("status=estimated 이면 추정 기록(estimate_ref)이 필요하다")
        return self


class InterventionPeriod(Strict):
    start: Num
    end: Num
    value: Num = Field(ge=0, le=1)
    regions: list[str] | None = None


# ---------------------------------------------------------------- 초기 조건·실행

class Seed(Strict):
    region: str
    count: Num = Field(gt=0)
    compartment: str | None = None     # None 이면 Initial.seed_compartment


class Initial(Strict):
    """초기 감염. seed_compartment 로 I1(감염 중)과 E1(잠복기) 배치를 바꿔 비교할 수 있다."""
    start_date: dt.date
    seed_compartment: Literal["I1", "E1"] = "I1"
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


class OdeSolver(Strict):
    """scipy.integrate.solve_ivp 설정. g, u 가 바뀌는 시점마다 구간을 나눠 적분한다."""
    method: Literal["DOP853", "RK45", "LSODA", "Radau", "BDF"] = "DOP853"
    rtol: Num = Field(1e-8, gt=0)
    atol: Num = Field(1e-6, gt=0, description="절대 허용 오차 [명]")


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
    ode: OdeSolver = Field(default_factory=OdeSolver)


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
