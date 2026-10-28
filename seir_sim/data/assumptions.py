"""가정값 목록 (자료가 아님). 웹 화면·문서가 같은 목록을 쓴다. 근거·불확실성은 docs/DATA_SOURCES.md 끝 절."""

ASSUMPTIONS = [
    {"name": "국가 간 항공 이동", "value": "5e6 회/일", "where": "전 세계 데이터셋 (--air-trips-per-day)",
     "basis": "확인한 승객 자료 없음. 크기 정도만 맞춘 가정", "uncertainty": "큼 (2배 이상)"},
    {"name": "국가 간 통근 비율", "value": "0.002", "where": "전 세계 데이터셋 (--commute-fraction)",
     "basis": "국경 통근 자료 미확보", "uncertainty": "큼"},
    {"name": "목적지 접촉 비율", "value": "0.3", "where": "전 세계·시도 데이터셋 (--contact-share)",
     "basis": "통근자 접촉 중 목적지 비율, 자료 없음", "uncertainty": "큼"},
    {"name": "국내 항공 이동 (대한민국)", "value": "9e4 회/일", "where": "시도 데이터셋",
     "basis": "국내선 승객 통계 미확보", "uncertainty": "중간"},
    {"name": "시도 간 통근 비율 (대한민국)", "value": "0.05", "where": "시도 데이터셋",
     "basis": "KOSIS 통근 자료 차단으로 미확보", "uncertainty": "큼"},
    {"name": "보고율 rho", "value": "0.5", "where": "3·5단계 추정", "basis": "자료로 식별 안 됨 (D-011)",
     "uncertainty": "큼 (0.2~1.0 이 같은 적합)"},
    {"name": "R0_max", "value": "6", "where": "3·5단계 추정", "basis": "u = 0 기준값, R_t 상한 (D-012)",
     "uncertainty": "상한에 닿으면 경고"},
    {"name": "감염병 매개변수 (σ, γ, P, T, f, λ, M)", "value": "COVID 유사 값", "where": "엔진·추정",
     "basis": "코드 검증용 가정, 실제 COVID-19 추정치 아님", "uncertainty": "알 수 없음"},
    {"name": "환경 보정 g", "value": "1 (neutral_default)", "where": "엔진",
     "basis": "기후 효과를 추정하지 않음. '효과 없음' 이라는 추정 결과가 아님", "uncertainty": "-"},
]
