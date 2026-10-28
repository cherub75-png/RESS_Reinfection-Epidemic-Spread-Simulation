"""D-007 (tau-leap / 하이브리드 eps) 와 D-004 (SDE 음수 처리) 조건별 검증. 기준은 정확한 CTMC.

D-007: 모형 3종 x 방법 2종 x eps {0.03, 0.01, 0.003, 0.001}. 선택 규칙 (실행 전에 정함):
  모든 지표에서 |z| < 3 이고 상대 편향 |bias| < 0.5% 인 가장 큰 eps 를 그 모형의 권장값으로 한다.
D-004: SDE 음수 처리 3종 x 시간 간격 {0.1, 0.05, 0.01} x 조건 4종 (인구 규모, 재감염, 낮은 유병률).
  지표: I_total 평균의 최대 |z|, 최종 누적 지표의 상대 편향, 소멸 비율, 인구 보존 오차.
지역은 합성, 감염병 값은 코드 검증용 가정이다 (실제 자료 아님).

사용법: python -I scripts/report_D007_D004.py [--workers 4] [--reps 400]
출력:   docs/reports/D007_D004.md, .json
"""

import argparse
import json
import multiprocessing as mp
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=1.0, P1=1.0, T1=1.0, Pmin=0.3, alpha=0.5,
            beta=0.3, lam=1 / 180, f1=0.01, phi_spec={"form": "power", "delta": 0.5}, M=8)
EPS = (0.03, 0.01, 0.003, 0.001)
DTS = (0.1, 0.05, 0.01)


def _setup():
    warnings.simplefilter("ignore")
    sys.path.insert(0, str(ROOT))


def model(name):
    """(system, X0, days, 지표 함수). 지표 함수: Trajectory -> dict(스칼라) 와 I_total 경로."""
    from seir_sim.model import analysis as A
    from seir_sim.model.params import EpiParams
    from seir_sim.model.reactions import ReactionSystem
    from seir_sim.model.regions import RegionSet
    from seir_sim.model.state import initial_state

    def P(R0, **kw):
        p = EpiParams(**{**BASE, **kw})
        return p.with_(c0=A.c0_reference(R0, p))

    if name == "M1_final_size":        # 재감염 없음, 사망 없음: 최종 규모 (대유행 조건부)
        N = 2e4
        sysm = ReactionSystem(P(2.0, M=2, lam=0.0, Pmin=0.0, alpha=1000.0, f1=0.0), RegionSet.single(N))
        X0 = initial_state(sysm.layout, np.array([N]), {0: 3.0})
        days = 400
    elif name == "M2_full_reinfection":  # 재감염·면역 소실·사망, 1년
        N = 2e4
        sysm = ReactionSystem(P(2.5), RegionSet.single(N))
        X0 = initial_state(sysm.layout, np.array([N]), {0: 10.0})
        days = 365
    elif name == "M3_three_regions":     # 3지역 균형 이동, 원점 1곳
        reg = RegionSet.synthetic_random(3, np.random.default_rng(5), 3e4, 2e-3)
        reg = RegionSet(reg.names, np.round(reg.population), reg.density, reg.contact, reg.mobility, True)
        sysm = ReactionSystem(P(2.5), reg)
        X0 = initial_state(sysm.layout, reg.population, {0: 10.0})
        days = 300
    elif name == "S_small_N":            # D-004 조건: 작은 인구
        N = 2e3
        sysm = ReactionSystem(P(2.5), RegionSet.single(N))
        X0 = initial_state(sysm.layout, np.array([N]), {0: 10.0})
        days = 365
    elif name == "S_large_N":            # D-004 조건: 큰 인구
        N = 2e5
        sysm = ReactionSystem(P(2.5), RegionSet.single(N))
        X0 = initial_state(sysm.layout, np.array([N]), {0: 10.0})
        days = 365
    elif name == "S_low_prevalence":     # D-004 조건: R0 1.3 (낮은 유병률, 긴 꼬리)
        N = 2e4
        sysm = ReactionSystem(P(1.3), RegionSet.single(N))
        X0 = initial_state(sysm.layout, np.array([N]), {0: 20.0})
        days = 365
    else:
        raise KeyError(name)
    return sysm, X0, days


def metrics(name, sysm, X0, tr):
    L = sysm.layout
    xe = tr.X[-1]
    N = X0.sum()
    out = {"attack": float((X0[:, L.S].sum() - xe[:, L.S].sum()) / N), "deaths": float(xe[:, L.D].sum() / N),
           "peak_I": float(np.nanmax(tr.I_total) / N), "conservation": float(abs(tr.X[-1].sum() - N) / N),
           "min_value": float(np.nanmin(tr.X))}
    if name == "M3_three_regions":
        I2 = tr.I_by_region[:, 2]
        hit = np.flatnonzero(I2 >= 10)
        out["arrival_r2"] = float(tr.t[hit[0]]) if hit.size else np.nan
        out["attack_r2"] = float((X0[2, L.S] - xe[2, L.S]) / X0[2].sum())
    return out, tr.I_total


def run_cell(args):
    _setup()
    name, method, param, reps, seed = args
    from seir_sim.simulate.ctmc import simulate_ctmc
    from seir_sim.simulate.hybrid import simulate_hybrid
    from seir_sim.simulate.sde import simulate_sde
    from seir_sim.simulate.tauleap import simulate_tau
    sysm, X0, days = model(name)
    seeds = np.random.SeedSequence(seed).spawn(reps)
    rows, paths = [], []
    t0 = time.perf_counter()
    for s in seeds:
        if method == "ctmc":
            tr = simulate_ctmc(sysm, X0, days, seed=s)
        elif method == "tau":
            tr = simulate_tau(sysm, X0, days, seed=s, eps=param)
        elif method == "hybrid":
            tr = simulate_hybrid(sysm, X0, days, seed=s, eps=param)
        else:
            tr = simulate_sde(sysm, X0, days, seed=s, dt=param[1], truncation=param[0])
        m, I = metrics(name, sysm, X0, tr)
        rows.append(m)
        paths.append(I)
    return {"name": name, "method": method, "param": param, "wall_s": time.perf_counter() - t0,
            "rows": rows, "I": np.array(paths)}


def compare(ref, cell, major_key="attack", major_min=0.1):
    """평균 차이의 z 와 상대 편향. 대유행 조건부 (attack >= 0.1) 와 소멸 비율도 비교한다."""
    def arr(c, k):
        return np.array([r[k] for r in c["rows"]], float)
    out = {}
    mr, mc = arr(ref, major_key) >= major_min, arr(cell, major_key) >= major_min
    out["major_fraction"] = {"ref": float(mr.mean()), "test": float(mc.mean()),
                             "z": float((mc.mean() - mr.mean()) / np.sqrt(mr.var() / mr.size + mc.var() / mc.size + 1e-12))}
    keys = [k for k in ref["rows"][0] if k not in ("conservation", "min_value")]
    for k in keys:
        a, b = arr(ref, k)[mr], arr(cell, k)[mc]
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if a.size < 10 or b.size < 10:
            continue
        se = np.sqrt(a.var(ddof=1) / a.size + b.var(ddof=1) / b.size)
        out[k] = {"ref": float(a.mean()), "test": float(b.mean()), "rel_bias": float(b.mean() / a.mean() - 1) if a.mean() else np.nan,
                  "z": float((b.mean() - a.mean()) / se) if se > 0 else 0.0}
    Ir, Ic = ref["I"][mr], cell["I"][mc]
    n = min(Ir.shape[1], Ic.shape[1])
    sd = np.sqrt(np.nanvar(Ir[:, :n], 0, ddof=1) / Ir.shape[0] + np.nanvar(Ic[:, :n], 0, ddof=1) / Ic.shape[0])
    ok = sd > 0
    out["I_total_max_abs_z"] = float(np.nanmax(np.abs((np.nanmean(Ic[:, :n], 0) - np.nanmean(Ir[:, :n], 0))[ok] / sd[ok])))
    out["conservation_max"] = float(max(r["conservation"] for r in cell["rows"]))
    out["min_value"] = float(min(r["min_value"] for r in cell["rows"]))
    return out


def worst(c):
    zs = [abs(v["z"]) for k, v in c.items() if isinstance(v, dict) and "z" in v and k != "major_fraction"]
    rb = [abs(v["rel_bias"]) for k, v in c.items() if isinstance(v, dict) and "rel_bias" in v and np.isfinite(v["rel_bias"])
          and k in ("attack", "deaths", "attack_r2")]
    return max(zs + [c["I_total_max_abs_z"], abs(c["major_fraction"]["z"])]), max(rb) if rb else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--reps", type=int, default=400)
    a = ap.parse_args()
    _setup()
    from seir_sim.provenance import environment_record
    t0 = time.perf_counter()
    m7 = ["M1_final_size", "M2_full_reinfection", "M3_three_regions"]
    m4 = ["S_small_N", "M2_full_reinfection", "S_large_N", "S_low_prevalence"]
    jobs = [(m, "ctmc", None, a.reps, 100) for m in sorted(set(m7 + m4))]
    jobs += [(m, meth, e, a.reps, 200) for m in m7 for meth in ("tau", "hybrid") for e in EPS]
    jobs += [(m, "sde", (tr, dt), a.reps, 300) for m in m4 for tr in ("flow_limit", "state_clip", "increment_clip") for dt in DTS]
    ctx = mp.get_context("forkserver")
    with ProcessPoolExecutor(a.workers, mp_context=ctx) as ex:
        res = list(ex.map(run_cell, jobs))
    ref = {r["name"]: r for r in res if r["method"] == "ctmc"}
    d7, d4 = {}, {}
    for r in res:
        if r["method"] in ("tau", "hybrid"):
            c = compare(ref[r["name"]], r)
            z, rb = worst(c)
            d7.setdefault(r["name"], {}).setdefault(r["method"], {})[str(r["param"])] = {**c, "worst_z": z, "worst_rel_bias": rb,
                                                                                         "wall_s": r["wall_s"]}
        elif r["method"] == "sde":
            c = compare(ref[r["name"]], r)
            z, rb = worst(c)
            d4.setdefault(r["name"], {}).setdefault(r["param"][0], {})[str(r["param"][1])] = {**c, "worst_z": z, "worst_rel_bias": rb,
                                                                                              "wall_s": r["wall_s"]}
    rec = {}
    for m, by in d7.items():
        for meth, cells in by.items():
            ok = [float(e) for e, c in cells.items() if c["worst_z"] < 3 and c["worst_rel_bias"] < 0.005]
            rec[f"{m}|{meth}"] = max(ok) if ok else None
    rep = {"environment": environment_record(), "reps": a.reps, "wall_seconds": time.perf_counter() - t0,
           "ctmc_wall_s": {k: v["wall_s"] for k, v in ref.items()}, "D007": d7, "D007_recommended_eps": rec, "D004": d4}
    out = ROOT / "docs" / "reports"
    (out / "D007_D004.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str))
    L = ["# D-007 / D-004 조건별 검증 (자동 생성: scripts/report_D007_D004.py)", "",
         f"기준: 정확한 CTMC, 반복 {a.reps}회 (각 방법·조건). 합성 지역, 코드 검증용 가정 매개변수 (실제 자료 아님). "
         f"전체 {rep['wall_seconds'] / 60:.1f} 분.", "",
         "z = (방법 평균 - CTMC 평균) / 두 평균의 표준오차. 대유행(공격률 >= 0.1) 조건부. 상대 편향은 공격률·누적 사망·지역 2 공격률.", "",
         "## D-007: tau-leap / 하이브리드 eps", "",
         "선택 규칙 (실행 전에 정함): 모든 지표 |z| < 3 이고 |상대 편향| < 0.5% 인 가장 큰 eps.", "",
         "| 모형 | 방법 | eps | 최악 |z| | 최악 상대 편향 | 공격률 z | I_total 최대 |z| | 대유행 비율 z | 시간 s |", "|---|---|---|---|---|---|---|---|---|"]
    for m, by in d7.items():
        for meth, cells in by.items():
            for e, c in cells.items():
                L.append(f"| {m} | {meth} | {e} | {c['worst_z']:.1f} | {c['worst_rel_bias'] * 100:.2f}% | {c['attack']['z']:+.1f} | "
                         f"{c['I_total_max_abs_z']:.1f} | {c['major_fraction']['z']:+.1f} | {c['wall_s']:.1f} |")
    L += ["", "권장 eps (규칙 적용 결과):", ""]
    for k, v in rec.items():
        L.append(f"- {k}: {v if v is not None else '격자 안에 통과값 없음'}")
    L += ["", "## D-004: SDE 음수 처리 (조건별)", "",
          "| 조건 | 처리 | dt | 최악 |z| | 최악 상대 편향 | 공격률 z | I_total 최대 |z| | 대유행 비율 (CTMC → SDE) | 보존 오차 | 최소값 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, by in d4.items():
        for trn, cells in by.items():
            for dt, c in cells.items():
                mf = c["major_fraction"]
                L.append(f"| {m} | {trn} | {dt} | {c['worst_z']:.1f} | {c['worst_rel_bias'] * 100:.2f}% | {c['attack']['z']:+.1f} | "
                         f"{c['I_total_max_abs_z']:.1f} | {mf['ref']:.3f} → {mf['test']:.3f} | {c['conservation_max']:.1e} | {c['min_value']:.2g} |")
    (out / "D007_D004.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
