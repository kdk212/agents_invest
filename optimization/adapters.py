"""Adapters that connect PRISM-INSIGHT dictionaries to optimization modules.

The upstream project frequently passes stock candidates and trading scenarios as
plain dictionaries. These helpers keep the optimization modules independent from
upstream internals while making integration straightforward.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Mapping

from .profit_scoring import ProfitScoreInput, ProfitScoringEngine
from .risk_governor import (
    CandidateRiskState,
    MarketRiskState,
    PortfolioRiskState,
    RiskGovernor,
)


def enrich_candidates_with_profit_scores(
    candidates: Iterable[Mapping[str, Any]],
    engine: ProfitScoringEngine | None = None,
) -> list[dict[str, Any]]:
    """Return candidates enriched with profit scoring fields.

    Expected upstream call site: after trigger_batch.py has selected candidates
    and before final sorting or downstream analysis dispatch.
    """

    scorer = engine or ProfitScoringEngine()
    enriched: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_dict = dict(candidate)
        score_input = candidate_to_profit_score_input(candidate_dict)
        score_result = scorer.score(score_input)
        candidate_dict.update(
            {
                "profit_score": score_result.profit_score,
                "raw_edge_score": score_result.raw_edge_score,
                "risk_penalty": score_result.risk_penalty,
                "expected_value": score_result.expected_value,
                "profit_decision_hint": score_result.decision_hint,
                "profit_score_reasons": list(score_result.reasons),
            }
        )
        enriched.append(candidate_dict)

    return sorted(
        enriched,
        key=lambda item: (
            _as_float(item.get("profit_score")),
            _as_float(item.get("expected_value")),
            _as_float(item.get("agent_fit_score")),
        ),
        reverse=True,
    )


def candidate_to_profit_score_input(candidate: Mapping[str, Any]) -> ProfitScoreInput:
    """Map a PRISM-INSIGHT candidate dict into ProfitScoreInput."""

    expected_return = _first_number(
        candidate,
        "expected_return_pct",
        "target_return_pct",
        "expected_profit_pct",
        "upside_pct",
    )
    expected_loss = _first_number(
        candidate,
        "expected_loss_pct",
        "stop_loss_pct",
        "downside_pct",
        "risk_pct",
    )
    risk_reward = _first_number(
        candidate,
        "risk_reward_ratio",
        "reward_risk_ratio",
    )
    if risk_reward <= 0 and expected_return > 0 and expected_loss > 0:
        risk_reward = expected_return / expected_loss

    return ProfitScoreInput(
        ticker=str(candidate.get("ticker") or candidate.get("code") or candidate.get("symbol") or ""),
        company_name=str(candidate.get("company_name") or candidate.get("name") or ""),
        trigger_type=str(candidate.get("trigger_type") or candidate.get("trigger") or ""),
        technical_edge=_score_from(candidate, "technical_edge", "technical_score", "ta_score"),
        flow_edge=_score_from(candidate, "flow_edge", "flow_score", "trading_flow_score", "supply_demand_score"),
        valuation_edge=_score_from(candidate, "valuation_edge", "financial_score", "valuation_score"),
        sector_edge=_score_from(candidate, "sector_edge", "industry_score", "sector_score"),
        news_quality=_score_from(candidate, "news_quality", "news_score", "event_score"),
        macro_alignment=_score_from(candidate, "macro_alignment", "market_score", "macro_score"),
        historical_trigger_edge=_score_from(candidate, "historical_trigger_edge", "trigger_win_score", "trigger_score"),
        liquidity_quality=_score_from(candidate, "liquidity_quality", "liquidity_score", "volume_score"),
        expected_return_pct=expected_return,
        expected_loss_pct=expected_loss,
        risk_reward_ratio=risk_reward,
        volatility_pct=_first_number(candidate, "volatility_pct", "volatility", "atr_pct"),
        market_regime=str(candidate.get("market_regime") or candidate.get("regime") or ""),
        metadata=candidate,
    )


def apply_risk_governor_to_scenario(
    scenario: Mapping[str, Any],
    candidate: Mapping[str, Any],
    portfolio: Mapping[str, Any],
    market: Mapping[str, Any],
    governor: RiskGovernor | None = None,
) -> dict[str, Any]:
    """Return a trading scenario with final risk-governor decision attached.

    Expected upstream call site: stock_tracking_agent.py after Buy Specialist
    returns a scenario and before KIS order execution.
    """

    scenario_dict = dict(scenario)
    gate = governor or RiskGovernor()
    decision = gate.evaluate_before_buy(
        candidate=_candidate_risk_state(scenario_dict, candidate),
        portfolio=_portfolio_risk_state(portfolio),
        market=_market_risk_state(market),
    )

    scenario_dict["risk_governor"] = asdict(decision)
    scenario_dict["risk_governor_reasons"] = list(decision.reasons)
    scenario_dict["risk_governor_warnings"] = list(decision.warnings)

    if not decision.approved:
        scenario_dict["decision"] = "no_entry"
        scenario_dict["action"] = "no_entry"
        scenario_dict["position_weight_pct"] = 0.0
    else:
        scenario_dict.setdefault("decision", "entry")
        scenario_dict["position_weight_pct"] = min(
            _as_float(scenario_dict.get("position_weight_pct"), decision.max_position_weight_pct),
            decision.max_position_weight_pct,
        )

    return scenario_dict


def _candidate_risk_state(
    scenario: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> CandidateRiskState:
    merged = {**dict(candidate), **dict(scenario)}
    return CandidateRiskState(
        ticker=str(merged.get("ticker") or merged.get("code") or merged.get("symbol") or ""),
        company_name=str(merged.get("company_name") or merged.get("name") or ""),
        sector=str(merged.get("sector") or merged.get("industry") or ""),
        trigger_type=str(merged.get("trigger_type") or merged.get("trigger") or ""),
        buy_score=_first_number(merged, "buy_score", "entry_score"),
        profit_score=_first_number(merged, "profit_score"),
        expected_value=_first_number(merged, "expected_value"),
        expected_loss_pct=_first_number(merged, "expected_loss_pct", "stop_loss_pct", "downside_pct"),
        risk_reward_ratio=_first_number(merged, "risk_reward_ratio", "reward_risk_ratio"),
        historical_trigger_win_rate=_first_number(merged, "historical_trigger_win_rate", "trigger_win_rate"),
        historical_trigger_count=int(_first_number(merged, "historical_trigger_count", "trigger_sample_count")),
        same_ticker_recent_losses=int(_first_number(merged, "same_ticker_recent_losses", "recent_loss_count")),
        metadata=merged,
    )


def _portfolio_risk_state(portfolio: Mapping[str, Any]) -> PortfolioRiskState:
    return PortfolioRiskState(
        current_slots=int(_first_number(portfolio, "current_slots", "holding_count", "positions_count")),
        max_slots=int(_first_number(portfolio, "max_slots", "max_positions", default=10)),
        same_sector_count=int(_first_number(portfolio, "same_sector_count", "sector_position_count")),
        max_same_sector=int(_first_number(portfolio, "max_same_sector", default=3)),
        sector_weight_pct=_first_number(portfolio, "sector_weight_pct", "same_sector_weight_pct"),
        max_sector_weight_pct=_first_number(portfolio, "max_sector_weight_pct", default=30.0),
        daily_realized_loss_pct=_first_number(portfolio, "daily_realized_loss_pct", "daily_pnl_pct"),
        max_daily_loss_pct=_first_number(portfolio, "max_daily_loss_pct", default=3.0),
        cash_weight_pct=_first_number(portfolio, "cash_weight_pct", "cash_pct"),
        min_cash_weight_pct=_first_number(portfolio, "min_cash_weight_pct"),
        recent_stop_losses=int(_first_number(portfolio, "recent_stop_losses", "recent_stop_loss_count")),
    )


def _market_risk_state(market: Mapping[str, Any]) -> MarketRiskState:
    return MarketRiskState(
        market_regime=str(market.get("market_regime") or market.get("regime") or ""),
        index_change_pct=_first_number(market, "index_change_pct", "kospi_change_pct", "market_change_pct"),
        volatility_spike=bool(market.get("volatility_spike", False)),
        risk_event_active=bool(market.get("risk_event_active", False)),
        new_buy_block=bool(market.get("new_buy_block", False)),
    )


def _score_from(data: Mapping[str, Any], *keys: str) -> float:
    value = _first_number(data, *keys)
    return max(0.0, min(100.0, value))


def _first_number(data: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in data:
            value = _as_float(data.get(key), default=None)
            if value is not None:
                return value
    return default


def _as_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
