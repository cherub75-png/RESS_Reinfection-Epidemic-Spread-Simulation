"""최신 자료 예측 (7단계): 가장 최근 기점의 4주 예측을 5단계와 같은 방법·같은 코드로 만든다.

- 기점: 자료의 마지막 날 이전 가장 가까운 일요일 (또는 사용자가 준 날짜). 기점 뒤 자료는 쓰지 않는다.
- SEIR: 5단계 순차 재추정의 마지막 결과에서 이어서 다시 추정한다 (outputs/stage5/seir_k{knot}_{ISO3}.pkl 필요).
- ML: 12개국 공통 분위수 GBM, 기점까지 관측이 끝난 (s, h) 만 학습.
- 하이브리드: 5단계 SEIR 예측의 잔차로 학습 (기점까지 관측이 끝난 것만).
- 결과에 자료 마지막 날짜와 경고를 함께 남긴다. 이 저장소가 받은 JHU CSSE 시계열은 2023-03-09 에서 끝나므로,
  지금 확보한 공개 자료로 만들 수 있는 가장 최근 예측은 2023-03 시점이며 실행 날짜의 현재 예측이 아니다.
"""

from __future__ import annotations

import datetime as dt
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from .baselines import baseline_forecast
from .metrics import QUANTILES
from .panel import load_panel
from .seir import RollingSpec, rolling_country
from .targets import history, rolling7, weekly

ROOT = Path(__file__).resolve().parents[2]
STAGE5 = ROOT / "outputs" / "stage5"


def last_sunday(date) -> pd.Timestamp:
    d = pd.Timestamp(date)
    return d - pd.Timedelta(days=(d.dayofweek + 1) % 7)


def latest_forecast(iso3: str, origin=None, knot: int = 14, countries=None, n_samples: int = 300,
                    stage5: Path = STAGE5, log=None) -> dict:
    from ..ml.features import daily_features, origin_rows, training_rows
    from ..ml.quantile import fit_hybrid, fit_ml, hybrid_features, hybrid_predict, ml_predict
    from ..surveillance.sources import COUNTRIES
    countries = list(countries or COUNTRIES)
    if iso3 not in countries:
        countries.append(iso3)
    panels = {c: load_panel(c) for c in countries}
    p = panels[iso3]
    last_data = p["cases"].dropna().index.max()
    t = last_sunday(last_data) if origin is None else pd.Timestamp(origin)
    if t > last_data:
        raise ValueError(f"기점 {t.date()} 이 자료 마지막 날 {last_data.date()} 보다 늦다")
    out = {"iso3": iso3, "origin": str(t.date()), "data_last_date": str(last_data.date()),
           "run_date": str(dt.date.today()), "quantile_levels": QUANTILES.tolist(),
           "target_weeks": [str((t + pd.Timedelta(days=7 * h)).date()) for h in (1, 2, 3, 4)],
           "warnings": [], "methods": {}}
    if (pd.Timestamp(dt.date.today()) - last_data).days > 30:
        out["warnings"].append(f"자료가 {last_data.date()} 에 끝난다. 이 예측은 {t.date()} 시점 예측이며 현재 예측이 아니다.")
    feats = {c: daily_features(pp) for c, pp in panels.items()}
    for var, base in (("cases", "lc0"), ("deaths", "ld0")):
        w = weekly(p[var])
        hist = history(w, t)
        res = {m: baseline_forecast(hist, m) for m in ("persistence", "trend")}
        train = pd.concat([training_rows(feats[c], rolling7(panels[c][var]), t, base=base) for c in countries])
        X0 = origin_rows(feats[iso3], t)
        res["ml"] = ml_predict(fit_ml(train), X0, base)
        out["methods"].setdefault("_history", {})[var] = {str(k.date()): float(v) for k, v in hist.iloc[-16:].items()}
        for m, q in res.items():
            out["methods"].setdefault(m, {})[var] = None if q is None else np.asarray(q).tolist()
    # SEIR (+ 하이브리드)
    path = stage5 / f"seir_k{knot}_{iso3}.pkl"
    if not path.exists():
        out["warnings"].append(f"SEIR 이전 추정 결과가 없다 ({path.name}): scripts/run_stage5_seir.py 를 먼저 실행해야 한다")
        return out
    with open(path, "rb") as f:
        prev = [r for r in pickle.load(f)["results"] if pd.Timestamp(r["origin"]) < t]
    if not prev:
        out["warnings"].append("기점 이전의 SEIR 추정 결과가 없다")
        return out
    if "theta" not in prev[-1]:
        out["warnings"].append("이전 SEIR 결과에 theta 가 없어 이어서 추정할 수 없다 (5단계를 현재 코드로 다시 실행)")
        return out
    r = rolling_country(iso3, p, [t], RollingSpec(knot_days=knot, n_samples=n_samples), resume=prev[-1], log=log)[0]
    out["seir_fit"] = {k: r[k] for k in ("success", "hessian_pd", "n_free", "wall_s", "Rt_last", "Rt_last_capped")}
    out["seir_fit"]["resumed_from"] = prev[-1]["origin"]
    for var, base in (("cases", "lc0"), ("deaths", "ld0")):
        q = np.asarray(r[f"{var}_q"])
        out["methods"].setdefault("seir", {})[var] = q.tolist()
        hr = []
        for c in countries:
            pc = stage5 / f"seir_k{knot}_{c}.pkl"
            if not pc.exists():
                continue
            with open(pc, "rb") as f:
                rows = pickle.load(f)["results"]
            wc = weekly(panels[c][var])
            for rr in rows:
                s = pd.Timestamp(rr["origin"])
                if s >= t:
                    continue
                y = wc.reindex([s + pd.Timedelta(days=7 * h) for h in (1, 2, 3, 4)]).to_numpy(float)
                Xs = origin_rows(feats[c], s)
                qq = np.asarray(rr[f"{var}_q"])
                Xh = hybrid_features(Xs, qq, base)
                Xh["resid"] = np.log1p(y) - np.log1p(qq[:, 4])
                ok = (s + pd.to_timedelta(7 * Xh["h"].to_numpy(), "D") <= t) & np.isfinite(y) & np.isfinite(Xh[base].to_numpy())
                hr.append(Xh[ok])
        hq, active = hybrid_predict(fit_hybrid(pd.concat(hr)) if hr else None, origin_rows(feats[iso3], t), q, base)
        out["methods"].setdefault("hybrid", {})[var] = np.asarray(hq).tolist()
        out.setdefault("hybrid_active", {})[var] = bool(active)
    return out
