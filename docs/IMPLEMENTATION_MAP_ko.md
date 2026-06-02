# PRISM-INSIGHT 보완 구현 지도

## 목표

`dragon1086/prism-insight`의 기존 에이전트를 유지하면서 수익 기대값, 리스크 제어, 페이퍼트레이딩 검증을 추가한다.

## 핵심 연결 지점

```text
trigger_batch.py
  -> ProfitScoringEngine
  -> stock_analysis_orchestrator.py
  -> cores/agents/trading_agents.py
  -> stock_tracking_agent.py
  -> RiskGovernor
  -> trading / KIS order execution
  -> tracking/journal.py
  -> PaperTradingValidator
```

## 1. `trigger_batch.py`

후보 종목이 만들어진 직후 `optimization.profit_scoring.ProfitScoringEngine`을 호출한다.

추가 필드:

- `profit_score`
- `risk_penalty`
- `expected_value`
- `decision_hint`
- `score_reasons`

최종 후보 정렬에는 기존 점수와 `profit_score`를 함께 사용한다.

## 2. `stock_tracking_agent.py`

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

## 3. `cores/agents/trading_agents.py`

Buy Specialist 프롬프트에 다음 문맥을 추가한다.

- Profit Score
- Expected Value
- Risk Governor Context
- Trigger Historical Win Rate
- Same Stock Recent Losses
- Market Regime Adjusted Minimum Score

응답 JSON에는 다음 필드를 권장한다.

```json
{
  "decision": "entry | no_entry",
  "buy_score": 0,
  "expected_return_pct": 0,
  "expected_loss_pct": 0,
  "expected_value": 0,
  "profit_score": 0,
  "risk_reward_ratio": 0,
  "position_weight_pct": 0,
  "no_entry_reasons": [],
  "risk_controls": []
}
```

## 4. `tracking/journal.py`

매수하지 않은 후보의 후행 성과도 기록한다.

추가 지표:

- 7일 수익률
- 14일 수익률
- 30일 수익률
- 30일 최고수익
- 30일 최대낙폭
- 트리거별 승률
- 트리거별 평균 수익
- 매수 후보와 관망 후보의 성과 차이

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
- 실행 방식: EC2 또는 ECS/Fargate
- 비밀값: AWS Secrets Manager 또는 SSM Parameter Store
- 로그: CloudWatch Logs
- 알림: Telegram + CloudWatch Alarm
- 스케줄: EventBridge 또는 상시 실행 프로세스
- 비상정지: 환경변수 또는 Parameter Store의 kill switch

실계좌 자동매매는 페이퍼트레이딩 검증 통과 후에만 켠다.
