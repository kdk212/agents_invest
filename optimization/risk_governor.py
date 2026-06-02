"""Final pre-trade risk gate for PRISM-INSIGHT."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class PortfolioRiskState:
    current_slots: int = 0
    max_slots: int = 10
    same_sector_count: int = 0
    max_same_sector: int = 3
    sector_weight_pct: float = 0.0
    max_sector_weight_pct: float = 30.0
    daily_realized_loss_pct: float = 0.0
    max_daily_loss_pct: float = 3.0
    cash_weight_pct: float = 0.0
    min_cash_weight_pct: float = 0.0
    recent_stop_losses: int = 0


@dataclass(frozen=True)
class MarketRiskState:
    market_regime: str = ""
    index_change_pct: float = 0.0
    volatility_spike: bool = False
    risk_event_active: bool = False
    new_buy_block: bool = False


@dataclass(frozen=True)
class CandidateRiskState:
    ticker: str
    company_name: str = ""
    sector: str = ""
    trigger_type: str = ""
    buy_score: float = 0.0
    profit_score: float = 0.0
    expected_value: float = 0.0
    expected_loss_pct: float = 0.0
    risk_reward_ratio: float = 0.0
    historical_trigger_win_rate: float = 0.0
    historical_trigger_count: int = 0
    same_ticker_recent_losses: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    action: str
    max_position_weight_pct: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


class RiskGovernor:
    """Applies hard risk gates and position-size limits."""

    def __init__(
        self,
        min_buy_score: float = 7.0,
        min_profit_score: float = 60.0,
        min_risk_reward: float = 1.2,
        max_expected_loss_pct: float = 7.0,
    ) -> None:
        self.min_buy_score = min_buy_score
        self.min_profit_score = min_profit_score
        self.min_risk_reward = min_risk_reward
        self.max_expected_loss_pct = max_expected_loss_pct

    def evaluate_before_buy(
        self,
        candidate: CandidateRiskState,
        portfolio: PortfolioRiskState,
        market: MarketRiskState,
    ) -> RiskDecision:
        blockers: list[str] = []
        warnings: list[str] = []
        self._check_portfolio(portfolio, blockers, warnings)
        self._check_market(market, blockers, warnings)
        self._check_candidate(candidate, market, blockers, warnings)
        max_weight = self._position_weight(candidate, portfolio, market, bool(blockers))
        if blockers:
            return RiskDecision(False, "no_entry", 0.0, tuple(blockers), tuple(warnings))
        return RiskDecision(True, "entry", max_weight, ("risk_gate_passed",), tuple(warnings))

    def _check_portfolio(self, portfolio: PortfolioRiskState, blockers: list[str], warnings: list[str]) -> None:
        if portfolio.current_slots >= portfolio.max_slots:
            blockers.append(f"최대 보유 종목 수 초과: {portfolio.current_slots}/{portfolio.max_slots}")
        if portfolio.same_sector_count >= portfolio.max_same_sector:
            blockers.append(f"동일 섹터 보유 한도 초과: {portfolio.same_sector_count}/{portfolio.max_same_sector}")
        if portfolio.sector_weight_pct >= portfolio.max_sector_weight_pct:
            blockers.append(f"섹터 비중 한도 초과: {portfolio.sector_weight_pct:.1f}%")
        if portfolio.daily_realized_loss_pct <= -abs(portfolio.max_daily_loss_pct):
            blockers.append(f"일일 손실 한도 도달: {portfolio.daily_realized_loss_pct:.1f}%")
        if portfolio.cash_weight_pct < portfolio.min_cash_weight_pct:
            blockers.append(f"현금 비중 부족: {portfolio.cash_weight_pct:.1f}%")
        if portfolio.recent_stop_losses >= 3:
            warnings.append("최근 손절이 많아 신규매수 비중 축소 필요")

    def _check_market(self, market: MarketRiskState, blockers: list[str], warnings: list[str]) -> None:
        if market.new_buy_block:
            blockers.append("시장 리스크 플래그로 신규매수 차단")
        if market.index_change_pct <= -2.5:
            blockers.append(f"시장 급락일 신규매수 차단: {market.index_change_pct:.1f}%")
        if market.risk_event_active and market.market_regime in {"moderate_bear", "strong_bear"}:
            blockers.append("약세장 위험 이벤트 활성화")
        if market.volatility_spike:
            warnings.append("변동성 급등 구간")
        if market.market_regime == "strong_bear":
            warnings.append("강한 약세장: 최저 비중만 허용")

    def _check_candidate(self, candidate: CandidateRiskState, market: MarketRiskState, blockers: list[str], warnings: list[str]) -> None:
        min_buy_score = self._regime_adjusted_min_buy_score(market.market_regime)
        min_profit_score = self._regime_adjusted_min_profit_score(market.market_regime)
        if candidate.buy_score < min_buy_score:
            blockers.append(f"매수 점수 미달: {candidate.buy_score:.1f} < {min_buy_score:.1f}")
        if candidate.profit_score and candidate.profit_score < min_profit_score:
            blockers.append(f"수익 최적화 점수 미달: {candidate.profit_score:.1f} < {min_profit_score:.1f}")
        if candidate.expected_value <= 0:
            blockers.append(f"기대값이 양수가 아님: {candidate.expected_value:.2f}%")
        if candidate.expected_loss_pct > self.max_expected_loss_pct:
            blockers.append(f"예상 손실폭 초과: {candidate.expected_loss_pct:.1f}%")
        if candidate.risk_reward_ratio and candidate.risk_reward_ratio < self.min_risk_reward:
            blockers.append(f"손익비 미달: {candidate.risk_reward_ratio:.2f} < {self.min_risk_reward:.2f}")
        if candidate.historical_trigger_count >= 5 and candidate.historical_trigger_win_rate < 35.0:
            blockers.append(f"동일 트리거 승률 부진: {candidate.historical_trigger_win_rate:.1f}%")
        if candidate.same_ticker_recent_losses >= 2:
            blockers.append("동일 종목 최근 반복 손실")
        if candidate.historical_trigger_count >= 3 and candidate.historical_trigger_win_rate < 45.0:
            warnings.append("동일 트리거 성과가 낮아 보수적 접근 필요")

    def _position_weight(self, candidate: CandidateRiskState, portfolio: PortfolioRiskState, market: MarketRiskState, blocked: bool) -> float:
        if blocked:
            return 0.0
        base_weight = 10.0
        if candidate.profit_score >= 80.0 and candidate.expected_value >= 3.0:
            base_weight = 12.0
        elif candidate.profit_score < 65.0:
            base_weight = 7.0
        if market.market_regime in {"moderate_bear", "strong_bear"}:
            base_weight *= 0.5
        elif market.market_regime == "sideways":
            base_weight *= 0.75
        if market.volatility_spike or portfolio.recent_stop_losses >= 3:
            base_weight *= 0.7
        remaining_sector_room = max(0.0, portfolio.max_sector_weight_pct - portfolio.sector_weight_pct)
        return round(max(0.0, min(base_weight, remaining_sector_room)), 2)

    def _regime_adjusted_min_buy_score(self, regime: str) -> float:
        if regime in {"strong_bear", "moderate_bear"}:
            return max(self.min_buy_score, 8.0)
        if regime == "sideways":
            return max(self.min_buy_score, 7.5)
        return self.min_buy_score

    def _regime_adjusted_min_profit_score(self, regime: str) -> float:
        if regime in {"strong_bear", "moderate_bear"}:
            return max(self.min_profit_score, 70.0)
        if regime == "sideways":
            return max(self.min_profit_score, 65.0)
        return self.min_profit_score
