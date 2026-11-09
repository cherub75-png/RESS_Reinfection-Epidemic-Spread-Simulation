"""웹 시나리오 요청 -> 설정 -> 앙상블 실행 -> 저장·요약 (작업 프로세스 안에서 실행).

감염병 기본값은 configs/example_single_region.yaml 의 COVID 유사 "코드 검증용 가정" 이다. 사용자가 바꾼 값과 기본값을
요약에 따로 기록한다 (labels.parameters). 지역은 데이터셋 저장소(registry)의 활성 버전 또는 단일 합성 지역이다.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import ClassVar, Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]


class SeedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: str = Field(max_length=40)
    count: float = Field(ge=0, le=1e7)              # 초기 감염 중 (I1)
    exposed: float = Field(0, ge=0, le=1e7)          # 초기 잠복 (E1)


class InterventionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0, le=3650)
    end: float = Field(gt=0, le=3650)
    value: float = Field(ge=0, le=1)
    regions: list[str] | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("개입 끝일은 시작일보다 커야 한다")
        return self


class DiseaseIn(BaseModel):
    """감염병 특성 (None 이면 기본 가정값). 기간은 일 단위로 받아 율(1/일)로 바꾼다."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field("사용자 정의", max_length=60)
    kind: Literal["respiratory", "contact", "vector", "other"] = "respiratory"
    incubation_days: float | None = Field(None, gt=0, le=60)          # sigma = 1 / 잠복기
    infectious_days: float | None = Field(None, gt=0, le=120)         # gamma = 1 / 감염 기간
    immunity_days: float | None = Field(None, ge=0, le=36500)         # lam = 1 / 면역 유지 기간 (0 = 소실 없음)
    P1: float | None = Field(None, ge=0, le=1)                        # 첫 감염 감수성
    Pmin: float | None = Field(None, ge=0, le=1)                      # 재감염 감수성 하한
    alpha: float | None = Field(None, ge=0, le=50)                    # 감수성 감소 속도
    T1: float | None = Field(None, ge=0, le=10)                       # 첫 감염 전파력
    beta: float | None = Field(None, ge=0, le=5)                      # 전파력 감소 지수
    f1: float | None = Field(None, ge=0, le=1)                        # 첫 감염 치명률
    phi_delta: float | None = Field(None, ge=0, le=5)                 # 치명률 감소 지수 phi(n) = n^-delta
    M: int | None = Field(None, ge=2, le=20)                          # 감염 횟수 칸 수


class UncertaintyIn(BaseModel):
    """매개변수 불확실성: [하한, 상한] 범위에서 실행마다 균등 분포로 한 번씩 뽑는다 (사용자 가정 범위)."""
    model_config = ConfigDict(extra="forbid")
    R0: tuple[float, float] | None = None
    incubation_days: tuple[float, float] | None = None
    infectious_days: tuple[float, float] | None = None
    immunity_days: tuple[float, float] | None = None
    f1: tuple[float, float] | None = None

    BOUNDS: ClassVar[dict] = {"R0": (0.0, 20.0), "incubation_days": (0.0, 60.0), "infectious_days": (0.0, 120.0),
              "immunity_days": (0.0, 36500.0), "f1": (0.0, 1.0)}

    @model_validator(mode="after")
    def _ranges(self):
        for k, (lo_b, hi_b) in self.BOUNDS.items():
            v = getattr(self, k)
            if v is None:
                continue
            lo, hi = v
            if not lo < hi:
                raise ValueError(f"불확실성 {k}: 하한 < 상한 이어야 한다")
            if lo < lo_b or hi > hi_b or (k in ("R0", "incubation_days", "infectious_days") and lo <= 0):
                raise ValueError(f"불확실성 {k}: 허용 범위 ({lo_b}, {hi_b}] 밖")
        return self

    def active(self) -> dict:
        return {k: getattr(self, k) for k in self.BOUNDS if getattr(self, k) is not None}


class ScenarioRequest(BaseModel):
    """화면에서 받는 시나리오 (모든 값 검증; 비운 값은 기본 가정값)."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field("시나리오", max_length=80)
    dataset: str = Field("KOR_admin1", pattern=r"^[A-Za-z0-9_]{1,40}$")   # 'synthetic_single' 또는 저장소 이름
    population: float | None = Field(None, gt=0, le=1e10)                 # synthetic_single 일 때만
    disease: DiseaseIn = Field(default_factory=DiseaseIn)
    R0: float = Field(2.5, gt=0, le=20)
    r0_reference: Literal["reference", "region", "origin", "population_mean", "network"] = "reference"
    reference_region: str | None = Field(None, max_length=40)
    method: Literal["ode", "sde", "ctmc", "tau", "hybrid"] = "hybrid"
    n_runs: int = Field(20, ge=1, le=500)
    n_workers: int = Field(1, ge=1, le=4)
    days: int = Field(180, ge=1, le=1095)
    start_date: dt.date = dt.date(2020, 1, 20)
    seeds: list[SeedIn] = Field(min_length=1, max_length=50)
    initial_immune_fraction: float = Field(0.0, ge=0, le=0.99)           # 시작 시 면역(보호) 상태 비율 (모든 지역 같게)
    interventions: list[InterventionIn] = Field(default_factory=list, max_length=50)
    use_mobility: bool = True
    use_commuting: bool = True
    climate: Literal["none", "exp_linear"] = "none"                      # exp_linear: 사용자 가정 기후 효과
    climate_a_T: float = Field(0.0, ge=-1, le=1)
    climate_a_H: float = Field(0.0, ge=-1, le=1)
    climate_T_ref: float = Field(15.0, ge=-40, le=50)
    climate_H_ref: float = Field(60.0, ge=0, le=100)
    eta: float = Field(0.2, ge=0, le=2)                                    # h(rho) = (rho/rho_ref)^eta
    tau_leap_epsilon: float = Field(0.003, ge=0.0005, le=0.1)        # D-007
    sde_dt: float = Field(0.05, ge=0.001, le=1)
    hybrid_up: float = Field(100, ge=2, le=1e6)
    hybrid_down: float = Field(50, ge=1, le=1e6)
    seed: int = Field(20260101, ge=0, le=2**31)
    # 자료 시기 (None = 저장소의 활성 버전 그대로). data.periods 가 같은 가정값으로 데이터셋을 다시 만든다.
    boundary_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")         # 경계 시점 (대한민국 시도)
    population_year: int | None = Field(None, ge=1960, le=2100)                     # 인구 기준 연도
    climate_period: str | None = Field(None, pattern=r"^era5_\d{4}-\d{2}_\d{4}-\d{2}$")   # 기후 기간 (ERA5)
    uncertainty: UncertaintyIn | None = None                                        # 매개변수 불확실성 범위

    @model_validator(mode="after")
    def _check(self):
        if self.hybrid_down >= self.hybrid_up:
            raise ValueError("하이브리드 전환 기준: 내려가는 기준 < 올라가는 기준")
        if all(s.count + s.exposed <= 0 for s in self.seeds):
            raise ValueError("초기 감염자(I) 또는 잠복자(E) 가 1명 이상 필요하다")
        return self


DEFAULT_KEYS = {"incubation_days": ("sigma", lambda v: 1 / v), "infectious_days": ("gamma", lambda v: 1 / v),
                "immunity_days": ("lam", lambda v: 0.0 if v == 0 else 1 / v), "P1": ("P1", float), "Pmin": ("Pmin", float),
                "alpha": ("alpha", float), "T1": ("T1", float), "beta": ("beta", float), "f1": ("f1", float),
                "M": ("M", int)}


def disease_defaults() -> dict:
    cfg = yaml.safe_load((ROOT / "configs" / "example_single_region.yaml").read_text())
    return cfg["disease"]


def _num(v):
    if isinstance(v, str) and "/" in v:
        a, b = v.split("/")
        return float(a) / float(b)
    return float(v)


def disease_block(dz: DiseaseIn) -> tuple[dict, dict]:
    """(설정의 disease 블록, 매개변수별 출처 표시 {이름: '사용자 입력'|'기본 가정값'})"""
    d = disease_defaults()
    src = {}
    for k in ("sigma", "gamma", "lam", "P1", "Pmin", "alpha", "T1", "beta", "f1", "M"):
        d[k] = _num(d[k]) if k != "M" else int(d[k])
        src[k] = "기본 가정값"
    for field, (key, conv) in DEFAULT_KEYS.items():
        v = getattr(dz, field)
        if v is not None:
            d[key] = conv(v)
            src[key] = "사용자 입력"
    if dz.phi_delta is not None:
        d["phi"] = {"form": "power", "delta": dz.phi_delta}
        src["phi"] = "사용자 입력"
    else:
        src["phi"] = "기본 가정값"
    d["name"] = dz.name
    d.pop("note", None)
    return d, src


def uses_periods(req: ScenarioRequest) -> bool:
    return any(v is not None for v in (req.boundary_date, req.population_year, req.climate_period))


def dataset_spec(req: ScenarioRequest, with_climate: bool = True, log=lambda m: None) -> str:
    """설정의 regions.path: 저장소 활성 버전 ("registry:이름") 또는 고른 시기의 변형본 파일 경로."""
    if not uses_periods(req) or (not with_climate and req.boundary_date is None and req.population_year is None):
        return f"registry:{req.dataset}"
    from ..data.periods import variant
    return str(variant(req.dataset, population_year=req.population_year, boundary_date=req.boundary_date,
                       climate_period=req.climate_period if with_climate else None, log=log))


def load_request_dataset(req: ScenarioRequest, with_climate: bool = True):
    from ..data.dataset import RegionDataset
    from ..data.versions import Registry
    spec = dataset_spec(req, with_climate)
    return RegionDataset.load(Registry().resolve(spec[len("registry:"):]) if spec.startswith("registry:") else spec)


def _region_populations(req: ScenarioRequest) -> dict:
    ds = load_request_dataset(req, with_climate=False)
    return dict(zip(ds.ids, ds.population.tolist()))


def build_config(req: ScenarioRequest, populations: dict | None = None) -> dict:
    d, _ = disease_block(req.disease)
    d["transmission"] = {"R0": req.R0, "r0_reference": req.r0_reference}
    if req.r0_reference == "region":
        d["transmission"]["reference_region"] = req.reference_region
    stochastic = req.method != "ode"
    rnd = (lambda x: float(round(x))) if stochastic else float
    if req.dataset == "synthetic_single":
        regions = {"source": "synthetic_single", "population": req.population or 1e6}
        pops = {"region0": float(req.population or 1e6)}
        seeds_regions = ["region0" for _ in req.seeds]
    else:
        regions = {"source": "dataset", "path": dataset_spec(req), "use_mobility": req.use_mobility,
                   "use_commuting": req.use_commuting}
        pops = populations if populations is not None else _region_populations(req)
        seeds_regions = [s.region for s in req.seeds]
    seeds = []
    for r, s in zip(seeds_regions, req.seeds):
        if s.count > 0:
            seeds.append({"region": r, "count": rnd(s.count), "compartment": "I1"})
        if s.exposed > 0:
            seeds.append({"region": r, "count": rnd(s.exposed), "compartment": "E1"})
    seeds = [x for x in seeds if x["count"] > 0]
    if req.initial_immune_fraction > 0:
        for r, n in pops.items():
            k = rnd(req.initial_immune_fraction * n)
            if k > 0:
                seeds.append({"region": r, "count": k, "compartment": "RP1"})
    env = {"g": {"form": "constant"}, "status": "neutral_default", "source": "none"}
    if req.climate == "exp_linear":
        env = {"g": {"form": "exp_linear", "a_T": req.climate_a_T, "a_H": req.climate_a_H, "T_ref": req.climate_T_ref,
                     "H_ref": req.climate_H_ref}, "status": "user_assumption", "source": "dataset"}
    return {
        "run_mode": "development",
        "meta": {"name": req.title, "source": "web", "note": "감염병 값: 사용자 입력 또는 코드 검증용 기본 가정값 (실제 추정치 아님)"},
        "disease": d,
        "regions": regions,
        "contact_model": {"h": {"form": "power", "eta": req.eta}, "rho_ref": "pop_weighted_mean"},
        "environment": env,
        "interventions": [i.model_dump() for i in req.interventions],
        "initial": {"start_date": str(req.start_date), "seed_compartment": "I1", "seeds": seeds},
        "simulation": {"days": req.days, "method": req.method, "n_runs": req.n_runs, "seed": req.seed,
                       "n_workers": req.n_workers, "tau_leap_epsilon": req.tau_leap_epsilon, "sde_dt": req.sde_dt,
                       "hybrid": {"threshold_up": req.hybrid_up, "threshold_down": req.hybrid_down}},
    }


def check_against_populations(req: ScenarioRequest, pops: dict) -> list[str]:
    """초기 조건이 인구와 모순되는지 검사한다 (오류 문장 목록)."""
    errs = []
    for s in req.seeds:
        if s.region not in pops:
            errs.append(f"지역 {s.region} 이 데이터셋에 없다")
            continue
        n = pops[s.region]
        if n is None or not np.isfinite(n):
            errs.append(f"지역 {s.region} 의 인구가 미확보다")
        elif s.count + s.exposed + req.initial_immune_fraction * n > n:
            errs.append(f"지역 {s.region}: 초기 감염 {s.count + s.exposed:g} 명 + 초기 면역이 인구 {n:,.0f} 명을 넘는다")
    for i in req.interventions:
        for r in i.regions or []:
            if r not in pops:
                errs.append(f"개입 지역 {r} 이 데이터셋에 없다")
    if req.r0_reference == "region" and req.reference_region not in pops:
        errs.append(f"기준 지역 {req.reference_region} 이 데이터셋에 없다")
    return errs


def estimate_cost(req: ScenarioRequest, K: int, population: float) -> dict:
    """대략적인 계산량 안내 (4코어 클라우드 환경 측정값 기반의 거친 추정; 정확한 예측이 아니다)."""
    days = req.days
    if req.method == "ode":
        sec = 0.002 * K * days / 365 * 10
    elif req.method == "ctmc":
        sec = req.n_runs * population * 2e-6 * max(1.0, days / 365) * 3       # 사건 수 ~ 인구 x 몇 회
    elif req.method == "sde":
        sec = req.n_runs * K * days / req.sde_dt * 2e-6
    else:                                                                   # tau, hybrid
        sec = req.n_runs * K * days * 6e-4 * (0.01 / req.tau_leap_epsilon) ** 0.5
    sec /= max(1, req.n_workers) ** 0.9
    level = "ok" if sec < 120 else ("warn" if sec < 1800 else "heavy")
    return {"seconds": float(sec), "level": level,
            "note": "경험식 추정 (실제 시간은 감염 규모·이동망에 따라 크게 다를 수 있음)"}


class LiveWriter:
    """실행 중 화면 갱신용 live.json: 지역별 I·E·D (프레임) 와 전체 S·E·I·D (일별) 의 평균.

    kind: "ode_preview" (시작 직후 결정론 ODE 1회, 확률 실행 결과 아님) -> "ensemble" (끝난 실행들의 평균, runs_done/n_runs)
    -> "final". 1초에 한 번까지만 쓴다. status.json 의 live_seq 가 바뀌면 화면이 다시 읽는다.
    """

    def __init__(self, job_dir: Path, t: np.ndarray, ids: list[str], N0: np.ndarray, n_runs: int, labels: dict):
        self.d, self.t, self.ids, self.N0, self.n_runs, self.labels = Path(job_dir), t, ids, N0, n_runs, labels
        self.fi = np.arange(0, t.size, max(1, int(np.ceil(t.size / 120))))
        self.sum = None
        self.n = 0
        self.seq = 0
        self.last = 0.0

    def preview(self, out: np.ndarray) -> None:
        self._write(np.asarray(out, float), "ode_preview")

    def add(self, r: int, out: np.ndarray) -> None:
        import time
        o = np.asarray(out, float)
        self.sum = o.copy() if self.sum is None else self.sum + o
        self.n += 1
        if time.time() - self.last >= 1.0 or self.n == self.n_runs:
            self._write(self.sum / self.n, "ensemble")

    def final(self) -> None:
        if self.sum is not None:
            self._write(self.sum / self.n, "final")

    def _write(self, mean: np.ndarray, kind: str) -> None:
        import time
        from .jobs import write_status
        fi = self.fi
        tot = mean.sum(axis=2)                                           # [4, T]
        payload = {"kind": kind, "runs_done": self.n, "n_runs": self.n_runs, "ids": self.ids,
                   "population": [round(float(v), 1) for v in self.N0], "t_frames": self.t[fi].tolist(),
                   "I": _clean(mean[2][fi], 1), "E": _clean(mean[1][fi], 1), "D": _clean(mean[3][fi], 2),
                   "daily": {"t": self.t.tolist(), "S": _clean(tot[0], 1), "E": _clean(tot[1], 1), "I": _clean(tot[2], 1),
                             "D": _clean(tot[3], 2)},
                   "population_total": float(self.N0.sum()), "labels": self.labels}
        tmp = self.d / "live.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False))
        tmp.replace(self.d / "live.json")
        self.seq += 1
        self.last = time.time()
        write_status(self.d, live_seq=self.seq, live_kind=kind)


def parameter_draws(req: ScenarioRequest) -> list[dict]:
    """실행마다 한 번씩 뽑은 매개변수 값 (불확실성 범위가 없으면 빈 목록). 시드에서 결정된다 (재현 가능)."""
    if req.uncertainty is None or not req.uncertainty.active():
        return []
    rng = np.random.default_rng([req.seed, 7_000_001])
    act = req.uncertainty.active()
    return [{k: float(rng.uniform(lo, hi)) for k, (lo, hi) in act.items()} for _ in range(req.n_runs)]


def apply_draw(req: ScenarioRequest, draw: dict, seed: int) -> ScenarioRequest:
    dz = req.disease.model_copy(update={k: v for k, v in draw.items() if k != "R0"})
    return req.model_copy(update={"disease": dz, "R0": draw.get("R0", req.R0), "n_runs": 1, "n_workers": 1, "seed": seed})


def _draw_one(args):
    req_raw, draw, seed = args
    from ..config.schema import Config
    from ..ensemble.runner import run_ensemble
    req = apply_draw(ScenarioRequest.model_validate(req_raw), draw, seed)
    res = run_ensemble(Config.model_validate(build_config(req)))
    return res.runs[0], res.run_meta[0], res.seeds[0]


def _run_with_draws(req: ScenarioRequest, cfg, draws: list[dict], cancel, progress, on_run):
    """불확실성 범위가 있을 때: 뽑은 매개변수마다 확률 실행 1회 (작업자가 여럿이면 병렬)."""
    import time
    from ..config.build import build_scenario
    from ..ensemble.runner import EnsembleCancelled, EnsembleResult
    seeds = [int(c.generate_state(1)[0]) for c in np.random.SeedSequence(req.seed).spawn(len(draws))]
    jobs = [(req.model_dump(mode="json"), d, s) for d, s in zip(draws, seeds)]
    t0 = time.perf_counter()
    outs = [None] * len(draws)
    if req.n_workers <= 1:
        for r, a in enumerate(jobs):
            if cancel is not None and cancel():
                raise EnsembleCancelled(f"{r}/{len(draws)} 실행 후 취소")
            outs[r] = _draw_one(a)
            on_run(r, outs[r][0])
            progress(r + 1, len(draws))
    else:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(req.n_workers, mp_context=mp.get_context("forkserver")) as ex:
            for r, o in enumerate(ex.map(_draw_one, jobs)):
                outs[r] = o
                on_run(r, o[0])
                progress(r + 1, len(draws))
                if cancel is not None and cancel():
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise EnsembleCancelled(f"{r + 1}/{len(draws)} 실행 후 취소")
    sc = build_scenario(cfg)
    T = outs[0][0].shape[1]
    return EnsembleResult(cfg.simulation.output_dt * np.arange(T), list(sc.system.regions.names),
                          np.stack([o[0] for o in outs]), req.method, [{**o[2], "draw": d} for o, d in zip(outs, draws)],
                          [o[1] for o in outs], cfg, sc.derived, time.perf_counter() - t0, 1000.0,
                          {"n_workers": req.n_workers, "parameter_uncertainty": {
                              "ranges": req.uncertainty.active(), "distribution": "균등 (실행마다 한 번 추출)",
                              "draws": draws, "label": "사용자 가정 범위 (추정값 아님)"}})


def run_scenario(req_raw: dict, job_dir: Path, cancel=None, progress=None) -> dict:
    from ..config.build import build_scenario
    from ..config.schema import Config
    from ..ensemble.runner import run_ensemble
    from .jobs import write_status
    req = ScenarioRequest.model_validate(req_raw)
    if uses_periods(req):
        write_status(job_dir, message="고른 시기의 자료로 데이터셋 준비 중")
        dataset_spec(req, log=lambda m: write_status(job_dir, message=m))
    cfg = Config.model_validate(build_config(req))
    (job_dir / "config.json").write_text(cfg.model_dump_json(indent=1))
    sc = build_scenario(cfg)
    T = int(np.floor(cfg.simulation.days / cfg.simulation.output_dt + 1e-9)) + 1
    draws = parameter_draws(req)
    live = LiveWriter(job_dir, cfg.simulation.output_dt * np.arange(T), list(sc.system.regions.names),
                      np.asarray(sc.system.regions.population, float), 1 if req.method == "ode" and not draws else req.n_runs,
                      {"method": req.method, "uncertainty": bool(draws)})
    if req.method != "ode" or draws:                                    # 바로 보이는 결정론 미리보기 (중앙값 매개변수)
        prev = run_ensemble(Config.model_validate(build_config(req.model_copy(update={"method": "ode", "n_runs": 1,
                                                                                         "n_workers": 1}))))
        live.preview(prev.runs[0])
    progress = progress or (lambda a, b: None)
    if draws:
        res = _run_with_draws(req, cfg, draws, cancel, progress, live.add)
    else:
        res = run_ensemble(cfg, progress=progress, cancel=cancel, on_run=live.add)
    live.final()
    res.save(str(job_dir))
    summary = web_summary(res, req, cfg)
    (job_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, default=_json_default))
    _write_csv(job_dir, summary)
    return summary


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _clean(a, nd=3) -> list:
    a = np.asarray(a, float)
    return [None if not np.isfinite(v) else round(float(v), nd) for v in a.ravel()] if a.ndim == 1 else \
        [[None if not np.isfinite(v) else round(float(v), nd) for v in row] for row in a]


def web_summary(res, req: ScenarioRequest, cfg) -> dict:
    s, rs = res.summary(), res.region_summary()
    runs = res.runs.astype(float)                       # [R, 4, T, K]: S, E, I, D
    R_, _, T, K = runs.shape
    pop0 = runs[:, :, 0, :].sum(axis=1).mean(axis=0)     # 지역별 초기 총인구 (S+E+I+D; 초기 면역은 S 에 없음)
    from ..config.build import build_scenario
    sc = build_scenario(cfg)
    N0 = sc.system.regions.population                   # 지역별 실제 초기 인구 (면역 포함)
    S0 = runs[:, 0, 0, :]
    first = (S0[:, None, :] - runs[:, 0]) / np.maximum(N0, 1)            # 첫 감염 누적 비율 [R, T, K]
    mean = runs.mean(axis=0)                            # [4, T, K]
    tot = runs.sum(axis=3)                              # [R, 4, T]
    alive_rest = N0.sum() - tot[:, 0] - tot[:, 1] - tot[:, 2] - tot[:, 3]   # 회복·면역 (R^P + R^W)
    new_first = np.diff(-tot[:, 0], axis=1, prepend=tot[:, 0, :1])           # 일별 첫 감염 (S 감소)
    step = max(1, int(np.ceil(T / 120)))
    fi = np.arange(0, T, step)
    q05i = np.percentile(runs[:, 2], 5, axis=0)
    q95i = np.percentile(runs[:, 2], 95, axis=0)
    d = res.derived
    derived = {k: d.get(k) for k in ("c0", "c0_basis", "reference_region", "c0_by_basis", "R0_reference", "R0_network_t0",
                                     "R0_isolated_population_weighted_mean", "population_share_isolated_R0_gt1",
                                     "R0_network_dominant_population_share", "regions_synthetic", "g_status")}
    warnings = []
    if d.get("R0_network_dominated_by_small_population"):
        warnings.append("지역망 R0 가 인구가 적은 지역에 지배된다 (D-008).")
    if d.get("regions_synthetic"):
        warnings.append("합성 지역 자료로 실행했다 (실제 지역 아님).")
    if req.climate != "none":
        warnings.append("기후 효과는 사용자 가정값이다 (실제 자료로 추정한 효과 아님). 기후 자료는 2020~2022 월 평균.")
    if not req.use_mobility or not req.use_commuting:
        warnings.append(f"지역 간 이동 {'끔' if not req.use_mobility else '켬'}, 통근 접촉 {'끔' if not req.use_commuting else '켬'}.")
    lb = sum(1 for m in res.run_meta if m.get("last_bin_warning"))
    if lb:
        warnings.append(f"{lb}개 실행에서 마지막 재감염 칸 점유율 경고 (M 부족 가능성).")
    pu = res.info.get("parameter_uncertainty")
    if pu:
        warnings.append("띠는 확률적 변동과 매개변수 불확실성(사용자가 정한 범위에서 균등 추출)을 함께 반영한다: "
                        + ", ".join(f"{k} {lo:g}~{hi:g}" for k, (lo, hi) in pu["ranges"].items()))
    if uses_periods(req):
        warnings.append(f"자료 시기: 경계 {req.boundary_date or '기본'}, 인구 {req.population_year or '기본'}, "
                        f"기후 {req.climate_period or '기본'} (같은 이동 가정값으로 다시 만든 데이터셋)")
    _, src = disease_block(req.disease)
    names = list(res.region_ids)
    return {
        "title": req.title, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "request": req.model_dump(mode="json"), "method": res.method, "n_runs": int(R_),
        "wall_seconds": res.wall_seconds, "start_date": str(req.start_date),
        "labels": {"kind": "scenario", "disease_values": "사용자 입력 또는 기본 가정값 (실제 추정치 아님)",
                   "parameters": src, "disease": cfg.disease.model_dump(mode="json"),
                   "environment": f"g: {cfg.environment.status}", "dataset": req.dataset},
        "derived": derived, "warnings": warnings,
        "parameter_uncertainty": pu, "dataset_provenance": _dataset_provenance(res),
        "daily": {"t": res.t.tolist(), "mean": _clean(s["mean"]), "q05": _clean(s["q05"]), "q25": _clean(np.percentile(tot[:, 2], 25, axis=0)),
                  "q50": _clean(s["q50"]), "q75": _clean(np.percentile(tot[:, 2], 75, axis=0)), "q95": _clean(s["q95"]),
                  "E_mean": _clean(tot[:, 1].mean(axis=0)), "D_mean": _clean(tot[:, 3].mean(axis=0)),
                  "D_q05": _clean(np.percentile(tot[:, 3], 5, axis=0)), "D_q95": _clean(np.percentile(tot[:, 3], 95, axis=0)),
                  "R_mean": _clean(alive_rest.mean(axis=0)), "new_first_mean": _clean(new_first.mean(axis=0)),
                  "cum_first_mean": _clean((tot[:, 0, :1] - tot[:, 0]).mean(axis=0)),
                  "deaths_mean": _clean(tot[:, 3].mean(axis=0))},
        "outbreak_probability": s["outbreak_probability"], "peak_I_mean": s["peak_I_mean"],
        "peak_day_median": s["peak_day_median"], "population_total": float(N0.sum()),
        "regions": [{"id": names[k], "population": float(N0[k]), "attack_mean": float(first[:, -1, k].mean()),
                     "deaths_mean": float(mean[3, -1, k]), "peak_I_mean": float(rs["mean"][:, k].max()),
                     "peak_day": float(res.t[int(np.argmax(rs["mean"][:, k]))]),
                     "arrival_probability": float(rs["arrival_probability"][k]),
                     "arrival_day_median": None if not np.isfinite(rs["arrival_day_median"][k]) else float(rs["arrival_day_median"][k])}
                    for k in range(K)],
        "frames": {"t": res.t[fi].tolist(), "I": _clean(mean[2][fi], 1), "E": _clean(mean[1][fi], 1),
                   "D": _clean(mean[3][fi], 2), "first": _clean(first.mean(axis=0)[fi], 5),
                   "I_q05": _clean(q05i[fi], 1), "I_q95": _clean(q95i[fi], 1)},
    }


def _dataset_provenance(res) -> dict:
    """화면의 '입력 자료' 표시용: 경계·인구·기후·이동의 출처와 시점."""
    p = res.derived.get("regions_provenance") or {}
    pop = p.get("population") or {}
    clim = p.get("climate") or {}
    a = p.get("assumptions") or {}
    return {"boundaries": p.get("boundaries"), "population": {k: pop.get(k) for k in ("source", "year", "rule")} | {
                "primary": (pop.get("primary") or {}).get("source"), "year_world": p.get("population_year")},
            "climate": {"periods": clim.get("periods"), "sources": clim.get("sources")},
            "assumptions": {k: a.get(k) for k in ("air_trips_per_day", "commute_fraction", "destination_contact_share")},
            "period_selection": p.get("period_selection")}


def _write_csv(job_dir: Path, summary: dict) -> None:
    import pandas as pd
    dd = summary["daily"]
    pd.DataFrame({"day": dd["t"], "I_total_mean": dd["mean"], "I_total_q05": dd["q05"], "I_total_q50": dd["q50"],
                  "I_total_q95": dd["q95"], "E_total_mean": dd["E_mean"], "D_total_mean": dd["D_mean"],
                  "R_total_mean": dd["R_mean"], "new_first_infections_mean": dd["new_first_mean"],
                  "cum_first_infections_mean": dd["cum_first_mean"]}).to_csv(job_dir / "daily.csv", index=False)
    pd.DataFrame(summary["regions"]).to_csv(job_dir / "regions.csv", index=False)
    fr = summary["frames"]
    rows = []
    for i, t in enumerate(fr["t"]):
        for k, r in enumerate(summary["regions"]):
            rows.append({"day": t, "region": r["id"], "I_mean": fr["I"][i][k], "E_mean": fr["E"][i][k], "D_mean": fr["D"][i][k],
                         "first_infected_fraction_mean": fr["first"][i][k]})
    pd.DataFrame(rows).to_csv(job_dir / "regions_daily.csv", index=False)
