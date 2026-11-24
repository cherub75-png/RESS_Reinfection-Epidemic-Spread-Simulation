"""대한민국 시도 경계 시계열 (admdongkor: 통계청 SGIS 행정동 경계 기반, 1975 ~ 현재) 을 받는다.

Natural Earth 1:10m 시도 경계는 광역시 면적이 실제보다 매우 작다 (광주 133 km², 실제 약 500 km²). 그래서 인구 격자 합산과
인구밀도에 큰 오차가 생긴다. 이 스크립트는 시점별 시도 경계(light, EPSG:4326) 만 받아 data_raw/admdongkor_sido/ 에 두고
manifest.json 에 저장소 커밋·파일 SHA-256 을 기록한다.
사용법: python -I scripts/fetch_admdongkor.py [--commit <해시>]
라이선스: 원자료 SGIS 공공누리 제1유형(출처표시), admdongkor 가공물 CC BY 4.0 (LICENSE-DATA).
"""

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/vuski/admdongkor"
OUT = ROOT / "data_raw" / "admdongkor_sido"
sys.path.insert(0, str(ROOT))


def sh(*a, cwd=None):
    return subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", default=None, help="고정할 커밋 (기본: master 최신)")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        sh("git", "clone", "-q", "--filter=blob:none", "--sparse", "--no-checkout", REPO, "r", cwd=tmp)
        r = Path(tmp) / "r"
        sh("git", "sparse-checkout", "set", "--no-cone", "/parquet/simplified/sido_*", "/LICENSE-DATA", cwd=r)
        sh("git", "checkout", "-q", a.commit or "master", cwd=r)
        commit, when = sh("git", "rev-parse", "HEAD", cwd=r), sh("git", "log", "-1", "--format=%cI", cwd=r)
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True)
        files = sorted((r / "parquet" / "simplified").glob("sido_*_light.parquet")) + [r / "LICENSE-DATA"]
        recs = []
        for f in files:
            shutil.copy2(f, OUT / f.name)
            b = (OUT / f.name).read_bytes()
            recs.append({"url": f"{REPO}/blob/{commit}/{f.relative_to(r)}", "path": str((OUT / f.name).relative_to(ROOT)),
                         "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
    from seir_sim.data.registry import DATASETS
    d = DATASETS["admdongkor_sido"]
    man_path = ROOT / "data_raw" / "manifest.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else {}
    man["admdongkor_sido"] = {"title": d.title, "kind": d.kind, "license": d.license, "source": d.source,
                              "version": f"git {commit[:12]} ({when})", "resolution": d.resolution,
                              "time_reference": d.time_reference, "note": d.note, "official_host": d.official_host,
                              "files": recs, "status": "ok",
                              "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    man_path.write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(f"{len(recs)} 파일, 커밋 {commit} ({when})")


if __name__ == "__main__":
    main()
