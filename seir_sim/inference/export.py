"""추정 결과 -> 엔진 설정 (7단계 통합).

SingleRegionModel 의 추정값(u(t) 구간값, I0)을 엔진 설정(YAML 사전)으로 옮긴다. 방정식·매개변수는 같다.
  - c0: reference 기준 R0 = R0_max (u = 0 일 때), 단일 지역이므로 h = 1
  - u(t): knot_days 마다 구간별 상수 [14k, 14(k+1)) -> interventions
  - 초기: I_1 = I0, E_1 = I0 gamma / sigma (start 날짜)
관측 매개변수(보고율·지연·요일·치명률 배율)는 엔진 상태가 아니라 관측 층이므로 meta.observation 에 기록만 한다.
엔진 ODE 와 추정용 FastODE 의 일치는 tests/test_integration.py 에서 확인한다.
"""

from __future__ import annotations

import numpy as np

from .calibrate import SingleRegionModel


def calibrated_config(m: SingleRegionModel, theta: np.ndarray, name: str, population_source: str,
                      provenance: dict, integer_seeds: bool = False, method: str = "ode", n_runs: int = 1) -> dict:
    par = m.unpack(np.asarray(theta, float))
    b = m.base
    I0 = float(min(par["I0"], m.N / 10))
    E0 = I0 * b.gamma / b.sigma
    if integer_seeds:
        I0, E0 = max(1.0, round(I0)), max(1.0, round(E0))
    days = m.spec.n_fit_days
    kd = m.spec.knot_days
    periods = []
    for k, mk in enumerate(par["m"]):
        s, e = k * kd, min((k + 1) * kd, days) if k < m.n_knots - 1 else days
        if e > s:
            periods.append({"start": s, "end": e, "value": float(1.0 - mk)})
    obs = {"rho": m.spec.rho, "delay_c": float(par["delay_c"]), "r_c": float(par["r_c"]), "w_c": par["w_c"].tolist()}
    if m.spec.use_deaths:
        obs.update({"k_f": par["k_f"].tolist(), "kf_knot_days": m.spec.kf_knot_days, "delay_d": float(par["delay_d"]),
                    "r_d": float(par["r_d"])})
    return {
        "run_mode": "development",
        "meta": {"name": name, "note": "3단계 추정값으로 만든 재현 설정 (u(t) 는 추정값, 방정식 매개변수는 가정값)",
                 "calibration": provenance, "observation": obs,
                 "R0_max": m.spec.R0_max, "fit_period": [m.spec.start, m.spec.fit_end]},
        "disease": {"name": "covid19_calibrated_u", "sigma": b.sigma, "gamma": b.gamma,
                    "transmission": {"R0": m.spec.R0_max, "r0_reference": "reference"},
                    "P1": b.P1, "T1": b.T1, "Pmin": b.Pmin, "alpha": b.alpha, "beta": b.beta, "lam": b.lam,
                    "f1": b.f1, "phi": dict(b.phi_spec), "M": b.M},
        "regions": {"source": "single", "name": name, "population": m.N, "population_source": population_source},
        "interventions": periods,
        "initial": {"start_date": m.spec.start, "seeds": [{"region": name, "count": I0, "compartment": "I1"},
                                                           {"region": name, "count": E0, "compartment": "E1"}]},
        "simulation": {"days": days, "method": method, "n_runs": n_runs},
    }
