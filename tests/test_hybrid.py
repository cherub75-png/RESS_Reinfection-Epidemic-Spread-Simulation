"""1-C 2b: 하이브리드 (CTMC + 이항 tau-leap) 검증."""

import numpy as np
import pytest

from conftest import make_params
from seir_sim.model import analysis as A
from seir_sim.model.drivers import Drivers, InterventionSchedule
from seir_sim.model.reactions import ReactionSystem
from seir_sim.model.regions import RegionSet
from seir_sim.model.state import initial_state
from seir_sim.simulate.ctmc import simulate_ctmc
from seir_sim.simulate.hybrid import simulate_hybrid

Z = 5.0


def _int_regions(reg):
    return RegionSet(reg.names, np.round(reg.population), reg.density, reg.contact, reg.mobility, True)


def test_conservation_nonnegativity_reproducibility():
    rng = np.random.default_rng(1)
    reg = _int_regions(RegionSet.synthetic_random(5, rng, total_population=2e5, mobility_scale=0.02))
    u = InterventionSchedule(5, [{"start": 20.0, "end": 50.0, "value": 0.4, "regions": [0, 2]}])
    sysm = ReactionSystem(make_params(M=4, f1=0.05, lam=1 / 30), reg, Drivers(5, None, None, u))
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, reg.population, {0: 5.0})
    a = simulate_hybrid(sysm, X0, 300, seed=7)
    b = simulate_hybrid(sysm, X0, 300, seed=7)
    np.testing.assert_array_equal(a.X, b.X)
    assert a.meta["max_abs_population_error"] == 0.0
    assert a.meta["min_value"] >= 0 and np.all(a.X == np.round(a.X))
    assert np.all(np.diff(a.totals(a.layout.D)) >= 0)
    assert a.meta["exact_events"] > 0 and a.meta["switches_to_leap"] > 0
    with pytest.raises(ValueError):
        simulate_hybrid(sysm, X0, 10, seed=0, threshold_up=10, threshold_down=20)


@pytest.mark.parametrize("R0,k,comp", [(2.5, 1, "I1"), (2.5, 1, "E1"), (2.5, 2, "I1"), (1.5, 1, "I1")])
def test_extinction_probability_matches_branching_process(R0, k, comp):
    """검증: 소규모 수 영역이 정확한 CTMC 로 처리되어 소멸 확률이 (1/R0)^k 와 같다.
    (같은 조건의 순수 tau-leap 은 0.335 로 z = -8.4 였다: docs/reports/1C_tau.md)
    판정: E+I = 0 이면 소멸, E+I >= 200 이면 대유행. N = 1e6, 4000회, z < 5."""
    p = make_params(M=2)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(R0, p)), RegionSet.single(1e6))
    L = sysm.layout
    X0 = initial_state(L, np.array([1e6]), {0: float(k)}, comp)
    R, ext = 4000, 0
    for s in np.random.SeedSequence(99).spawn(R):
        tr = simulate_hybrid(sysm, X0, 10_000, output_dt=10_000, seed=s, stop_EI_at_or_below=0,
                             stop_EI_at_or_above=200)
        assert tr.meta["stopped_at"] is not None
        fs = tr.meta["final_state"][0]
        ext += int(fs[L.E_slice].sum() + fs[L.I_slice].sum() == 0)
    q = (1 / R0) ** k
    assert abs(ext / R - q) / np.sqrt(q * (1 - q) / R) < Z, ext / R


def _final_sizes(sim, sysm, X0, ss, **kw):
    L = sysm.layout
    out = []
    for s in ss:
        tr = sim(sysm, X0, 10_000, output_dt=10_000, seed=s, stop_EI_at_or_below=0, **kw)
        out.append((X0[0, L.S] - tr.meta["final_state"][0, L.S]) / X0.sum())
    return np.array(out)


@pytest.fixture(scope="module")
def final_size_setup():
    N = 2e4
    p = make_params(M=2, lam=0.0, Pmin=0.0, alpha=1000.0)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.0, p)), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 3.0})
    zc = _final_sizes(simulate_ctmc, sysm, X0, np.random.SeedSequence(10).spawn(600))
    return sysm, X0, zc


@pytest.mark.parametrize("up,down", [(100.0, 50.0), (10.0, 5.0), (1000.0, 500.0)])
def test_final_size_distribution_matches_ctmc_across_thresholds(final_size_setup, up, down):
    """검증: 유행이 커졌다가(exact -> leap) 끝나면서 다시 작아지는(leap -> exact) 경우,
    최종 규모 분포가 CTMC 와 같다. 전환 기준 (100, 50) 외에 (10, 5), (1000, 500) 도 같은지 본다.
    지표: 소규모 발생 비율(두 표본 비율 z), 대유행 조건부 평균(z), 표준편차 비율 [0.8, 1.25].
    조건: 재감염 없음(lambda = 0, P(n>=2) = 0), N = 2e4, I0 = 3, 각 600회.

    eps = 0.003 을 쓴다. 기본 eps = 0.01 에서는 최종 규모가 CTMC 보다 약 +0.0023 (0.3%) 크다 (z ~ 5.6).
    이것은 순수 tau-leap 에서도 같게(z = 5.9) 나타나는 leap 단계의 O(eps) 오차이고, eps = 0.003 이면
    사라진다 (z = -0.06). 전환 자체의 효과만 분리해 보려고 eps 를 낮췄다 (docs/DECISIONS.md D-007)."""
    sysm, X0, zc = final_size_setup
    R = zc.size
    zh = _final_sizes(simulate_hybrid, sysm, X0, np.random.SeedSequence(11).spawn(R),
                      threshold_up=up, threshold_down=down, eps=0.003)
    minor_c, minor_h = np.mean(zc < 0.1), np.mean(zh < 0.1)
    pp = 0.5 * (minor_c + minor_h)
    assert abs(minor_c - minor_h) / np.sqrt(2 * pp * (1 - pp) / R) < Z
    mc, mh = zc[zc >= 0.1], zh[zh >= 0.1]
    z = (mh.mean() - mc.mean()) / np.sqrt(mh.var(ddof=1) / mh.size + mc.var(ddof=1) / mc.size)
    assert abs(z) < Z, z
    ratio = mh.std(ddof=1) / mc.std(ddof=1)
    assert 0.8 < ratio < 1.25, ratio


def test_trajectory_distribution_matches_ctmc_through_switching():
    """검증: 전체 모형(재감염, 사망, M = 8)에서 초기 10명으로 시작해 50~100 전환 구간을 지나는 동안과
    그 뒤의 I_total 분포가 CTMC 와 같다. 각 300회, N = 2e4, 기본 eps = 0.01.
      - 매일(0~200일) 평균 z < 5
      - 20일마다 두 표본 KS 검정 p > 1e-3 (10회 검정)
      - 20일마다 사분위 범위 비율 [0.75, 1.33]
    전환 구간에서 불연속이나 편향이 있으면 전환 시기(대략 20~40일)의 z 와 KS 가 나빠진다.
    표준편차 비율은 쓰지 않는다: 초기 확산이 늦어진 극단 경로 몇 개가 표준편차를 좌우해서, 시드만 다른
    CTMC 두 묶음끼리도 100일 표준편차가 356 과 134 로 달랐다."""
    from scipy.stats import ks_2samp
    N = 2e4
    p = make_params(M=8)
    sysm = ReactionSystem(p.with_(c0=A.c0_reference(2.5, p)), RegionSet.single(N))
    X0 = initial_state(sysm.layout, np.array([N]), {0: 10.0})
    R = 300
    Ic = np.stack([simulate_ctmc(sysm, X0, 200, seed=s).I_total for s in np.random.SeedSequence(2).spawn(R)])
    trs = [simulate_hybrid(sysm, X0, 200, seed=s) for s in np.random.SeedSequence(1).spawn(R)]
    Ih = np.stack([t.I_total for t in trs])
    sd = np.sqrt((Ih.var(0, ddof=1) + Ic.var(0, ddof=1)) / R)
    ok = sd > 0
    z = (Ih.mean(0) - Ic.mean(0))[ok] / sd[ok]
    assert np.abs(z).max() < Z, np.abs(z).max()
    for d in range(20, 201, 20):
        assert ks_2samp(Ic[:, d], Ih[:, d]).pvalue > 1e-3, d
        iqr = lambda v: np.subtract(*np.percentile(v, [75, 25]))  # noqa: E731
        assert 0.75 < iqr(Ih[:, d]) / iqr(Ic[:, d]) < 1.33, d
    # 히스테리시스: 한 경로에서 전환이 거의 반복되지 않는다
    assert max(t.meta["switches_to_leap"] + t.meta["switches_to_exact"] for t in trs) <= 5


def test_multiregion_spread_matches_ctmc():
    """검증: 3지역 지역망(통근 C, 이동 omega)에서 1지역에 1명을 심었을 때, 지역별 I 의 분포가 CTMC 와 같다.
    다른 지역으로의 유입(정확 모드 E·I 이동)과 지역 간 감염이 함께 검증된다.
    60, 120일의 지역별 평균 z < 5, 표준편차 비율 [0.75, 1.33] (지역별 소멸·유입 시점의 큰 분산 고려). 각 400회."""
    pop = np.array([2e4, 1.5e4, 1e4])
    C = np.array([[0.9, 0.07, 0.03], [0.05, 0.9, 0.05], [0.04, 0.06, 0.9]])
    om = np.array([[0, 2e-3, 1e-3], [2e-3 * 2 / 1.5, 0, 1e-3], [1e-3 * 2, 1e-3 * 1.5, 0]])
    om[0, 1], om[1, 0] = 2e-3, 2e-3 * 2e4 / 1.5e4
    om[0, 2], om[2, 0] = 1e-3, 1e-3 * 2e4 / 1e4
    om[1, 2], om[2, 1] = 1e-3, 1e-3 * 1.5e4 / 1e4
    reg = RegionSet(("a", "b", "c"), pop, np.ones(3), C, om, True)
    assert reg.mobility_imbalance() < 1e-12
    p = make_params(M=3)
    sysm = ReactionSystem(p, reg)
    sysm = sysm.with_params(c0=A.c0_network(2.5, sysm))
    X0 = initial_state(sysm.layout, pop, {0: 1.0})
    R = 400
    Xc = np.stack([simulate_ctmc(sysm, X0, 120, seed=s).I_by_region for s in np.random.SeedSequence(3).spawn(R)])
    Xh = np.stack([simulate_hybrid(sysm, X0, 120, seed=s).I_by_region for s in np.random.SeedSequence(4).spawn(R)])
    for d in (60, 120):
        mc, mh = Xc[:, d].mean(0), Xh[:, d].mean(0)
        sc, sh = Xc[:, d].std(0, ddof=1), Xh[:, d].std(0, ddof=1)
        z = (mh - mc) / np.sqrt((sc ** 2 + sh ** 2) / R)
        assert np.abs(z).max() < Z, (d, z)
        ratio = sh / sc
        assert np.all((ratio > 0.75) & (ratio < 1.33)), (d, ratio)
