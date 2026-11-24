"""대한민국 시도 인구표·월 기후표 만들기 (Google COVID-19 Open Data v3 의 시도 파일에서; 값은 원값 그대로 옮긴다).

인구: KR_xx.csv 의 population 열 (파일 안에서 상수). Google 집계의 2차 자료이며, 원출처(행정안전부 주민등록 또는
      Wikidata 등)는 파일에 기록되어 있지 않아 확인하지 못했다 → tier = secondary.
기후: average_temperature_celsius, relative_humidity 일별 값 (NOAA GHCN-D 관측소 자료를 Google 이 지역에 배정한 값)의
      달별 평균 (관측된 날만, 2020-01 ~ 마지막 관측일). 기후평년값(30년)이 아니다.
출력: data_processed/tables/KOR_admin1_population_gc19od.csv, KOR_admin1_climate_gc19od.csv
"""

import csv
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw" / "gc19od_kr"
OUT = ROOT / "data_processed" / "tables"
CODES = ["11", "26", "27", "28", "29", "30", "31", "41", "42", "43", "44", "45", "46", "47", "48", "49", "50"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = json.loads((ROOT / "data_raw" / "manifest.json").read_text())
    entry = man.get("gc19od_kr", {})
    pop_rows, clim_rows, report = [], [], {}
    for c in CODES:
        d = pd.read_csv(RAW / f"KR_{c}.csv", low_memory=False)
        p = d["population"].dropna().unique()
        if p.size != 1:
            raise ValueError(f"KR_{c}: population 값이 하나가 아니다 {p}")
        pop_rows.append({"id": f"KR-{c}", "name": d["subregion1_name"].iloc[0], "population": int(p[0]),
                         "source": "Google COVID-19 Open Data v3 KR_" + c + ".csv population",
                         "tier": "secondary", "reference_date": "unknown (원출처 미기록)",
                         "note": "Google 집계값. 원출처 확인 못 함"})
        d["date"] = pd.to_datetime(d["date"])
        w = d.set_index("date")[["average_temperature_celsius", "relative_humidity"]].apply(pd.to_numeric, errors="coerce")
        w = w.dropna(how="all")
        period = f"{w.index.min().date()}~{w.index.max().date()}"
        g = w.groupby(w.index.month)
        n = g.count()
        m = g.mean()
        for month in range(1, 13):
            clim_rows.append({"id": f"KR-{c}", "month": month,
                              "tavg": round(float(m.loc[month, "average_temperature_celsius"]), 3) if month in m.index else "",
                              "rh": round(float(m.loc[month, "relative_humidity"]), 3) if month in m.index else "",
                              "n_days": int(n.loc[month, "average_temperature_celsius"]) if month in n.index else 0,
                              "source": "Google COVID-19 Open Data v3 weather (NOAA GHCN-D 관측소 기반)", "period": period})
        report[f"KR-{c}"] = {"population": int(p[0]), "weather_period": period, "weather_days": int(len(w))}
    for name, rows in (("KOR_admin1_population_gc19od.csv", pop_rows), ("KOR_admin1_climate_gc19od.csv", clim_rows)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader()
            wr.writerows(rows)
    meta = {"inputs": {"dataset": "gc19od_kr", "version": entry.get("version"), "retrieved_utc": entry.get("retrieved_utc"),
                       "license": entry.get("license")},
            "population_total": sum(r["population"] for r in pop_rows), "regions": report}
    (OUT / "KOR_admin1_tables.meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in meta.items() if k != "regions"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
