import numpy as np
import pytest

from seir_sim.model.params import EpiParams

# COVID 유사 "초기 코드 검증용 가정" (실제 추정치가 아님)
BASE = dict(sigma=1 / 5.2, gamma=1 / 7, c0=2.5 / 7, P1=1.0, T1=1.0, Pmin=0.3,
            alpha=0.5, beta=0.3, lam=1 / 180, f1=0.01,
            phi_spec={"form": "power", "delta": 0.5}, M=4)


@pytest.fixture
def base_params():
    return EpiParams(**BASE)


def make_params(**kw):
    d = dict(BASE)
    d.update(kw)
    return EpiParams(**d)


def random_state(layout, rng, scale=1000.0):
    return rng.random((layout.K, layout.ncomp)) * scale
