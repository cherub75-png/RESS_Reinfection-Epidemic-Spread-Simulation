"""웹 시나리오 요청 -> 설정 -> 앙상블 실행 -> 저장·요약 (작업 프로세스 안에서 실행).

감염병 기본값은 configs/example_single_region.yaml 의 COVID 유사 "코드 검증용 가정" 이다. 화면에 그렇게 표시한다.
지역은 데이터셋 저장소(registry)의 활성 버전 또는 단일 합성 지역이다.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]


class SeedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: str = Field(max_length=40)
    count: float = Field(gt=0, le=1e7)


class InterventionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0, le=3650)
    end: float = Field(gt=0, le=3650)
    value: float = Field(ge=0, le=1)
    regions: list[str] | None = Field(default=None, max_length=300)


class ScenarioRequest(BaseModel):
    """화면에서 받는 시나리오 (모든 값 검증; 나머지는 기본 가정값)."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field("시나리오", max_length=80)
    dataset: str = Field("KOR_admin1", pattern=r"^[A-Za-z0-9_]{1,40}$")   # 'synthetic_single' 또는 저장소 이름
    population: float | None = Field(None, gt=0, le=1e10)                 # synthetic_single 일 때만
    R0: float = Field(2.5, gt=0, le=20)
    r0_reference: Literal["reference", "region", "origin", "population_mean", "network"] = "reference"
    reference_region: str | None = Field(None, max_length=40)
    method: Literal["ode", "sde", "ctmc", "tau", "hybrid"] = "hybrid"
    n_runs: int = Field(20, ge=1, le=500)
    n_workers: int = Field(1, ge=1, le=4)
    days: int = Field(180, ge=1, le=1095)
    start_date: dt.date = dt.date(2020, 1, 20)
    seeds: list[SeedIn] = Field(min_length=1, max_length=20)
    interventions: list[InterventionIn] = Field(default_factory=list, max_length=50)
    eta: float = Field(0.2, ge=0, le=2)                                    # h(rho) = (rho/rho_ref)^eta
    seed: int = Field(20260101, ge=0, le=2**31)


def disease_defaults() -> dict:
    cfg = yaml.safe_load((ROOT / "configs" / "example_single_region.yaml").read_text())
    return cfg["disease"]


def build_config(req: ScenarioRequest) -> dict:
    d = disease_defaults()
    d["transmission"] = {"R0": req.R0, "r0_reference": req.r0_reference}
    if req.r0_reference == "region":
        d["transmission"]["reference_region"] = req.reference_region
    if req.dataset == "synthetic_single":
        regions = {"source": "synthetic_single", "population": req.population or 1e6}
        region_names = ["region0"]
    else:
        regions = {"source": "dataset", "path": f"registry:{req.dataset}"}
        region_names = None
    seeds = [{"region": s.region if region_names is None else region_names[0], "count": s.count} for s in req.seeds]
    if req.method != "ode":
        seeds = [{**s, "count": float(max(1, round(s["count"])))} for s in seeds]
    return {
        "run_mode": "development",
        "meta": {"name": req.title, "source": "web", "note": "감염병 값은 코드 검증용 가정 (실제 추정치 아님)"},
        "disease": d,
        "regions": regions,
        "contact_model": {"h": {"form": "power", "eta": req.eta}, "rho_ref": "pop_weighted_mean"},
        "environment": {"g": {"form": "constant"}, "status": "neutral_default", "source": "none"},
        "interventions": [i.model_dump() for i in req.interventions],
        "initial": {"start_date": str(req.start_date), "seed_compartment": "I1", "seeds": seeds},
        "simulation": {"days": req.days, "method": req.method, "n_runs": req.n_runs, "seed": req.seed,
                       "n_workers": req.n_workers},
    }


def run_scenario(req_raw: dict, job_dir: Path, cancel=None, progress=None) -> dict:
    from ..config.build import build_scenario
    from ..config.schema import Config
    from ..ensemble.runner import run_ensemble
    req = ScenarioRequest.model_validate(req_raw)
    cfg = Config.model_validate(build_config(req))
    (job_dir / "config.json").write_text(cfg.model_dump_json(indent=1))
    res = run_ensemble(cfg, progress=progress, cancel=cancel)
    res.save(str(job_dir))
    summary = web_summary(res, req, cfg)
    (job_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, default=_json_default))
    _write_csv(job_dir, res, summary)
    return summary


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _clean(a) -> list:
    return [None if not np.isfinite(v) else float(v) for v in np.asarray(a, float)]


def web_summary(res, req: ScenarioRequest, cfg) -> dict:
    s, rs = res.summary(), res.region_summary()
    runs = res.runs.astype(float)                       # [R, 4, T, K]: S, E, I, D
    pop0 = runs[:, :, 0, :].sum(axis=1).mean(axis=0)     # 지역별 초기 총인구
    S0, Send = runs[:, 0, 0, :], runs[:, 0, -1, :]
    attack = ((S0 - Send) / np.maximum(pop0, 1)).mean(axis=0)
    deaths = runs[:, 3, -1, :].mean(axis=0)
    T = res.t.size
    step = max(1, int(np.ceil(T / 120)))
    frames_idx = np.arange(0, T, step)
    prev = rs["mean"][frames_idx] / np.maximum(pop0, 1) * 1e5         # 10만 명당 유병 (평균)
    d = res.derived
    derived = {k: d.get(k) for k in ("c0", "c0_basis", "reference_region", "c0_by_basis", "R0_reference", "R0_network_t0",
                                     "R0_isolated_population_weighted_mean", "population_share_isolated_R0_gt1",
                                     "R0_network_dominant_population_share", "regions_synthetic", "g_status")}
    warnings = []
    if d.get("R0_network_dominated_by_small_population"):
        warnings.append("지역망 R0 가 인구가 적은 지역에 지배된다 (D-008).")
    if d.get("regions_synthetic"):
        warnings.append("합성 지역 자료로 실행했다 (실제 지역 아님).")
    lb = res.run_meta and sum(1 for m in res.run_meta if m.get("last_bin_warning"))
    if lb:
        warnings.append(f"{lb}개 실행에서 마지막 재감염 칸 점유율 경고 (M 부족 가능성).")
    names = list(res.region_ids)
    return {
        "title": req.title, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "request": req.model_dump(mode="json"), "method": res.method, "n_runs": int(runs.shape[0]),
        "wall_seconds": res.wall_seconds, "start_date": str(req.start_date),
        "labels": {"kind": "scenario", "disease_values": "가정 (코드 검증용, 실제 추정치 아님)",
                   "environment": "g = 1 (neutral_default)", "dataset": req.dataset},
        "derived": derived, "warnings": warnings,
        "daily": {"t": res.t.tolist(), "mean": _clean(s["mean"]), "q05": _clean(s["q05"]), "q50": _clean(s["q50"]),
                  "q95": _clean(s["q95"]), "deaths_mean": _clean(runs[:, 3].sum(axis=2).mean(axis=0))},
        "outbreak_probability": s["outbreak_probability"], "peak_I_mean": s["peak_I_mean"],
        "peak_day_median": s["peak_day_median"],
        "regions": [{"id": names[k], "population": float(pop0[k]), "attack_mean": float(attack[k]),
                     "deaths_mean": float(deaths[k]), "peak_I_mean": float(rs["mean"][:, k].max()),
                     "peak_day": float(res.t[int(np.argmax(rs["mean"][:, k]))]),
                     "arrival_probability": float(rs["arrival_probability"][k]),
                     "arrival_day_median": None if not np.isfinite(rs["arrival_day_median"][k]) else float(rs["arrival_day_median"][k])}
                    for k in range(len(names))],
        "frames": {"t": res.t[frames_idx].tolist(), "prevalence_per_100k": np.round(prev, 3).tolist(),
                   "max": float(np.nanmax(prev)) if prev.size else 0.0},
    }


def _write_csv(job_dir: Path, res, summary: dict) -> None:
    import pandas as pd
    dd = summary["daily"]
    pd.DataFrame({"day": dd["t"], "I_total_mean": dd["mean"], "I_total_q05": dd["q05"], "I_total_q50": dd["q50"],
                  "I_total_q95": dd["q95"], "D_total_mean": dd["deaths_mean"]}).to_csv(job_dir / "daily.csv", index=False)
    pd.DataFrame(summary["regions"]).to_csv(job_dir / "regions.csv", index=False)
