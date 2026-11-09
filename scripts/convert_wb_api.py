"""World Bank 공식 API JSON (data_raw/wb_population_api/SP.POP.TOTL.json) -> datahub 와 같은 열 형식 CSV.

열: Country Name, Country Code, Year, Value. 값이 없는 (국가, 연도) 는 쓰지 않는다 (미확보). 값은 바꾸지 않는다.
출력: data_processed/tables/wb_population_api.csv (+ 같은 이름 .json 에 API lastupdated 와 원파일 SHA-256)
사용법: python -I scripts/convert_wb_api.py
"""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data_raw" / "wb_population_api" / "SP.POP.TOTL.json"
OUT = ROOT / "data_processed" / "tables" / "wb_population_api.csv"


def main():
    raw = SRC.read_bytes()
    head, rows = json.loads(raw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Country Name", "Country Code", "Year", "Value"])
        for r in rows:
            if r["value"] is None or not r["countryiso3code"]:
                continue
            w.writerow([r["country"]["value"], r["countryiso3code"], int(r["date"]), int(r["value"])])
            n += 1
    meta = {"source": "World Bank WDI API, SP.POP.TOTL", "api_lastupdated": head.get("lastupdated"),
            "raw_file": str(SRC.relative_to(ROOT)), "raw_sha256": hashlib.sha256(raw).hexdigest(), "rows": n,
            "years": [min(int(r["date"]) for r in rows if r["value"] is not None),
                      max(int(r["date"]) for r in rows if r["value"] is not None)]}
    OUT.with_suffix(".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(meta)


if __name__ == "__main__":
    main()
