"""머신러닝 예측과 SEIR 잔차 보정 (4단계).

- features: 기점 이전 자료만으로 만든 특성 (누설 검사 포함)
- quantile: 국가 공통(전 세계) 분위수 GBM
- hybrid: SEIR 예측 + ML 잔차 분위수 보정
방정식 구조는 바꾸지 않는다. 학습된 h, g, phi 함수 등록(model.functions 레지스트리)은 실제 공간 자료가 확보된 뒤의 과제다.
"""
