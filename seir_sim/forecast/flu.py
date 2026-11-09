"""인플루엔자 주간 양성률 예측 (docs/reports/11_influenza_protocol.md, 결과 전에 고정).

주 색인 i 는 FluData.weeks 의 위치 (ISO 주, 월요일 시작). 기점 i 의 예측은 주 i 까지의 자료만 쓴다.
척도: z = logit((x + 0.5) / (n + 1)). 특성에는 검사 n >= 10, 정답에는 n >= 20 인 주만 쓴다 (flunet.MIN_TESTS_*).
분위수는 metrics.QUANTILES (9개). 기준 모델 분위수 규칙은 COVID 5단계와 같다 (그 계열의 과거 같은 방법 오차).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import expit

from ..surveillance import flunet as F
from .metrics import QUANTILES

HORIZONS = (1, 2, 3, 4)
PHI = 0.75                                    # 감쇠 추세 (COVID 와 같은 값)
MIN_ERRORS = 8
COVID_GAP = (pd.Timestamp("2020-03-01"), pd.Timestamp("2022-06-30"))   # 계절 기준·기후값 계산에서 뺀다 (유행 거의 없음)
SEASON_YEARS = 8
SEASON_MIN_VALUES = 5
CLIM_YEARS = 10
FEATURES = ["z0", "z1", "z2", "z3", "dz1", "dz2", "lt", "dlt", "sinw", "cosw", "nh", "alat", "h", "clim_z", "ly_z"]
CLIMATE_FEATURES = ["ah0", "t0", "ah4", "ah_clim_t", "ah_anom"]


def isoweek(weeks: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(weeks.isocalendar().week, int)


def _near_week(w: np.ndarray, target: int) -> np.ndarray:
    """ISO 주가 target ±1 인가 (53주 해와 연도 경계 포함)."""
    d = np.abs(w - target)
    return (d <= 1) | (d >= 51)


class FluData:
    """선택된 계열의 [주 x 계열] 검사 수·양성 수와 파생 값. climate: 주 x iso3 의 기후 표 (선택)."""

    def __init__(self, df: pd.DataFrame, series: list[str], start: str = "2009-01-05", end: str | None = None,
                 lat: dict | None = None, climate: pd.DataFrame | None = None):
        end = end or str(df["week"].max().date())
        T, X = F.wide(df, series, start, end)
        self.weeks = T.index
        self.series = list(series)
        self.tests = T.to_numpy(float)
        self.pos = X.to_numpy(float)
        self.zf = F.logit_positivity(self.tests, self.pos, F.MIN_TESTS_FEATURE)
        self.zt = F.logit_positivity(self.tests, self.pos, F.MIN_TESTS_TARGET)
        self.pt = F.positivity(self.tests, self.pos, F.MIN_TESTS_TARGET)
        meta = F.series_meta(df).loc[self.series]
        self.meta = meta
        self.nh = (meta["hemisphere"] == "NH").to_numpy(float)
        self.alat = np.array([abs(lat.get(i, np.nan)) if lat else np.nan for i in meta["iso3"]])
        self.lat = np.array([lat.get(i, np.nan) if lat else np.nan for i in meta["iso3"]])
        self.iw = isoweek(self.weeks)
        self.gap = (self.weeks >= COVID_GAP[0]) & (self.weeks <= COVID_GAP[1])
        self.clim = None
        if climate is not None:
            ah = climate.pivot(index="week", columns="id", values="ah").reindex(self.weeks)
            tt = climate.pivot(index="week", columns="id", values="tavg").reindex(self.weeks)
            self.clim = {"ah": np.column_stack([ah[i].to_numpy(float) if i in ah else np.full(len(self.weeks), np.nan) for i in meta["iso3"]]),
                         "t": np.column_stack([tt[i].to_numpy(float) if i in tt else np.full(len(self.weeks), np.nan) for i in meta["iso3"]])}
        self._season_tables()

    def index(self, week) -> int:
        return int(self.weeks.get_loc(pd.Timestamp(week)))

    # ------------------------------------------------------------------ 계절 평균 (기점까지 자료만)
    def _season_tables(self):
        """M[w][i, k] = 계열 k 의 ISO 주 w±1 값(과거 SEASON_YEARS 년, 주 i 까지, 코로나19 시기 제외)의 평균 (logit, 정답 기준).
        기후값 A[w][i, k] 도 같은 방식 (CLIM_YEARS 년, 주 i 보다 이전)."""
        Wn = len(self.weeks)
        span = int(round(SEASON_YEARS * 52.18))
        self.M = {}
        ok = np.isfinite(self.zt) & ~self.gap[:, None]
        v = np.where(ok, self.zt, 0.0)
        for w in range(1, 54):
            m = _near_week(self.iw, w)[:, None] & ok
            C = np.cumsum(np.where(m, v, 0.0), axis=0)
            N = np.cumsum(m, axis=0)
            Cl = np.vstack([np.zeros((span, C.shape[1])), C[:-span]]) if span < Wn else np.zeros_like(C)
            Nl = np.vstack([np.zeros((span, N.shape[1])), N[:-span]]) if span < Wn else np.zeros_like(N)
            with np.errstate(invalid="ignore", divide="ignore"):
                self.M[w] = np.where(N - Nl > 0, (C - Cl) / (N - Nl), np.nan)
        self.A = None
        if self.clim is not None:
            span = int(round(CLIM_YEARS * 52.18))
            ah = self.clim["ah"]
            okc = np.isfinite(ah)
            self.A = {}
            for w in range(1, 54):
                m = _near_week(self.iw, w)[:, None] & okc
                C = np.cumsum(np.where(m, ah, 0.0), axis=0)
                N = np.cumsum(m, axis=0)
                # 주 i 보다 52주 이상 이전 값만 (그 해의 같은 철은 아직 진행 중일 수 있으므로 과거 연도만)
                C = np.vstack([np.zeros((52, C.shape[1])), C[:-52]])
                N = np.vstack([np.zeros((52, N.shape[1])), N[:-52]])
                Cl = np.vstack([np.zeros((span, C.shape[1])), C[:-span]])
                Nl = np.vstack([np.zeros((span, N.shape[1])), N[:-span]])
                with np.errstate(invalid="ignore", divide="ignore"):
                    self.A[w] = np.where(N - Nl > 0, (C - Cl) / (N - Nl), np.nan)

    def target_isoweek(self, i: int, h: int) -> int:
        return int(isoweek(pd.DatetimeIndex([self.weeks[i] + pd.Timedelta(weeks=h)]))[0])

    # ------------------------------------------------------------------ 기준 모델
    def _point(self, z: np.ndarray, i: int, h: int, method: str) -> float:
        if i < 0 or not np.isfinite(z[i]):
            return np.nan
        if method == "persistence":
            return z[i]
        if i < 1 or not np.isfinite(z[i - 1]):
            return np.nan
        g = z[i] - z[i - 1]
        return z[i] + g * sum(PHI ** k for k in range(1, h + 1))

    def _errors(self, k: int, method: str, h: int) -> np.ndarray:
        """e[j] = zt[j + h] - 점 예측(j) (j = 0..W-h-1, 계산할 수 없으면 NaN). 계열·방법·h 마다 한 번 계산."""
        cache = self.__dict__.setdefault("_err_cache", {})
        key = (k, method, h)
        if key not in cache:
            zf, zt = self.zf[:, k], self.zt[:, k]
            n = zf.size - h
            p = zf[:n].copy()
            if method == "trend":
                g = np.full(n, np.nan)
                g[1:] = zf[1:n] - zf[: n - 1]
                p = p + g * sum(PHI ** m for m in range(1, h + 1))
            cache[key] = zt[h: h + n] - p
        return cache[key]

    def baseline(self, k: int, i: int, method: str) -> np.ndarray | None:
        """계열 k, 기점 i 의 [H, Q] 양성률 분위수 (persistence, trend). 오차가 MIN_ERRORS 개 미만이면 None.
        오차 = 과거 기점 j (1 <= j <= i - h) 의 같은 방법 예측과, 기점 i 까지 관측된 대상 j + h 의 차 (logit)."""
        zf = self.zf[:, k]
        out = np.empty((len(HORIZONS), QUANTILES.size))
        for a, h in enumerate(HORIZONS):
            p = self._point(zf, i, h, method)
            if not np.isfinite(p):
                return None
            e = self._errors(k, method, h)[1: max(1, i - h + 1)]
            err = e[np.isfinite(e)]
            if err.size < MIN_ERRORS:
                return None
            if method == "persistence":
                err = np.concatenate([err, -err])
            out[a] = expit(p + np.quantile(err, QUANTILES))
        return out

    def seasonal(self, k: int, i: int) -> np.ndarray | None:
        """같은 ISO 주 ±1 의 과거 절기 양성률 (최근 SEASON_YEARS 년, 기점까지, 코로나19 시기 제외) 의 경험 분위수."""
        out = np.empty((len(HORIZONS), QUANTILES.size))
        lo = self.weeks[i] - pd.Timedelta(days=int(SEASON_YEARS * 365.25))
        base = (self.weeks <= self.weeks[i]) & (self.weeks > lo) & ~self.gap & np.isfinite(self.pt[:, k])
        for a, h in enumerate(HORIZONS):
            m = base & _near_week(self.iw, self.target_isoweek(i, h))
            v = self.pt[m, k]
            if v.size < SEASON_MIN_VALUES:
                return None
            out[a] = np.quantile(v, QUANTILES)
        return out

    # ------------------------------------------------------------------ ML 특성
    def features(self, i: int, h: int, climate: bool = True) -> pd.DataFrame:
        """기점 주 i (모든 계열) 의 예측 주 h 특성. 주 i 까지의 자료만 쓴다."""
        zf = self.zf
        g = lambda a, j: a[j] if j >= 0 else np.full(a.shape[1], np.nan)   # noqa: E731
        lt_hist = np.log1p(self.tests)
        f = {"z0": g(zf, i), "z1": g(zf, i - 1), "z2": g(zf, i - 2), "z3": g(zf, i - 3)}
        f["dz1"], f["dz2"] = f["z0"] - f["z1"], f["z0"] - f["z2"]
        f["lt"] = g(lt_hist, i)
        prev = lt_hist[max(0, i - 4): i] if i > 0 else np.full((1, len(self.series)), np.nan)
        with np.errstate(invalid="ignore"):
            f["dlt"] = f["lt"] - np.nanmean(prev, axis=0) if np.isfinite(prev).any() else np.full(len(self.series), np.nan)
        ang = 2 * np.pi * self.iw[i] / 52.18
        f["sinw"], f["cosw"] = np.full(len(self.series), np.sin(ang)), np.full(len(self.series), np.cos(ang))
        f["nh"], f["alat"], f["h"] = self.nh, self.alat, np.full(len(self.series), float(h))
        f["clim_z"] = self.M[self.target_isoweek(i, h)][i]
        f["ly_z"] = g(zf, i + h - 52)
        if climate and self.clim is not None:
            ah, tt = self.clim["ah"], self.clim["t"]
            f["ah0"], f["t0"] = g(ah, i), g(tt, i)
            with np.errstate(invalid="ignore"):
                f["ah4"] = np.nanmean(ah[max(0, i - 3): i + 1], axis=0) if np.isfinite(ah[max(0, i - 3): i + 1]).any() else np.full(len(self.series), np.nan)
            f["ah_clim_t"] = self.A[self.target_isoweek(i, h)][i]
            f["ah_anom"] = f["ah0"] - self.A[int(self.iw[i])][i]
        out = pd.DataFrame(f)
        out["series"] = self.series
        out["week"] = self.weeks[i]
        return out

    def training_rows(self, origin_i: int, first_week: str = "2010-01-04", climate: bool = True,
                      exclude: tuple[str, ...] = ()) -> pd.DataFrame:
        """대상 주 s + h <= 기점 주 이고 정답이 있는 행 (s >= first_week). 정답 = logit 양성률."""
        i0 = max(4, self.index(first_week) if pd.Timestamp(first_week) >= self.weeks[0] else 0)
        parts = []
        for h in HORIZONS:
            for s in range(i0, origin_i - h + 1):
                y = self.zt[s + h]
                if not np.isfinite(y).any():
                    continue
                f = self.features(s, h, climate)
                f["target"] = y
                parts.append(f[np.isfinite(y)])
        out = pd.concat(parts, ignore_index=True)
        if exclude:
            out = out[~out["series"].isin(exclude)]
        return out


def feature_list(climate: bool) -> list[str]:
    return FEATURES + (CLIMATE_FEATURES if climate else [])


# ------------------------------------------------------------------ 시간순 구간 보정 (규약 6절)
def conformal_adjust(fc: pd.DataFrame, to_z, from_z, window_weeks: int = 52, min_rows: int = 300,
                     origin_col: str = "origin", target_col: str = "target_week", qcols=None) -> pd.DataFrame:
    """fc: 한 방법의 예측 표 (origin, target, h, truth, 분위수 열). 기점 o 의 행을, 기점이 [o - window, o) 이고
    대상 주 <= o 인 과거 예측 (모든 계열) 의 z 척도 오차로 보정한다: q'_k = q_k + quantile_{tau_k}(z_truth - q_k).
    보정 표본이 min_rows 미만이면 그대로 둔다. 반환: 보정된 분위수 열과 cal_n (보정에 쓴 행 수, 0 = 보정 안 함)."""
    qcols = qcols or [f"q{k}" for k in range(QUANTILES.size)]
    out = fc.copy()
    out["cal_n"] = 0
    Z = to_z(fc[qcols].to_numpy(float))
    zt = to_z(fc["truth"].to_numpy(float))
    org = pd.to_datetime(fc[origin_col]).to_numpy()
    tgt = pd.to_datetime(fc[target_col]).to_numpy()
    hh = fc["h"].to_numpy()
    newq = Z.copy()
    win = np.timedelta64(window_weeks * 7, "D")
    for o in np.unique(org):
        rows = np.flatnonzero(org == o)
        for h in np.unique(hh[rows]):
            r = rows[hh[rows] == h]
            cal = (org < o) & (org >= o - win) & (tgt <= o) & (hh == h) & np.isfinite(zt)
            n = int(cal.sum())
            if n < min_rows:
                continue
            delta = np.array([np.quantile(zt[cal] - Z[cal, k], QUANTILES[k]) for k in range(QUANTILES.size)])
            newq[r] = Z[r] + delta
            out.loc[out.index[r], "cal_n"] = n
    newq = np.sort(newq, axis=1)
    out[qcols] = from_z(newq)
    return out


def feature_table(data: FluData, climate: bool = True, first_week: str = "2010-01-04") -> pd.DataFrame:
    """모든 (계열, 주 s, 예측 주 h) 의 특성과 정답 (정답이 아직 없으면 NaN). 특성은 기점과 무관하게 주 s 까지의 자료로만
    정해지므로 한 번만 만들고, 기점 o 의 학습 행 = target_week <= o 이고 정답이 있는 행, 예측 행 = week == o 인 행."""
    i0 = max(4, int(np.searchsorted(data.weeks, pd.Timestamp(first_week))))
    parts = []
    for h in HORIZONS:
        for s in range(i0, len(data.weeks)):
            f = data.features(s, h, climate)
            f["target"] = data.zt[s + h] if s + h < len(data.weeks) else np.nan
            f["truth"] = data.pt[s + h] if s + h < len(data.weeks) else np.nan
            f["target_week"] = data.weeks[s] + pd.Timedelta(weeks=h)
            parts.append(f)
    return pd.concat(parts, ignore_index=True)
