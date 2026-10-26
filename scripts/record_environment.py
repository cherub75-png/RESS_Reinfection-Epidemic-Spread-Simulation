"""실행 환경을 env/environment.json 과 env/requirements-lock.txt 에 기록한다.

사용법: python scripts/record_environment.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seir_sim.provenance import environment_record  # noqa: E402


def main():
    rec = environment_record()
    out = ROOT / "env"
    out.mkdir(exist_ok=True)
    rec.pop("git_commit", None)   # 커밋 해시는 실행 기록에만 남긴다 (자기 참조 방지)
    (out / "environment.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    lock = "\n".join(f"{k}=={v}" for k, v in sorted(rec["packages"].items(), key=lambda kv: kv[0].lower()))
    (out / "requirements-lock.txt").write_text(
        "# 이 저장소가 실제로 쓰는 패키지의 검증된 버전 (scripts/record_environment.py 로 생성)\n" + lock + "\n")
    print(json.dumps(rec, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
