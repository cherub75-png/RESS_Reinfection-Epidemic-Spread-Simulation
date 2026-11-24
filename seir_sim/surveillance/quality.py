"""감시 자료 품질 점검: 결측, 음수(소급 정정), 주간 보고, 요일 효과, 급증(누적 보고), 출처 간 일치."""

from __future__ import annotations

import numpy as np
import pandas as pd

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def series_qc(s: pd.Series, start: str | None = None, end: str | None = None) -> dict:
    """일별 발생 수 시계열 하나의 품질 지표."""
    s = s.astype(float)
    if start or end:
        s = s.loc[start:end]
    valid = s.dropna()
    if valid.empty:
        return {"n_days": int(s.size), "n_valid": 0}
    span = s.loc[valid.index[0]:valid.index[-1]]
    pos = valid[valid > 0]
    zero_frac = float((valid == 0).mean())
    # 주간 보고 판정: 0 이 아닌 값의 70% 이상이 한 요일에 몰리고, 0 인 날이 절반 이상
    wd_nonzero = pos.groupby(pos.index.dayofweek).size().reindex(range(7), fill_value=0)
    top_wd_share = float(wd_nonzero.max() / max(wd_nonzero.sum(), 1))
    weekly = bool(zero_frac > 0.5 and top_wd_share > 0.7)
    # 요일 효과: 값 / 중심 7일 평균 의 요일별 평균 (7일 평균이 10 이상인 날만)
    ma = valid.rolling(7, center=True).mean()
    ok = ma >= 10
    ratio = (valid[ok] / ma[ok]).groupby(valid[ok].index.dayofweek).mean().reindex(range(7))
    # 급증: 직전 14일 양수 값 중앙값의 10배를 넘는 날 (누적 보고 의심)
    med = pos.rolling(14, min_periods=7).median().shift(1).reindex(valid.index)
    spikes = valid[(med > 0) & (valid > 10 * med)]
    return {
        "first_date": str(valid.index[0].date()), "last_date": str(valid.index[-1].date()),
        "n_days": int(span.size), "n_valid": int(valid.size),
        "missing_frac": float(span.isna().mean()),
        "n_negative": int((valid < 0).sum()), "negative_sum": float(valid[valid < 0].sum()),
        "zero_frac": zero_frac, "reporting_days_per_week": round(7 * (1 - zero_frac), 2),
        "weekly_reporting": weekly, "top_weekday_share_of_nonzero": top_wd_share,
        "weekday_ratio": {WEEKDAYS[i]: (None if np.isnan(v) else round(float(v), 3)) for i, v in ratio.items()},
        "n_spikes": int(spikes.size), "spike_dates": [str(d.date()) for d in spikes.index[:10]],
        "total": float(valid.sum()), "max": float(valid.max()),
    }


def compare_series(a: pd.Series, b: pd.Series, cumulative: bool = True) -> dict:
    """두 출처의 같은 변수를 공통 날짜에서 비교한다. cumulative=True 면 누적, 아니면 일별."""
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if j.empty:
        return {"n_common": 0}
    if cumulative:
        nz = j[(j.a > 0) | (j.b > 0)]
        rel = (nz.a - nz.b).abs() / nz[["a", "b"]].max(axis=1)
        last = j.iloc[-1]
        return {"n_common": int(j.shape[0]), "first": str(j.index[0].date()), "last": str(j.index[-1].date()),
                "median_rel_diff": float(rel.median()), "max_rel_diff": float(rel.max()),
                "last_a": float(last.a), "last_b": float(last.b),
                "last_rel_diff": float(abs(last.a - last.b) / max(last.a, last.b, 1))}
    d = j.a - j.b
    return {"n_common": int(j.shape[0]), "exact_match_frac": float((d == 0).mean()),
            "corr": float(j.a.corr(j.b)), "sum_a": float(j.a.sum()), "sum_b": float(j.b.sum())}
