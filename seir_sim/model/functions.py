"""감염 횟수별 함수(1.2절)와 공간·환경 결합 함수(1.3절).

1.2절의 함수는 사용자가 정의한 식을 그대로 구현한다.
- P(n) = P_min + (P_1 - P_min) * exp(-alpha * (n - 1))   감수성
- T(n) = T_1 * n**(-beta)                                  전파력
- P(n, tau) = P(n) + [P_1 - P(n)] * (1 - exp(-lam * tau))  회복 후 tau 경과 시 감수성
- f(n) = f_1 * phi(n), phi(1) = 1                          치사율

phi, h, g 는 "형태(form) + 계수" 로 지정하며 레지스트리에 등록된다.
2단계에서 학습한 함수(표, 스플라인 등)는 새 form 을 등록하는 방식으로 추가한다.
방정식 구조는 바뀌지 않고 함수만 교체된다.

색인 규약 (docs/MODEL.md 참고)
P(n), T(n), f(n) 의 n 은 "n번째 감염" 을 뜻한다.
- 감염 이력이 없는 S 는 첫 감염의 감수성 P(1) = P_1 을 쓴다.
- n회 감염 후 회복한 R_n 은 다음(n+1번째) 감염의 감수성 P(n+1) 을 쓴다.
- I_n 은 n번째 감염 중이므로 T(n), f(n) 을 쓴다.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

ArrayLike = np.ndarray | float | int


# ---------------------------------------------------------------- 1.2절 함수

def susceptibility(n: ArrayLike, P1: float, Pmin: float, alpha: float) -> np.ndarray:
    """P(n): n번째 감염에 대한 감수성 (n >= 1)."""
    n = np.asarray(n, dtype=float)
    return Pmin + (P1 - Pmin) * np.exp(-alpha * (n - 1.0))


def transmissibility(n: ArrayLike, T1: float, beta: float) -> np.ndarray:
    """T(n): n번째 감염 중인 사람의 전파력 (n >= 1)."""
    n = np.asarray(n, dtype=float)
    return T1 * n ** (-beta)


def susceptibility_waning(n: ArrayLike, tau: ArrayLike, P1: float, Pmin: float,
                          alpha: float, lam: float) -> np.ndarray:
    """P(n, tau) = P(n) + [P_1 - P(n)](1 - exp(-lam tau)).

    n 은 "다음 감염의 번호" 이다. 직전 감염(n-1번째)에서 회복한 뒤 tau 만큼
    지난 사람의 n번째 감염 감수성을 뜻한다. R_l 구획에는 n = l + 1 을 넣는다.
    """
    Pn = susceptibility(n, P1, Pmin, alpha)
    tau = np.asarray(tau, dtype=float)
    return Pn + (P1 - Pn) * (1.0 - np.exp(-lam * tau))


# ---------------------------------------------------------------- 레지스트리

PhiFn = Callable[[np.ndarray], np.ndarray]
_PHI_FORMS: dict[str, Callable[..., PhiFn]] = {}
_H_FORMS: dict[str, Callable[..., Callable[[np.ndarray], np.ndarray]]] = {}
_G_FORMS: dict[str, Callable[..., Callable[..., np.ndarray]]] = {}


def register_phi(name: str):
    def deco(builder):
        _PHI_FORMS[name] = builder
        return builder
    return deco


def register_h(name: str):
    def deco(builder):
        _H_FORMS[name] = builder
        return builder
    return deco


def register_g(name: str):
    def deco(builder):
        _G_FORMS[name] = builder
        return builder
    return deco


def _build(registry: dict, kind: str, spec: dict):
    spec = dict(spec)
    form = spec.pop("form")
    if form not in registry:
        raise ValueError(f"알 수 없는 {kind} form: {form!r} (등록됨: {sorted(registry)})")
    return registry[form](**spec)


def build_phi(spec: dict) -> PhiFn:
    return _build(_PHI_FORMS, "phi", spec)


def build_h(spec: dict):
    return _build(_H_FORMS, "h", spec)


def build_g(spec: dict):
    return _build(_G_FORMS, "g", spec)


# ---------------------------------------------------------------- phi(n): 치사율 형태

@register_phi("power")
def _phi_power(delta: float) -> PhiFn:
    """phi(n) = n^(-delta)."""
    return lambda n: np.asarray(n, dtype=float) ** (-delta)


@register_phi("constant")
def _phi_constant() -> PhiFn:
    return lambda n: np.ones_like(np.asarray(n, dtype=float))


@register_phi("table")
def _phi_table(values: list[float]) -> PhiFn:
    """phi(n) = values[n-1]. n 이 표 길이를 넘으면 마지막 값을 쓴다. 학습 결과 저장용."""
    v = np.asarray(values, dtype=float)
    if v.ndim != 1 or v.size == 0:
        raise ValueError("phi table 은 비어 있지 않은 1차원 목록이어야 한다")

    def phi(n):
        idx = np.clip(np.asarray(n, dtype=int) - 1, 0, v.size - 1)
        return v[idx]
    return phi


# ---------------------------------------------------------------- h(rho): 밀도 -> 접촉

@register_h("power")
def _h_power(eta: float) -> Callable[[np.ndarray, float], np.ndarray]:
    """h(rho) = (rho / rho_ref)^eta,  h(rho_ref) = 1."""
    def h(rho, rho_ref):
        return (np.asarray(rho, dtype=float) / rho_ref) ** eta
    return h


@register_h("constant")
def _h_constant():
    return lambda rho, rho_ref: np.ones_like(np.asarray(rho, dtype=float))


# ---------------------------------------------------------------- g(env): 환경 -> 전파

@register_g("constant")
def _g_constant():
    def g(temperature, humidity):
        return np.ones_like(np.asarray(temperature, dtype=float))
    return g


@register_g("exp_linear")
def _g_exp_linear(a_T: float, a_H: float, T_ref: float, H_ref: float):
    """g = exp(a_T (T - T_ref) + a_H (H - H_ref)),  기준 환경에서 g = 1.

    후보 함수일 뿐이다. 계수는 2단계에서 실제 자료로 검증·추정한다.
    단위: T 는 섭씨(°C), H 는 상대습도(%) 또는 비습(g/kg) 중 설정에서 정한 것.
    """
    def g(temperature, humidity):
        T = np.asarray(temperature, dtype=float)
        H = np.asarray(humidity, dtype=float)
        return np.exp(a_T * (T - T_ref) + a_H * (H - H_ref))
    return g
