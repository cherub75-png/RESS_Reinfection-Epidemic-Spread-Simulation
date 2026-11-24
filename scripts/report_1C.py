"""1-C 보고서: CTMC 검증 통계값과 계산 성능.

사용법: python scripts/report_1C.py
출력:   docs/reports/1C_ctmc.json, docs/reports/1C_ctmc.md
지역은 합성 자료, 감염병 값은 코드 검증용 가정이다.
"""

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seir_sim.model import analysis as A                 # noqa: E402
from seir_sim.model.params import EpiParams              # noqa: E402
from seir_sim.model.reactions import MOVE, ReactionSystem  # noqa: E402
from seir_sim.model.regions import RegionSet             # noqa: E402
from seir_sim.model.state import initial_state           # noqa: E402
from seir_sim.provenance import environment_record       # noqa: E402
from seir_sim.simulate.ctmc import simulate_ctmc         # noqa: E402
from seir_sim.simulate.ode import integrate_ode          # noqa: E402

BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1.0, T1=1.0, Pmin=0.3, alpha=0.5,
            beta=0.3, lam=1 / 180, f1=0.01, phi_spec={"form": "power", "delta": 0.5}, M=8)


def P(**kw):
    p = EpiParams(**{**BASE, **kw})
    return p.with_(c0=A.c0_reference(2.5, p))


def extinction():
    out = []
    for R0, k, comp in ((2.5, 1, "I1"), (2.5, 1, "E1"), (2.5, 2, "I1"), (1.5, 1, "I1")):
        p = EpiParams(**{**BASE, "M": 2})
        sysm = ReactionSystem(p.with_(c0=A.c0_reference(R0, p)), RegionSet.single(1e6))
        X0 = initial_state(sysm.layout, np.array([1e6]), {0: float(k)}, comp)
        R, ext = 4000, 0
        for s in np.random.SeedSequence(99).spawn(R):
            fs = simulate_ctmc(sysm, X0, 1e4, output_dt=1e4, seed=s, stop_EI_at_or_below=0,
                               stop_EI_at_or_above=200).meta["final_state"][0]
            ext += int(fs[sysm.layout.E_slice].sum() + fs[sysm.layout.I_slice].sum() == 0)
        q = (1 / R0) ** k
        out.append({"R0": R0, "k": k, "seed": comp, "theory": q, "estimate": ext / R,
                    "z": (ext / R - q) / np.sqrt(q * (1 - q) / R)})
    return out


def final_size():
    R0, N, I0 = 2.5, 5000.0, 10.0
    p = EpiParams(**{**BASE, "M": 2, "lam": 0.0, "Pmin": 0.0, "alpha": 1000.0, "f1": 0.0})
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(R0, p)), RegionSet.single(N))
    L = sysm.layout
    X0 = initial_state(L, np.array([N]), {0: I0})
    S0 = N - I0
    s_inf = brentq(lambda s: np.log(S0 / s) - R0 * (S0 - s + I0) / N, 1e-9, S0 * (1 - 1e-12))
    z = (S0 - s_inf) / N
    sig2 = z * (1 - z) * (1 + R0 ** 2 * (1 - z)) / (1 - R0 * (1 - z)) ** 2
    Zs = np.array([(S0 - simulate_ctmc(sysm, X0, 1e4, output_dt=1e4, seed=s, stop_EI_at_or_below=0)
                    .meta["final_state"][0, L.S]) / N for s in np.random.SeedSequence(5).spawn(600)])
    major = Zs[Zs > 0.3]
    return {"N": N, "runs": 600, "major": int(major.size), "z_theory": z, "z_mean": float(major.mean()),
            "z_se": float(major.std(ddof=1) / np.sqrt(major.size)),
            "var_ratio_N_var_over_theory": float(N * major.var(ddof=1) / sig2)}


def lln():
    rows = []
    for N in (5e3, 5e4, 5e5):
        sysm = ReactionSystem(P(), RegionSet.single(N))
        X0 = initial_state(sysm.layout, np.array([N]), {0: N * 0.01})
        ode = integrate_ode(sysm, X0, 365).I_total
        R = 16 if N < 5e5 else 4
        I = np.stack([simulate_ctmc(sysm, X0, 365, seed=s).I_total for s in np.random.SeedSequence(3).spawn(R)])
        rows.append({"N": N, "runs": R,
                     "sup_mean_dev_over_peak": float(np.max(np.abs(I.mean(0) - ode)) / ode.max()),
                     "median_single_path_sup_dev_over_peak": float(np.median(np.max(np.abs(I - ode), axis=1)) / ode.max())})
    return rows


def performance():
    rows = []
    for label, reg in (("단일 지역 N=1e4", RegionSet.single(1e4)), ("단일 지역 N=1e5", RegionSet.single(1e5)),
                       ("단일 지역 N=1e6", RegionSet.single(1e6))):
        sysm = ReactionSystem(P(), reg)
        X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
        t = time.perf_counter()
        tr = simulate_ctmc(sysm, X0, 365, seed=0)
        w = time.perf_counter() - t
        rows.append({"case": label, "days": 365, "channels": len(sysm.channels), "events": tr.meta["events"],
                     "wall_s": w, "events_per_s": tr.meta["events"] / w})
    # 합성 17지역 (5천만 명) — 1일만 실행해 사건율을 잰 뒤 365일로 외삽
    rng = np.random.default_rng(7)
    reg = RegionSet.synthetic_random(17, rng, 5e7, 1e-3)
    reg = RegionSet(reg.names, np.round(reg.population), reg.density, reg.contact, reg.mobility, True)
    sysm = ReactionSystem(P(), reg)
    X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
    t = time.perf_counter()
    tr = simulate_ctmc(sysm, X0, 1, seed=0)
    w = time.perf_counter() - t
    move_share = float(sysm.propensities(X0, 0.0)[sysm.channels.kind == MOVE].sum() / sysm.propensities(X0, 0.0).sum())
    rows.append({"case": "합성 17지역 5천만 명 (1일 측정)", "days": 1, "channels": len(sysm.channels),
                 "events": tr.meta["events"], "wall_s": w, "events_per_s": tr.meta["events"] / w,
                 "move_share_of_rate_at_t0": move_share,
                 "extrapolated_hours_per_365d_run_lower_bound": tr.meta["events"] * 365 / (tr.meta["events"] / w) / 3600})
    return rows


def main():
    simulate_ctmc(ReactionSystem(P(), RegionSet.single(100)), initial_state(
        ReactionSystem(P(), RegionSet.single(100)).layout, np.array([100.0]), {0: 1.0}), 1, seed=0)  # JIT 컴파일
    t0 = time.perf_counter()
    rep = {"environment": environment_record(), "extinction": extinction(), "final_size": final_size(),
           "lln": lln(), "performance": performance()}
    rep["total_wall_s"] = time.perf_counter() - t0
    rep["peak_rss_MB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    out = ROOT / "docs" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / "1C_ctmc.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str))
    e = rep["environment"]
    md = ["# 1-C CTMC 보고서 (자동 생성: scripts/report_1C.py)", "",
          f"환경: Python {e['python']}, CPU {e['cpu_count']}코어, 패키지 {e['packages']}, 커밋 {e['git_commit']}", "",
          "## 1. 소멸 확률 (분기과정 이론 (1/R0)^k, 4000회)", "", "| R0 | k | 구획 | 이론 | 추정 | z |", "|---|---|---|---|---|---|"]
    md += [f"| {r['R0']} | {r['k']} | {r['seed']} | {r['theory']:.4f} | {r['estimate']:.4f} | {r['z']:+.2f} |" for r in rep["extinction"]]
    f = rep["final_size"]
    md += ["", "## 2. 최종 규모 (대유행 조건부, N = 5000, 600회)", "",
           f"이론 z = {f['z_theory']:.4f}, 표본 평균 {f['z_mean']:.4f} (SE {f['z_se']:.4f}), "
           f"N·Var / 점근 분산 = {f['var_ratio_N_var_over_theory']:.3f}", "",
           "## 3. 대수의 법칙 (전체 모형, M = 8, 초기 1%)", "", "| N | 회 | 평균-ODE 최대차/최고값 | 단일 경로 최대차/최고값 (중앙값) |", "|---|---|---|---|"]
    md += [f"| {r['N']:.0e} | {r['runs']} | {r['sup_mean_dev_over_peak']:.4f} | {r['median_single_path_sup_dev_over_peak']:.4f} |" for r in rep["lln"]]
    md += ["", "## 4. 계산 성능", "", "| 경우 | 기간 | 사건 수(채널) | 발생 사건 | 시간 s | 사건/s |", "|---|---|---|---|---|---|"]
    md += [f"| {r['case']} | {r['days']} | {r['channels']} | {r['events']} | {r['wall_s']:.2f} | {r['events_per_s']:.2e} |" for r in rep["performance"]]
    big = rep["performance"][-1]
    md += ["", f"합성 17지역: t0 에서 전체 율 중 이동 사건 비율 {big['move_share_of_rate_at_t0']:.3f}. "
           f"365일 1회 외삽 하한 {big['extrapolated_hours_per_365d_run_lower_bound']:.1f} 시간 (감염 확산 후 사건이 더 늘어남).", "",
           f"전체 실행 {rep['total_wall_s']:.0f} s, 최대 메모리 {rep['peak_rss_MB']:.0f} MB."]
    (out / "1C_ctmc.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore")
    main()
