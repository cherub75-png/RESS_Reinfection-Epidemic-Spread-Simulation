"""ERA5 국가별 주간 기후 (기온, 수증기압, 절대습도) -> data_processed/climate/era5_weekly_countries.parquet (+ .json 출처).

인플루엔자 예측의 기후 특성용 (docs/reports/11_influenza_protocol.md 4절). 매일 00·12 UTC 표본, 셀 중심 포함·cos 위도 가중.
확정 ERA5 마지막 날 뒤는 ERA5T 예비판 (era5t_samples > 0).
사용법: python -I scripts/build_era5_weekly.py [--start 2009-01-05] [--end <마지막 월요일>]
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    from seir_sim.data import era5
    from seir_sim.data.boundaries import load_admin0
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2009-01-05")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    stop_t = dt.date.fromisoformat(era5.dataset_attrs().get("valid_time_stop_era5t"))
    end = a.end or str(stop_t - dt.timedelta(days=stop_t.weekday() + 7))       # 예비판이 다 있는 마지막 주
    g = load_admin0(ROOT / "data_raw" / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson")
    df = era5.weekly_region_series(g, g.ids, a.start, end, log=lambda m: print(m, flush=True))
    out = ROOT / "data_processed" / "climate" / "era5_weekly_countries.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    meta = {**df.attrs, "start": a.start, "end": end, "regions": "Natural Earth admin 0", "rows": len(df),
            "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(meta)


if __name__ == "__main__":
    main()
