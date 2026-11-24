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
| 9 | 성능·안정성·보안 종합 검증 | 완료 | `docs/VALIDATION_REPORT.md`, `docs/reports/9_performance.md`, `docs/reports/9_sensitivity.md` |
| 10 | 문서·배포 묶음 (로컬 실행판 압축본) | 완료 (공개 배포는 승인 필요로 안 함) | `docs/USER_GUIDE.md`, `scripts/make_release.py` |
| 11 | 인플루엔자 (WHO FluNet) 시간순 예측 검증·최신 예측, 구간 보정 | 완료 | `docs/reports/11_influenza_protocol.md`, `docs/reports/11_influenza_validation.md`, `docs/reports/12_interval_calibration.md` |
| 12 | 최신 자료·시기 선택, 웹 작업 공간 | 완료 | `seir_sim/data/periods.py`, `seir_sim/web/`, D-021 |

## 자료 접근 제약 (이 클라우드 환경)
- 2026-11 사용자가 네트워크 허용 도메인을 추가함: WHO FluNet, KOSIS, 공공데이터포털, 질병청, 기상청, World Bank, UN, WorldPop, WorldClim 서버 접속 가능.
- API 키가 필요한 KOSIS·공공데이터포털·기상청 API허브는 키가 없어 쓰지 않았다 (환경 변수 `KOSIS_API_KEY`, `DATA_GO_KR_KEY`, `KMA_API_KEY` 가 있으면 쓸 수 있음).

## 미완성·차단 항목 (실제 상태)
| 항목 | 상태 | 이유 / 대안 |
|---|---|---|
| 대한민국 시도 인구 (주민등록, 1차) | 범위에서 제외 (사용자 결정, D-027) | WorldPop 모델 추정으로 완료. 2020년 값은 2차 자료 표와 중앙 1.2% 차이 |
| 시도별 u(t) 추정 | 범위에서 제외 (사용자 결정, D-027) | 공식 시도별 일별 확진 자료 없음. 설계만 기록 (D-026) |
| 기후 효과 g 추정 | 안 함 | u(t) 와 함께 식별 어려움. 기후 특성의 예측 기여는 시험함 (기여 없음) (D-025) |
| 지역 간 이동 실측량 | 미확보 | 노선 구조는 실제(2014), 규모는 가정값. 공식 이동 통계는 KOSIS 키 필요, 항공 승객 OD 는 유료 |
| COVID-19 현재 시점 예측 | 불가 | 확진·사망 자료가 2023-03-09 에 끝남. 인플루엔자는 최신 예측 가능 |
| 자료 빈티지 (소급 보완 재현) | 없음 | FluNet·JHU 는 받은 날의 최종판. 2026-11 부터 받은 판을 보관함 |
| 백신·변이 구획 | 없음 | 방정식(1절) 범위 밖 (사용자 결정: 방정식 변경 안 함) |
| 공개 배포·PR | 안 함 | 사용자 결정 |
