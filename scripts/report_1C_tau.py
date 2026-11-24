"""1-C 2a 보고서: 이동 사건 합치기 효과와 이항 tau-leaping 의 정확도·성능.

사용법: python scripts/report_1C_tau.py
출력:   docs/reports/1C_tau.json, docs/reports/1C_tau.md
지역은 합성 자료, 감염병 값은 코드 검증용 가정이다.
"""

import json
import resource
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from seir_sim.model import analysis as A                 # noqa: E402
from seir_sim.model.params import EpiParams              # noqa: E402
from seir_sim.model.reactions import ReactionSystem      # noqa: E402
from seir_sim.model.regions import RegionSet             # noqa: E402
from seir_sim.model.state import initial_state           # noqa: E402
from seir_sim.provenance import environment_record       # noqa: E402
from seir_sim.simulate.ctmc import simulate_ctmc         # noqa: E402
from seir_sim.simulate.ode import integrate_ode          # noqa: E402
from seir_sim.simulate.tauleap import simulate_tau       # noqa: E402

BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1.0, T1=1.0, Pmin=0.3, alpha=0.5,
            beta=0.3, lam=1 / 180, f1=0.01, phi_spec={"form": "power", "delta": 0.5}, M=8)


def P(**kw):
    p = EpiParams(**{**BASE, **kw})
    return p.with_(c0=A.c0_reference(2.5, p))


def int_regions(reg):
    return RegionSet(reg.names, np.round(reg.population), reg.density, reg.contact, reg.mobility, True)


def vs_ctmc():
    N, R = 2e4, 300
    sysm = ReactionSystem(P(), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 200.0})
    It = np.stack([simulate_tau(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(1).spawn(R)])
    Ic = np.stack([simulate_ctmc(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(2).spawn(R)])
    idx = np.arange(20, 201, 20)
    st, sc = It[:, idx].std(0, ddof=1), Ic[:, idx].std(0, ddof=1)
    z = (It[:, idx].mean(0) - Ic[:, idx].mean(0)) / np.sqrt((st ** 2 + sc ** 2) / R)
    ok = sc > 5
    return {"N": N, "runs": R, "max_abs_z_mean": float(np.abs(z).max()),
            "sd_ratio_min": float((st[ok] / sc[ok]).min()), "sd_ratio_max": float((st[ok] / sc[ok]).max())}


def eps_sensitivity():
    N = 1e7
    sysm = ReactionSystem(P(), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 1e5})
    ode = integrate_ode(sysm, X0, 365, rtol=1e-10, atol=1e-6).I_total
    rows = []
    for eps in (0.1, 0.03, 0.01, 0.003):
        devs, walls, steps = [], [], []
        for s in range(3):
            tr = simulate_tau(sysm, X0, 365, seed=s, eps=eps)
            devs.append(np.max(np.abs(tr.I_total - ode)) / ode.max())
            walls.append(tr.meta["wall_seconds"])
            steps.append(tr.meta["steps"])
        rows.append({"eps": eps, "sup_dev_over_peak_mean_of_3": float(np.mean(devs)),
                     "steps": int(np.mean(steps)), "wall_s": float(np.mean(walls))})
    return rows


def extinction_tau():
    p = EpiParams(**{**BASE, "M": 2})
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), RegionSet.single(1e6))
    L = sysm.layout
    X0 = initial_state(L, np.array([1e6]), {0: 1.0})
    R, ext = 4000, 0
    for s in np.random.SeedSequence(99).spawn(R):
        tr = simulate_tau(sysm, X0, 120, output_dt=120, seed=s)
        xe = tr.X[-1, 0]
        ext += int(xe[L.E_slice].sum() + xe[L.I_slice].sum() == 0 and xe[L.RP_slice].sum() + xe[L.D] < 200)
    return {"theory": 0.4, "estimate": ext / R, "z": (ext / R - 0.4) / np.sqrt(0.24 / R)}


def performance():
    rows = []
    cases = [("단일 지역 N=1e6", RegionSet.single(1e6), 10.0)]
    for K, pop in ((17, 5e7), (200, 7.8e9)):
        reg = int_regions(RegionSet.synthetic_random(K, np.random.default_rng(K), pop, 1e-3))
        cases.append((f"합성 {K}지역 {pop:.1e}명", reg, 10.0))
    for label, reg, seed_n in cases:
        t = time.perf_counter()
        sysm = ReactionSystem(P(), reg)
        build = time.perf_counter() - t
        X0 = initial_state(sysm.layout, reg.population, {0: seed_n})
        ode = integrate_ode(sysm, X0, 365)
        tr = simulate_tau(sysm, X0, 365, seed=0)
        rows.append({"case": label, "K": reg.K, "build_s": build, "ode_s": ode.meta["wall_seconds"],
                     "tau_s": tr.meta["wall_seconds"], "tau_steps": tr.meta["steps"],
                     "tau_min": tr.meta["min_tau"], "pop_err": tr.meta["max_abs_population_error"]})
    return rows


def main():
    warnings.simplefilter("ignore")
    s0 = ReactionSystem(P(), RegionSet.single(100.0))
    simulate_tau(s0, initial_state(s0.layout, np.array([100.0]), {0: 1.0}), 1, seed=0)
    simulate_ctmc(s0, initial_state(s0.layout, np.array([100.0]), {0: 1.0}), 1, seed=0)
    t0 = time.perf_counter()
    rep = {"environment": environment_record(), "vs_ctmc": vs_ctmc(), "eps": eps_sensitivity(),
           "extinction_tau": extinction_tau(), "performance": performance()}
    rep["total_wall_s"] = time.perf_counter() - t0
    rep["peak_rss_MB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    out = ROOT / "docs" / "reports"
    (out / "1C_tau.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str))
    e, v, x = rep["environment"], rep["vs_ctmc"], rep["extinction_tau"]
    md = ["# 1-C 2a: 이항 tau-leaping 보고서 (자동 생성: scripts/report_1C_tau.py)", "",
          f"환경: Python {e['python']}, CPU {e['cpu_count']}코어, 패키지 {e['packages']}, 커밋 {e['git_commit']}", "",
          "## 1. CTMC 와 분포 비교 (전체 모형, M = 8, N = 2e4, 초기 1%, 200일, 각 300회, eps = 0.03)", "",
          f"평균 차이 최대 |z| = {v['max_abs_z_mean']:.2f}, 표준편차 비율 {v['sd_ratio_min']:.3f} ~ {v['sd_ratio_max']:.3f}", "",
          "## 2. eps 민감도 (N = 1e7, 초기 1%, 365일, 3회 평균; 확률적 편차 ~ 1/sqrt(N) = 3e-4)", "",
          "| eps | max|tau - ODE| / 최고값 | 단계 수 | 시간 s |", "|---|---|---|---|"]
    md += [f"| {r['eps']} | {r['sup_dev_over_peak_mean_of_3']:.2e} | {r['steps']} | {r['wall_s']:.2f} |" for r in rep["eps"]]
    md += ["", "## 3. 소규모 수 영역 정확도 (소멸 확률, R0 = 2.5, 1명, 4000회)", "",
           f"이론 0.4, tau-leap 추정 {x['estimate']:.4f} (z = {x['z']:+.2f}). 120일 시점에 E+I = 0 이고 누적 감염 < 200 이면 소멸로 본다.", "",
           "## 4. 계산 성능 (365일 1회, 이동 사건 합친 후)", "",
           "| 경우 | K | 구성 s | ODE s | tau s | tau 단계 | 최소 tau | 보존 오차 |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['case']} | {r['K']} | {r['build_s']:.2f} | {r['ode_s']:.2f} | {r['tau_s']:.2f} | {r['tau_steps']} | {r['tau_min']:.1e} | {r['pop_err']:.0f} |"
           for r in rep["performance"]]
    md += ["", f"전체 실행 {rep['total_wall_s']:.0f} s, 최대 메모리 {rep['peak_rss_MB']:.0f} MB."]
    (out / "1C_tau.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
