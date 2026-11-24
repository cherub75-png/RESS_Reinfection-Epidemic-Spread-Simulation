"""6단계: 외부 원자료 갱신 관리 (네트워크 없이, 가짜 내려받기 함수로 검사)."""

import datetime as dt
import json

import pytest

from seir_sim.data.registry import DATASETS
from seir_sim.data.updater import Updater

DID = "openflights"


def _fake(content: dict, fail: set = frozenset()):
    def dl(url, dest):
        if url in fail:
            return False, "HTTP 403 (가짜 차단)"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.get(url, b"same"))
        return True, ""
    return dl


def test_unchanged_updated_failed_and_archive(tmp_path):
    raw = tmp_path / "raw"
    urls = DATASETS[DID].urls
    u = Updater(raw, _fake({x: b"v1" for x in urls}))
    r = u.check_update(DID)
    assert r["result"] == "updated" and r["archived_to"] is None          # 처음 받음
    man = json.loads((raw / "manifest.json").read_text())
    assert man[DID]["status"] == "ok" and len(man[DID]["files"]) == len(urls)
    assert u.check_update(DID)["result"] == "unchanged"
    # 내용이 바뀌면 이전 파일을 보관하고 교체
    u.download = _fake({x: b"v2" for x in urls})
    r = u.check_update(DID)
    assert r["result"] == "updated" and r["archived_to"]
    name = urls[0].rstrip("/").split("/")[-1]
    assert (raw / DID / name).read_bytes() == b"v2"
    assert (raw / r["archived_to"] / name).read_bytes() == b"v1"
    man = json.loads((raw / "manifest.json").read_text())
    assert len(man[DID]["history"]) == 1                                  # 처음 받은 판이 이력으로
    # 실패하면 기존 파일·manifest 그대로, 임시 파일 정리
    u.download = _fake({x: b"v3" for x in urls}, fail={urls[-1]})
    r = u.check_update(DID)
    assert r["result"] == "failed" and "기존 자료 유지" in r["message"]
    assert (raw / DID / name).read_bytes() == b"v2"
    assert json.loads((raw / "manifest.json").read_text()) == man
    assert not any((raw / "_staging" / DID).iterdir())
    assert [x["result"] for x in u.log()] == ["updated", "unchanged", "updated", "failed"]


def test_policy_and_due(tmp_path):
    u = Updater(tmp_path / "raw", _fake({}))
    assert not u.due(DID)                                                   # 정책 없으면 자동 확인 안 함
    u.set_policy(DID, 7, auto=True)
    assert u.due(DID)                                                       # 확인 기록 없음
    u.check_update(DID)
    assert not u.due(DID)
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=8)
    assert u.due(DID, now=later)
    with pytest.raises(ValueError):
        u.set_policy(DID, 0)
    with pytest.raises(KeyError):
        u.set_policy("nope", 7)
    st = {s["id"]: s for s in u.status()}
    assert st[DID]["policy"] == {"interval_days": 7, "auto": True}


def test_unavailable_dataset_is_reported(tmp_path):
    u = Updater(tmp_path / "raw", _fake({}))
    r = u.check_update("gpw_v4_11")
    assert r["result"] == "unavailable"
