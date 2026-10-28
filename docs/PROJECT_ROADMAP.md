# 프로젝트 로드맵

기준: "프로젝트 최종 완성 지시서" (2026-10-28). 상태는 실제 실행·테스트 결과로만 갱신한다.

| 단계 | 내용 | 상태 | 근거 |
|---|---|---|---|
| 1 | 시뮬레이션 엔진 (ODE, CTMC, tau-leap, SDE, 하이브리드, 데이터 계층, 앙상블) | 완료 | `docs/reports/STAGE1_REPORT.md` |
| 2 | 실제 감염병 자료 수집·품질 검증 | 완료 | `docs/reports/2_data_quality.md`, `docs/DATA_SOURCES.md` |
| 3 | 관측 모형과 매개변수 추정 | 완료 | `docs/reports/3_calibration.md`, `tests/test_inference.py` |
| 4 | 머신러닝·기준 모델 비교 | 완료 | `seir_sim/ml/`, `docs/reports/5_forecast_validation.md` |
| 5 | COVID-19 시간순 예측 검증 | 완료 (구간 7일 비교는 4개국 부가 실험) | `docs/reports/5_protocol.md`, `docs/reports/5_forecast_validation.md` |
| 6 | 공간·자연환경 자료 완성, 업데이트 관리 | 부분 완료 (아래 미완성 항목) | `seir_sim/data/versions.py`, `seir_sim/data/updater.py` |
| 7 | 엔진·자료·추정 결과 통합 | 완료 | `docs/reports/7_integration.md`, `tests/test_integration.py` |
| 8 | 웹 애플리케이션 (로컬) | 완료 | `seir_sim/web/`, `tests/test_web.py`, `tests/ui/smoke.mjs` |
| 9 | 성능·안정성·보안 종합 검증 | 진행 | `docs/VALIDATION_REPORT.md` |
| 10 | 문서·배포 묶음 | 예정 | |

## 자료 접근 제약 (이 클라우드 환경)
- 접근 가능: GitHub raw (OWID, JHU, OxCGRT, Natural Earth, OpenFlights, datahub), Google Cloud Storage (COVID-19 Open Data), PyPI, npm
- 차단 (403): WHO, ECDC, CDC, KDCA, KOSIS, data.go.kr, World Bank API, UN WPP, WorldPop, GPW, WorldClim, Open-Meteo, NASA POWER, Zenodo, figshare, Hugging Face
- 차단된 자료는 "미확보" 로 기록하고, 로컬 파일 입력 경로를 제공한다 (6단계).

## 미완성·차단 항목 (실제 상태)
| 항목 | 상태 | 이유 / 대안 |
|---|---|---|
| 대한민국 시도 인구 (1차 자료) | 2차 자료로 대체 | KOSIS·WorldPop 차단. Google Open Data 시도 인구(원출처 미기록)를 secondary 로 표시해 사용. 1차 자료는 로컬 인구표 경로로 교체 가능 |
| 기후 (WorldClim, ERA5) | 미확보 | 서버 차단. 대한민국 시도만 NOAA 관측소 기반 2020~2022 월 평균(2차) 있음. 기후 효과 g 는 추정하지 않음 (g = 1) |
| 시도별 u(t) 추정 | 안 함 | 시도 확진이 2020-09-09 까지만 있음 (2차 자료) |
| 지역 간 이동 실측량 | 미확보 | 항공 승객·통근 통계 서버 차단. 노선 구조는 실제, 규모는 가정값 |
| 최신(현재) 예측 | 불가 | 확보한 감염병 자료가 2023-03-09 에 끝남. 2023-03 기점 예측만 가능 |
| 백신·변이 구획 | 없음 | 방정식(1절) 범위 밖. u(t)·치명률 배율에 흡수 |
| 공개 배포 | 안 함 | 사용자 승인 필요. 로컬 실행판만 제공 |
