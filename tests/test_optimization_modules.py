from optimization.paper_validator import PaperTrade, PaperTradingValidator
from optimization.profit_scoring import ProfitScoreInput, ProfitScoringEngine
from optimization.risk_governor import (
    CandidateRiskState,
    MarketRiskState,
    PortfolioRiskState,
    RiskGovernor,
)


def test_profit_scoring_ranks_stronger_candidate_first():
    engine = ProfitScoringEngine()
    weak = ProfitScoreInput(
        ticker="000001",
        technical_edge=45,
        flow_edge=40,
        valuation_edge=35,
        sector_edge=30,
        news_quality=40,
        macro_alignment=35,
        historical_trigger_edge=30,
        liquidity_quality=70,
        expected_return_pct=6,
        expected_loss_pct=8,
        risk_reward_ratio=0.75,
        market_regime="sideways",
    )
    strong = ProfitScoreInput(
        ticker="000002",
        technical_edge=82,
        flow_edge=78,
        valuation_edge=70,
        sector_edge=85,
        news_quality=74,
        macro_alignment=80,
        historical_trigger_edge=72,
        liquidity_quality=90,
        expected_return_pct=15,
        expected_loss_pct=5,
        risk_reward_ratio=3.0,
        market_regime="moderate_bull",
    )

    ranked = engine.score_many([weak, strong])

    assert ranked[0].ticker == "000002"
    assert ranked[0].decision_hint in {"strong_candidate", "candidate"}
    assert ranked[1].decision_hint in {"watch_only", "avoid"}


def test_risk_governor_blocks_negative_expected_value():
    decision = RiskGovernor().evaluate_before_buy(
        candidate=CandidateRiskState(
            ticker="000001",
            buy_score=8,
            profit_score=72,
            expected_value=-0.5,
            expected_loss_pct=5,
            risk_reward_ratio=1.8,
        ),
        portfolio=PortfolioRiskState(current_slots=3, same_sector_count=1),
        market=MarketRiskState(market_regime="moderate_bull"),
    )

    assert not decision.approved
    assert decision.action == "no_entry"
    assert any("기대값" in reason for reason in decision.reasons)


def test_risk_governor_approves_clean_candidate():
    decision = RiskGovernor().evaluate_before_buy(
        candidate=CandidateRiskState(
            ticker="000002",
            buy_score=8.2,
            profit_score=78,
            expected_value=3.5,
            expected_loss_pct=5,
            risk_reward_ratio=2.2,
            historical_trigger_win_rate=62,
            historical_trigger_count=12,
        ),
        portfolio=PortfolioRiskState(
            current_slots=4,
            max_slots=10,
            same_sector_count=1,
            sector_weight_pct=10,
            cash_weight_pct=30,
        ),
        market=MarketRiskState(market_regime="moderate_bull", index_change_pct=0.5),
    )

    assert decision.approved
    assert decision.action == "entry"
    assert decision.max_position_weight_pct > 0


def test_paper_validator_rejects_too_few_trades():
    report = PaperTradingValidator().validate(
        [
            PaperTrade(ticker="000001", return_pct=3.0),
            PaperTrade(ticker="000002", return_pct=-1.0),
        ]
    )

    assert not report.approved_for_live
    assert any("거래 수 부족" in gate for gate in report.failed_gates)


def test_paper_validator_approves_diversified_positive_results():
    trades = []
    triggers = ["거래량 급증", "마감 강도", "갭 상승", "시총 대비 자금"]
    sectors = ["전기전자", "바이오", "자동차", "금융"]
    returns = [3.0, 2.5, -1.0, 4.0, 1.5, -1.2, 2.2, 3.1, -0.8, 2.7]
    for idx in range(40):
        trades.append(
            PaperTrade(
                ticker=f"{idx:06d}",
                trigger_type=triggers[idx % len(triggers)],
                sector=sectors[idx % len(sectors)],
                return_pct=returns[idx % len(returns)],
            )
        )

    report = PaperTradingValidator().validate(trades)

    assert report.approved_for_live
    assert report.total_trades == 40
    assert report.expectancy_pct > 0
    assert not report.failed_gates
