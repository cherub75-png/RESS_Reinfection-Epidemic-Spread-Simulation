# 사용자 안내서

이 프로그램은 재감염을 포함한 SEIR 방정식(작업 지시서 1절)으로 감염병 전파를 계산한다. 같은 방정식을 다섯 가지 방법(ODE, SDE, CTMC, tau-leaping, 하이브리드)으로 풀고, 실제 자료로 개입 효과 u(t)와 관측 매개변수를 추정하며, 과거 자료로 예측 성능을 검증한다. 로컬 웹 화면과 명령줄을 함께 제공한다.

## 1. 먼저 알아 둘 것

| 결과 종류 | 뜻 | 어디서 |
|---|---|---|
| 시나리오 | 사용자가 정한 R0·개입·초기 감염으로 방정식을 푼 결과. "이렇게 가정하면 이렇게 된다" (예측 아님) | 웹 "시나리오 실행", `seir_sim run` |
| 예측 검증 | 과거 각 기점에서 그날까지의 자료만으로 만든 예측을 실제와 비교한 성능 | 웹 "예측 검증", `docs/reports/5_forecast_validation.md` |
| 최신 자료 예측 | 가장 최근 자료 기점 다음 4주의 예측 | 웹 "최신 자료 예측", `seir_sim forecast` |

- 감염병 매개변수(잠복기, 감염 기간, 재감염 감수성, 치명률 등)는 **COVID 유사 코드 검증용 가정값**이다. 실제 추정치가 아니다.
- 이 저장소가 받은 COVID-19 확진·사망 자료(JHU CSSE)는 **2023-03-09** 에서 끝난다. 그래서 "최신 자료 예측" 도 2023-03 시점의 예측이다.
- 자료의 출처·등급·가정값은 웹 "자료 출처·가정" 과 `docs/DATA_SOURCES.md` 에 있다.

## 2. 설치

```bash
pip install -e ".[test,web]"           # Python 3.13
python -I scripts/fetch_data.py        # 공개 자료 내려받기 (출처·SHA-256 기록). 네트워크 정책에 따라 일부 미확보
python -I scripts/record_environment.py
```
자료를 만드는 순서 (처음 한 번)
```bash
python -I scripts/build_regions.py world --year 2019 --air-trips-per-day 5e6 --commute-fraction 0.002 \
    --contact-share 0.3 --out data_processed/world_countries_2019.nc
python -I scripts/make_kor_admin1_tables.py
python -I scripts/build_regions.py admin1 --country KOR --air-trips-per-day 9e4 --commute-fraction 0.05 \
    --contact-share 0.3 --population-table data_processed/tables/KOR_admin1_population_gc19od.csv \
    --climate-table data_processed/tables/KOR_admin1_climate_gc19od.csv --out data_processed/KOR_admin1_gc19od.nc
python -m seir_sim data register --name world_countries data_processed/world_countries_2019.nc --note "..."
python -m seir_sim data activate --name world_countries v1
python -m seir_sim data register --name KOR_admin1 data_processed/KOR_admin1_gc19od.nc --note "..."
python -m seir_sim data activate --name KOR_admin1 v1
```
`--air-trips-per-day`, `--commute-fraction`, `--contact-share` 는 자료가 아니라 가정값이며 기본값이 없다. 반드시 정해서 넣는다.

## 3. 웹 화면

```bash
python -m seir_sim.web                 # http://127.0.0.1:8765 (이 컴퓨터에서만 접속)
```
- **시나리오 실행**: 데이터셋(저장소 활성 버전 또는 합성 단일 지역), R0 와 기준(reference 기본 / 기준 지역 / 원점 / 인구가중 평균 / 지역망), 방법, 실행 횟수, 기간, 초기 감염, 개입 구간을 정하고 실행한다. 진행률이 보이고 취소할 수 있다.
- **결과·비교**: 저장된 작업 목록, 지역별 유병 지도(재생·시간 막대), 전체 감염 중 I(t) 그래프(마우스를 올리면 값), 지역 표(열 이름을 누르면 정렬), R0 기준별 c0 기록, 내보내기(CSV, JSON, NetCDF, 실행 기록). 시나리오를 2~5개 골라 비교할 수 있다.
- **예측 검증**: 5단계 결과 표와 그래프, 국가별 과거 예측 대 관측.
- **최신 자료 예측**: 국가를 골라 실행. 5단계 SEIR 결과가 있어야 SEIR·하이브리드가 나온다.
- **데이터 관리**: 데이터셋 버전 목록, 검증 결과, 이전 활성 버전 대비 변화, 활성화, 되돌리기. 출처 열이 있는 인구표(CSV)로 새 버전을 만들 수 있다 (등록만 하고 활성화는 직접).
- **자료 출처·가정**: 외부 자료의 상태(확보/미확보), 신뢰 등급, 라이선스, 가정값 목록.
- 화면 오른쪽 위에서 밝게/어둡게를 고를 수 있다.

공개 서버로 배포하지 않는다. 다른 주소로 열려면 `--host` 를 직접 지정해야 하며, 공개 배포는 별도 승인이 필요하다.

## 4. 명령줄

```bash
python -m seir_sim info configs/world_countries_2019.yaml                  # R0 기준별 값, 자료 품질
python -m seir_sim run configs/world_countries_2019.yaml --out outputs/world --method hybrid --runs 100 --workers 4
python -m seir_sim data list                                               # 데이터셋 버전
python -m seir_sim data validate data_processed/KOR_admin1_gc19od.nc
python -m seir_sim data diff --name KOR_admin1 new.nc                      # 활성 버전과 비교
python -m seir_sim data rollback --name KOR_admin1
python -m seir_sim forecast --country KOR --out outputs/forecast_KOR.json  # 최신 자료 예측
```
설정 파일에서 저장소 데이터셋을 쓰려면 `regions: {source: dataset, path: "registry:KOR_admin1"}` (활성 버전) 또는 `"registry:KOR_admin1@v1"` (고정 버전).

### R0 기준 (`disease.transmission.r0_reference`)
| 값 | 뜻 |
|---|---|
| `reference` (기본) | 기준 밀도, g = 1, u = 0, 단일 지역에서 R0 = c0 P1 T1 / γ |
| `region` + `reference_region` | 사용자가 고른 지역의 고립 R0 가 목표 |
| `origin` | 첫 초기 감염 지역의 고립 R0 (비교용) |
| `population_mean` | 인구가중 평균 고립 R0 (비교용) |
| `network` | 지역망 다음 세대 행렬의 스펙트럼 반지름 (작은 고밀도 지역이 지배할 수 있음) |

어느 기준이든 c0 하나를 모든 지역에 쓴다. 모든 기준의 c0 는 실행 기록 `derived.c0_by_basis` 에 남는다.

### 계산 방법 고르기
| 방법 | 쓰임 |
|---|---|
| `hybrid` | 기본 권장. 감염자가 적은 지역은 정확한 사건 단위, 많은 지역은 tau-leaping |
| `ode` | 평균 궤적 1회 (결정론) |
| `ctmc` | 정확한 기준. 인구가 크면 매우 느리다 |
| `tau`, `sde` | 빠른 근사. 감염자가 적은 영역에서 부정확 |
누적 지표를 정밀하게 볼 때는 `simulation.tau_leap_epsilon` 을 0.003 으로 낮춘다 (D-007, `docs/reports/D007_D004.md`).

## 5. 결과 파일

시나리오 (`outputs/<폴더>/` 또는 웹 `outputs/web_jobs/<id>/`)
- `ensemble.nc`: 실행별·지역별 S, E, I, D 와 요약 통계
- `summary_daily.parquet`, `summary_regions.parquet`, 웹은 `daily.csv`, `regions.csv`, `summary.json`
- `run_record.json`: 설정 전체, 설정 해시, 시드, 실행 환경(패키지 버전), 지역 자료 출처, R0 기준별 값

## 6. 재현

- 같은 설정·같은 코드·같은 시드면 병렬 여부와 관계없이 같은 결과가 나온다 (테스트로 확인).
- 데이터셋은 저장소에 SHA-256 과 함께 등록되며, 파일이 바뀌면 불러오기를 거부한다.
- 보고서는 모두 `scripts/` 의 스크립트로 다시 만들 수 있다 (각 보고서 머리말에 명령이 있다).

## 7. 한계 (요약)

- 방정식에 백신·변이·연령 구조·해외 유입 항이 없다. 그 효과는 추정 u(t) 와 치명률 배율에 흡수된다.
- 보고율은 자료로 식별되지 않아 가정값(0.5)이다.
- 대한민국 시도 인구는 2차 자료(Google Open Data), 시도 간 이동 규모는 가정값이다. 시도별 u(t) 는 추정하지 않았다.
- 기후 효과 g 는 추정하지 않았다 (g = 1). WorldClim·ERA5 는 이 환경에서 받지 못했다.
- 예측 성능은 12개국 2020-07 ~ 2023-01 의 과거 검증 결과이며 다른 시기·병원체의 정확도를 보장하지 않는다.
자세한 내용: `docs/VALIDATION_REPORT.md`, `docs/DECISIONS.md`.
