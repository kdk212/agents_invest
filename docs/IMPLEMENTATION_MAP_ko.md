# PRISM-INSIGHT 보완 구현 지도

## 목표

`dragon1086/prism-insight`의 기존 에이전트를 유지하면서 수익 기대값, 리스크 제어, 페이퍼트레이딩 검증, 성과 피드백을 추가한다.

에이전트별 상세 보완 방향은 [PRISM-INSIGHT 에이전트별 보완 매트릭스](AGENT_ENHANCEMENT_MATRIX_ko.md)를 기준으로 한다.

## 핵심 연결 지점

```text
trigger_batch.py
  -> PerformanceFeedbackEngine
  -> ProfitScoringEngine
  -> stock_analysis_orchestrator.py
  -> cores/agents/trading_agents.py
  -> stock_tracking_agent.py
  -> RiskGovernor
  -> trading / KIS order execution
  -> tracking/journal.py
  -> candidate_performance_tracker
  -> PaperTradingValidator
```

## 1. `trigger_batch.py`

후보 종목이 만들어진 직후 `optimization.profit_scoring.ProfitScoringEngine`을 호출한다. paper/live 성과 기록이 있으면 `optimization.performance_feedback.PerformanceFeedbackEngine`이 먼저 과거 트리거/섹터/종목 성과를 보조 점수로 변환한다.

추가 필드:

- `profit_score`
- `risk_penalty`
- `expected_value`
- `decision_hint`
- `score_reasons`
- `historical_trigger_edge`
- `historical_sector_edge`
- `historical_ticker_edge`
- `performance_feedback_warnings`

최종 후보 정렬에는 기존 점수와 `profit_score`를 함께 사용한다.

자동 패치:

```bash
python scripts/patch_prism_adapters.py
python scripts/patch_prism_adapters.py --check
```

## 2. `cores/agents/trading_agents.py`

Buy Specialist 프롬프트는 원본 CAN SLIM 프레임워크를 유지한다. 여기에 작은 Profit Optimization Addendum만 삽입한다.

추가 판단 컨텍스트:

- `profit_score`
- `expected_value`
- `risk_penalty`
- `risk_governor_context`
- `trigger_historical_win_rate`
- `historical_trigger_count`
- `performance_feedback_warnings`

응답 JSON 권장 필드:

```json
{
  "decision": "entry | no_entry",
  "buy_score": 0,
  "expected_return_pct": 0,
  "expected_loss_pct": 0,
  "expected_value": 0,
  "profit_score": 0,
  "risk_penalty": 0,
  "risk_reward_ratio": 0,
  "position_weight_pct": 0,
  "risk_governor_context": {},
  "no_entry_reasons": [],
  "risk_controls": []
}
```

## 3. `stock_tracking_agent.py`

Buy Specialist가 매수 시나리오를 만든 뒤, 실제 주문 전 `optimization.risk_governor.RiskGovernor`를 호출한다.

차단 조건 예시:

- 최대 보유 종목 수 초과
- 같은 섹터 집중 초과
- 일일 손실 한도 도달
- 시장 급락일 신규매수
- 기대값 음수
- 손익비 미달
- 동일 트리거 과거 승률 부진
- 동일 종목 반복 손실

`approved=False`이면 주문을 실행하지 않고 `scenario["decision"] = "no_entry"`로 저장한다.

## 4. `tracking/journal.py`와 성과 피드백

매수하지 않은 후보의 후행 성과도 기록한다. 기록된 결과는 다음 후보 점수화의 보조 신호로 다시 들어간다.

추가 지표:

- 7일 수익률
- 14일 수익률
- 30일 수익률
- 30일 최고수익
- 30일 최대낙폭
- 트리거별 승률
- 트리거별 평균 수익
- 섹터별 평균 수익
- 종목별 반복 손실
- 매수 후보와 관망 후보의 성과 차이

현재 저장소에는 이를 위한 `db/candidate_performance_tracker.sql` 스키마와 `optimization/performance_feedback.py` 피드백 엔진이 포함되어 있다.

## 5. 실계좌 전환 기준

`optimization.paper_validator.PaperTradingValidator`로 최소 기준을 통과해야 한다.

기본 기준:

- 거래 수 30건 이상
- 승률 45% 이상
- 기대값 0.5% 이상
- MDD 15% 이하
- Profit Factor 1.2 이상
- 특정 섹터/트리거 의존도 55% 이하

## AWS 24시간 운영 방향

초기 권장 구조:

- AWS 리전: `ap-southeast-2`
- 실행 방식: EC2 paper 모드
- 비밀값: SSM Parameter Store SecureString
- 운영값: `/agents-invest/*` Parameter Store
- 로그: systemd journal, 이후 CloudWatch Logs
- 알림: Telegram + CloudWatch Alarm
- 비상정지: `/agents-invest/kill-switch=true`

실계좌 자동매매는 페이퍼트레이딩 검증 통과 후에만 켠다.
