# 프로젝트 로드맵

기준: "프로젝트 최종 완성 지시서" (2026-10-28). 상태는 실제 실행·테스트 결과로만 갱신한다.

| 단계 | 내용 | 상태 | 근거 |
|---|---|---|---|
| 1 | 시뮬레이션 엔진 (ODE, CTMC, tau-leap, SDE, 하이브리드, 데이터 계층, 앙상블) | 완료 | `docs/reports/STAGE1_REPORT.md` |
| 2 | 실제 감염병 자료 수집·품질 검증 | 완료 | `docs/reports/2_data_quality.md`, `docs/DATA_SOURCES.md` |
| 3 | 관측 모형과 매개변수 추정 | 완료 | `docs/reports/3_calibration.md`, `tests/test_inference.py` |
| 4 | 머신러닝·기준 모델 비교 | 진행 (코드·테스트 완료, 실행 중) | `seir_sim/ml/`, `tests/test_forecast.py` |
| 5 | COVID-19 시간순 예측 검증 | 진행 (규약 고정, 실행 중) | `docs/reports/5_protocol.md` |
| 6 | 공간·자연환경 자료 완성, 업데이트 관리 | 진행 | `seir_sim/data/versions.py`, `tests/test_data_versions.py` |
| 7 | 엔진·자료·추정 결과 통합 | 진행 | `seir_sim/inference/export.py`, `tests/test_integration.py` |
| 8 | 웹 애플리케이션 | 예정 | |
| 9 | 성능·안정성·보안 종합 검증 | 예정 | |
| 10 | 문서·배포 묶음 | 예정 | |

## 자료 접근 제약 (이 클라우드 환경)
- 접근 가능: GitHub raw (OWID, JHU, OxCGRT, Natural Earth, OpenFlights, datahub), Google Cloud Storage (COVID-19 Open Data), PyPI, npm
- 차단 (403): WHO, ECDC, CDC, KDCA, KOSIS, data.go.kr, World Bank API, UN WPP, WorldPop, GPW, WorldClim, Open-Meteo, NASA POWER, Zenodo, figshare, Hugging Face
- 차단된 자료는 "미확보" 로 기록하고, 로컬 파일 입력 경로를 제공한다 (6단계).
