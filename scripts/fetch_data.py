"""외부 자료를 내려받고 출처·라이선스·용량·SHA-256 을 기록한다.

사용법: python -I scripts/fetch_data.py [자료 id ...]   (기본: 전체)
출력:   data_raw/<id>/<파일>, data_raw/manifest.json, docs/DATA_SOURCES.md

내려받기 전에 HEAD 요청으로 용량을 확인해 기록한다. 실패(정책 차단 등)는 그대로 기록하고,
대체 자료를 만들거나 꾸며 넣지 않는다.
"""

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seir_sim.data.registry import DATASETS, TIER  # noqa: E402

RAW = ROOT / "data_raw"


def head_size(url: str) -> tuple[str, int | None]:
    r = subprocess.run(["curl", "-sIL", "--max-time", "30", url], capture_output=True, text=True)
    status, size = "no response", None
    for line in r.stdout.splitlines():
        low = line.lower()
        if low.startswith("http/"):
            status = line.strip()
        if low.startswith("content-length:"):
            try:
                size = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return status, size


def download(url: str, dest: Path) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-sSfL", "--max-time", "600", "-o", str(dest), url], capture_output=True, text=True)
    return r.returncode == 0, r.stderr.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(ids):
    RAW.mkdir(exist_ok=True)
    man_path = RAW / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {}
    for did in ids:
        d = DATASETS[did]
        entry = {"title": d.title, "kind": d.kind, "license": d.license, "source": d.source,
                 "version": d.version, "resolution": d.resolution, "time_reference": d.time_reference,
                 "note": d.note, "official_host": d.official_host, "files": [], "status": "ok",
                 "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if not d.urls:
            entry["status"] = "unavailable: " + d.note
        for url in d.urls:
            status, size = head_size(url)
            name = url.rstrip("/").split("/")[-1]
            dest = RAW / did / name
            ok, err = download(url, dest) if " 200" in status else (False, status)
            f = {"url": url, "head_status": status, "content_length": size}
            if ok:
                f.update({"path": str(dest.relative_to(ROOT)), "bytes": dest.stat().st_size, "sha256": sha256(dest)})
            else:
                f["error"] = err or status
                entry["status"] = "blocked or failed"
            entry["files"].append(f)
        vfile = RAW / did / "VERSION"
        if vfile.exists():
            entry["version"] = vfile.read_text().strip()
        manifest[did] = entry
        print(did, entry["status"])
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    write_markdown(manifest)


def write_markdown(manifest):
    ok = [d for d, e in manifest.items() if e["status"] == "ok"]
    bad = [d for d, e in manifest.items() if e["status"] != "ok"]
    lines = ["# 외부 자료 출처 (scripts/fetch_data.py 가 생성)", "",
             "원본 파일은 `data_raw/` 에 있고 git 에 넣지 않는다. 같은 파일인지는 SHA-256 으로 확인한다.",
             "품질 점검 결과: `docs/reports/2_data_quality.md`.", "",
             "## 확보 현황 요약", "",
             "| id | 종류 | 상태 | 신뢰 등급 | 재배포 |", "|---|---|---|---|---|"]
    for did in ok + bad:
        e = manifest[did]
        tier, redis = TIER.get(did, ("-", "-"))
        lines.append(f"| {did} | {e['kind']} | {'확보' if did in ok else '미확보: ' + e['status']} | {tier} | {redis} |")
    lines += ["", "신뢰 등급: primary = 원출처 기관 자료, compiled = 연구기관이 공식 발표를 모은 자료, "
              "secondary = 2차 집계 또는 여러 출처 혼합.", "",
              "## 상세", "",
             "| id | 종류 | 상태 | 출처 | 라이선스 | 버전 | 해상도 | 기준 시점 | 용량 |", "|---|---|---|---|---|---|---|---|---|"]
    for did, e in manifest.items():
        size = sum(f.get("bytes", 0) for f in e["files"])
        lines.append(f"| {did} | {e['kind']} | {e['status']} | {e['source']} | {e['license']} | {e['version']} | "
                     f"{e['resolution']} | {e['time_reference']} | {size / 1e6:.1f} MB |")
    lines += ["", "## 파일", ""]
    for did, e in manifest.items():
        lines.append(f"### {did}: {e['title']}")
        if e.get("note"):
            lines.append(f"- 비고: {e['note']}")
        if e.get("official_host"):
            lines.append(f"- 공식 사이트: {e['official_host']}")
        for f in e["files"]:
            if "sha256" in f:
                lines.append(f"- {f['url']} → `{f['path']}` ({f['bytes']} bytes, sha256 `{f['sha256'][:16]}…`, {e['retrieved_utc']})")
            else:
                lines.append(f"- {f['url']} → 실패: {f.get('error', '')}")
        lines.append("")
    derived = ROOT / "docs" / "data_sources_derived.md"       # 손으로 관리하는 파생 자료·가정 절 (덮어쓰지 않음)
    if derived.exists():
        lines += ["", derived.read_text().rstrip()]
    (ROOT / "docs" / "DATA_SOURCES.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] or list(DATASETS))
