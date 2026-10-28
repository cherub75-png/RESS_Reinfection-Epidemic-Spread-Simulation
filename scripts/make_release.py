"""최종 결과물 압축본 만들기: git 에 커밋된 내용(HEAD) + 브랜치·커밋 정보.

원자료(data_raw), 가공 자료(data_processed), 실행 결과(outputs) 는 넣지 않는다 (라이선스·용량; 내려받기·재생성 방법은
docs/USER_GUIDE.md 2절). 커밋되지 않은 변경이 있으면 멈춘다 (압축본이 기록된 커밋과 같도록).
사용법: python -I scripts/make_release.py [--out outputs/release]
"""

import argparse
import datetime as dt
import io
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*a) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "outputs" / "release"))
    a = ap.parse_args()
    if git("status", "--porcelain"):
        sys.exit("커밋되지 않은 변경이 있다. 먼저 커밋한다.")
    commit, short, branch = git("rev-parse", "HEAD"), git("rev-parse", "--short", "HEAD"), git("rev-parse", "--abbrev-ref", "HEAD")
    import re
    remote = re.sub(r"//[^@/]*@", "//", git("remote", "get-url", "origin"))      # 주소에 인증 정보가 있으면 지운다
    when = git("log", "-1", "--format=%cI")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"epidemic_seir_sim_{short}"
    tar = subprocess.run(["git", "archive", "--format=zip", f"--prefix={name}/", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    info = (f"저장소: {remote}\n브랜치: {branch}\n커밋: {commit}\n커밋 시각: {when}\n"
            f"압축본 생성: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}\n\n"
            "포함: git HEAD 의 모든 파일 (소스, 테스트, 설정, 문서, 보고서, 그림, 웹 화면, Leaflet 1.9.4).\n"
            "제외: data_raw (외부 원자료), data_processed (가공 자료), outputs (실행 결과). 다시 만드는 방법: docs/USER_GUIDE.md 2절.\n"
            "시작: README.md -> docs/USER_GUIDE.md -> docs/VALIDATION_REPORT.md\n")
    zpath = out / f"{name}.zip"
    with zipfile.ZipFile(io.BytesIO(tar)) as src, zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr(f"{name}/RELEASE_INFO.txt", info)
    print(zpath, f"{zpath.stat().st_size / 1e6:.1f} MB")
    print(info)


if __name__ == "__main__":
    main()
