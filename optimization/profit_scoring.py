"""Profit scoring helpers for PRISM-INSIGHT candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


DEFAULT_WEIGHTS = {
    "technical_edge": 0.20,
    "flow_edge": 0.15,
    "valuation_edge": 0.15,
    "sector_edge": 0.15,
    "news_quality": 0.10,
    "macro_alignment": 0.10,
    "historical_trigger_edge": 0.10,
    "liquidity_quality": 0.05,
}


@dataclass(frozen=True)
class ProfitScoreInput:
    ticker: str
    company_name: str = ""
    trigger_type: str = ""
    technical_edge: float = 0.0
    flow_edge: float = 0.0
    valuation_edge: float = 0.0
    sector_edge: float = 0.0
    news_quality: float = 0.0
    macro_alignment: float = 0.0
    historical_trigger_edge: float = 0.0
    liquidity_quality: float = 0.0
    expected_return_pct: float = 0.0
    expected_loss_pct: float = 0.0
    risk_reward_ratio: float = 0.0
    volatility_pct: float = 0.0
    market_regime: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfitScoreResult:
    ticker: str
    company_name: str
    trigger_type: str
    profit_score: float
    raw_edge_score: float
    risk_penalty: float
    expected_value: float
    risk_reward_ratio: float
    decision_hint: str
    reasons: tuple[str, ...]


class ProfitScoringEngine:
    """Ranks stock candidates by edge, risk, and expected value."""

    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        self._normalize_weights()

    def score(self, item: ProfitScoreInput) -> ProfitScoreResult:
        edge_score = self._weighted_edge_score(item)
        risk_penalty, risk_reasons = self._risk_penalty(item)
        expected_value = self._expected_value(item, edge_score)
        profit_score = max(0.0, min(100.0, edge_score - risk_penalty))
        reasons = self._score_reasons(item, edge_score, risk_penalty, expected_value)
        reasons.extend(risk_reasons)
        return ProfitScoreResult(
            ticker=item.ticker,
            company_name=item.company_name,
            trigger_type=item.trigger_type,
            profit_score=round(profit_score, 2),
            raw_edge_score=round(edge_score, 2),
            risk_penalty=round(risk_penalty, 2),
            expected_value=round(expected_value, 4),
            risk_reward_ratio=round(item.risk_reward_ratio, 3),
            decision_hint=self._decision_hint(profit_score, expected_value),
            reasons=tuple(reasons[:8]),
        )

    def score_many(self, items: list[ProfitScoreInput]) -> list[ProfitScoreResult]:
        scored = [self.score(item) for item in items]
        return sorted(
            scored,
            key=lambda result: (result.profit_score, result.expected_value),
            reverse=True,
        )

    def from_mapping(self, data: Mapping[str, Any]) -> ProfitScoreInput:
        return ProfitScoreInput(
            ticker=str(data.get("ticker") or data.get("code") or ""),
            company_name=str(data.get("company_name") or data.get("name") or ""),
            trigger_type=str(data.get("trigger_type") or ""),
            technical_edge=self._as_score(data.get("technical_edge")),
            flow_edge=self._as_score(data.get("flow_edge")),
            valuation_edge=self._as_score(data.get("valuation_edge")),
            sector_edge=self._as_score(data.get("sector_edge")),
            news_quality=self._as_score(data.get("news_quality")),
            macro_alignment=self._as_score(data.get("macro_alignment")),
            historical_trigger_edge=self._as_score(data.get("historical_trigger_edge")),
            liquidity_quality=self._as_score(data.get("liquidity_quality")),
            expected_return_pct=self._as_float(data.get("expected_return_pct")),
            expected_loss_pct=self._as_float(data.get("expected_loss_pct")),
            risk_reward_ratio=self._as_float(data.get("risk_reward_ratio")),
            volatility_pct=self._as_float(data.get("volatility_pct")),
            market_regime=str(data.get("market_regime") or ""),
            metadata=data,
        )

    def _normalize_weights(self) -> None:
        total = sum(max(0.0, value) for value in self.weights.values())
        if total <= 0:
            self.weights = dict(DEFAULT_WEIGHTS)
            total = sum(self.weights.values())
        self.weights = {key: max(0.0, value) / total for key, value in self.weights.items()}

    def _weighted_edge_score(self, item: ProfitScoreInput) -> float:
        return sum(self._as_score(getattr(item, name)) * weight for name, weight in self.weights.items())

    def _risk_penalty(self, item: ProfitScoreInput) -> tuple[float, list[str]]:
        penalty = 0.0
        reasons: list[str] = []
        if item.expected_loss_pct > 7.0:
            penalty += min(20.0, (item.expected_loss_pct - 7.0) * 2.0)
            reasons.append(f"손실폭이 큼: {item.expected_loss_pct:.1f}%")
        if item.risk_reward_ratio and item.risk_reward_ratio < 1.2:
            penalty += 8.0
            reasons.append(f"손익비 낮음: {item.risk_reward_ratio:.2f}")
        if item.volatility_pct > 12.0:
            penalty += min(12.0, (item.volatility_pct - 12.0) * 0.8)
            reasons.append(f"변동성 높음: {item.volatility_pct:.1f}%")
        if item.market_regime in {"strong_bear", "moderate_bear"}:
            penalty += 5.0
            reasons.append("약세장 리스크")
        if 0 < item.historical_trigger_edge < 35.0:
            penalty += 6.0
            reasons.append("동일 트리거 과거 성과 부진")
        return penalty, reasons

    def _expected_value(self, item: ProfitScoreInput, edge_score: float) -> float:
        win_probability = max(0.05, min(0.85, edge_score / 100.0))
        expected_gain = max(0.0, item.expected_return_pct)
        expected_loss = max(0.0, item.expected_loss_pct)
        return (win_probability * expected_gain) - ((1.0 - win_probability) * expected_loss)

    def _decision_hint(self, profit_score: float, expected_value: float) -> str:
        if profit_score >= 75.0 and expected_value > 0:
            return "strong_candidate"
        if profit_score >= 65.0 and expected_value > 0:
            return "candidate"
        if profit_score >= 55.0:
            return "watch_only"
        return "avoid"

    def _score_reasons(self, item: ProfitScoreInput, edge_score: float, risk_penalty: float, expected_value: float) -> list[str]:
        reasons = [
            f"종합 우위 점수 {edge_score:.1f}",
            f"리스크 감점 {risk_penalty:.1f}",
            f"기대값 {expected_value:.2f}%",
        ]
        strengths = [
            ("기술", item.technical_edge),
            ("수급", item.flow_edge),
            ("밸류에이션", item.valuation_edge),
            ("섹터", item.sector_edge),
            ("뉴스", item.news_quality),
            ("매크로", item.macro_alignment),
            ("과거 트리거", item.historical_trigger_edge),
        ]
        for label, value in sorted(strengths, key=lambda pair: pair[1], reverse=True)[:3]:
            if value >= 65.0:
                reasons.append(f"{label} 우위 {value:.0f}")
        return reasons

    @staticmethod
    def _as_score(value: Any) -> float:
        return max(0.0, min(100.0, ProfitScoringEngine._as_float(value)))

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            if value in ("", None):
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0
