# 진행 기록

마지막 갱신: 1-C 2b 진행 중 (자율 진행)

## 완료 (테스트로 검증됨)
- 1-A 골격, 설정, 매개변수, 공통 사건 목록, R0 분석
- 1-B ODE 와 검증 (`docs/reports/1B_ode_validation.md`)
- 1-C CTMC (`docs/reports/1C_ctmc.md`), 이동 사건 합치기, 이항 tau-leaping (`docs/reports/1C_tau.md`)
- 1-C 2b SDE: flow_limit 음수 처리 (DECISIONS D-004)

## 진행 중 / 남음
- [ ] 1-C 2b 하이브리드 (CTMC + 이항 tau-leap), 전환 구간 검증
- [ ] 1-C 2b 모형 비교 보고서
- [ ] 1-D 범용 데이터 파이프라인 (자료 서버 차단: DECISIONS D-006)
- [ ] 1-E 앙상블 실행기, CLI, 예제 그림
- [ ] 1단계 최종 보고

## 알려진 한계
- 200지역(국가 규모) tau-leaping 은 1회 815초 (조밀한 합성 이동망 기준). 희소한 실제 이동망에서 다시 측정해야 한다.
- 모든 예제 지역은 합성 자료다. 실제 지역 자료는 아직 없다.
