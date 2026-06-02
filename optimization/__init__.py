"""Optimization add-ons for PRISM-INSIGHT."""

from .adapters import (
    apply_risk_governor_to_scenario,
    candidate_to_profit_score_input,
    enrich_candidates_with_profit_scores,
)
from .paper_validator import PaperTrade, PaperTradingValidator, ValidationReport
from .profit_scoring import ProfitScoreInput, ProfitScoreResult, ProfitScoringEngine
from .risk_governor import (
    CandidateRiskState,
    MarketRiskState,
    PortfolioRiskState,
    RiskDecision,
    RiskGovernor,
)

__all__ = [
    "CandidateRiskState",
    "MarketRiskState",
    "PaperTrade",
    "PaperTradingValidator",
    "PortfolioRiskState",
    "ProfitScoreInput",
    "ProfitScoreResult",
    "ProfitScoringEngine",
    "RiskDecision",
    "RiskGovernor",
    "ValidationReport",
    "apply_risk_governor_to_scenario",
    "candidate_to_profit_score_input",
    "enrich_candidates_with_profit_scores",
]
