"""Recommendation-driven paper portfolio tracking.

Rules requested by the operator:
- Portfolio starts on 2026-06-01 by default.
- Every daily recommendation is treated as one new investment unit.
- Repeated recommendations add weight: A recommended twice and B once => A:B = 2:1.
- When a sell signal is triggered for a ticker, all units in that ticker are sold at once.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "runtime" / "candidate_history.sqlite3"
DEFAULT_OUTPUT_PATH = ROOT / "dashboard" / "portfolio_status.json"
DEFAULT_START_DATE = "2026-06-01"


@dataclass
class Unit:
    ticker: str
    company_name: str
    signal_date: str
    trigger_type: str
    entry_price: float
    stop_loss_price: float | None = None
    target_price: float | None = None


@dataclass
class Position:
    ticker: str
    company_name: str
    units: list[Unit] = field(default_factory=list)
    peak_price: float = 0.0

    def add(self, unit: Unit) -> None:
        self.units.append(unit)
        self.peak_price = max(self.peak_price, unit.entry_price)

    @property
    def unit_count(self) -> int:
        return len(self.units)

    @property
    def cost(self) -> float:
        return sum(unit.entry_price for unit in self.units)

    @property
    def avg_entry(self) -> float:
        return self.cost / self.unit_count if self.unit_count else 0.0

    @property
    def avg_stop(self) -> float | None:
        values = [unit.stop_loss_price for unit in self.units if unit.stop_loss_price and unit.stop_loss_price > 0]
        return sum(values) / len(values) if values else None

    @property
    def avg_target(self) -> float | None:
        values = [unit.target_price for unit in self.units if unit.target_price and unit.target_price > 0]
        return sum(values) / len(values) if values else None


def update_portfolio_status(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    start = _iso_date(start_date or os.getenv("PORTFOLIO_START_DATE", DEFAULT_START_DATE))
    end = _iso_date(end_date or _today_ymd())
    rows = _load_recommendation_rows(Path(db_path), start=start)
    if not rows:
        payload = _empty_payload(start=start, end=end, reason="no_recommendations_yet")
        _write_json(Path(output_path), payload)
        return payload

    tickers = sorted({row["ticker"] for row in rows})
    price_map = _load_price_map(tickers, start=start, end=end)
    if not price_map:
        payload = _empty_payload(start=start, end=end, reason="price_data_unavailable")
        payload["recommendation_count"] = len(rows)
        _write_json(Path(output_path), payload)
        return payload

    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_date.setdefault(row["signal_date"], []).append(row)

    open_positions: dict[str, Position] = {}
    realized_cash = 0.0
    total_invested = 0.0
    realized_pnl = 0.0
    trade_count = 0
    sell_signals: list[dict[str, Any]] = []
    recommendation_counts: dict[str, int] = {}
    equity_rows: list[dict[str, Any]] = []

    calendar = _portfolio_calendar(start, end, price_map)
    for current in calendar:
        current_key = current.strftime("%Y-%m-%d")

        for row in rows_by_date.get(current_key, []):
            ticker = row["ticker"]
            price = _price_on_or_before(price_map.get(ticker), current_key)
            entry_price = _positive_float(row.get("price_at_signal")) or price
            if not entry_price or entry_price <= 0:
                continue
            unit = Unit(
                ticker=ticker,
                company_name=row.get("company_name") or ticker,
                signal_date=current_key,
                trigger_type=row.get("trigger_type") or "PRISM",
                entry_price=entry_price,
                stop_loss_price=_positive_float(row.get("stop_loss_price")),
                target_price=_positive_float(row.get("target_price")),
            )
            open_positions.setdefault(
                ticker,
                Position(ticker=ticker, company_name=unit.company_name),
            ).add(unit)
            total_invested += entry_price
            trade_count += 1
            recommendation_counts[ticker] = recommendation_counts.get(ticker, 0) + 1

        for ticker in list(open_positions):
            position = open_positions[ticker]
            price = _price_on_or_before(price_map.get(ticker), current_key)
            if not price or price <= 0:
                continue
            position.peak_price = max(position.peak_price, price)
            reason = _sell_reason(position, price)
            if not reason:
                continue
            proceeds = price * position.unit_count
            pnl = proceeds - position.cost
            realized_cash += proceeds
            realized_pnl += pnl
            sell_signals.append(
                {
                    "date": current_key,
                    "ticker": ticker,
                    "company_name": position.company_name,
                    "units": position.unit_count,
                    "exit_price": round(price, 2),
                    "avg_entry": round(position.avg_entry, 2),
                    "realized_return_pct": _pct(pnl / position.cost if position.cost else 0.0),
                    "reason": reason,
                }
            )
            del open_positions[ticker]

        holding_value = 0.0
        for ticker, position in open_positions.items():
            price = _price_on_or_before(price_map.get(ticker), current_key)
            if price and price > 0:
                holding_value += price * position.unit_count
        net_value = realized_cash + holding_value
        total_return = (net_value / total_invested - 1) if total_invested else 0.0
        equity_rows.append(
            {
                "date": current_key,
                "invested": round(total_invested, 2),
                "net_value": round(net_value, 2),
                "return_pct": _pct(total_return),
                "open_positions": len(open_positions),
                "open_units": sum(position.unit_count for position in open_positions.values()),
            }
        )

    latest = equity_rows[-1] if equity_rows else {}
    current_holdings = _holdings_payload(open_positions, price_map, equity_rows[-1]["date"] if equity_rows else end)
    total_return_value = _float_from_pct_text(latest.get("return_pct"))
    elapsed_days = max((pd.to_datetime(end).date() - pd.to_datetime(start).date()).days, 1)
    annualized = (math.pow(1 + total_return_value, 365 / elapsed_days) - 1) if total_return_value > -1 else -1.0

    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start,
        "end_date": end,
        "rule": "daily recommendation adds one unit; repeated ticker recommendations add weight; sell signal exits all ticker units",
        "recommendation_count": len(rows),
        "trade_count": trade_count,
        "summary": {
            "total_invested": round(total_invested, 2),
            "net_value": latest.get("net_value", 0),
            "realized_cash": round(realized_cash, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_return_pct": latest.get("return_pct", "0.00%"),
            "annualized_return_pct": _pct(annualized),
            "open_positions": len(open_positions),
            "open_units": sum(position.unit_count for position in open_positions.values()),
            "sell_signal_count": len(sell_signals),
        },
        "holdings": current_holdings,
        "sell_signals": sell_signals[-20:][::-1],
        "equity_curve": equity_rows[-120:],
        "recommendation_weights": _recommendation_weights(recommendation_counts, rows),
    }
    _write_json(Path(output_path), payload)
    return payload


def _load_recommendation_rows(db_path: Path, *, start: str) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    query = """
        SELECT
            ticker,
            company_name,
            trigger_type,
            selected_at,
            signal_date,
            profit_score,
            price_at_signal,
            target_price,
            stop_loss_price
        FROM candidate_performance_tracker
        WHERE COALESCE(signal_date, selected_at) >= ?
        ORDER BY COALESCE(signal_date, selected_at), id
    """
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(query, (start.replace("-", ""),))]
    normalized = []
    for row in rows:
        signal_date = _row_date(row.get("signal_date") or row.get("selected_at"))
        if not signal_date or signal_date < start:
            continue
        ticker = str(row.get("ticker") or "").zfill(6)
        if not ticker:
            continue
        normalized.append({**row, "ticker": ticker, "signal_date": signal_date})
    return normalized


def _load_price_map(tickers: list[str], *, start: str, end: str) -> dict[str, pd.Series]:
    price_map: dict[str, pd.Series] = {}
    start_ymd = start.replace("-", "")
    end_ymd = end.replace("-", "")
    for ticker in tickers:
        try:
            from krx_data_client import get_market_ohlcv_by_date

            df = get_market_ohlcv_by_date(start_ymd, end_ymd, ticker)
        except Exception:
            df = pd.DataFrame()
        if df is None or df.empty:
            continue
        close_col = _first_column(df, ["Close", "종가", "close"])
        if close_col is None:
            continue
        series = pd.to_numeric(df[close_col], errors="coerce")
        series.index = pd.to_datetime(series.index).strftime("%Y-%m-%d")
        series = series.dropna()
        if not series.empty:
            price_map[ticker] = series
    return price_map


def _portfolio_calendar(start: str, end: str, price_map: dict[str, pd.Series]) -> list[pd.Timestamp]:
    dates = set()
    for series in price_map.values():
        dates.update(str(index) for index in series.index if start <= str(index) <= end)
    if not dates:
        return list(pd.date_range(start=start, end=end, freq="B"))
    return [pd.Timestamp(value) for value in sorted(dates)]


def _holdings_payload(open_positions: dict[str, Position], price_map: dict[str, pd.Series], current_date: str) -> list[dict[str, Any]]:
    rows = []
    for ticker, position in open_positions.items():
        price = _price_on_or_before(price_map.get(ticker), current_date) or 0.0
        value = price * position.unit_count
        pnl = value - position.cost
        rows.append(
            {
                "ticker": ticker,
                "company_name": position.company_name,
                "units": position.unit_count,
                "weight_units": position.unit_count,
                "avg_entry": round(position.avg_entry, 2),
                "current_price": round(price, 2),
                "market_value": round(value, 2),
                "return_pct": _pct(pnl / position.cost if position.cost else 0.0),
                "avg_stop": round(position.avg_stop, 2) if position.avg_stop else None,
                "avg_target": round(position.avg_target, 2) if position.avg_target else None,
                "last_signal_date": max(unit.signal_date for unit in position.units),
            }
        )
    return sorted(rows, key=lambda item: item["weight_units"], reverse=True)


def _recommendation_weights(counts: dict[str, int], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = {row["ticker"]: row.get("company_name") or row["ticker"] for row in rows}
    return [
        {"ticker": ticker, "company_name": names.get(ticker, ticker), "units": units}
        for ticker, units in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20]
    ]


def _sell_reason(position: Position, price: float) -> str | None:
    stop = position.avg_stop
    target = position.avg_target
    if stop and price <= stop:
        return "stop_loss"
    if target and price >= target:
        return "target_hit"
    return None


def _price_on_or_before(series: pd.Series | None, date_key: str) -> float | None:
    if series is None or series.empty:
        return None
    if date_key in series.index:
        return float(series.loc[date_key])
    before = series[series.index <= date_key]
    if before.empty:
        return None
    return float(before.iloc[-1])


def _empty_payload(*, start: str, end: str, reason: str) -> dict[str, Any]:
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start,
        "end_date": end,
        "reason": reason,
        "summary": {
            "total_invested": 0,
            "net_value": 0,
            "realized_cash": 0,
            "realized_pnl": 0,
            "total_return_pct": "0.00%",
            "annualized_return_pct": "0.00%",
            "open_positions": 0,
            "open_units": 0,
            "sell_signal_count": 0,
        },
        "holdings": [],
        "sell_signals": [],
        "equity_curve": [],
        "recommendation_weights": [],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _row_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def _iso_date(value: str) -> str:
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return date.today().isoformat()


def _today_ymd() -> str:
    return date.today().strftime("%Y%m%d")


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if number > 0 else None


def _pct(value: float) -> str:
    try:
        return f"{value * 100:.2f}%"
    except Exception:
        return "0.00%"


def _float_from_pct_text(value: Any) -> float:
    try:
        return float(str(value).replace("%", "")) / 100
    except Exception:
        return 0.0


def _first_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column
    return None
