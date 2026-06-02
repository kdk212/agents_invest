# PRISM-INSIGHT 어댑터 연결 가이드

## 목적

원본 PRISM-INSIGHT의 에이전트와 트리거는 유지하면서 `agents_invest`의 보완 모듈을 실제 코드 흐름에 연결한다.

이 문서는 원본 `dragon1086/prism-insight`의 현재 구조를 기준으로 한다.

## 1. `trigger_batch.py` 후보 점수화 연결

### 확인된 원본 구조

핵심 함수:

```python
def select_final_tickers(triggers: dict, trade_date: str = None, use_hybrid: bool = True, lookback_days: int = 10, macro_context: dict = None) -> dict:
```

원본 흐름:

1. 각 트리거 함수가 DataFrame을 반환한다.
2. `select_final_tickers()`가 트리거별 후보를 모은다.
3. `score_candidates_by_agent_criteria()`가 `agent_fit_score`, `risk_reward_ratio`, `stop_loss_pct`, `target_price`를 붙인다.
4. `final_score`로 정렬한다.
5. 최종 3개 종목을 선택한다.

### 추가 import

`trigger_batch.py` 상단 import 영역에 추가한다.

```python
from optimization import enrich_trigger_dataframe_with_profit_scores
```

만약 원본이 `prism-insight/` 하위 폴더에 있고 `optimization/`은 저장소 루트에 있다면, 실행 진입점에서 루트 경로가 `PYTHONPATH`에 포함되어야 한다.

### 연결 위치

`select_final_tickers()` 안에서 다음 블록을 찾는다.

```python
scored_df["final_score"] = (
    scored_df["composite_score_norm"] * w_comp +
    scored_df["agent_fit_score"] * w_agent +
    scored_df["rs_score"] * w_rs +
    scored_df["extension_score"] * w_ext
)

# Sort by final score
scored_df = scored_df.sort_values("final_score", ascending=False)
```

그 직후에 추가한다.

```python
scored_df = enrich_trigger_dataframe_with_profit_scores(
    scored_df,
    trigger_type=name,
    market_regime=_regime,
)
```

### 정렬 기준

원본은 아래처럼 선택 기준을 정한다.

```python
score_column = "final_score" if use_hybrid and trade_date else "composite_score"
```

수익 최적화 점수를 우선하려면 다음처럼 바꾼다.

```python
score_column = "profit_score" if use_hybrid and trade_date else "composite_score"
```

보수적으로는 `final_score`를 유지하고, `profit_score`는 tie-breaker로만 써도 된다. 다만 현재 `enrich_trigger_dataframe_with_profit_scores()`가 `profit_score`, `expected_value`, `final_score` 순으로 DataFrame을 정렬하므로, 실제 선택 품질을 강화하려면 `score_column = "profit_score"`가 더 명확하다.

### JSON 출력에 추가할 필드

`output_file` 저장부에서 `stock_info`에 다음 필드를 추가한다.

```python
if "profit_score" in stocks_df.columns:
    stock_info["profit_score"] = float(stocks_df.loc[ticker, "profit_score"])
if "expected_value" in stocks_df.columns:
    stock_info["expected_value"] = float(stocks_df.loc[ticker, "expected_value"])
if "risk_penalty" in stocks_df.columns:
    stock_info["risk_penalty"] = float(stocks_df.loc[ticker, "risk_penalty"])
if "profit_decision_hint" in stocks_df.columns:
    stock_info["profit_decision_hint"] = str(stocks_df.loc[ticker, "profit_decision_hint"])
```

## 2. `stock_tracking_agent.py` RiskGovernor 연결

### 확인된 원본 구조

핵심 함수:

```python
async def process_reports(self, pdf_report_paths: List[str]) -> Tuple[int, int]:
```

원본 흐름:

1. `_analyze_report_core()`가 report를 분석한다.
2. `_extract_trading_scenario()`가 Buy Specialist LLM 시나리오를 만든다.
3. 보유 여부, 슬롯 수, 섹터 분산을 확인한다.
4. `analysis_result["decision"] == "Enter"`이면 `buy_stock()`을 호출한다.
5. 실제 KIS 매수 주문을 실행한다.

### 추가 import

`stock_tracking_agent.py` 상단 import 영역에 추가한다.

```python
from optimization import apply_risk_governor_to_scenario
```

### 연결 위치

`process_reports()` 안에서 다음 블록을 찾는다.

```python
buy_score = scenario.get("buy_score", 0)
min_score = scenario.get("min_score", 0)
logger.info(f"Buy score check: {company_name}({ticker}) - Score: {buy_score}")

if analysis_result.get("decision") == "Enter":
    buy_success = await self.buy_stock(ticker, company_name, current_price, scenario, rank_change_msg)
```

`if analysis_result.get("decision") == "Enter":` 바로 전에 다음을 추가한다.

```python
trigger_info = getattr(self, "trigger_info_map", {}).get(ticker, {})
portfolio_context = {
    "holding_count": current_slots,
    "max_positions": self.max_slots,
    "same_sector_count": 0,
    "max_same_sector": self.MAX_SAME_SECTOR,
    "cash_pct": 0,
}
market_context = {
    "market_regime": scenario.get("market_condition", ""),
    "index_change_pct": scenario.get("index_change_pct", 0),
    "volatility_spike": scenario.get("volatility_spike", False),
    "risk_event_active": scenario.get("risk_event_active", False),
}
candidate_context = {
    "code": ticker,
    "name": company_name,
    "sector": sector,
    "trigger_type": trigger_info.get("trigger_type", ""),
    "historical_trigger_win_rate": scenario.get("historical_trigger_win_rate", 0),
    "historical_trigger_count": scenario.get("historical_trigger_count", 0),
}

scenario = apply_risk_governor_to_scenario(
    scenario=scenario,
    candidate=candidate_context,
    portfolio=portfolio_context,
    market=market_context,
)
analysis_result["scenario"] = scenario
analysis_result["decision"] = self._normalize_decision(scenario.get("decision", analysis_result.get("decision")))

if scenario.get("decision") == "no_entry":
    reason = "; ".join(scenario.get("risk_governor_reasons", [])) or "RiskGovernor blocked entry"
    logger.info(f"Purchase deferred by RiskGovernor: {company_name}({ticker}) - {reason}")
    state["should_save_watchlist"] = True
    state["skip_reason"] = state["skip_reason"] or reason
    continue
```

### 주의

`same_sector_count`, `cash_pct`, `index_change_pct`는 원본에 실제 계산값이 있으면 그 값으로 교체해야 한다. 초기에 값이 없으면 0으로 두되, RiskGovernor가 최소한 기대값, 손익비, 손실폭, 시장 급락 플래그를 기준으로 동작하게 한다.

## 3. Buy Specialist 프롬프트 보완

대상 파일:

```text
cores/agents/trading_agents.py
```

Buy Specialist 응답 JSON에 다음 필드를 요구한다.

```json
{
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

## 4. 테스트 순서

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/check_integration.py
python -m runtime.preflight --json
```

## 5. 권장 적용 순서

1. `trigger_batch.py`에 DataFrame 어댑터를 먼저 연결한다.
2. JSON 출력에 `profit_score`, `expected_value`를 추가한다.
3. 페이퍼 모드에서 후보 순위 변화를 확인한다.
4. `stock_tracking_agent.py`에 RiskGovernor를 연결한다.
5. RiskGovernor 차단 종목이 watchlist/history에 남는지 확인한다.
6. 최소 20거래일 이상 페이퍼트레이딩 후 live 전환 여부를 판단한다.
