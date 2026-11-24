"""웹 작업 관리: 대기열, 별도 프로세스 실행, 진행률, 취소, 저장 (outputs/web_jobs/<id>/).

작업 하나 = 프로세스 하나 (forkserver). 동시에 max_concurrent 개까지 돌리고 나머지는 대기한다.
진행률은 작업 폴더의 status.json 으로 주고받고, 취소는 cancel 파일로 알린다 (실행 사이마다 확인).
서버가 다시 시작되면 끝나지 않은 작업은 'interrupted' 로 표시한다 (결과를 지어내지 않는다).
"""

from __future__ import annotations

import datetime as dt
import json
import multiprocessing as mp
import queue
import re
import threading
import traceback
import uuid
from pathlib import Path

JOB_ID = re.compile(r"^[0-9a-f]{32}$")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_status(job_dir: Path, **kw) -> None:
    p = job_dir / "status.json"
    cur = json.loads(p.read_text()) if p.exists() else {}
    cur.update(kw, updated_utc=_now())
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False))
    tmp.replace(p)


PASS_ENV = ("SEIR_SIM_DATASET_STORE", "SEIR_SIM_RAW_DIR")


def _job_main(kind: str, job_dir: str, env: dict | None = None) -> None:
    """작업 프로세스 진입점. env: 제출 시점의 설정 환경 변수 (forkserver 자식은 서버 시작 때 환경을 물려받으므로 따로 넘긴다)."""
    import os
    import warnings
    warnings.simplefilter("ignore")
    for k, v in (env or {}).items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    d = Path(job_dir)
    req = json.loads((d / "request.json").read_text())
    write_status(d, state="running", started_utc=_now(), progress=0.0)
    try:
        if kind == "scenario":
            from .scenario import run_scenario
            run_scenario(req, d, cancel=lambda: (d / "cancel").exists(),
                         progress=lambda a, b: write_status(d, progress=a / b, message=f"{a}/{b} 실행"))
        elif kind == "forecast":
            from ..forecast.operational import latest_forecast
            out = latest_forecast(req["iso3"], req.get("origin"), log=lambda m: write_status(d, message=m))
            (d / "result.json").write_text(json.dumps(out, ensure_ascii=False))
        elif kind == "update":
            from ..data.updater import Updater
            out = Updater().check_update(req["id"])
            (d / "result.json").write_text(json.dumps(out, ensure_ascii=False, default=str))
            if out["result"] == "failed":
                raise RuntimeError(out.get("message", "갱신 실패"))
        elif kind == "flu_forecast":
            from ..forecast.flu_operational import latest_flu_forecast
            out = latest_flu_forecast(with_seir=bool(req.get("seir")), log=lambda m: write_status(d, message=m))
            (d / "result.json").write_text(json.dumps(out, ensure_ascii=False))
        elif kind == "climate":
            from ..data import era5, periods
            out = era5.monthly_means(req["start"], req["end"], periods.CLIMATE / f"era5_{req['start']}_{req['end']}",
                                     log=lambda m: write_status(d, message=m))
            (d / "result.json").write_text(json.dumps(out, ensure_ascii=False, default=str))
        elif kind == "dataset":
            from .datasets import build_and_register
            out = build_and_register(req, d)
            (d / "result.json").write_text(json.dumps(out, ensure_ascii=False, default=str))
        else:
            raise ValueError(kind)
        write_status(d, state="done", finished_utc=_now(), progress=1.0)
    except Exception as e:  # noqa: BLE001 (작업 실패를 기록하고 프로세스는 끝낸다)
        from ..ensemble.runner import EnsembleCancelled
        if isinstance(e, EnsembleCancelled):
            write_status(d, state="cancelled", finished_utc=_now(), message=str(e))
        else:
            write_status(d, state="failed", finished_utc=_now(), message=f"{type(e).__name__}: {e}",
                         traceback=traceback.format_exc()[-4000:])


class JobManager:
    def __init__(self, root: Path, max_concurrent: int = 1, max_seconds: float = 6 * 3600):
        self.root = Path(root)
        self.max_seconds = max_seconds
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self.q: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.procs: dict[str, mp.Process] = {}
        self.ctx = mp.get_context("forkserver")
        for st in self.root.glob("*/status.json"):          # 이전 서버에서 끝나지 않은 작업
            s = json.loads(st.read_text())
            if s.get("state") in ("queued", "running"):
                write_status(st.parent, state="interrupted", message="서버가 다시 시작되어 작업이 끝나지 못했다")
        self._threads = [threading.Thread(target=self._worker, daemon=True) for _ in range(max_concurrent)]
        for t in self._threads:
            t.start()

    def dir(self, job_id: str) -> Path:
        if not JOB_ID.match(job_id):
            raise KeyError(job_id)
        d = self.root / job_id
        if not d.is_dir():
            raise KeyError(job_id)
        return d

    def submit(self, kind: str, request: dict, title: str) -> str:
        job_id = uuid.uuid4().hex
        d = self.root / job_id
        d.mkdir()
        (d / "request.json").write_text(json.dumps(request, ensure_ascii=False, default=str))
        write_status(d, id=job_id, kind=kind, title=title, state="queued", created_utc=_now(), progress=0.0)
        self.q.put((kind, job_id))
        return job_id

    def _worker(self):
        while True:
            kind, job_id = self.q.get()
            d = self.root / job_id
            if (d / "cancel").exists():
                write_status(d, state="cancelled", message="시작 전 취소")
                continue
            import os
            env = {k: os.environ.get(k) for k in PASS_ENV}
            p = self.ctx.Process(target=_job_main, args=(kind, str(d), env))
            p.start()
            with self.lock:
                self.procs[job_id] = p
            p.join(self.max_seconds)
            if p.is_alive():                                     # 시간 상한: 멈추고 실패로 기록
                p.terminate()
                p.join(10)
                write_status(d, state="failed", message=f"시간 상한 {self.max_seconds:.0f}초를 넘어 중단했다")
            with self.lock:
                self.procs.pop(job_id, None)
            try:
                s = self.status(job_id)
            except (KeyError, OSError):                         # 사용자가 끝난 작업을 지웠다: 다음 작업으로
                continue
            if s.get("state") == "running":                   # 프로세스가 비정상 종료
                write_status(d, state="failed", message=f"작업 프로세스 종료 코드 {p.exitcode}")

    def status(self, job_id: str) -> dict:
        return json.loads((self.dir(job_id) / "status.json").read_text())

    def cancel(self, job_id: str) -> dict:
        d = self.dir(job_id)
        (d / "cancel").touch()
        s = self.status(job_id)
        if s.get("state") == "queued":
            write_status(d, state="cancelled", message="시작 전 취소")
        return self.status(job_id)

    def rename(self, job_id: str, title: str) -> dict:
        write_status(self.dir(job_id), title=title)
        return self.status(job_id)

    def delete(self, job_id: str) -> None:
        """끝난 작업 폴더만 지운다 (작업 id 형식과 폴더 위치는 dir() 가 확인한다)."""
        import shutil
        d = self.dir(job_id)
        if self.status(job_id).get("state") in ("queued", "running"):
            raise ValueError("대기 중이거나 실행 중인 작업은 지울 수 없다 (먼저 취소)")
        with self.lock:
            p = self.procs.get(job_id)
        if p is not None:                                     # 완료를 기록한 뒤 프로세스가 끝나기까지 잠깐 기다린다
            import time
            t0 = time.time()
            while p.is_alive() and time.time() - t0 < 15:
                time.sleep(0.1)
            if p.is_alive():
                raise ValueError("작업 프로세스가 아직 끝나지 않았다 (잠시 뒤 다시)")
        if d.parent.resolve() != self.root.resolve():
            raise ValueError("작업 폴더 위치가 올바르지 않다")
        shutil.rmtree(d)

    def list(self) -> list[dict]:
        out = []
        for st in self.root.glob("*/status.json"):
            try:
                out.append(json.loads(st.read_text()))
            except json.JSONDecodeError:
                continue
        return sorted(out, key=lambda s: s.get("created_utc", ""), reverse=True)

    def wait(self, job_id: str, timeout: float = 600.0) -> dict:
        """테스트용: 끝날 때까지 기다린다."""
        import time
        t0 = time.time()
        while time.time() - t0 < timeout:
            s = self.status(job_id)
            if s.get("state") in ("done", "failed", "cancelled", "interrupted"):
                return s
            time.sleep(0.2)
        raise TimeoutError(job_id)
