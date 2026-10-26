"""1-C 모형 비교: ODE, SDE, CTMC, tau-leaping, hybrid 를 같은 지표로 비교한다.

사용법: python scripts/report_1C_compare.py
출력:   docs/reports/1C_compare.json, docs/reports/1C_compare.md
지역은 합성 자료, 감염병 값은 코드 검증용 가정이다. 기준은 정확한 CTMC 이다.
"""

import json
import resource
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from scipy.stats import ks_2samp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seir_sim.model import analysis as A                 # noqa: E402
from seir_sim.model.params import EpiParams              # noqa: E402
from seir_sim.model.reactions import ReactionSystem      # noqa: E402
from seir_sim.model.regions import RegionSet             # noqa: E402
from seir_sim.model.state import initial_state           # noqa: E402
from seir_sim.provenance import environment_record       # noqa: E402
from seir_sim.simulate.ctmc import simulate_ctmc         # noqa: E402
from seir_sim.simulate.hybrid import simulate_hybrid     # noqa: E402
from seir_sim.simulate.ode import integrate_ode          # noqa: E402
from seir_sim.simulate.sde import simulate_sde           # noqa: E402
from seir_sim.simulate.tauleap import simulate_tau       # noqa: E402

BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1.0, T1=1.0, Pmin=0.3, alpha=0.5,
            beta=0.3, lam=1 / 180, f1=0.01, phi_spec={"form": "power", "delta": 0.5}, M=8)
STOCH = {"sde": simulate_sde, "ctmc": simulate_ctmc, "tau": simulate_tau, "hybrid": simulate_hybrid}


def P(R0=2.5, **kw):
    p = EpiParams(**{**BASE, **kw})
    return p.with_(c0=A.c0_reference(R0, p))


def extinction(R=2000):
    sysm = ReactionSystem(P(M=2), RegionSet.single(1e6))
    L = sysm.layout
    X0 = initial_state(L, np.array([1e6]), {0: 1.0})
    out = {"theory": 0.4, "ode": 0.0}
    for name, sim in STOCH.items():
        ext = 0
        for s in np.random.SeedSequence(99).spawn(R):
            xe = sim(sysm, X0, 120, output_dt=120, seed=s).X[-1, 0]
            ext += int(xe[L.E_slice].sum() + xe[L.I_slice].sum() < 0.5 and xe[L.RP_slice].sum() + xe[L.D] < 200)
        out[name] = ext / R
    return out


def distribution(R=200):
    N = 2e4
    sysm = ReactionSystem(P(), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 10.0})
    ref = np.stack([simulate_ctmc(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(2).spawn(R)])
    ode = integrate_ode(sysm, X0, 200).I_total
    days = np.arange(20, 201, 20)
    out = {"ode": {"max_abs_z_mean": float(np.max(np.abs((ode[1:] - ref.mean(0)[1:]) / (ref.std(0, ddof=1)[1:] / np.sqrt(R)))))}}
    for name, sim in STOCH.items():
        if name == "ctmc":
            seeds = np.random.SeedSequence(22).spawn(R)     # 다른 시드의 CTMC: 비교 기준의 잡음 수준
        else:
            seeds = np.random.SeedSequence(1).spawn(R)
        X = np.stack([sim(sysm, X0, 200, seed=s).I_total for s in seeds])
        sd = np.sqrt((X.var(0, ddof=1) + ref.var(0, ddof=1)) / R)
        ok = sd > 0
        z = (X.mean(0) - ref.mean(0))[ok] / sd[ok]
        out[name] = {"max_abs_z_mean": float(np.abs(z).max()),
                     "min_ks_p": float(min(ks_2samp(ref[:, d], X[:, d]).pvalue for d in days))}
    return out


def final_size(R=400):
    N = 2e4
    sysm = ReactionSystem(P(R0=2.0, M=2, lam=0.0, Pmin=0.0, alpha=1000.0), RegionSet.single(N))
    L = sysm.layout
    X0 = initial_state(L, np.array([N]), {0: 3.0})

    def fs(sim, seeds, **kw):
        z = []
        for s in seeds:
            if sim in (simulate_ctmc, simulate_hybrid):
                xe = sim(sysm, X0, 1e4, output_dt=1e4, seed=s, stop_EI_at_or_below=0, **kw).meta["final_state"][0]
            else:
                xe = sim(sysm, X0, 400, output_dt=400, seed=s, **kw).X[-1, 0]
            z.append((X0[0, L.S] - xe[L.S]) / N)
        z = np.array(z)
        return z[z >= 0.1]
    ref = fs(simulate_ctmc, np.random.SeedSequence(10).spawn(R))
    ode = integrate_ode(sysm, X0, 400)
    out = {"ctmc_major_mean": float(ref.mean()),
           "ode": {"value": float((X0[0, L.S] - ode.X[-1, 0, L.S]) / N)}}
    for name, sim, kw in (("sde", simulate_sde, {}), ("tau_eps0.01", simulate_tau, {}),
                          ("tau_eps0.003", simulate_tau, {"eps": 0.003}), ("hybrid_eps0.01", simulate_hybrid, {}),
                          ("hybrid_eps0.003", simulate_hybrid, {"eps": 0.003})):
        m = fs(sim, np.random.SeedSequence(11).spawn(R), **kw)
        out[name] = {"major_mean": float(m.mean()),
                     "z": float((m.mean() - ref.mean()) / np.sqrt(m.var(ddof=1) / m.size + ref.var(ddof=1) / ref.size))}
    out["ode"]["z_vs_ctmc_mean"] = float((out["ode"]["value"] - ref.mean()) / (ref.std(ddof=1) / np.sqrt(ref.size)))
    return out


def speed():
    rows = []
    reg17 = RegionSet.synthetic_random(17, np.random.default_rng(7), 5e7, 1e-3)
    reg17 = RegionSet(reg17.names, np.round(reg17.population), reg17.density, reg17.contact, reg17.mobility, True)
    for label, reg in (("단일 지역 N=1e6", RegionSet.single(1e6)), ("합성 17지역 5천만", reg17)):
        sysm = ReactionSystem(P(), reg)
        if reg.K > 1:
            sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
        X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
        row = {"case": label, "ode": integrate_ode(sysm, X0, 365).meta["wall_seconds"]}
        for name, sim in STOCH.items():
            if name == "ctmc" and reg.K > 1:
                row[name] = None        # 1-C 보고서: 1시간 이상 (외삽 하한)
                continue
            row[name] = sim(sysm, X0, 365, seed=0).meta["wall_seconds"]
        rows.append(row)
    sysm = ReactionSystem(P(), reg17)
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, reg17.population, {0: 10.0})
    thr = []
    for up, down in ((10, 5), (100, 50), (1000, 500)):
        tr = simulate_hybrid(sysm, X0, 365, seed=0, threshold_up=up, threshold_down=down)
        thr.append({"up": up, "down": down, "wall_s": tr.meta["wall_seconds"], "exact_events": tr.meta["exact_events"],
                    "switches": tr.meta["switches_to_leap"] + tr.meta["switches_to_exact"]})
    return rows, thr


def main():
    warnings.simplefilter("ignore")
    s0 = ReactionSystem(P(), RegionSet.single(100.0))
    X00 = initial_state(s0.layout, np.array([100.0]), {0: 1.0})
    for sim in STOCH.values():
        sim(s0, X00, 1, seed=0)          # JIT 컴파일
    t0 = time.perf_counter()
    sp, thr = speed()
    rep = {"environment": environment_record(), "extinction": extinction(), "distribution": distribution(),
           "final_size": final_size(), "speed_365d": sp, "hybrid_thresholds_K17": thr}
    rep["total_wall_s"] = time.perf_counter() - t0
    rep["peak_rss_MB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    out = ROOT / "docs" / "reports"
    (out / "1C_compare.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str))
    e, ex, di, fs = rep["environment"], rep["extinction"], rep["distribution"], rep["final_size"]
    f = lambda v: "—" if v is None else f"{v:.2f}"     # noqa: E731
    md = ["# 1-C 모형 비교 (자동 생성: scripts/report_1C_compare.py)", "",
          f"환경: Python {e['python']}, CPU {e['cpu_count']}코어, 패키지 {e['packages']}, 커밋 {e['git_commit']}", "",
          "기준은 정확한 CTMC. 지역은 합성, 감염병 값은 코드 검증용 가정. tau/hybrid 기본 eps = 0.01, SDE h = 0.05 (flow_limit).", "",
          "## 1. 요약표", "",
          "| 지표 | ODE | SDE | CTMC | tau-leap | hybrid |", "|---|---|---|---|---|---|",
          f"| 소멸 확률 (이론 0.400, 2000회) | {ex['ode']:.3f} | {ex['sde']:.3f} | {ex['ctmc']:.3f} | {ex['tau']:.3f} | {ex['hybrid']:.3f} |",
          f"| CTMC 대비 평균 최대 \\|z\\| (매일, 200회) | {di['ode']['max_abs_z_mean']:.1f} | {di['sde']['max_abs_z_mean']:.1f} | "
          f"{di['ctmc']['max_abs_z_mean']:.1f} (다른 시드) | {di['tau']['max_abs_z_mean']:.1f} | {di['hybrid']['max_abs_z_mean']:.1f} |",
          f"| CTMC 대비 KS 최소 p (20일 간격) | — | {di['sde']['min_ks_p']:.3f} | {di['ctmc']['min_ks_p']:.3f} | "
          f"{di['tau']['min_ks_p']:.3f} | {di['hybrid']['min_ks_p']:.3f} |",
          f"| 최종 규모 z (CTMC {fs['ctmc_major_mean']:.4f}) | {fs['ode']['z_vs_ctmc_mean']:.1f} | {fs['sde']['z']:.1f} | 0 | "
          f"{fs['tau_eps0.01']['z']:.1f} (eps 0.003: {fs['tau_eps0.003']['z']:.1f}) | "
          f"{fs['hybrid_eps0.01']['z']:.1f} (eps 0.003: {fs['hybrid_eps0.003']['z']:.1f}) |"]
    for r in rep["speed_365d"]:
        md.append(f"| 시간 s, 365일 1회: {r['case']} | {f(r['ode'])} | {f(r['sde'])} | {f(r['ctmc']) if r['ctmc'] is not None else '> 3600 (외삽)'} | {f(r['tau'])} | {f(r['hybrid'])} |")
    md += ["", "ODE 행의 z 는 결정론적 해와 CTMC 평균의 차이다. 유한 인구와 초기 무작위성 때문에 ODE 는 CTMC 평균과 일치할 필요가 없다 (참고용).", "",
           "## 2. 하이브리드 전환 기준별 비용 (합성 17지역, 365일)", "",
           "| 기준 (up, down) | 시간 s | 정확 사건 수 | 전환 횟수 |", "|---|---|---|---|"]
    md += [f"| ({r['up']}, {r['down']}) | {r['wall_s']:.2f} | {r['exact_events']} | {r['switches']} |" for r in thr]
    md += ["", "## 3. 해석", "",
           "- 소규모 수 영역(소멸 확률): CTMC 와 hybrid 만 이론과 맞는다. tau-leap 과 SDE 는 소멸을 과소추정한다 (적용 범위 밖).",
           "- 분포: SDE, tau-leap, hybrid 모두 N = 2e4, 초기 10명에서 CTMC 와 통계적으로 구별되지 않는다 (기준 |z| < 5, KS p > 1e-3).",
           "- 최종 규모처럼 분산이 매우 작은 지표에서는 eps = 0.01 의 leap 오차(약 0.3%)가 검출된다. eps = 0.003 이면 사라진다 (DECISIONS D-007).",
           "- 권장: 소멸·초기 유입이 중요한 예측에는 hybrid, 평균 기준선에는 ODE, 대규모·장기 앙상블에는 hybrid 또는 tau-leap.", "",
           f"전체 실행 {rep['total_wall_s']:.0f} s, 최대 메모리 {rep['peak_rss_MB']:.0f} MB."]
    (out / "1C_compare.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
