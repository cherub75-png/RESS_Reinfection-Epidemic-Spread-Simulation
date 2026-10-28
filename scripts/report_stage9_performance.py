"""9단계 성능·안정성 측정 (실행 시간, 최대 메모리, 앙상블 크기에 따른 통계 안정성, 동시 작업).

각 경우를 별도 프로세스에서 실행해 최대 메모리(ru_maxrss)를 따로 잰다. 감염병 값은 코드 검증용 가정이다.
사용법: python -I scripts/report_stage9_performance.py [--skip-world]
출력:   docs/reports/9_performance.md, .json
"""

import argparse
import json
import multiprocessing as mp
import resource
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DISEASE = {"sigma": 1 / 5.2, "gamma": 1 / 7, "transmission": {"R0": 2.5, "r0_reference": "reference"}, "P1": 1.0, "T1": 1.0,
           "Pmin": 0.3, "alpha": 0.5, "beta": 0.3, "lam": 1 / 180, "f1": 0.01, "phi": {"form": "power", "delta": 0.5}, "M": 8}


def cfg(regions, seeds, days, method, runs, workers=1, eps=0.003):
    return {"run_mode": "development", "meta": {"name": "perf"}, "disease": DISEASE, "regions": regions,
            "contact_model": {"h": {"form": "power", "eta": 0.2}, "rho_ref": "pop_weighted_mean"},
            "initial": {"start_date": "2020-01-20", "seeds": seeds},
            "simulation": {"days": days, "method": method, "n_runs": runs, "n_workers": workers, "tau_leap_epsilon": eps}}


CASES = {
    "single_1e6_ode": (lambda: cfg({"source": "synthetic_single", "population": 1e6}, [{"region": "region0", "count": 10}], 365, "ode", 1)),
    "single_2e4_ctmc_x20": (lambda: cfg({"source": "synthetic_single", "population": 2e4}, [{"region": "region0", "count": 10}], 365, "ctmc", 20)),
    "single_1e6_hybrid_x20": (lambda: cfg({"source": "synthetic_single", "population": 1e6}, [{"region": "region0", "count": 10}], 365, "hybrid", 20)),
    "single_1e6_tau_x20": (lambda: cfg({"source": "synthetic_single", "population": 1e6}, [{"region": "region0", "count": 10}], 365, "tau", 20)),
    "single_1e6_sde_x20": (lambda: cfg({"source": "synthetic_single", "population": 1e6}, [{"region": "region0", "count": 10}], 365, "sde", 20)),
    "kor17_ode": (lambda: cfg({"source": "dataset", "path": "registry:KOR_admin1"}, [{"region": "KR-11", "count": 10}], 365, "ode", 1)),
    "kor17_hybrid_x1": (lambda: cfg({"source": "dataset", "path": "registry:KOR_admin1"}, [{"region": "KR-11", "count": 10}], 365, "hybrid", 1)),
    "kor17_hybrid_x20_w4": (lambda: cfg({"source": "dataset", "path": "registry:KOR_admin1"}, [{"region": "KR-11", "count": 10}], 365, "hybrid", 20, 4)),
    "kor17_hybrid_eps0.01_x20_w4": (lambda: cfg({"source": "dataset", "path": "registry:KOR_admin1"}, [{"region": "KR-11", "count": 10}], 365, "hybrid", 20, 4, 0.01)),
    "kor17_hybrid_3y_x4_w4": (lambda: cfg({"source": "dataset", "path": "registry:KOR_admin1"}, [{"region": "KR-11", "count": 10}], 1095, "hybrid", 4, 4)),
    "world246_ode": (lambda: cfg({"source": "dataset", "path": "registry:world_countries"}, [{"region": "CHN", "count": 10}], 365, "ode", 1)),
    "world246_hybrid_eps0.01_x4_w4": (lambda: cfg({"source": "dataset", "path": "registry:world_countries"}, [{"region": "CHN", "count": 10}], 365, "hybrid", 4, 4, 0.01)),
}


def run_case(name, q):
    warnings.simplefilter("ignore")
    from seir_sim.config.schema import Config
    from seir_sim.ensemble.runner import run_ensemble
    c = Config.model_validate(CASES[name]())
    t0 = time.perf_counter()
    res = run_ensemble(c)
    wall = time.perf_counter() - t0
    s = res.summary()
    q.put({"case": name, "wall_s": wall, "runs": int(res.runs.shape[0]), "K": len(res.region_ids), "days": float(res.t[-1]),
           "method": res.method, "peak_I_mean": s["peak_I_mean"], "result_MB": res.runs.nbytes / 1e6,
           "maxrss_MB_self": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
           "maxrss_MB_children": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024})


def ensemble_stability(q):
    """하이브리드 반복 수 R 에 따른 요약 통계 (같은 시드열의 앞쪽 R 개): 정점 평균과 그 표준오차, 대유행 확률."""
    warnings.simplefilter("ignore")
    from seir_sim.config.schema import Config
    from seir_sim.ensemble.runner import run_ensemble
    c = Config.model_validate(cfg({"source": "synthetic_single", "population": 1e5}, [{"region": "region0", "count": 3}], 200, "hybrid", 400, 4))
    res = run_ensemble(c)
    I = res.I_total
    peak = I.max(axis=1)
    out = []
    for R in (10, 20, 50, 100, 200, 400):
        p = peak[:R]
        ob = p >= 1000
        out.append({"R": R, "outbreak_probability": float(ob.mean()), "outbreak_se": float(np.sqrt(ob.mean() * (1 - ob.mean()) / R)),
                    "peak_mean_given_outbreak": float(p[ob].mean()) if ob.any() else None,
                    "peak_se_given_outbreak": float(p[ob].std(ddof=1) / np.sqrt(ob.sum())) if ob.sum() > 1 else None})
    q.put({"case": "ensemble_stability", "rows": out, "wall_s": res.wall_seconds})


def concurrent_jobs():
    """웹 작업 관리자로 같은 작업 2개를 동시(2개)·순차(1개)로 돌린 시간."""
    import tempfile
    from seir_sim.web.jobs import JobManager
    req = {"title": "perf", "dataset": "KOR_admin1", "R0": 2.5, "method": "hybrid", "n_runs": 8, "days": 180,
           "seeds": [{"region": "KR-11", "count": 10}]}
    out = {}
    for conc in (1, 2):
        with tempfile.TemporaryDirectory() as d:
            jm = JobManager(Path(d), max_concurrent=conc)
            t0 = time.perf_counter()
            ids = [jm.submit("scenario", req, f"perf{i}") for i in range(2)]
            st = [jm.wait(i, 1800) for i in ids]
            out[f"max_concurrent_{conc}"] = {"wall_s": time.perf_counter() - t0, "states": [s["state"] for s in st]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-world", action="store_true")
    a = ap.parse_args()
    ctx = mp.get_context("forkserver")
    results = []
    for name in CASES:
        if a.skip_world and name.startswith("world"):
            continue
        q = ctx.Queue()
        p = ctx.Process(target=run_case, args=(name, q))
        p.start()
        r = q.get()
        p.join()
        print(r, flush=True)
        results.append(r)
    q = ctx.Queue()
    p = ctx.Process(target=ensemble_stability, args=(q,))
    p.start()
    stab = q.get()
    p.join()
    conc = concurrent_jobs()
    from seir_sim.provenance import environment_record
    rep = {"environment": environment_record(), "cases": results, "ensemble_stability": stab, "concurrent_jobs": conc}
    out = ROOT / "docs" / "reports"
    (out / "9_performance.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str))
    env = rep["environment"]
    L = ["# 9단계 성능 측정 (자동 생성: scripts/report_stage9_performance.py)", "",
         f"환경: CPU {env.get('cpu_count', '?')}개, Python {env.get('python', '?')}. 각 경우를 별도 프로세스에서 실행 (최대 메모리 = 그 프로세스와 자식의 ru_maxrss).",
         "감염병 값은 코드 검증용 가정, 하이브리드 eps 는 표에 적은 값.", "",
         "| 경우 | 방법 | 지역 수 | 기간 (일) | 실행 수 | 시간 (초) | 실행당 (초) | 결과 배열 MB | 최대 메모리 MB (본/자식) |", "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['case']} | {r['method']} | {r['K']} | {r['days']:.0f} | {r['runs']} | {r['wall_s']:.1f} | {r['wall_s'] / r['runs']:.2f} | "
                 f"{r['result_MB']:.1f} | {r['maxrss_MB_self']:.0f} / {r['maxrss_MB_children']:.0f} |")
    L += ["", "## 앙상블 크기에 따른 안정성 (단일 지역 N = 1e5, 초기 3명, 하이브리드 400회 중 앞쪽 R 개)", "",
          "| R | 대유행 확률 | 표준오차 | 대유행 시 정점 평균 | 표준오차 |", "|---|---|---|---|---|"]
    def n0(v):
        return "–" if v is None else f"{v:,.0f}"
    for r in stab["rows"]:
        L.append(f"| {r['R']} | {r['outbreak_probability']:.3f} | {r['outbreak_se']:.3f} | "
                 f"{n0(r['peak_mean_given_outbreak'])} | {n0(r['peak_se_given_outbreak'])} |")
    L += ["", "## 동시 작업 (웹 작업 관리자, 대한민국 시도 하이브리드 8회 x 180일 작업 2개)", ""]
    for k, v in conc.items():
        L.append(f"- {k}: {v['wall_s']:.1f} 초, 상태 {v['states']}")
    (out / "9_performance.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
