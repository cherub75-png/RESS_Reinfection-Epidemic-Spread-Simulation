"""1-B 검증 보고서 생성: 계산 시간, R0 기준 비교, 초기 구획 비교, M 수렴표.

사용법: python scripts/report_1B.py
출력:   docs/reports/1B_ode_validation.json, docs/reports/1B_ode_validation.md
모든 지역은 합성 자료이며, 감염병 값은 코드 검증용 가정이다.
"""

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seir_sim.model import analysis as A                 # noqa: E402
from seir_sim.model.params import EpiParams              # noqa: E402
from seir_sim.model.reactions import ReactionSystem      # noqa: E402
from seir_sim.model.regions import RegionSet             # noqa: E402
from seir_sim.model.state import initial_state           # noqa: E402
from seir_sim.provenance import environment_record       # noqa: E402
from seir_sim.simulate.ode import integrate_ode          # noqa: E402

BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1.0, T1=1.0, Pmin=0.3, alpha=0.5,
            beta=0.3, lam=1 / 180, f1=0.01, phi_spec={"form": "power", "delta": 0.5}, M=4)
H = {"form": "power", "eta": 0.2}


def summary(tr, pop):
    I = tr.I_total
    L = tr.layout
    return {"peak_day": int(tr.t[np.argmax(I)]), "peak_I": float(I.max()),
            "ever_infected_frac_proxy": float(1 - tr.totals(L.S)[-1] / pop),
            "deaths": float(tr.totals(L.D)[-1]),
            "wall_s": tr.meta["wall_seconds"], "nfev": tr.meta["nfev"],
            "pop_err": tr.meta["max_rel_population_error"],
            "last_bin_share_infectious": tr.meta["last_bin_share"]["infectious"]}


def timing():
    rows = []
    for K, label in ((1, "단일 지역"), (17, "합성 17지역 (시도 규모)"), (200, "합성 200지역 (국가 규모 미리보기)")):
        rng = np.random.default_rng(K)
        reg = RegionSet.single(5e7) if K == 1 else RegionSet.synthetic_random(K, rng, 5e7 if K == 17 else 7.8e9, 1e-3)
        t0 = time.perf_counter()
        sysm = ReactionSystem(EpiParams(**BASE), reg, h_spec=H)
        sysm = sysm.with_params(c0=A.c0_network(2.5, sysm) if K <= 17 else A.c0_reference(2.5, sysm.params))
        build = time.perf_counter() - t0
        X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
        tr = integrate_ode(sysm, X0, 365)
        rows.append({"case": label, "K": K, "channels": len(sysm.channels), "build_s": build,
                     **summary(tr, reg.population.sum())})
    return rows


def r0_basis_comparison():
    rng = np.random.default_rng(7)
    reg = RegionSet.synthetic_random(17, rng, 5e7, 1e-3)
    base = ReactionSystem(EpiParams(**BASE), reg, h_spec=H)
    out = {}
    for basis in ("reference", "network"):
        c0 = A.c0_reference(2.5, base.params) if basis == "reference" else A.c0_network(2.5, base)
        sysm = base.with_params(c0=c0)
        rep = A.r0_report(sysm)
        tr = integrate_ode(sysm, initial_state(sysm.layout, reg.population, {0: 10.0}), 365)
        iso = list(rep["R0_isolated_by_region"].values())
        out[basis] = {"c0": c0, "R0_reference": rep["R0_reference"], "R0_network_t0": rep["R0_network_t0"],
                      "R0_isolated_min": min(iso), "R0_isolated_max": max(iso),
                      "R0_isolated_seed_region": iso[0], **summary(tr, reg.population.sum())}
    return out


def seed_compartment_comparison():
    rng = np.random.default_rng(7)
    reg = RegionSet.synthetic_random(17, rng, 5e7, 1e-3)
    sysm = ReactionSystem(EpiParams(**BASE), reg, h_spec=H)
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    out = {}
    for comp in ("I1", "E1"):
        tr = integrate_ode(sysm, initial_state(sysm.layout, reg.population, {0: 10.0}, comp), 365)
        out[comp] = summary(tr, reg.population.sum())
    return out


def m_convergence():
    reg = RegionSet.single(1e6)
    table = {}
    for days in (365, 1095, 3650):
        res = {}
        for M in (1, 2, 3, 4, 6, 8, 10, 12, 16, 20):
            p = EpiParams(**{**BASE, "M": M})
            sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), reg)
            tr = integrate_ode(sysm, initial_state(sysm.layout, reg.population, {0: 10.0}), days)
            res[M] = (tr.I_total, tr.totals(tr.layout.D)[-1], tr.meta["last_bin_share"]["infectious"])
        Iref, Dref, _ = res[20]
        table[days] = {M: {"err_I": float(np.max(np.abs(v[0] - Iref)) / Iref.max()),
                           "err_D": float(abs(v[1] - Dref) / Dref), "last_bin_I_share": v[2]}
                       for M, v in res.items() if M != 20}
    return table


def main():
    t0 = time.perf_counter()
    rep = {"environment": environment_record(), "timing_365d": timing(),
           "r0_basis": r0_basis_comparison(), "seed_compartment": seed_compartment_comparison(),
           "M_convergence_vs_M20": m_convergence()}
    rep["total_wall_s"] = time.perf_counter() - t0
    rep["peak_rss_MB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    out = ROOT / "docs" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / "1B_ode_validation.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str))

    e = rep["environment"]
    md = ["# 1-B ODE 검증 보고서 (자동 생성: scripts/report_1B.py)", "",
          f"환경: Python {e['python']}, {e['platform']}, CPU {e['cpu_count']}코어, "
          f"패키지 {e['packages']}, 커밋 {e['git_commit']}", "",
          "모든 지역은 **합성 자료**이고, 감염병 값은 **코드 검증용 가정**이다. 해법은 DOP853 (rtol 1e-8, atol 1e-6) 이다.", "",
          "## 1. 계산 시간 (365일, 1회)", "",
          "| 경우 | K | 사건 수 | 구성 s | 적분 s | nfev | 인구 보존 오차 |", "|---|---|---|---|---|---|---|"]
    for r in rep["timing_365d"]:
        md.append(f"| {r['case']} | {r['K']} | {r['channels']} | {r['build_s']:.2f} | {r['wall_s']:.2f} | {r['nfev']} | {r['pop_err']:.1e} |")
    md += ["", f"보고서 전체 실행 {rep['total_wall_s']:.1f} s, 최대 메모리 {rep['peak_rss_MB']:.0f} MB.", "",
           "## 2. R0 기준 비교 (합성 17지역, 목표 R0 = 2.5, h: eta = 0.2)", "",
           "| c0 결정 기준 | c0 | R0_reference | R0_network_t0 | 고립 R0 (최소~최대) | 최고점 일 | 최고 I | 1-S/N (365일) | 사망 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for b, r in rep["r0_basis"].items():
        md.append(f"| {b} | {r['c0']:.4f} | {r['R0_reference']:.3f} | {r['R0_network_t0']:.3f} | "
                  f"{r['R0_isolated_min']:.2f}~{r['R0_isolated_max']:.2f} | {r['peak_day']} | {r['peak_I']:.3e} | "
                  f"{r['ever_infected_frac_proxy']:.3f} | {r['deaths']:.3e} |")
    md += ["", "## 3. 초기 감염 구획 비교 (합성 17지역, network 기준)", "",
           "| 구획 | 최고점 일 | 최고 I | 사망 |", "|---|---|---|---|"]
    for c, r in rep["seed_compartment"].items():
        md.append(f"| {c} | {r['peak_day']} | {r['peak_I']:.4e} | {r['deaths']:.4e} |")
    md += ["", "## 4. M 수렴 (단일 지역, 기준 M = 20)", "",
           "값: I_total 최대 상대 차이 / D 상대 차이 / 마지막 칸 I 점유율 최대값", "",
           "| M | " + " | ".join(f"{d}일" for d in rep["M_convergence_vs_M20"]) + " |",
           "|---|" + "---|" * len(rep["M_convergence_vs_M20"])]
    Ms = list(next(iter(rep["M_convergence_vs_M20"].values())).keys())
    for M in Ms:
        cells = [f"{v[M]['err_I']:.1e} / {v[M]['err_D']:.1e} / {v[M]['last_bin_I_share']:.2f}"
                 for v in rep["M_convergence_vs_M20"].values()]
        md.append(f"| {M} | " + " | ".join(cells) + " |")
    (out / "1B_ode_validation.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
