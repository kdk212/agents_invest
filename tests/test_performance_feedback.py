from __future__ import annotations

from optimization.adapters import enrich_candidates_with_profit_scores
from optimization.performance_feedback import CandidateOutcome, PerformanceFeedbackEngine


def test_performance_feedback_summarizes_trigger_edge() -> None:
    outcomes = [
        CandidateOutcome(ticker="AAA", trigger_type="breakout", sector="AI", return_14d=8.0, max_drawdown_30d=3.0),
        CandidateOutcome(ticker="BBB", trigger_type="breakout", sector="AI", return_14d=5.0, max_drawdown_30d=2.0),
        CandidateOutcome(ticker="CCC", trigger_type="breakout", sector="AI", return_14d=-1.0, max_drawdown_30d=6.0),
        CandidateOutcome(ticker="DDD", trigger_type="breakout", sector="AI", return_14d=7.0, max_drawdown_30d=4.0),
        CandidateOutcome(ticker="EEE", trigger_type="breakout", sector="AI", return_14d=4.0, max_drawdown_30d=4.0),
    ]

    bucket = PerformanceFeedbackEngine(min_samples=5).summarize(outcomes, "trigger_type")[0]

    assert bucket.key == "breakout"
    assert bucket.sample_count == 5
    assert bucket.win_rate_pct == 80.0
    assert bucket.edge_score > 60.0
    assert bucket.warnings == ()


def test_performance_feedback_warns_on_weak_history() -> None:
    outcomes = [
        {"ticker": "AAA", "trigger_type": "gap", "sector": "Bio", "return_14d": -4.0, "max_drawdown_30d": 13.0},
        {"ticker": "BBB", "trigger_type": "gap", "sector": "Bio", "return_14d": -2.0, "max_drawdown_30d": 15.0},
        {"ticker": "CCC", "trigger_type": "gap", "sector": "Bio", "return_14d": 1.0, "max_drawdown_30d": 12.5},
        {"ticker": "DDD", "trigger_type": "gap", "sector": "Bio", "return_14d": -1.0, "max_drawdown_30d": 14.0},
        {"ticker": "EEE", "trigger_type": "gap", "sector": "Bio", "return_14d": -3.0, "max_drawdown_30d": 16.0},
    ]

    bucket = PerformanceFeedbackEngine(min_samples=5).summarize(outcomes, "trigger_type")[0]

    assert bucket.edge_score < 50.0
    assert any("승률" in warning for warning in bucket.warnings)
    assert any("수익률" in warning for warning in bucket.warnings)
    assert any("낙폭" in warning for warning in bucket.warnings)


def test_enrich_candidates_uses_feedback_before_profit_scoring() -> None:
    candidates = [
        {
            "ticker": "NEXT",
            "trigger_type": "breakout",
            "sector": "AI",
            "technical_score": 60.0,
            "expected_return_pct": 8.0,
            "expected_loss_pct": 3.0,
        }
    ]
    outcomes = [
        {"ticker": "AAA", "trigger_type": "breakout", "sector": "AI", "return_14d": 8.0, "max_drawdown_30d": 3.0},
        {"ticker": "BBB", "trigger_type": "breakout", "sector": "AI", "return_14d": 5.0, "max_drawdown_30d": 2.0},
        {"ticker": "CCC", "trigger_type": "breakout", "sector": "AI", "return_14d": -1.0, "max_drawdown_30d": 6.0},
        {"ticker": "DDD", "trigger_type": "breakout", "sector": "AI", "return_14d": 7.0, "max_drawdown_30d": 4.0},
        {"ticker": "EEE", "trigger_type": "breakout", "sector": "AI", "return_14d": 4.0, "max_drawdown_30d": 4.0},
    ]

    enriched = enrich_candidates_with_profit_scores(candidates, performance_outcomes=outcomes)

    assert enriched[0]["historical_trigger_edge"] > 60.0
    assert enriched[0]["historical_sector_edge"] > 60.0
    assert enriched[0]["trigger_sample_count"] == 5
    assert enriched[0]["profit_score"] > 0.0
    assert enriched[0]["performance_feedback_reasons"]
