# PRISM-INSIGHT 어댑터 연결 가이드

## 목적

원본 PRISM-INSIGHT의 에이전트와 트리거는 유지하면서 `agents_invest`의 수익 최적화 보완 모듈을 실제 코드 흐름에 연결합니다.

자동 연결은 우선 `python scripts/patch_prism_adapters.py`로 시도합니다. 자동 패치가 실패하면 이 문서를 기준으로 같은 위치에 수동 연결합니다.

## 자동 패치 대상

현재 자동 패치는 원본 `prism-insight/` 아래의 세 파일을 보강합니다.

- `trigger_batch.py`: 후보 종목 DataFrame에 `profit_score`, `expected_value`, `risk_penalty`를 붙이고 정렬 기준과 JSON 출력에 반영
- `stock_tracking_agent.py`: trigger JSON의 수익 컨텍스트를 Buy Specialist 프롬프트와 최종 RiskGovernor에 전달하고, 매수 직전 차단 후보를 주문으로 보내지 않음
- `cores/agents/trading_agents.py`: Buy Specialist 프롬프트에 수익 기대값, 과거 트리거 성과, 위험 제어 컨텍스트 추가

확인만 할 때:

```bash
python scripts/patch_prism_adapters.py --check
```

실제 반영할 때:

```bash
python scripts/patch_prism_adapters.py
python scripts/check_integration.py
```

## 1. `trigger_batch.py` 후보 점수화 연결

추가 import:

```python
from optimization import enrich_trigger_dataframe_with_profit_scores
```

`select_final_tickers()` 안에서 원본이 `final_score`를 계산하고 정렬한 직후에 추가합니다.

```python
scored_df = enrich_trigger_dataframe_with_profit_scores(
    scored_df,
    trigger_type=name,
    market_regime=_regime,
)
```

하이브리드 선택 기준은 수익 최적화 점수를 우선하도록 바꿉니다.

```python
score_column = "profit_score" if use_hybrid and trade_date else "composite_score"
```

그리고 `output_file` JSON 저장부의 `stock_info`에도 다음 필드를 포함합니다.

```python
stock_info["profit_score"] = float(stocks_df.loc[ticker, "profit_score"])
stock_info["expected_value"] = float(stocks_df.loc[ticker, "expected_value"])
stock_info["risk_penalty"] = float(stocks_df.loc[ticker, "risk_penalty"])
stock_info["profit_decision_hint"] = str(stocks_df.loc[ticker, "profit_decision_hint"])
stock_info["profit_score_reasons"] = str(stocks_df.loc[ticker, "profit_score_reasons"])
```

이 연결은 원본 트리거 로직을 지우지 않습니다. 기존 점수에 기대수익, 손실위험, 과거 트리거 성과를 추가로 반영하고, 그 결과를 다음 단계의 tracking agent가 읽을 수 있게 넘깁니다.

## 2. `stock_tracking_agent.py` RiskGovernor 연결

추가 import:

```python
from optimization import apply_risk_governor_to_scenario
```

`trigger_results_file`을 읽을 때 `profit_score`, `expected_value`, `risk_penalty`, `profit_decision_hint`, `profit_score_reasons`를 `trigger_info_map`에 보관합니다. `_extract_trading_scenario()`는 이 값을 `agents_invest Profit Context`로 Buy Specialist 프롬프트에 넣고, `_analyze_report_core()`는 LLM 시나리오에 `trigger_profit_context`로 병합합니다.

그 다음 `analysis_result["decision"] == "Enter"`로 매수하기 직전에 `scenario`를 RiskGovernor에 통과시킵니다.

```python
scenario = apply_risk_governor_to_scenario(
    scenario=scenario,
    candidate=candidate_context,
    portfolio=portfolio_context,
    market=market_context,
)
analysis_result["scenario"] = scenario
analysis_result["decision"] = self._normalize_decision(
    scenario.get("decision", analysis_result.get("decision"))
)

if scenario.get("decision") == "no_entry":
    reason = "; ".join(scenario.get("risk_governor_reasons", [])) or "RiskGovernor blocked entry"
    logger.info(f"Purchase deferred by RiskGovernor: {company_name}({ticker}) - {reason}")
    state["should_save_watchlist"] = True
    state["skip_reason"] = state["skip_reason"] or reason
    continue
```

초기에는 `same_sector_count`, `cash_pct`, `index_change_pct`를 보수적인 기본값으로 넣어도 됩니다. 원본 코드에서 실제 계산값을 찾으면 그 값으로 교체합니다.

## 3. Buy Specialist 프롬프트 보완

대상 파일:

```text
prism-insight/cores/agents/trading_agents.py
```

원본 Buy Specialist는 CAN SLIM 기반 판단을 유지합니다. 여기에 `agents_invest Profit Optimization Addendum`을 추가해 다음 정보를 보조 판단 근거로 쓰게 합니다.

- `profit_score`
- `expected_value`
- `risk_penalty`
- `trigger_historical_win_rate`
- `risk_governor_context`

권장 판단 규칙:

- `profit_score >= 70`이고 `expected_value > 0`이면 매수 근거로 우호적입니다.
- `profit_score < 55`, `expected_value <= 0`, `risk_penalty >= 25` 중 하나라도 있으면 보수적으로 판단합니다.
- 과거 트리거 승률이 40% 미만이고 표본이 10건 이상이면 추가 확인 근거가 필요합니다.
- RiskGovernor가 차단한 후보는 Buy Specialist가 긍정적으로 보더라도 진입하지 않습니다.

Buy Specialist JSON 응답에는 다음 필드를 추가로 요구합니다.

```json
{
  "expected_value": 0,
  "profit_score": 0,
  "risk_penalty": 0,
  "risk_governor_context": {},
  "no_entry_reasons": [],
  "risk_controls": []
}
```

## 4. 테스트 순서

원본을 붙이기 전 저장소 준비상태 확인:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/check_integration.py --allow-missing-upstream
python -m runtime.preflight --json
```

원본 PRISM-INSIGHT를 붙이고 자동 패치를 적용한 뒤 최종 확인:

```bash
python scripts/patch_prism_adapters.py
python scripts/check_integration.py
python scripts/patch_prism_adapters.py --check
python -m pytest -q
python -m runtime.preflight --json
```

## 5. 권장 적용 순서

1. GitHub Actions의 `integrate-prism-insight` 워크플로로 원본을 `prism-insight/`에 가져옵니다.
2. 자동 패치가 세 파일에 적용됐는지 확인합니다.
3. `trigger_batch.py` 후보 순위가 `profit_score` 기준으로 변했고 JSON에도 수익 필드가 저장되는지 확인합니다.
4. `stock_tracking_agent.py`에서 Buy Specialist가 `agents_invest Profit Context`를 받는지 확인합니다.
5. RiskGovernor 차단 후보가 실제 주문으로 가지 않는지 paper 모드에서 확인합니다.
6. 최소 20거래일 이상 paper 검증 후 live 전환 여부를 판단합니다.
