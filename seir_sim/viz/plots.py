"""앙상블 결과 그림 (matplotlib, PNG). 색은 dataviz 기본 팔레트(파랑 단일 색조 순차 램프)를 쓴다."""

from __future__ import annotations

from pathlib import Path

import numpy as np

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e1"
BLUE = "#2a78d6"
BAND = "#b7d3f6"
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
# 범주 색 (고정 순서, dataviz 기본 팔레트 1~5번; validate_palette.js 로 밝은 배경 검사 통과,
# 3~5번은 대비 3:1 미만이라 그림에 직접 이름표를 붙이고 보고서에 표를 함께 둔다)
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _cmap():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("seq_blue", RAMP)


def _font():
    import logging
    import matplotlib
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    from matplotlib import font_manager
    for name in ("Noto Sans CJK KR", "NanumGothic", "Noto Sans KR", "UnDotum", "WenQuanYi Zen Hei"):
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return True
    return False


def plot_I_total(res, path: str | Path, title: str | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ko = _font()
    s = res.summary()
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150, facecolor=SURFACE)
    _style(ax)
    ax.fill_between(res.t, s["q05"], s["q95"], color=BAND, alpha=0.7, linewidth=0,
                    label="5–95%" if ko else "5-95%")
    ax.plot(res.t, s["mean"], color=BLUE, linewidth=2, label="평균" if ko else "mean")
    i = int(np.argmax(s["mean"]))
    ax.annotate(f"{s['mean'][i]:,.0f}", (res.t[i], s["mean"][i]), xytext=(6, 6), textcoords="offset points",
                color=INK, fontsize=9)
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("일" if ko else "day", color=INK_2)
    ax.set_ylabel("감염 중 (I_total)" if ko else "infectious I_total", color=INK_2)
    head = title or ("I_total(t) 평균과 5–95% 구간" if ko else "I_total(t): mean and 5-95% band")
    sub = f"{res.method}, R = {res.runs.shape[0]}, " + ("합성 지역" if res.derived.get("regions_synthetic")
                                                       else "실제 지역 자료 + 명시적 가정") if ko else \
        f"{res.method}, R = {res.runs.shape[0]}"
    ax.set_title(head + "\n" + sub, loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def plot_region_heatmap(res, path: str | Path, top: int = 25, names: dict | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    ko = _font()
    rs = res.region_summary()
    M = rs["mean"]                                       # [T, K]
    order = np.argsort(M.max(axis=0))[::-1][:top]
    data = M[:, order].T
    fig, ax = plt.subplots(figsize=(8, 0.28 * len(order) + 1.4), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    im = ax.imshow(np.maximum(data, 1.0), aspect="auto", cmap=_cmap(), norm=LogNorm(vmin=1, vmax=max(data.max(), 10)),
                   extent=[res.t[0], res.t[-1], len(order) - 0.5, -0.5], interpolation="nearest")
    labels = [(names or {}).get(res.region_ids[k], res.region_ids[k]) for k in order]
    ax.set_yticks(range(len(order)), labels, fontsize=8, color=INK_2)
    ax.tick_params(colors=INK_2, labelsize=8)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    ax.set_xlabel("일" if ko else "day", color=INK_2)
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.ax.tick_params(colors=INK_2, labelsize=8)
    cb.set_label("평균 감염 중 인원 (로그)" if ko else "mean infectious (log)", color=INK_2, fontsize=9)
    cb.outline.set_visible(False)
    ax.set_title(("지역별 평균 감염 중 인원, 최고값 상위 %d개" % len(order)) if ko else
                 "Mean infectious by region, top %d by peak" % len(order), loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def plot_arrival_map(res, lon: np.ndarray, lat: np.ndarray, population: np.ndarray, path: str | Path,
                     geoms=None):
    """지역 대표 좌표에 중앙 도착일(감염 중 >= 1명이 처음 나온 날)을 색으로, 인구를 크기로 그린다."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ko = _font()
    rs = res.region_summary()
    day = rs["arrival_day_median"]
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150, facecolor=SURFACE)
    _style(ax)
    ax.grid(False)
    if geoms is not None:
        for g in geoms:
            parts = getattr(g, "geoms", [g])
            for p in parts:
                x, y = p.exterior.xy
                ax.fill(x, y, color="#f0efec", edgecolor="#d6d5d0", linewidth=0.3)
    size = 6 + 80 * np.sqrt(population / population.max())
    reached = np.isfinite(day)
    ax.scatter(lon[~reached], lat[~reached], s=size[~reached], facecolors="none", edgecolors="#a9a8a2",
               linewidths=0.6, label="365일 안 미도달" if ko else "not reached")
    sc = ax.scatter(lon[reached], lat[reached], s=size[reached], c=day[reached], cmap=_cmap(),
                    edgecolors=SURFACE, linewidths=0.6)
    cb = fig.colorbar(sc, ax=ax, pad=0.01, shrink=0.85)
    cb.ax.tick_params(colors=INK_2, labelsize=8)
    cb.set_label("중앙 도착일" if ko else "median arrival day", color=INK_2, fontsize=9)
    cb.outline.set_visible(False)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 85)
    ax.set_xlabel("경도" if ko else "longitude", color=INK_2)
    ax.set_ylabel("위도" if ko else "latitude", color=INK_2)
    ax.set_title(("지역별 중앙 도착일 (원 크기 = 인구)" if ko else "Median arrival day by region (size = population)"),
                 loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
