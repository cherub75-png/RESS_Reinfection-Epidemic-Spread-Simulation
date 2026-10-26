"""지역 데이터셋 만들기 (명령줄).

  python -I scripts/build_regions.py world --year 2019 --air-trips-per-day 5e6 \\
      --commute-fraction 0.002 --contact-share 0.3 --out data_processed/world_countries_2019.nc
  python -I scripts/build_regions.py admin1 --country KOR --air-trips-per-day 9e4 \\
      --commute-fraction 0.05 --contact-share 0.3 --out data_processed/KOR_admin1.nc \\
      [--population-raster data_raw/worldpop_kor_2020_1km/kor_ppp_2020_1km_Aggregated_UNadj.tif]

가정 매개변수(--air-trips-per-day, --commute-fraction, --contact-share)는 기본값이 없다. 반드시 명시한다.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seir_sim.data.build import build_admin1, build_world_countries  # noqa: E402

RAW = ROOT / "data_raw"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="scope", required=True)
    for name in ("world", "admin1"):
        s = sub.add_parser(name)
        s.add_argument("--air-trips-per-day", type=float, required=True, help="지역 간 하루 항공 이동 횟수 (가정)")
        s.add_argument("--commute-fraction", type=float, required=True, help="다른 지역 통근 비율 (가정)")
        s.add_argument("--contact-share", type=float, required=True, help="통근자 접촉 중 목적지 비율 (가정)")
        s.add_argument("--out", required=True)
    sub.choices["world"].add_argument("--year", type=int, required=True)
    sub.choices["admin1"].add_argument("--country", required=True, help="ISO3, 예: KOR")
    sub.choices["admin1"].add_argument("--population-raster", default=None)
    a = ap.parse_args()
    air = (RAW / "openflights" / "airports.dat", RAW / "openflights" / "routes.dat")
    if a.scope == "world":
        ds = build_world_countries(RAW / "ne_admin0_10m" / "ne_10m_admin_0_countries.geojson",
                                   RAW / "wb_population" / "population.csv", a.year, *air,
                                   a.air_trips_per_day, a.commute_fraction, a.contact_share)
    else:
        ds = build_admin1(RAW / "ne_admin1_10m" / "ne_10m_admin_1_states_provinces.geojson", a.country, *air,
                          a.air_trips_per_day, a.commute_fraction, a.contact_share, a.population_raster)
    ds.save(a.out)
    q = ds.quality()
    print(json.dumps({"out": a.out, "K": ds.K, "quality": {k: v for k, v in q.items() if k != "missing_population"},
                      "missing_population": len(q["missing_population"]),
                      "excluded_regions": len(ds.provenance.get("excluded_regions", []))}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
