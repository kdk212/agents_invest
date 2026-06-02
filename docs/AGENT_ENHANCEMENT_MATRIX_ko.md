# PRISM-INSIGHT 에이전트별 보완 매트릭스

이 문서는 `dragon1086/prism-insight`의 원본 에이전트를 유지하면서 `agents_invest`가 어떤 보완 신호를 추가하는지 정리합니다.

원칙은 세 가지입니다.

1. 원본 에이전트의 역할과 프롬프트를 대체하지 않습니다.
2. 수익 기대값, 리스크, 과거 성과 신호를 보조 근거로 추가합니다.
3. 실계좌 주문 직전에는 LLM 판단보다 RiskGovernor를 우선합니다.

## 전체 흐름

```text
Trigger Batch
  -> ProfitScoringEngine
  -> Analysis Agents
  -> Strategy / Buy Specialist
  -> RiskGovernor
  -> Paper or Live Execution
  -> Journal / Performance Tracker
  -> PaperTradingValidator
```

## 에이전트/팀별 보완

| 원본 팀 | 원본 역할 | 그대로 유지 | agents_invest 보완 | 적용 위치 |
|---|---|---|---|---|
| 거시경제 팀 | 시장 국면, 섹터 로테이션, 리스크 이벤트 | 시장 체제 판단과 섹터 리더 분석 | 시장 국면을 `ProfitScoringEngine`과 `RiskGovernor`의 가중치/차단 조건에 반영 | `optimization/profit_scoring.py`, `optimization/risk_governor.py` |
| 분석 팀 | 기술적, 재무, 산업, 뉴스, 시장 분석 | 보고서 생성과 CAN SLIM 근거 생산 | 분석 결과를 수익 기대값 입력값으로 정규화하고, 과열/유동성/손실폭 페널티 추가 | `optimization/adapters.py` |
| 전략 팀 | 투자 전략 수립 | 기존 전략 판단 | `profit_score`, `expected_value`, `risk_penalty`, 과거 트리거 승률을 추가 판단 근거로 제공 | `scripts/patch_prism_adapters.py` -> `trading_agents.py` |
| 커뮤니케이션 팀 | 요약, 품질 평가, 번역 | 리포트/메시지 품질 유지 | 실계좌 전환 전 검증 상태, 킬스위치, 리스크 차단 사유를 로그/알림에 포함할 수 있도록 구조화 | `runtime/preflight.py`, `agents_invest_runner.py` |
| 매매 팀 - Buy Specialist | 진입/미진입, 목표가, 손절가, 포트폴리오 문맥 | CAN SLIM 기반 진입 판단 | JSON 출력에 `profit_score`, `expected_value`, `risk_governor_context`, `no_entry_reasons`, `risk_controls`를 요구 | `patch_trading_agents()` |
| 매매 팀 - Sell Specialist | 보유/전량매도, 손절, trailing stop | 원본 매도 원칙 유지 | RiskGovernor와 일일 손실 한도, 킬스위치를 상위 안전장치로 둠 | `runtime/safety.py`, 향후 sell adapter |
| 매매 팀 - Journal | 매매 기록과 피드백 루프 | 원본 journal/intuition 활용 | 매수하지 않은 후보의 후행 성과까지 기록할 수 있는 스키마 추가 | `db/candidate_performance_tracker.sql` |
| 상담/텔레그램 팀 | 사용자 상호작용과 알림 | 원본 Telegram 흐름 유지 | AWS Kill Switch, preflight 실패, RiskGovernor 차단 사유를 알림 대상으로 확장 가능 | `docs/AWS_24H_OPERATION_ko.md` |

## 자동 패치 대상

`scripts/patch_prism_adapters.py`는 PRISM-INSIGHT 원본이 `prism-insight/` 하위 폴더에 들어온 뒤 다음 파일을 보수적으로 패치합니다.

| 파일 | 보완 내용 |
|---|---|
| `prism-insight/trigger_batch.py` | 최종 후보 DataFrame에 `profit_score`, `expected_value`, `risk_penalty`를 추가하고 정렬 기준에 반영 |
| `prism-insight/stock_tracking_agent.py` | 실제 매수 직전 `RiskGovernor`를 호출해 주문을 차단할 수 있게 함 |
| `prism-insight/cores/agents/trading_agents.py` | Buy Specialist 프롬프트에 Profit Optimization Addendum을 삽입 |

패치 확인:

```bash
python scripts/patch_prism_adapters.py --check
```

## AWS 콘솔에서 사용자가 설정해야 하는 것

현재 필요한 AWS 콘솔 설정은 다음입니다.

1. EC2 인스턴스
   - Region: `ap-southeast-2`
   - Ubuntu LTS
   - `t3.small` 이상
   - SSH는 본인 IP만 허용

2. IAM Role
   - EC2에 `deploy/aws/iam_policy_agents_invest_runtime.json` 기준 권한 연결
   - SSM 기본값을 만들 때만 `deploy/aws/iam_policy_agents_invest_setup.json` 기준 권한 사용

3. Systems Manager Parameter Store
   - `deploy/aws/put_default_parameters.sh`로 기본값 생성
   - SecureString의 `CHANGE_ME`를 실제 값으로 교체
   - 반드시 확인할 값:

```text
/agents-invest/kill-switch=false
/agents-invest/trading-mode=paper
/agents-invest/paper-validation-approved=false
/agents-invest/max-daily-loss-pct=3.0
/agents-invest/max-positions=10
/agents-invest/max-sector-weight-pct=30.0
```

4. 실계좌 전환 전 필수 조건

```text
APP_ENV=production
TRADING_MODE=live
PAPER_VALIDATION_APPROVED=true
KILL_SWITCH=false
ENABLE_SSM_SETTINGS=true
```

Parameter Store 기준으로는 다음이 충족되어야 합니다.

```text
/agents-invest/trading-mode=live
/agents-invest/paper-validation-approved=true
/agents-invest/kill-switch=false
```

## 아직 남은 실제 완성 작업

- GitHub Actions에서 `integrate-prism-insight` 워크플로를 실행해 원본을 실제 하위 폴더로 병합
- 자동 패치가 최신 원본에 정상 적용되는지 CI로 확인
- 페이퍼트레이딩 최소 표본을 쌓고 `PaperTradingValidator`로 검증
- Telegram 알림과 CloudWatch 로그 연결
- 실계좌 주문은 위 조건을 모두 만족한 뒤 검토
