"""Paper-trading validation metrics for PRISM-INSIGHT."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class PaperTrade:
    ticker: str
    company_name: str = ""
    trigger_type: str = ""
    sector: str = ""
    entry_date: str = ""
    exit_date: str = ""
    return_pct: float = 0.0
    holding_days: int = 0
    max_gain_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_score: float = 0.0
    buy_score: float = 0.0


@dataclass(frozen=True)
class ValidationThresholds:
    min_trades: int = 30
    min_win_rate_pct: float = 45.0
    min_expectancy_pct: float = 0.5
    max_mdd_pct: float = 15.0
    min_profit_factor: float = 1.2
    max_single_trigger_dependency_pct: float = 55.0
    max_single_sector_dependency_pct: float = 55.0


@dataclass(frozen=True)
class ValidationReport:
    approved_for_live: bool
    total_trades: int
    win_rate_pct: float
    cumulative_return_pct: float
    average_return_pct: float
    average_win_pct: float
    average_loss_pct: float
    expectancy_pct: float
    profit_factor: float
    max_drawdown_pct: float
    best_trigger: str
    worst_trigger: str
    concentration_warnings: tuple[str, ...]
    failed_gates: tuple[str, ...]


class PaperTradingValidator:
    """Validates simulated trade results against live-trading gates."""

    def __init__(self, thresholds: ValidationThresholds | None = None) -> None:
        self.thresholds = thresholds or ValidationThresholds()

    def validate(self, trades: list[PaperTrade]) -> ValidationReport:
        if not trades:
            return ValidationReport(
                approved_for_live=False,
                total_trades=0,
                win_rate_pct=0.0,
                cumulative_return_pct=0.0,
                average_return_pct=0.0,
                average_win_pct=0.0,
                average_loss_pct=0.0,
                expectancy_pct=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                best_trigger="",
                worst_trigger="",
                concentration_warnings=(),
                failed_gates=("페이퍼트레이딩 거래 기록 없음",),
            )

        returns = [trade.return_pct for trade in trades]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        win_rate = len(wins) / len(trades) * 100.0
        average_return = mean(returns)
        average_win = mean(wins) if wins else 0.0
        average_loss = mean(losses) if losses else 0.0
        cumulative_return = self._compound_return(returns)
        max_drawdown = self._max_drawdown(returns)
        profit_factor = self._profit_factor(wins, losses)
        expectancy = self._expectancy(win_rate, average_win, average_loss)
        trigger_stats = self._group_stats(trades, "trigger_type")
        sector_stats = self._group_stats(trades, "sector")
        best_trigger, worst_trigger = self._best_and_worst(trigger_stats)
        concentration_warnings = self._concentration_warnings(trades, trigger_stats, sector_stats)
        failed_gates = self._failed_gates(
            total_trades=len(trades),
            win_rate=win_rate,
            expectancy=expectancy,
            max_drawdown=max_drawdown,
            profit_factor=profit_factor,
            concentration_warnings=concentration_warnings,
        )
        return ValidationReport(
            approved_for_live=not failed_gates,
            total_trades=len(trades),
            win_rate_pct=round(win_rate, 2),
            cumulative_return_pct=round(cumulative_return, 2),
            average_return_pct=round(average_return, 2),
            average_win_pct=round(average_win, 2),
            average_loss_pct=round(average_loss, 2),
            expectancy_pct=round(expectancy, 2),
            profit_factor=round(profit_factor, 3),
            max_drawdown_pct=round(max_drawdown, 2),
            best_trigger=best_trigger,
            worst_trigger=worst_trigger,
            concentration_warnings=tuple(concentration_warnings),
            failed_gates=tuple(failed_gates),
        )

    def _failed_gates(
        self,
        total_trades: int,
        win_rate: float,
        expectancy: float,
        max_drawdown: float,
        profit_factor: float,
        concentration_warnings: list[str],
    ) -> list[str]:
        thresholds = self.thresholds
        failed: list[str] = []
        if total_trades < thresholds.min_trades:
            failed.append(f"거래 수 부족: {total_trades} < {thresholds.min_trades}")
        if win_rate < thresholds.min_win_rate_pct:
            failed.append(f"승률 부족: {win_rate:.1f}% < {thresholds.min_win_rate_pct:.1f}%")
        if expectancy < thresholds.min_expectancy_pct:
            failed.append(f"기대값 부족: {expectancy:.2f}% < {thresholds.min_expectancy_pct:.2f}%")
        if max_drawdown > thresholds.max_mdd_pct:
            failed.append(f"MDD 초과: {max_drawdown:.1f}% > {thresholds.max_mdd_pct:.1f}%")
        if profit_factor < thresholds.min_profit_factor:
            failed.append(f"손익비 계수 부족: {profit_factor:.2f} < {thresholds.min_profit_factor:.2f}")
        failed.extend(concentration_warnings)
        return failed

    def _concentration_warnings(self, trades: list[PaperTrade], trigger_stats: dict[str, list[float]], sector_stats: dict[str, list[float]]) -> list[str]:
        total = len(trades)
        warnings: list[str] = []
        for trigger, values in trigger_stats.items():
            share = len(values) / total * 100.0
            if trigger and share > self.thresholds.max_single_trigger_dependency_pct:
                warnings.append(f"특정 트리거 의존 과다: {trigger} {share:.1f}%")
        for sector, values in sector_stats.items():
            share = len(values) / total * 100.0
            if sector and share > self.thresholds.max_single_sector_dependency_pct:
                warnings.append(f"특정 섹터 의존 과다: {sector} {share:.1f}%")
        return warnings

    @staticmethod
    def _compound_return(returns: list[float]) -> float:
        value = 1.0
        for return_pct in returns:
            value *= 1.0 + (return_pct / 100.0)
        return (value - 1.0) * 100.0

    @staticmethod
    def _max_drawdown(returns: list[float]) -> float:
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for return_pct in returns:
            equity *= 1.0 + (return_pct / 100.0)
            peak = max(peak, equity)
            drawdown = (peak - equity) / peak * 100.0
            max_drawdown = max(max_drawdown, drawdown)
        return max_drawdown

    @staticmethod
    def _profit_factor(wins: list[float], losses: list[float]) -> float:
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def _expectancy(win_rate_pct: float, average_win: float, average_loss: float) -> float:
        win_probability = win_rate_pct / 100.0
        loss_probability = 1.0 - win_probability
        return (win_probability * average_win) + (loss_probability * average_loss)

    @staticmethod
    def _group_stats(trades: list[PaperTrade], field_name: str) -> dict[str, list[float]]:
        stats: dict[str, list[float]] = {}
        for trade in trades:
            key = str(getattr(trade, field_name) or "")
            stats.setdefault(key, []).append(trade.return_pct)
        return stats

    @staticmethod
    def _best_and_worst(stats: dict[str, list[float]]) -> tuple[str, str]:
        averages = {key: mean(values) for key, values in stats.items() if key and values}
        if not averages:
            return "", ""
        return max(averages, key=averages.get), min(averages, key=averages.get)
