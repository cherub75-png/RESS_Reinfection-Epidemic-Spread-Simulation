"""최신 자료로 지역 데이터셋을 다시 만들어 저장소에 등록한다 (활성화는 --activate 를 줄 때만).

순서: 원자료 받기 (World Bank API, WorldPop, 시도 경계) -> World Bank 변환 -> ERA5 최근 12개월 월 평균
      -> 변형본 (경계 최신판, 인구 최신 연도, 기후 최근 12개월) -> 등록.
"최신" 의 기준: 인구는 전망치가 아닌 가장 최근 연도, 경계는 가장 최근 시점 파일, 기후는 확정 ERA5 의 마지막 12개월.
사용법: python -I scripts/build_latest_datasets.py [--skip-fetch] [--activate]
"""

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run(*a):
    print("$", " ".join(a), flush=True)
    subprocess.run([sys.executable, "-I", *a], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--activate", action="store_true")
    a = ap.parse_args()
    if not a.skip_fetch:
        run("scripts/fetch_data.py", "wb_population_api", "worldpop_kor_r2025a_1km", "who_flunet")
        run("scripts/fetch_admdongkor.py")
    run("scripts/convert_wb_api.py")
    from seir_sim.data import era5, periods
    from seir_sim.data.versions import Registry
    stop = dt.date.fromisoformat(era5.dataset_attrs()["valid_time_stop"])
    end = dt.date(stop.year, stop.month, 1) if stop.day >= 28 else dt.date(stop.year - (stop.month == 1), (stop.month - 2) % 12 + 1, 1)
    start = dt.date(end.year - 1 + (end.month == 12), end.month % 12 + 1, 1)
    label = f"era5_{start:%Y-%m}_{end:%Y-%m}"
    if not (periods.CLIMATE / label / "provenance.json").exists():
        era5.monthly_means(f"{start:%Y-%m}", f"{end:%Y-%m}", periods.CLIMATE / label)
    reg = Registry()
    for name in ("KOR_admin1", "world_countries"):
        fam = "KOR" if name.startswith("KOR") else "world"
        o = periods.options(fam)
        path = periods.variant(name, population_year=o["latest"]["population"], climate_period=label,
                               boundary_date=o["latest"]["boundaries"] if fam == "KOR" else None, log=print)
        note = (f"최신 자료: 인구 {o['latest']['population']}, 기후 {label}"
                + (f", 경계 {o['latest']['boundaries']}" if fam == "KOR" else "") + ". 이동 가정값은 원본과 같음")
        v = reg.register(name, path, note)
        print(name, v, note)
        if a.activate:
            reg.activate(name, v)
            print(name, "활성화", v)


if __name__ == "__main__":
    main()
