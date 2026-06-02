"""Patch imported PRISM-INSIGHT files to use agents_invest adapters.

Usage:
    python scripts/patch_prism_adapters.py
    python scripts/patch_prism_adapters.py --check

This script expects upstream PRISM-INSIGHT to be imported under prism-insight/.
It is intentionally conservative: it searches for known upstream code anchors and
only inserts small adapter wiring blocks.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRIGGER_BATCH = ROOT / "prism-insight" / "trigger_batch.py"
STOCK_TRACKING = ROOT / "prism-insight" / "stock_tracking_agent.py"
TRADING_AGENTS = ROOT / "prism-insight" / "cores" / "agents" / "trading_agents.py"


@dataclass(frozen=True)
class PatchResult:
    path: str
    changed: bool
    message: str


TRIGGER_IMPORT = "from optimization import enrich_trigger_dataframe_with_profit_scores"
TRIGGER_PATCH = """\n                scored_df = enrich_trigger_dataframe_with_profit_scores(\n                    scored_df,\n                    trigger_type=name,\n                    market_regime=_regime,\n                )\n"""
TRIGGER_SORT_ANCHOR = """                # Sort by final score
                scored_df = scored_df.sort_values(\"final_score\", ascending=False)
"""
TRIGGER_SCORE_COLUMN_OLD = '    score_column = "final_score" if use_hybrid and trade_date else "composite_score"'
TRIGGER_SCORE_COLUMN_NEW = '    score_column = "profit_score" if use_hybrid and trade_date else "composite_score"'

STOCK_IMPORT = "from optimization import apply_risk_governor_to_scenario"
STOCK_ANCHOR = """                    if analysis_result.get(\"decision\") == \"Enter\":
                        buy_success = await self.buy_stock(ticker, company_name, current_price, scenario, rank_change_msg)
"""
STOCK_PATCH = """                    trigger_info = getattr(self, \"trigger_info_map\", {}).get(ticker, {})
                    portfolio_context = {
                        \"holding_count\": current_slots,
                        \"max_positions\": self.max_slots,
                        \"same_sector_count\": 0,
                        \"max_same_sector\": self.MAX_SAME_SECTOR,
                        \"cash_pct\": 0,
                    }
                    market_context = {
                        \"market_regime\": scenario.get(\"market_condition\", \"\"),
                        \"index_change_pct\": scenario.get(\"index_change_pct\", 0),
                        \"volatility_spike\": scenario.get(\"volatility_spike\", False),
                        \"risk_event_active\": scenario.get(\"risk_event_active\", False),
                    }
                    candidate_context = {
                        \"code\": ticker,
                        \"name\": company_name,
                        \"sector\": sector,
                        \"trigger_type\": trigger_info.get(\"trigger_type\", \"\"),
                        \"historical_trigger_win_rate\": scenario.get(\"historical_trigger_win_rate\", 0),
                        \"historical_trigger_count\": scenario.get(\"historical_trigger_count\", 0),
                    }
                    scenario = apply_risk_governor_to_scenario(
                        scenario=scenario,
                        candidate=candidate_context,
                        portfolio=portfolio_context,
                        market=market_context,
                    )
                    analysis_result[\"scenario\"] = scenario
                    analysis_result[\"decision\"] = self._normalize_decision(
                        scenario.get(\"decision\", analysis_result.get(\"decision\"))
                    )
                    if scenario.get(\"decision\") == \"no_entry\":
                        reason = \"; \".join(scenario.get(\"risk_governor_reasons\", [])) or \"RiskGovernor blocked entry\"
                        logger.info(f\"Purchase deferred by RiskGovernor: {company_name}({ticker}) - {reason}\")
                        state[\"should_save_watchlist\"] = True
                        state[\"skip_reason\"] = state[\"skip_reason\"] or reason
                        continue

                    if analysis_result.get(\"decision\") == \"Enter\":
                        buy_success = await self.buy_stock(ticker, company_name, current_price, scenario, rank_change_msg)
"""

PROFIT_ADDENDUM_MARKER = "## agents_invest Profit Optimization Addendum"
TRADING_AGENT_ADDENDUM_EN = """
        ## agents_invest Profit Optimization Addendum

        If the prompt includes `profit_score`, `expected_value`, `risk_penalty`,
        `trigger_historical_win_rate`, or `risk_governor_context`, use them as
        additional evidence without replacing the CAN SLIM framework.
        - Treat profit_score >= 70 and expected_value > 0 as supportive context.
        - Treat profit_score < 55, expected_value <= 0, or risk_penalty >= 25 as a
          serious warning that must be addressed in rejection_reason or rationale.
        - If trigger_historical_win_rate is available and below 40% after at least
          10 prior samples, require one extra confirmation before Enter.
        - Always include these output fields when possible: profit_score,
          expected_value, risk_penalty, risk_governor_context, no_entry_reasons,
          risk_controls.

"""
TRADING_AGENT_ADDENDUM_KO = """
        ## agents_invest Profit Optimization Addendum

        프롬프트에 `profit_score`, `expected_value`, `risk_penalty`,
        `trigger_historical_win_rate`, `risk_governor_context`가 주입되어 있다면
        CAN SLIM 프레임워크를 대체하지 말고 추가 근거로 사용하십시오.
        - profit_score >= 70 이고 expected_value > 0 이면 진입 판단의 보조 근거로 봅니다.
        - profit_score < 55, expected_value <= 0, risk_penalty >= 25 중 하나라도 있으면
          rejection_reason 또는 rationale에서 반드시 다뤄야 하는 경고로 봅니다.
        - trigger_historical_win_rate가 있고 과거 표본이 10건 이상이며 승률이 40% 미만이면
          진입 전 추가 확인 1개를 더 요구합니다.
        - 가능하면 출력 JSON에 profit_score, expected_value, risk_penalty,
          risk_governor_context, no_entry_reasons, risk_controls를 포함하십시오.

"""
TRADING_AGENT_ANCHORS = (
    ("        ## JSON Response Format\n", TRADING_AGENT_ADDENDUM_EN),
    ("        ## JSON 응답 형식\n", TRADING_AGENT_ADDENDUM_KO),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Patch imported PRISM-INSIGHT adapter wiring")
    parser.add_argument("--check", action="store_true", help="do not write files; fail if patches are not applied")
    args = parser.parse_args(argv)

    results = [
        patch_trigger_batch(check=args.check),
        patch_stock_tracking(check=args.check),
        patch_trading_agents(check=args.check),
    ]
    for result in results:
        status = "changed" if result.changed else "ok"
        print(f"{status}: {result.path} - {result.message}")

    if args.check and any(result.changed for result in results):
        return 2
    return 0


def patch_trigger_batch(check: bool = False) -> PatchResult:
    if not TRIGGER_BATCH.exists():
        return PatchResult(str(TRIGGER_BATCH), False, "missing; import upstream first")

    original = TRIGGER_BATCH.read_text(encoding="utf-8")
    text = original

    if TRIGGER_IMPORT not in text:
        text = text.replace("import logging\n", f"import logging\n{TRIGGER_IMPORT}\n", 1)

    if "enrich_trigger_dataframe_with_profit_scores(" not in text:
        if TRIGGER_SORT_ANCHOR not in text:
            raise RuntimeError("trigger_batch.py anchor not found for profit-score patch")
        text = text.replace(TRIGGER_SORT_ANCHOR, TRIGGER_SORT_ANCHOR + TRIGGER_PATCH, 1)

    if TRIGGER_SCORE_COLUMN_OLD in text:
        text = text.replace(TRIGGER_SCORE_COLUMN_OLD, TRIGGER_SCORE_COLUMN_NEW, 1)

    changed = text != original
    if changed and not check:
        TRIGGER_BATCH.write_text(text, encoding="utf-8", newline="")
    return PatchResult(str(TRIGGER_BATCH), changed, "profit scoring adapter wired" if changed else "already wired")


def patch_stock_tracking(check: bool = False) -> PatchResult:
    if not STOCK_TRACKING.exists():
        return PatchResult(str(STOCK_TRACKING), False, "missing; import upstream first")

    original = STOCK_TRACKING.read_text(encoding="utf-8")
    text = original

    if STOCK_IMPORT not in text:
        text = text.replace(
            "from cores.utils import parse_llm_json\n",
            f"from cores.utils import parse_llm_json\n{STOCK_IMPORT}\n",
            1,
        )

    if "apply_risk_governor_to_scenario(" not in text:
        if STOCK_ANCHOR not in text:
            raise RuntimeError("stock_tracking_agent.py anchor not found for risk-governor patch")
        text = text.replace(STOCK_ANCHOR, STOCK_PATCH, 1)

    changed = text != original
    if changed and not check:
        STOCK_TRACKING.write_text(text, encoding="utf-8", newline="")
    return PatchResult(str(STOCK_TRACKING), changed, "risk governor adapter wired" if changed else "already wired")


def patch_trading_agents(check: bool = False) -> PatchResult:
    if not TRADING_AGENTS.exists():
        return PatchResult(str(TRADING_AGENTS), False, "missing; import upstream first")

    original = TRADING_AGENTS.read_text(encoding="utf-8")
    text = original

    if PROFIT_ADDENDUM_MARKER not in text:
        for anchor, addendum in TRADING_AGENT_ANCHORS:
            if anchor not in text:
                raise RuntimeError(f"trading_agents.py anchor not found: {anchor.strip()}")
            text = text.replace(anchor, addendum + anchor, 1)

    changed = text != original
    if changed and not check:
        TRADING_AGENTS.write_text(text, encoding="utf-8", newline="")
    return PatchResult(str(TRADING_AGENTS), changed, "profit context prompt addendum wired" if changed else "already wired")


if __name__ == "__main__":
    raise SystemExit(main())
