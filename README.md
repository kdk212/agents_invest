# agents_invest

PRISM-INSIGHT 기반 수익 최적화 보완 작업 저장소입니다.

## 목표

`dragon1086/prism-insight`의 기존 에이전트를 최대한 그대로 활용하되, 다음 보완 계층을 추가해 실전 운영 전 검증 가능한 투자 자동화 구조를 만듭니다.

- 후보 종목 수익 기대값 점수화
- 매수 전 리스크 차단
- 페이퍼트레이딩 검증
- 트리거/섹터/에이전트별 성과 피드백
- 24시간 운영을 위한 AWS 배포 준비

## 현재 포함된 모듈

- `optimization/profit_scoring.py`: 후보 종목 점수화 엔진
- `optimization/risk_governor.py`: 매수 직전 리스크 게이트
- `optimization/paper_validator.py`: 페이퍼트레이딩 실계좌 전환 검증
- `tests/test_optimization_modules.py`: 대표 의사결정 테스트
- `docs/`: PRISM-INSIGHT 연결 설계와 구현 지도

## 적용 방향

1. PRISM-INSIGHT 원본을 별도 작업 경로에 준비합니다.
2. 이 저장소의 `optimization/` 폴더를 PRISM-INSIGHT 루트에 복사합니다.
3. `trigger_batch.py`에 `ProfitScoringEngine`을 연결합니다.
4. `stock_tracking_agent.py`의 주문 실행 직전에 `RiskGovernor`를 연결합니다.
5. 페이퍼트레이딩 결과를 `PaperTradingValidator`로 검증합니다.
6. 검증 기준을 통과한 뒤 AWS에서 24시간 운영 구조를 구성합니다.

## 주의

수익은 보장할 수 없습니다. 실계좌 자동매매는 충분한 페이퍼트레이딩, 손실 한도, 모니터링, 비상 정지 장치가 준비된 뒤에만 켜야 합니다.

PRISM-INSIGHT는 AGPL-3.0 및 상업 라이선스 조건이 있으므로, 외부 제공 서비스나 SaaS 형태로 운영할 경우 원저작자 라이선스 조건을 별도로 확인해야 합니다.
