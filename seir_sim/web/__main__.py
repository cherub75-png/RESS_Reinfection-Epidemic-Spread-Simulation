"""python -m seir_sim.web [--host 127.0.0.1] [--port 8765]

기본은 이 컴퓨터에서만 접속할 수 있는 127.0.0.1 이다. 다른 주소로 열려면 --host 를 명시해야 한다 (공개 배포는 별도 승인 필요).
"""

import argparse


def main():
    import uvicorn
    from .app import create_app
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--max-jobs", type=int, default=1, help="동시에 실행할 작업 수")
    a = ap.parse_args()
    hosts = None if a.host in ("127.0.0.1", "localhost") else ["127.0.0.1", "localhost", a.host]
    uvicorn.run(create_app(max_concurrent=a.max_jobs, allowed_hosts=hosts, auto_updates=True), host=a.host, port=a.port,
                log_level="info")


if __name__ == "__main__":
    main()
