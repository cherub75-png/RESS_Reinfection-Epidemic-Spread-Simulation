"""외부 원자료 갱신 관리: 갱신 확인, 주기 설정, 실패 시 이전 자료 유지, 이전 판 보존, 변경 기록.

흐름 (check_update)
  1. 새 파일을 data_raw/_staging/<id>/<시각>/ 에 받는다 (기존 파일은 건드리지 않음).
  2. 하나라도 실패하면 받은 것을 지우고 'failed' 로 기록한다. 기존 자료는 그대로다 (시뮬레이션은 기존 자료로 계속 실행 가능).
  3. 모두 받았으면 SHA-256 을 manifest 와 비교한다. 같으면 'unchanged'.
  4. 다르면 기존 파일을 data_raw/_archive/<id>/<시각>/ 로 옮기고 새 파일을 넣은 뒤 manifest 를 갱신한다 ('updated').
     manifest 항목의 history 에 이전 판(받은 시각, SHA-256, 보관 위치)을 남긴다.
원자료가 바뀌어도 파생 데이터셋(data_processed)은 자동으로 바뀌지 않는다. 다시 만들어 새 버전으로 등록하고 검증한 뒤
활성화한다 (data.versions). 그래서 갱신이 잘못되어도 활성 데이터셋은 영향을 받지 않는다.

주기: data_raw/update_policy.json  {id: {"interval_days": 7, "auto": false}}. auto 가 참인 자료만 웹 서버가 시작할 때
기한이 지났으면 갱신 확인 작업을 올린다. 기본은 수동이다.
기록: data_raw/update_log.json (최근 500건).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .registry import DATASETS

ROOT = Path(__file__).resolve().parents[2]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def curl_download(url: str, dest: Path) -> tuple[bool, str]:
    """환경의 프록시·인증서 설정을 그대로 쓰는 curl. 차단(403 등)은 실패로 돌려주고 우회하지 않는다."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-sSfL", "--max-time", "600", "-o", str(dest), url], capture_output=True, text=True)
    return r.returncode == 0, r.stderr.strip()


class Updater:
    def __init__(self, raw: Path | None = None, downloader=curl_download):
        import os
        self.raw = Path(raw or os.environ.get("SEIR_SIM_RAW_DIR") or ROOT / "data_raw")
        self.download = downloader

    # ------------------------------------------------------------------ 기록·정책
    def _read(self, name, default):
        p = self.raw / name
        return json.loads(p.read_text()) if p.exists() else default

    def _write(self, name, obj):
        self.raw.mkdir(parents=True, exist_ok=True)
        p = self.raw / name
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
        tmp.replace(p)

    def policy(self) -> dict:
        return self._read("update_policy.json", {})

    def set_policy(self, did: str, interval_days: int | None, auto: bool = False) -> dict:
        if did not in DATASETS:
            raise KeyError(did)
        if interval_days is not None and not (1 <= int(interval_days) <= 3650):
            raise ValueError("interval_days 는 1~3650")
        pol = self.policy()
        pol[did] = {"interval_days": None if interval_days is None else int(interval_days), "auto": bool(auto)}
        self._write("update_policy.json", pol)
        return pol[did]

    def log(self) -> list:
        return self._read("update_log.json", [])

    def _append_log(self, rec: dict):
        lg = self.log()
        lg.append(rec)
        self._write("update_log.json", lg[-500:])

    def last_check(self, did: str) -> dict | None:
        for r in reversed(self.log()):
            if r["id"] == did:
                return r
        return None

    def due(self, did: str, now: dt.datetime | None = None) -> bool:
        p = self.policy().get(did) or {}
        if not p.get("interval_days"):
            return False
        last = self.last_check(did)
        if last is None:
            return True
        t = dt.datetime.fromisoformat(last["checked_utc"])
        return (now or _now()) - t >= dt.timedelta(days=p["interval_days"])

    # ------------------------------------------------------------------ 갱신 확인
    def check_update(self, did: str, apply: bool = True) -> dict:
        d = DATASETS[did]
        ts = _now().strftime("%Y%m%dT%H%M%S%fZ")
        rec = {"id": did, "checked_utc": _now().isoformat(timespec="seconds"), "files": []}
        if not d.urls:
            rec.update(result="unavailable", message=d.note or "내려받을 주소가 없다")
            self._append_log(rec)
            return rec
        man = self._read("manifest.json", {})
        old = {f.get("url"): f for f in man.get(did, {}).get("files", [])}
        stage = self.raw / "_staging" / did / ts
        new = []
        for url in d.urls:
            name = url.rstrip("/").split("/")[-1]
            ok, err = self.download(url, stage / name)
            if not ok:
                shutil.rmtree(stage, ignore_errors=True)
                rec.update(result="failed", message=f"{url}: {err or '실패'} (기존 자료 유지)")
                self._append_log(rec)
                return rec
            sha = _sha256(stage / name)
            prev = old.get(url, {}).get("sha256")
            new.append({"url": url, "name": name, "sha256": sha, "bytes": (stage / name).stat().st_size,
                        "changed": prev != sha, "previous_sha256": prev})
        rec["files"] = [{k: f[k] for k in ("url", "sha256", "changed", "previous_sha256", "bytes")} for f in new]
        if not any(f["changed"] for f in new):
            shutil.rmtree(stage, ignore_errors=True)
            rec.update(result="unchanged")
            self._append_log(rec)
            return rec
        if not apply:
            rec.update(result="changed_not_applied", staging=str(stage.relative_to(self.raw)))
            self._append_log(rec)
            return rec
        dest = self.raw / did
        archive = self.raw / "_archive" / did / ts
        entry = man.get(did, {})
        for f in new:
            if (dest / f["name"]).exists():
                archive.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest / f["name"]), archive / f["name"])
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stage / f["name"]), dest / f["name"])
        shutil.rmtree(stage, ignore_errors=True)
        hist = entry.get("history", [])
        if entry:
            hist.append({"retrieved_utc": entry.get("retrieved_utc"),
                         "files": [{"url": f.get("url"), "sha256": f.get("sha256")} for f in entry.get("files", [])],
                         "archived_to": str(archive.relative_to(self.raw)) if archive.exists() else None})
        entry.update({"title": d.title, "kind": d.kind, "license": d.license, "source": d.source, "version": d.version,
                      "resolution": d.resolution, "time_reference": d.time_reference, "note": d.note,
                      "official_host": d.official_host, "status": "ok", "retrieved_utc": rec["checked_utc"],
                      "files": [{"url": f["url"], "path": str((dest / f["name"]).relative_to(ROOT)) if (dest / f["name"]).is_relative_to(ROOT)
                                 else str(dest / f["name"]), "bytes": f["bytes"], "sha256": f["sha256"]} for f in new],
                      "history": hist})
        man[did] = entry
        self._write("manifest.json", man)
        rec.update(result="updated", archived_to=str(archive.relative_to(self.raw)) if archive.exists() else None,
                   message="원자료가 바뀌었다. 파생 데이터셋은 다시 만들어 새 버전으로 등록해야 반영된다.")
        self._append_log(rec)
        return rec

    def status(self) -> list[dict]:
        man = self._read("manifest.json", {})
        pol = self.policy()
        out = []
        for did, d in DATASETS.items():
            e = man.get(did, {})
            last = self.last_check(did)
            out.append({"id": did, "title": d.title, "status": e.get("status", "not fetched"),
                        "retrieved_utc": e.get("retrieved_utc"), "time_reference": d.time_reference,
                        "license": d.license, "policy": pol.get(did), "last_check": last,
                        "due": self.due(did), "versions_kept": len(e.get("history", []))})
        return out
