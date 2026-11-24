# Epidemic-Spread-Simulation_Claude-Code

전 세계 재감염 SEIR 전파 시뮬레이터. 재감염을 포함한 SEIR 방정식(작업 지시서 1절)을 ODE, SDE, CTMC, tau-leaping, 하이브리드로 풀고, 실제 COVID-19 자료로 개입 효과 u(t)와 관측 매개변수를 추정하며, 과거 자료로 시간순 예측 성능을 검증한다. 로컬 웹 화면을 제공한다.

- 수학 기준은 작업 지시서 1절이다. 구현 해석과 유도: `docs/MODEL.md`
- 특정 국가 전용 코드는 없다. 같은 파이프라인이 전 세계 국가 단위와 한 나라의 1급 행정구역을 만든다.
- 감염병 매개변수는 COVID 유사 **코드 검증용 가정값**이다. 실제 자료로 추정한 것은 u(t), 초기 감염, 보고 지연·과산포·치명률 배율이다.
- **설치 없이 쓰는 사이트(브라우저 계산판)**: `site/` (`python -I scripts/build_static_site.py` 로 만들어 게시, D-028).
- 사용법: `docs/USER_GUIDE.md`. 검증 결과: `docs/VALIDATION_REPORT.md`. 단계 현황: `docs/PROJECT_ROADMAP.md`. **짧은 요약: `docs/SUMMARY_REPORT.md`**.
- 인플루엔자: WHO FluNet 주간 양성률의 시간순 검증과 최신 자료 예측 (`docs/reports/11_influenza_validation.md`).
- 지역 자료 기본값은 확보한 최신판 (시도 경계 통계청 SGIS 2026-10, WorldPop 2025, World Bank 2025, ERA5 2025-07 ~ 2026-06). 다른 시기를 고를 수 있다.

## 빠른 시작
```bash
pip install -e ".[test,web]"
python -m pytest                        # 단위·통합·API 테스트
python -m seir_sim.web                  # 로컬 웹 화면 http://127.0.0.1:8765
python -m seir_sim run configs/example_single_region.yaml --out outputs/single --method hybrid --runs 100
```
실제 자료 내려받기와 데이터셋 만들기: `docs/USER_GUIDE.md` 2절. 배포용 압축본(커밋된 내용 + 브랜치·커밋 정보): `python -I scripts/make_release.py`.

## 결과 구분
| 종류 | 뜻 |
|---|---|
| 실제 관측 자료 | `data_raw/` 원자료 (출처·SHA-256: `docs/DATA_SOURCES.md`) |
| 2차 자료 | 원출처가 기록되지 않은 집계 (예: 대한민국 시도 인구, Google Open Data) — 등급 secondary |
| 가정값 | 항공 이동 규모, 통근 비율, 접촉 비율, 보고율, 감염병 매개변수 (`seir_sim/data/assumptions.py`) |
| 추정값 | 3단계 추정 결과 (`docs/reports/3_calibration.md`) |
| 예측값 | 5단계·최신 자료 예측 (검증은 기점 뒤 실제 관측으로만) |
| 합성 자료 | 테스트·추정기 검증 전용 (`synthetic` 표시) |

## 구조
```
seir_sim/config       YAML 스키마, 시나리오 구성 (R0 -> c0, 기준 지역, 자료 역할 분리)
seir_sim/model        함수(P,T,f,phi,h,g), 매개변수, 상태, 지역, 외부 입력, 공통 사건 목록, R0 분석
seir_sim/simulate     ode, ctmc, tauleap, sde, hybrid (같은 사건 목록)
seir_sim/data         경계, 인구(표·격자), 이동, 통근, 기후, 데이터셋, 버전 관리(registry)
seir_sim/surveillance 감시 자료 로더, 품질 점검, 관측 구간
seir_sim/inference    추정용 적분기, 관측 모형, 벌점 우도 추정, 엔진 설정 내보내기
seir_sim/forecast     예측 대상, 지표, 기준 모델, SEIR 순차 재추정, 최신 자료 예측
seir_sim/ml           특성 (누설 검사), 국가 공통 분위수 GBM, SEIR 잔차 보정
seir_sim/ensemble     앙상블 실행기 (시드, 병렬, 진행률·취소, 저장)
seir_sim/web          로컬 웹 애플리케이션 (FastAPI + 정적 화면)
scripts/              자료 내려받기·만들기, 보고서 생성
configs/              예제·보정 설정
docs/                 MODEL, DECISIONS, DATA_SOURCES, PROGRESS, PROJECT_ROADMAP, USER_GUIDE, VALIDATION_REPORT, reports/
tests/                pytest, tests/ui (Playwright 화면 시험)
```

## 이 환경의 자료 제약
처음에는 WHO, KDCA, KOSIS, WorldPop, WorldClim 등이 네트워크 정책으로 막혀 있었다. 2026-11 사용자가 도메인을 허용해 WHO FluNet, WorldPop, World Bank API 를 받았다. API 키가 필요한 KOSIS·공공데이터포털·기상청은 키가 없어 쓰지 않았다. 받지 못한 자료는 "미확보" 로 기록했고 임의 값으로 채우지 않았다. 해결 방법: `docs/DECISIONS.md` D-006, 로컬 파일 입력 경로(`--population-table`, `--climate-table`, 웹 "데이터 관리").
