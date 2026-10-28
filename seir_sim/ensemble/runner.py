"""앙상블 실행기 (1.6절): R회 반복, 시드 기록, 병렬 실행, 요약 통계, NetCDF/Parquet 저장.

통계 (1.6절)
  I_total(t) = sum_i sum_n I_{n,i}(t),  I_i(t) = sum_n I_{n,i}(t)
  평균 Ī(t), 분산 Var = (1/(R-1)) sum_r (I^(r) - Ī)^2, 5-95% 구간(표본 분위수), 대유행 발생 확률
대유행 정의: max_t I_total(t) >= outbreak_threshold (설정의 이름 있는 매개변수, 기본 1000명).

시드: SeedSequence(simulation.seed).spawn(R) 의 r 번째 자식이 r 번째 실행의 시드다. 같은 설정, 같은 코드면
병렬 여부와 관계없이 같은 결과가 나온다 (테스트로 확인).
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from ..config.build import Scenario, build_scenario
from ..config.schema import Config
from ..provenance import config_hash, environment_record
from ..simulate.ctmc import simulate_ctmc
from ..simulate.hybrid import simulate_hybrid
from ..simulate.ode import integrate_ode
from ..simulate.sde import simulate_sde
from ..simulate.tauleap import simulate_tau

STORED = ("S", "E", "I", "D")


def _simulate(sc: Scenario, method: str, seed) -> tuple[np.ndarray, dict]:
    sim = sc.config.simulation
    kw = dict(days=sim.days, output_dt=sim.output_dt, last_bin_warn=sim.last_bin_warn)
    s, X0 = sc.system, sc.X0
    if method == "ode":
        tr = integrate_ode(s, X0, method=sim.ode.method, rtol=sim.ode.rtol, atol=sim.ode.atol, **kw)
    elif method == "ctmc":
        tr = simulate_ctmc(s, X0, seed=seed, **kw)
    elif method == "tau":
        tr = simulate_tau(s, X0, seed=seed, eps=sim.tau_leap_epsilon, **kw)
    elif method == "sde":
        tr = simulate_sde(s, X0, seed=seed, dt=sim.sde_dt, **kw)
    elif method == "hybrid":
        tr = simulate_hybrid(s, X0, seed=seed, eps=sim.tau_leap_epsilon, threshold_up=sim.hybrid.threshold_up,
                             threshold_down=sim.hybrid.threshold_down, **kw)
    else:
        raise ValueError(method)
    L = tr.layout
    out = np.stack([tr.X[:, :, L.S], tr.X[:, :, L.E_slice].sum(axis=2), tr.X[:, :, L.I_slice].sum(axis=2),
                    tr.X[:, :, L.D]], axis=0)                   # [4, T, K]
    meta = {k: v for k, v in tr.meta.items() if k != "final_state" and not isinstance(v, np.ndarray)}
    return out, meta


# 작업자 프로세스 (설정에서 시나리오를 한 번만 만든다)
_WORKER: dict = {}


def _init_worker(cfg_json: str):
    import warnings
    warnings.simplefilter("ignore")
    _WORKER["sc"] = build_scenario(Config.model_validate_json(cfg_json))


def _work(args):
    r, method, seed = args
    out, meta = _simulate(_WORKER["sc"], method, seed)
    return r, out, meta


@dataclass
class EnsembleResult:
    t: np.ndarray
    region_ids: list[str]
    runs: np.ndarray                  # [R, 4, T, K] float32: S, E, I, D
    method: str
    seeds: list[dict]
    run_meta: list[dict]
    config: Config
    derived: dict
    wall_seconds: float
    outbreak_threshold: float
    info: dict = field(default_factory=dict)

    @property
    def I_total(self) -> np.ndarray:
        """[R, T]"""
        return self.runs[:, 2].sum(axis=2).astype(float)

    def summary(self) -> dict:
        I = self.I_total
        R = I.shape[0]
        mean = I.mean(axis=0)
        var = I.var(axis=0, ddof=1) if R > 1 else np.zeros_like(mean)
        q05, q50, q95 = np.percentile(I, [5, 50, 95], axis=0)
        peak = I.max(axis=1)
        return {"mean": mean, "var": var, "q05": q05, "q50": q50, "q95": q95,
                "outbreak_probability": float(np.mean(peak >= self.outbreak_threshold)),
                "outbreak_probability_se": float(np.sqrt(np.mean(peak >= self.outbreak_threshold)
                                                         * (1 - np.mean(peak >= self.outbreak_threshold)) / R)),
                "peak_I_mean": float(peak.mean()), "peak_day_median": float(np.median(self.t[I.argmax(axis=1)]))}

    def region_summary(self) -> dict:
        Ir = self.runs[:, 2].astype(float)                       # [R, T, K]
        R = Ir.shape[0]
        arrive = np.where((Ir >= 1).any(axis=1), self.t[np.argmax(Ir >= 1, axis=1)], np.nan)   # [R, K]
        return {"mean": Ir.mean(axis=0), "var": Ir.var(axis=0, ddof=1) if R > 1 else np.zeros(Ir.shape[1:]),
                "q05": np.percentile(Ir, 5, axis=0), "q95": np.percentile(Ir, 95, axis=0),
                "arrival_probability": np.mean(np.isfinite(arrive), axis=0),
                "arrival_day_median": np.nanmedian(np.where(np.isfinite(arrive), arrive, np.nan), axis=0)
                if np.isfinite(arrive).any() else np.full(Ir.shape[2], np.nan)}

    # ------------------------------------------------------------ 저장

    def save(self, outdir: str) -> dict:
        import pandas as pd
        import xarray as xr
        os.makedirs(outdir, exist_ok=True)
        s, rs = self.summary(), self.region_summary()
        with np.errstate(all="ignore"):
            arrival_med = rs["arrival_day_median"]
        ds = xr.Dataset(
            {name: (("run", "time", "region"), self.runs[:, k]) for k, name in enumerate(STORED)}
            | {"I_total_mean": (("time",), s["mean"]), "I_total_var": (("time",), s["var"]),
               "I_total_q05": (("time",), s["q05"]), "I_total_q50": (("time",), s["q50"]),
               "I_total_q95": (("time",), s["q95"]),
               "I_region_mean": (("time", "region"), rs["mean"]), "I_region_var": (("time", "region"), rs["var"]),
               "I_region_q05": (("time", "region"), rs["q05"]), "I_region_q95": (("time", "region"), rs["q95"]),
               "arrival_probability": (("region",), rs["arrival_probability"]),
               "arrival_day_median": (("region",), arrival_med)},
            coords={"run": np.arange(self.runs.shape[0]), "time": self.t, "region": self.region_ids},
            attrs=self.attrs(s))
        nc = os.path.join(outdir, "ensemble.nc")
        ds.to_netcdf(nc, engine="h5netcdf")
        pd.DataFrame({"day": self.t, "I_total_mean": s["mean"], "I_total_var": s["var"], "I_total_q05": s["q05"],
                      "I_total_q50": s["q50"], "I_total_q95": s["q95"]}).to_parquet(os.path.join(outdir, "summary_daily.parquet"))
        pd.DataFrame({"region": self.region_ids, "arrival_probability": rs["arrival_probability"],
                      "arrival_day_median": arrival_med, "peak_I_mean": rs["mean"].max(axis=0),
                      "peak_day_of_mean": self.t[rs["mean"].argmax(axis=0)]}).to_parquet(os.path.join(outdir, "summary_regions.parquet"))
        with open(os.path.join(outdir, "run_record.json"), "w", encoding="utf-8") as fh:
            json.dump(json.loads(ds.attrs["record"]), fh, ensure_ascii=False, indent=1)
        return {"netcdf": nc, "dir": outdir}

    def attrs(self, s: dict) -> dict:
        cfg = json.loads(self.config.model_dump_json())
        cfg.get("meta", {}).pop("_config_dir", None)
        derived = {k: v for k, v in self.derived.items() if k != "regions_provenance"}
        record = {"method": self.method, "n_runs": int(self.runs.shape[0]), "wall_seconds": self.wall_seconds,
                  "config": cfg, "config_sha256": config_hash(cfg), "derived": derived,
                  "regions_provenance": self.derived.get("regions_provenance", {}),
                  "regions_synthetic": bool(self.derived.get("regions_synthetic")),
                  "seeds": self.seeds, "environment": environment_record(),
                  "outbreak_threshold": self.outbreak_threshold,
                  "outbreak_probability": s["outbreak_probability"],
                  "run_meta_summary": _meta_summary(self.run_meta), **self.info}
        return {"record": json.dumps(record, ensure_ascii=False, default=str),
                "synthetic_regions": int(bool(self.derived.get("regions_synthetic"))),
                "format": "seir_sim ensemble v1"}


def _meta_summary(metas: list[dict]) -> dict:
    out = {}
    for key in ("wall_seconds", "events", "steps", "exact_events", "switches_to_leap", "switches_to_exact",
                "max_abs_population_error", "max_rel_population_error"):
        vals = [m[key] for m in metas if key in m and m[key] is not None]
        if vals:
            out[key] = {"min": float(np.min(vals)), "mean": float(np.mean(vals)), "max": float(np.max(vals))}
    warn = [m.get("last_bin_warning") for m in metas if "last_bin_warning" in m]
    if warn:
        out["last_bin_warning_runs"] = int(np.sum(warn))
    trunc = [m["truncation"] for m in metas if "truncation" in m]
    if trunc:
        out["sde_truncation_limited_mass_over_flow_max"] = float(max(t["limited_mass_over_flow"] for t in trunc))
    return out


class EnsembleCancelled(Exception):
    """cancel() 가 참을 돌려 실행을 멈췄다."""


def run_ensemble(cfg: Config, method: str | None = None, n_runs: int | None = None,
                 n_workers: int | None = None, outbreak_threshold: float = 1000.0,
                 progress=None, cancel=None) -> EnsembleResult:
    """progress(done, total): 실행 하나가 끝날 때마다 부른다. cancel(): 참이면 남은 실행을 멈추고 EnsembleCancelled."""
    import warnings
    sim = cfg.simulation
    method = method or sim.method
    R = 1 if method == "ode" else (n_runs or sim.n_runs)
    workers = n_workers or sim.n_workers
    sc = build_scenario(cfg)
    children = np.random.SeedSequence(sim.seed).spawn(R)
    seeds = [{"run": r, "entropy": str(c.entropy), "spawn_key": list(c.spawn_key)} for r, c in enumerate(children)]
    t0 = time.perf_counter()
    T = int(np.floor(sim.days / sim.output_dt + 1e-9)) + 1
    runs = np.empty((R, len(STORED), T, sc.system.regions.K), dtype=np.float32)
    metas: list[dict] = [{}] * R
    if workers <= 1 or R == 1:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for r, c in enumerate(children):
                if cancel is not None and cancel():
                    raise EnsembleCancelled(f"{r}/{R} 실행 후 취소")
                out, meta = _simulate(sc, method, c)
                runs[r], metas[r] = out, meta
                if progress is not None:
                    progress(r + 1, R)
    else:
        import multiprocessing as mp
        # fork 는 다중 스레드 부모에서 교착 위험이 있어 forkserver 를 쓴다 (작업자는 설정 JSON 에서 시나리오를 새로 만든다)
        ctx = mp.get_context("forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_init_worker,
                                 initargs=(cfg.model_dump_json(),)) as ex:
            done = 0
            for r, out, meta in ex.map(_work, [(r, method, c) for r, c in enumerate(children)], chunksize=1):
                runs[r], metas[r] = out, meta
                done += 1
                if progress is not None:
                    progress(done, R)
                if cancel is not None and cancel():
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise EnsembleCancelled(f"{done}/{R} 실행 후 취소")
    wall = time.perf_counter() - t0
    t = sim.output_dt * np.arange(T)
    return EnsembleResult(t, list(sc.system.regions.names), runs, method, seeds, metas, cfg, sc.derived, wall,
                          outbreak_threshold, {"n_workers": workers})
