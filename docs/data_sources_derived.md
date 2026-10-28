## 파생 자료와 가정값 (손으로 관리: docs/data_sources_derived.md, fetch_data.py 가 이 절을 DATA_SOURCES.md 끝에 붙인다)

### 파생 자료 (이 저장소 코드가 원자료에서 만든 것)

| 파일 | 만드는 코드 | 입력 | 처리 | 등급 |
|---|---|---|---|---|
| `data_processed/tables/KOR_admin1_population_gc19od.csv` | `scripts/make_kor_admin1_tables.py` | gc19od_kr `KR_xx.csv` population 열 | 그대로 옮김 (시도 17개, 합 51,673,394) | secondary (원출처 미기록) |
| `data_processed/tables/KOR_admin1_climate_gc19od.csv` | 같은 스크립트 | gc19od_kr 기상 열 (NOAA GHCN-D 관측소 기반) | 달별 평균 (관측된 날만, 2020-01-01 ~ 2022-09 중순; 달마다 관측일 수 n_days 기록) | secondary, 기후평년값 아님 |
| `data_processed/KOR_admin1_gc19od.nc` (저장소 등록 이름 `KOR_admin1` v1) | `scripts/build_regions.py admin1 --population-table ... --climate-table ...` | NE admin1 경계, 위 두 표, OpenFlights | 측지 면적·중심, 균형 항공 ω, radiation 통근 C | 혼합 (아래 가정 포함) |
| `data_processed/world_countries_2019.nc` (등록 이름 `world_countries` v1) | `scripts/build_regions.py world --year 2019 ...` | NE admin0, World Bank 2019 (+ NE POP_EST), OpenFlights | 같은 처리 | 혼합 (아래 가정 포함) |
| `outputs/stage5/*` | `scripts/run_stage5_seir.py`, `scripts/report_stage5_forecast.py` | JHU, OxCGRT, Google 이동, OWID 백신·인구 | 시간순 예측 결과 (예측값이며 관측값 아님) | 모형 산출물 |

등록된 데이터셋의 SHA-256·검증 결과·이전 버전과의 차이: `data_processed/datasets/registry.json` (`python -m seir_sim data list`).

### 가정값 (자료가 아님; 사용자가 바꿀 수 있음)

| 이름 | 값 | 쓰는 곳 | 근거·불확실성 |
|---|---|---|---|
| 국가 간 항공 이동 | 5e6 회/일 | 전 세계 데이터셋 `--air-trips-per-day` | 출처 확인한 승객 자료 없음. 크기 정도만 맞춘 가정 (불확실성 큼: 2배 이상) |
| 국가 간 통근 비율 | 0.002 | 전 세계 `--commute-fraction` | 가정. 국경 통근 자료 미확보 |
| 목적지 접촉 비율 | 0.3 | 전 세계·시도 `--contact-share` | 가정. 통근자 접촉 중 목적지에서 일어나는 비율 |
| 국내 항공 이동 (대한민국) | 9e4 회/일 | 시도 데이터셋 | 가정. 국내선 승객 통계(국토교통부 항공정보포털) 미확보 |
| 시도 간 통근 비율 (대한민국) | 0.05 | 시도 데이터셋 | 가정. 통계청 통근 자료(KOSIS) 차단으로 미확보 |
| 보고율 rho | 0.5 | 3·5단계 추정 | 식별 불가 (D-011) |
| R0_max | 6 | 3·5단계 추정 | u = 0 기준값, 상한 역할 (D-012) |
| 감염병 매개변수 (σ, γ, P, T, f, λ 등) | 1단계 COVID 유사 값 | 엔진·추정 | 코드 검증용 가정. 실제 COVID-19 추정치가 아님 |

### 실제 관측값·추정값·예측값 구분
- 관측값: `data_raw/` 의 원자료와, 원자료를 그대로 옮긴 표 (위 표의 secondary 표 포함).
- 추정값: 3단계 u(t), I0, 지연, 과산포, k_f (보고서 3_calibration). 관측값으로 쓰지 않는다.
- 예측값: 5단계·최신 자료 예측. 검증에는 기점 뒤의 실제 관측값만 쓴다.
- 합성 자료: 테스트와 추정기 검증에만 쓰며 synthetic 표시가 붙는다.
