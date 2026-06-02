"""Performance feedback helpers for PRISM-INSIGHT optimization.

The feedback loop turns paper/live outcome history into conservative scoring
signals. It does not replace the upstream agents; it adds historical context that
can be fed into ProfitScoringEngine and RiskGovernor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class CandidateOutcome:
    ticker: str
    trigger_type: str = ""
    sector: str = ""
    entry_decision: str = "unknown"
    return_7d: float | None = None
    return_14d: float | None = None
    return_30d: float | None = None
    max_gain_30d: float | None = None
    max_drawdown_30d: float | None = None
    realized_return: float | None = None
    profit_score: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerformanceBucket:
    key: str
    sample_count: int
    win_rate_pct: float
    average_return_pct: float
    average_drawdown_pct: float
    average_max_gain_pct: float
    profit_factor: float
    edge_score: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CandidateFeedback:
    ticker: str
    trigger_type: str
    sector: str
    historical_trigger_edge: float
    historical_sector_edge: float
    historical_ticker_edge: float
    trigger_sample_count: int
    sector_sample_count: int
    ticker_sample_count: int
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]


class PerformanceFeedbackEngine:
    """Summarizes prior outcomes and produces next-candidate feedback signals."""

    def __init__(self, min_samples: int = 5, return_window: str = "return_14d") -> None:
        self.min_samples = max(1, int(min_samples))
        self.return_window = return_window

    def build_feedback(
        self,
        candidates: Iterable[Mapping[str, Any]],
        outcomes: Iterable[CandidateOutcome | Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return candidate dicts enriched with historical performance signals."""
        outcome_list = [self._coerce_outcome(outcome) for outcome in outcomes]
        trigger_buckets = self._buckets_by(outcome_list, "trigger_type")
        sector_buckets = self._buckets_by(outcome_list, "sector")
        ticker_buckets = self._buckets_by(outcome_list, "ticker")

        enriched: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_dict = dict(candidate)
            feedback = self.feedback_for_candidate(
                candidate_dict,
                trigger_buckets=trigger_buckets,
                sector_buckets=sector_buckets,
                ticker_buckets=ticker_buckets,
            )
            candidate_dict.update(
                {
                    "historical_trigger_edge": feedback.historical_trigger_edge,
                    "historical_sector_edge": feedback.historical_sector_edge,
                    "historical_ticker_edge": feedback.historical_ticker_edge,
                    "trigger_sample_count": feedback.trigger_sample_count,
                    "sector_sample_count": feedback.sector_sample_count,
                    "ticker_sample_count": feedback.ticker_sample_count,
                    "performance_feedback_warnings": list(feedback.warnings),
                    "performance_feedback_reasons": list(feedback.reasons),
                }
            )
            enriched.append(candidate_dict)
        return enriched

    def feedback_for_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        trigger_buckets: Mapping[str, PerformanceBucket],
        sector_buckets: Mapping[str, PerformanceBucket],
        ticker_buckets: Mapping[str, PerformanceBucket],
    ) -> CandidateFeedback:
        ticker = str(candidate.get("ticker") or candidate.get("code") or candidate.get("symbol") or "")
        trigger_type = str(candidate.get("trigger_type") or candidate.get("trigger") or "")
        sector = str(candidate.get("sector") or candidate.get("industry") or "")

        trigger_bucket = trigger_buckets.get(trigger_type)
        sector_bucket = sector_buckets.get(sector)
        ticker_bucket = ticker_buckets.get(ticker)

        warnings: list[str] = []
        reasons: list[str] = []
        for label, bucket in (
            ("trigger", trigger_bucket),
            ("sector", sector_bucket),
            ("ticker", ticker_bucket),
        ):
            if not bucket:
                continue
            reasons.append(
                f"{label}:{bucket.key} samples={bucket.sample_count} win={bucket.win_rate_pct:.1f}% edge={bucket.edge_score:.1f}"
            )
            warnings.extend(bucket.warnings)

        return CandidateFeedback(
            ticker=ticker,
            trigger_type=trigger_type,
            sector=sector,
            historical_trigger_edge=self._bucket_edge(trigger_bucket),
            historical_sector_edge=self._bucket_edge(sector_bucket),
            historical_ticker_edge=self._bucket_edge(ticker_bucket),
            trigger_sample_count=trigger_bucket.sample_count if trigger_bucket else 0,
            sector_sample_count=sector_bucket.sample_count if sector_bucket else 0,
            ticker_sample_count=ticker_bucket.sample_count if ticker_bucket else 0,
            warnings=tuple(dict.fromkeys(warnings)),
            reasons=tuple(reasons),
        )

    def summarize(self, outcomes: Iterable[CandidateOutcome | Mapping[str, Any]], field_name: str) -> list[PerformanceBucket]:
        outcome_list = [self._coerce_outcome(outcome) for outcome in outcomes]
        return sorted(
            self._buckets_by(outcome_list, field_name).values(),
            key=lambda bucket: (bucket.edge_score, bucket.sample_count),
            reverse=True,
        )

    def _buckets_by(self, outcomes: list[CandidateOutcome], field_name: str) -> dict[str, PerformanceBucket]:
        grouped: dict[str, list[CandidateOutcome]] = {}
        for outcome in outcomes:
            key = str(getattr(outcome, field_name) or "")
            if key:
                grouped.setdefault(key, []).append(outcome)
        return {key: self._bucket(key, values) for key, values in grouped.items()}

    def _bucket(self, key: str, outcomes: list[CandidateOutcome]) -> PerformanceBucket:
        returns = [value for outcome in outcomes if (value := self._outcome_return(outcome)) is not None]
        drawdowns = [outcome.max_drawdown_30d for outcome in outcomes if outcome.max_drawdown_30d is not None]
        gains = [outcome.max_gain_30d for outcome in outcomes if outcome.max_gain_30d is not None]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        sample_count = len(returns)
        win_rate = (len(wins) / sample_count * 100.0) if sample_count else 0.0
        average_return = mean(returns) if returns else 0.0
        average_drawdown = mean(drawdowns) if drawdowns else 0.0
        average_gain = mean(gains) if gains else 0.0
        profit_factor = self._profit_factor(wins, losses)
        edge_score = self._edge_score(
            sample_count=sample_count,
            win_rate_pct=win_rate,
            average_return_pct=average_return,
            average_drawdown_pct=average_drawdown,
            profit_factor=profit_factor,
        )
        return PerformanceBucket(
            key=key,
            sample_count=sample_count,
            win_rate_pct=round(win_rate, 2),
            average_return_pct=round(average_return, 3),
            average_drawdown_pct=round(average_drawdown, 3),
            average_max_gain_pct=round(average_gain, 3),
            profit_factor=round(profit_factor, 3),
            edge_score=round(edge_score, 2),
            warnings=tuple(self._warnings(sample_count, win_rate, average_return, average_drawdown)),
        )

    def _edge_score(
        self,
        *,
        sample_count: int,
        win_rate_pct: float,
        average_return_pct: float,
        average_drawdown_pct: float,
        profit_factor: float,
    ) -> float:
        if sample_count <= 0:
            return 50.0
        sample_confidence = min(1.0, sample_count / max(self.min_samples, 1))
        win_component = max(0.0, min(100.0, win_rate_pct))
        return_component = max(0.0, min(100.0, 50.0 + average_return_pct * 5.0))
        pf_component = max(0.0, min(100.0, profit_factor * 35.0))
        drawdown_penalty = max(0.0, min(25.0, max(0.0, average_drawdown_pct - 8.0) * 1.5))
        raw = (win_component * 0.40) + (return_component * 0.35) + (pf_component * 0.25) - drawdown_penalty
        return 50.0 + ((raw - 50.0) * sample_confidence)

    def _warnings(
        self,
        sample_count: int,
        win_rate_pct: float,
        average_return_pct: float,
        average_drawdown_pct: float,
    ) -> list[str]:
        warnings: list[str] = []
        if sample_count and sample_count < self.min_samples:
            warnings.append(f"표본 부족: {sample_count} < {self.min_samples}")
        if sample_count >= self.min_samples and win_rate_pct < 40.0:
            warnings.append(f"과거 승률 낮음: {win_rate_pct:.1f}%")
        if sample_count >= self.min_samples and average_return_pct < 0.0:
            warnings.append(f"과거 평균 수익률 음수: {average_return_pct:.2f}%")
        if average_drawdown_pct > 12.0:
            warnings.append(f"과거 평균 낙폭 큼: {average_drawdown_pct:.1f}%")
        return warnings

    def _bucket_edge(self, bucket: PerformanceBucket | None) -> float:
        return bucket.edge_score if bucket else 50.0

    def _outcome_return(self, outcome: CandidateOutcome) -> float | None:
        for value in (
            getattr(outcome, self.return_window, None),
            outcome.realized_return,
            outcome.return_14d,
            outcome.return_30d,
            outcome.return_7d,
        ):
            if value is not None:
                return float(value)
        return None

    @staticmethod
    def _profit_factor(wins: list[float], losses: list[float]) -> float:
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def _coerce_outcome(outcome: CandidateOutcome | Mapping[str, Any]) -> CandidateOutcome:
        if isinstance(outcome, CandidateOutcome):
            return outcome
        data = dict(outcome)
        return CandidateOutcome(
            ticker=str(data.get("ticker") or data.get("code") or data.get("symbol") or ""),
            trigger_type=str(data.get("trigger_type") or data.get("trigger") or ""),
            sector=str(data.get("sector") or data.get("industry") or ""),
            entry_decision=str(data.get("entry_decision") or data.get("decision") or "unknown"),
            return_7d=_optional_float(data.get("return_7d")),
            return_14d=_optional_float(data.get("return_14d")),
            return_30d=_optional_float(data.get("return_30d")),
            max_gain_30d=_optional_float(data.get("max_gain_30d")),
            max_drawdown_30d=_optional_float(data.get("max_drawdown_30d")),
            realized_return=_optional_float(data.get("realized_return")),
            profit_score=_optional_float(data.get("profit_score")),
            metadata=data,
        )


def _optional_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
