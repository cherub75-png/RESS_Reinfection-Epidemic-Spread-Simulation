# Epidemic-Spread-Simulation_Claude-Code

전 세계 재감염 SEIR 전파 예측 시뮬레이터. 지역 자료와 감염병 매개변수를 넣으면 ODE, SDE, CTMC, tau-leaping, 하이브리드로 앙상블 예측을 낸다.
- 수학 기준은 작업 지시서 1절이다. 구현 해석과 유도는 `docs/MODEL.md` 에 있다.
- 특정 국가 전용 코드는 없다. 같은 파이프라인이 전 세계 국가 단위와 한 나라의 1급 행정구역을 만든다.

## 진행 상태 (1단계)
| 단계 | 내용 | 상태 | 보고서 |
|---|---|---|---|
| 1-A | 골격, 설정, 매개변수, 공통 사건 목록, R0 분석 | 완료 | |
| 1-B | ODE 와 검증 | 완료 | `docs/reports/1B_ode_validation.md` |
| 1-C | CTMC, 이동 사건 합치기, 이항 tau-leap, SDE, 하이브리드, 모형 비교 | 완료 | `docs/reports/1C_*.md` |
| 1-D | 범용 데이터 파이프라인 | 완료 (일부 자료 미확보) | `docs/DATA_SOURCES.md` |
| 1-E | 앙상블 실행기, 명령줄, 예제 그림 | 완료 | `docs/reports/STAGE1_REPORT.md` |

진행 기록: `docs/PROGRESS.md`. 결정과 근거(확인이 필요한 항목 포함): `docs/DECISIONS.md`.

## 설치와 테스트
```bash
pip install -e ".[test]"
python -m pytest                       # 약 4~5분, 실제 자료가 없으면 해당 점검 테스트는 건너뜀
python scripts/record_environment.py   # env/ 에 실행 환경과 패키지 버전 기록
```

## 실행
```bash
python -m seir_sim info configs/example_single_region.yaml           # 시나리오 점검 (R0 보고 등)
python -m seir_sim run  configs/example_single_region.yaml --out outputs/single --method hybrid --runs 100 --workers 4
```
결과 (`--out` 폴더)
- `ensemble.nc`: 실행별 지역별 S, E, I, D 와 요약 통계 (NetCDF)
- `summary_daily.parquet`, `summary_regions.parquet`
- `run_record.json`: 설정, 시드, 환경, 자료 출처
- 그림: `I_total.png`, `regions_heatmap.png`, `arrival_map.png`

방법 선택 (`--method`, `docs/reports/1C_compare.md`)
- `hybrid`: 기본 권장. 소멸·초기 유입까지 정확하다.
- `ode`: 평균 기준선
- `tau`, `sde`: 대규모 빠른 근사. 감염자가 적은 영역에서는 부정확하다.
- `ctmc`: 정확한 기준. 큰 인구에서는 매우 느리다.

## 실제 지역 자료 만들기
```bash
python -I scripts/fetch_data.py        # 내려받기 + 출처·라이선스·SHA-256 기록 (docs/DATA_SOURCES.md)
python -I scripts/build_regions.py world --year 2019 --air-trips-per-day 5e6 \
    --commute-fraction 0.002 --contact-share 0.3 --out data_processed/world_countries_2019.nc
python -m seir_sim run configs/world_countries_2019.yaml --out outputs/world --runs 100 --workers 4 \
    --outlines data_raw/ne_admin0_10m/ne_10m_admin_0_countries.geojson
```

### 자료 구분
- **실제 자료**: Natural Earth 경계(5.2.0-pre), World Bank 국가 인구, OpenFlights 공항·노선(2014년)
- **명시적 가정**: 하루 항공 이동 횟수, 통근 비율, 목적지 접촉 비율 (명령줄에서 반드시 지정, 기본값 없음)
- **미확보** (이 클라우드 환경의 네트워크 정책 차단): WorldPop / GPW 인구 격자 (→ 대한민국 시도별 인구), WorldClim 기후. 해결 방법은 `docs/DECISIONS.md` D-006 에 있다.
- **합성 자료**: `configs/example_*.yaml` 의 지역. 결과 파일에 `synthetic_regions = 1` 로 표시된다.
- 감염병 매개변수는 모두 COVID 유사 **코드 검증용 가정**이다. 실제 추정치가 아니다 (2단계에서 보정).

## 구조
```
seir_sim/config     YAML 스키마, 시나리오 구성 (R0 -> c0 유도, 자료 역할 분리)
seir_sim/model      함수(P,T,f,phi,h,g), 매개변수, 상태, 지역, 외부 입력, 공통 사건 목록, R0 분석
seir_sim/simulate   ode, ctmc, tauleap, sde, hybrid (같은 사건 목록 사용)
seir_sim/data       registry, geo, boundaries, population, mobility, commuting, climate, dataset, build
seir_sim/ensemble   앙상블 실행기 (시드, 병렬, 통계, 저장)
seir_sim/viz        그림
seir_sim/inference, ml, forecast   2단계 이후 (미구현)
scripts/            자료 내려받기·만들기, 보고서 생성
configs/            예제 설정
docs/               MODEL, DECISIONS, DATA_SOURCES, PROGRESS, reports/
```
