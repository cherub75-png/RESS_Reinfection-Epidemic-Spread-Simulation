# Epidemic-Spread-Simulation_Claude-Code

전 세계 재감염 SEIR 전파 예측 시뮬레이터. 수학 기준은 작업 지시서 1절이고, 구현 해석은 `docs/MODEL.md` 에 기록한다.

## 진행 상태
| 단계 | 내용 | 상태 |
|---|---|---|
| 1-A | 골격, 설정, 매개변수, 공통 사건 목록, R0 분석 | 완료 |
| 1-B | ODE 적분기와 검증 (`docs/reports/1B_ode_validation.md`) | 완료 |
| 1-C | CTMC / tau-leaping / SDE / hybrid | 예정 |
| 1-D | 데이터 전처리 (GPW, Natural Earth, WorldClim, OpenFlights, radiation) | 예정 |
| 1-E | 앙상블 실행기, CLI, 예제 그림 | 예정 |

## 실행
```bash
pip install -e ".[test]"        # 의존성: numpy, scipy, pydantic, PyYAML (+ pytest)
python -m pytest                # 테스트
python scripts/record_environment.py   # env/ 에 실행 환경 기록
python scripts/report_1B.py            # 1-B 검증 보고서 (약 35초)
```

## 구조
```
seir_sim/config     YAML 스키마, 시나리오 구성 (R0 -> c0 유도 포함)
seir_sim/model      functions(P,T,f,phi,h,g) params state regions drivers reactions analysis
seir_sim/simulate   적분기 (1-B, 1-C)
seir_sim/data       데이터 계층 (1-D)
seir_sim/ensemble   앙상블 (1-E)
seir_sim/viz        그림 (1-E)
seir_sim/inference  매개변수 추정 (2단계)
seir_sim/ml         머신러닝 보정 (2단계)
seir_sim/forecast   최신 자료 예측 (최종 단계)
configs/            예제 설정 (현재는 합성 자료만)
docs/MODEL.md       수학 해석·유도 노트
env/                실행 환경과 패키지 버전 기록
```

예제의 감염병 값은 COVID 유사 **코드 검증용 가정**이다. 예제의 지역은 **합성 자료**다.
