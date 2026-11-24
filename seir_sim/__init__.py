"""전 세계 재감염 SEIR 전파 예측 시뮬레이터.

모듈 구성 (단계)
  config     설정 스키마와 시나리오 구성                         1-A
  model      매개변수, 함수, 상태 배치, 공통 사건 목록, R0 분석   1-A
  simulate   ODE / SDE / CTMC / tau-leaping / hybrid 적분기       1-B, 1-C
  data       인구·경계·기후·이동 전처리와 출처 기록                1-D
  ensemble   앙상블 실행, 시드 기록, 병렬화, 저장                 1-E
  viz        그림                                                  1-E
  inference  매개변수 추정 (관측 모형, 입자 필터, ABC)             2단계
  ml         머신러닝 보정 (함수 학습, 대리모형)                   2단계
  forecast   최신 자료 기반 예측                                   최종 단계
"""

__version__ = "0.1.0"
