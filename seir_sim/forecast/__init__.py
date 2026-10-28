"""시간순 예측 검증 (5단계).

- targets: 주간 합 예측 대상, 기점(origin) 이전 자료만 쓰는 이력
- metrics: MAE, RMSE, MASE, WIS, CRPS, 구간 포함률·폭, 정점 지표
- baselines: 지속 예측, 52주 계절 단순 예측, 감쇠 로그 추세
- seir: 보정 SEIR 의 기점별 순차 재추정과 예측 분포
- evaluate: 방법 비교 표 (같은 기점·대상 집합에서만 비교)
"""
