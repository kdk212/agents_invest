#!/usr/bin/env python3
"""Optimize AI WIN recommendation count and rebuild dashboard portfolio.

Uses public OHLCV data, avoids KRX direct login, chooses the best top-N count by
backtest, then rebuilds the mock portfolio with this rule:
previous close data -> next trading-day open buy -> daily close performance.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECOMMENDATION = ROOT / "dashboard" / "prism_latest_morning.json"
DEFAULT_STRATEGY = ROOT / "dashboard" / "adaptive_strategy.json"
DEFAULT_PORTFOLIO = ROOT / "dashboard" / "portfolio_status.json"


@dataclass
class BacktestResult:
    period_months: int
    top_n: int
    start: date
    end: date
    total_return: float
    cagr: float
    mdd: float
    trades: int


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize AI WIN count and rebuild portfolio")
    parser.add_argument("--recommendation-file", default=str(DEFAULT_RECOMMENDATION))
    parser.add_argument("--strategy-file", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--portfolio-file", default=str(DEFAULT_PORTFOLIO))
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--universe-size", type=int, default=180)
    parser.add_argument("--min-top-n", type=int, default=3)
    parser.add_argument("--max-top-n", type=int, default=8)
    parser.add_argument("--period-months", default="24,18,12")
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()

    try:
        import FinanceDataReader as fdr
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "reason": "FinanceDataReader_missing",
            "next_action": ".venv/bin/python -m pip install finance-datareader",
            "error": f"{exc.__class__.__name__}: {exc}",
        }, ensure_ascii=False))
        return 2

    as_of = pd.to_datetime(args.as_of_date).date() if args.as_of_date else date.today()
    portfolio_start = pd.to_datetime(args.portfolio_start).date()
    periods = [int(x.strip()) for x in args.period_months.split(",") if x.strip()]
    top_values = list(range(args.min_top_n, args.max_top_n + 1))

    listing = load_listing(fdr)
    tickers = select_universe(listing, args.universe_size)
    history_start = min(as_of - timedelta(days=max(periods) * 31 + 430), portfolio_start - timedelta(days=430))
    histories = load_histories(fdr, tickers, history_start, as_of)
    if not histories:
        print(json.dumps({"ok": False, "reason": "no_price_history"}, ensure_ascii=False))
        return 2

    calendar = trading_calendar(histories, history_start, as_of)
    results: list[BacktestResult] = []
    for months in periods:
        start = as_of - timedelta(days=months * 31)
        for top_n in top_values:
            result = run_backtest(histories, listing, calendar, start, as_of, top_n)
            if result:
                results.append(result)

    if not results:
        print(json.dumps({"ok": False, "reason": "no_backtest_result"}, ensure_ascii=False))
        return 2

    best = max(results, key=lambda item: (item.cagr, item.total_return, -item.top_n))

    latest_signal_day = previous_trading_day(calendar, as_of) or as_of
    latest_picks = make_signal_picks(histories, listing, latest_signal_day, best.top_n)
    rec_path = Path(args.recommendation_file)
    write_recommendation_file(rec_path, latest_picks, latest_signal_day, best.top_n)

    strategy = {
        "source": "ai_win_public_fallback_backtest",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_period_months": best.period_months,
        "selected_top_n": best.top_n,
        "score_threshold": best.top_n,
        "stop_multiplier": 2.5,
        "take_profit_trigger_pct": 30.0,
        "take_profit_trailing_pct": 10.0,
        "best_summary": result_dict(best),
        "tested": [result_dict(x) for x in sorted(results, key=lambda item: (-item.cagr, item.top_n))[:20]],
        "note": "전일 종가 기준 신호와 다음 영업일 시초가 매수 규칙으로 추천 개수 3~8개, 최근 24/18/12개월 CAGR을 비교합니다.",
    }
    Path(args.strategy_file).write_text(json.dumps(strategy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    portfolio = build_portfolio(histories, listing, calendar, portfolio_start, as_of, best.top_n)
    Path(args.portfolio_file).write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "selected_top_n": best.top_n,
        "selected_period_months": best.period_months,
        "backtest_cagr_pct": round(best.cagr * 100, 2),
        "backtest_total_return_pct": round(best.total_return * 100, 2),
        "portfolio_return_pct": portfolio["summary"]["total_return_pct"],
        "portfolio_rule": portfolio["rule"],
        "recommendation_file": str(rec_path),
        "strategy_file": str(args.strategy_file),
        "portfolio_file": str(args.portfolio_file),
    }, ensure_ascii=False, indent=2))
    return 0


def load_listing(fdr) -> pd.DataFrame:
    listing = fdr.StockListing("KRX")
    listing["Code"] = listing["Code"].astype(str).str.zfill(6)
    return listing.set_index("Code", drop=False)


def select_universe(listing: pd.DataFrame, size: int) -> list[str]:
    frame = listing.copy()
    if "Market" in frame.columns:
        frame = frame[frame["Market"].isin(["KOSPI", "KOSDAQ"])]
    for col in ("Amount", "Marcap", "MarketCap"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
            frame = frame.sort_values(col, ascending=False)
            break
    return frame.index.astype(str).str.zfill(6)[:size].tolist()


def load_histories(fdr, tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    histories: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            df = fdr.DataReader(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        except Exception:
            continue
        if df is None or df.empty or "Close" not in df.columns or len(df) < 140:
            continue
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        histories[ticker] = df
    return histories


def trading_calendar(histories: dict[str, pd.DataFrame], start: date, end: date) -> list[date]:
    return sorted({idx.date() for df in histories.values() for idx in df.index if start <= idx.date() <= end})


def run_backtest(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, calendar: list[date], start: date, end: date, top_n: int) -> BacktestResult | None:
    days = [d for d in calendar if start <= d <= end]
    if len(days) < 40:
        return None
    value = 1.0
    peak = 1.0
    mdd = 0.0
    trades = 0
    step = 5
    for i in range(1, len(days) - step, step):
        signal_day = days[i - 1]
        buy_day = days[i]
        exit_day = days[min(i + step, len(days) - 1)]
        picks = make_signal_picks(histories, listing, signal_day, top_n)
        returns = []
        for item in picks:
            df = histories.get(item["code"])
            if df is None:
                continue
            buy = open_on_or_after(df, buy_day)
            sell = close_on_or_before(df, exit_day)
            if buy and sell and buy > 0:
                returns.append(sell / buy - 1)
        if not returns:
            continue
        value *= 1 + float(np.mean(returns))
        peak = max(peak, value)
        mdd = min(mdd, value / peak - 1)
        trades += len(returns)
    if trades == 0:
        return None
    days_count = max((end - start).days, 1)
    total_return = value - 1
    cagr = math.pow(value, 365 / days_count) - 1 if value > 0 else -1
    return BacktestResult(round((end - start).days / 30), top_n, start, end, total_return, cagr, mdd, trades)


def make_signal_picks(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, signal_day: date, top_n: int) -> list[dict[str, Any]]:
    scored = score_universe(histories, listing, signal_day)
    if scored.empty:
        return []
    picks = scored.sort_values("ai_win_score", ascending=False).head(top_n)
    rows = []
    for rank, (ticker, row) in enumerate(picks.iterrows(), 1):
        latest = float(row["current_price"])
        stop_pct = min(max(float(row.get("vol60", 0.03)) / math.sqrt(252) * math.sqrt(5) * 2.5, 0.045), 0.18)
        rows.append({
            "rank": rank,
            "code": ticker,
            "name": row.get("name") or ticker,
            "trigger_type": "AI WIN 전일종가 모멘텀 상위주",
            "current_price": round(latest, 0),
            "change_rate": round(float(row.get("mom20", 0.0)) * 100, 2),
            "profit_score": round(float(row["ai_win_score_100"]), 2),
            "adaptive_profit_score": round(float(row["ai_win_score_100"]), 2),
            "ai_win_score": round(float(row["ai_win_score"]), 4),
            "ai_win_score_100": round(float(row["ai_win_score_100"]), 2),
            "forward_quality_score": round(float(row["forward_quality_score"]), 4),
            "stop_loss_pct": round(stop_pct * 100, 2),
            "stop_loss_price": round(latest * (1 - stop_pct), 0),
            "target_price": round(latest * 1.3, 0),
            "take_profit_trigger_pct": 30.0,
            "take_profit_trailing_pct": 10.0,
            "source": "ai_win_public_fallback_backtest",
        })
    return rows


def score_universe(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, day: date) -> pd.DataFrame:
    rows = []
    for ticker, df in histories.items():
        sliced = df[df.index.date <= day]
        row = score_ticker(ticker, sliced, listing)
        if row:
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    return score_frame(pd.DataFrame(rows).set_index("code"))


def score_ticker(ticker: str, df: pd.DataFrame, listing: pd.DataFrame) -> dict[str, Any] | None:
    if df is None or df.empty or len(df) < 130 or "Close" not in df.columns:
        return None
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(close) < 130:
        return None
    volume = pd.to_numeric(df.get("Volume", pd.Series(index=df.index, data=0)), errors="coerce").fillna(0)
    trading_value = close.reindex(volume.index).ffill() * volume
    latest = float(close.iloc[-1])
    daily = close.pct_change(fill_method=None)
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    peak20 = close.tail(20).max()
    trough20 = close.tail(20).min()
    peak60 = close.tail(60).max()
    mom20 = latest / close.iloc[-21] - 1
    mom60 = latest / close.iloc[-61] - 1
    mom120 = latest / close.iloc[-121] - 1
    trend = latest / ma60 - 1 + (ma20 / ma60 - 1)
    vol60 = float(daily.tail(60).std() * math.sqrt(252))
    hit20 = float((daily.tail(20) > 0).mean())
    pullback_resilience = float(latest / peak20 - trough20 / peak20) if peak20 else 0.0
    acceleration = float(mom20 - (mom60 - mom20) / 2)
    drawdown = float(latest / peak60 - 1) if peak60 else 0.0
    overextension = float(latest / ma20 - 1) if ma20 else 0.0
    risk_score = vol60 + max(0.0, -drawdown) + max(0.0, overextension - 0.18)
    turnover_change = float(trading_value.tail(5).mean() / trading_value.tail(60).mean() - 1) if trading_value.tail(60).mean() else 0.0
    name = str(listing.loc[ticker].get("Name") or ticker) if ticker in listing.index else ticker
    return {"code": ticker, "name": name, "current_price": latest, "mom20": float(mom20), "mom60": float(mom60), "mom120": float(mom120), "trend": float(trend), "vol60": vol60, "hit20": hit20, "pullback_resilience": pullback_resilience, "acceleration": acceleration, "turnover_change": turnover_change, "drawdown_from_60d_peak": drawdown, "risk_score": float(risk_score)}


def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.replace([np.inf, -np.inf], np.nan).copy()
    out["forward_quality_score"] = 0.22 * zscore(out["hit20"]) + 0.18 * zscore(out["pullback_resilience"]) + 0.18 * zscore(out["acceleration"]) + 0.12 * zscore(out["turnover_change"].clip(-1, 5)) - 0.22 * zscore(out["risk_score"]) - 0.18 * zscore(out["drawdown_from_60d_peak"].abs())
    out["ai_win_score"] = 0.20 * zscore(out["mom20"]) + 0.30 * zscore(out["mom60"]) + 0.20 * zscore(out["mom120"]) + 0.15 * zscore(out["trend"]) - 0.15 * zscore(out["vol60"]) + out["forward_quality_score"]
    out["ai_win_score_100"] = (out["ai_win_score"].rank(pct=True) * 100).clip(0, 100)
    return out


def zscore(series: pd.Series) -> pd.Series:
    clean = series.replace([np.inf, -np.inf], np.nan)
    std = clean.std(skipna=True)
    if std is None or pd.isna(std) or math.isclose(float(std), 0.0):
        return pd.Series(0.0, index=series.index)
    return (clean - clean.mean(skipna=True)) / std


def previous_trading_day(calendar: list[date], day: date) -> date | None:
    prev = [d for d in calendar if d < day]
    return prev[-1] if prev else None


def close_on_or_before(df: pd.DataFrame, day: date) -> float | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    sliced = df[df.index.date <= day]
    if sliced.empty:
        return None
    value = pd.to_numeric(sliced["Close"], errors="coerce").dropna()
    return float(value.iloc[-1]) if not value.empty else None


def open_on_or_after(df: pd.DataFrame, day: date) -> float | None:
    if df is None or df.empty:
        return None
    col = "Open" if "Open" in df.columns else "Close"
    sliced = df[df.index.date >= day]
    if sliced.empty:
        return None
    value = pd.to_numeric(sliced[col], errors="coerce").dropna()
    return float(value.iloc[0]) if not value.empty else None


def close_on_exact_or_before(df: pd.DataFrame, day: date) -> float | None:
    return close_on_or_before(df, day)


def write_recommendation_file(path: Path, picks: list[dict[str, Any]], signal_day: date, top_n: int) -> None:
    payload = {
        "metadata": {
            "trigger_mode": "morning",
            "trade_date": signal_day.strftime("%Y%m%d"),
            "source": "ai_win_public_fallback_backtest",
            "selected_top_n": top_n,
            "recommendation_policy": f"전일 종가 기준 AI WIN 백테스트 최적 상위 {top_n}개",
            "note": "전일 종가까지의 데이터로 신호를 만들고 다음 영업일 시초가 매수를 가정합니다.",
        },
        "AI WIN 전일종가 모멘텀 상위주": picks,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_portfolio(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, calendar: list[date], start: date, end: date, top_n: int) -> dict[str, Any]:
    days = [d for d in calendar if start <= d <= end]
    lots: list[dict[str, Any]] = []
    equity_curve = []
    for buy_day in days:
        signal_day = previous_trading_day(calendar, buy_day)
        if not signal_day:
            continue
        for item in make_signal_picks(histories, listing, signal_day, top_n):
            df = histories.get(item["code"])
            entry = open_on_or_after(df, buy_day) if df is not None else None
            if not entry or entry <= 0:
                continue
            lots.append({
                "ticker": item["code"],
                "company_name": item.get("name") or item["code"],
                "entry_date": buy_day,
                "signal_date": signal_day,
                "entry": float(entry),
                "stop_pct": float(item.get("stop_loss_pct") or 5.0),
                "target": float(item.get("target_price") or entry * 1.3),
            })
        invested = sum(lot["entry"] for lot in lots)
        value = 0.0
        for lot in lots:
            current = close_on_exact_or_before(histories.get(lot["ticker"], pd.DataFrame()), buy_day) or lot["entry"]
            value += current
        ret = value / invested - 1 if invested > 0 else 0.0
        equity_curve.append({"date": buy_day.strftime("%Y-%m-%d"), "invested": round(invested, 2), "net_value": round(value, 2), "return_pct": f"{ret * 100:.2f}%", "open_positions": len({lot["ticker"] for lot in lots}), "open_units": len(lots)})

    holdings_map: dict[str, dict[str, Any]] = {}
    for lot in lots:
        current = close_on_or_before(histories.get(lot["ticker"], pd.DataFrame()), end) or lot["entry"]
        h = holdings_map.setdefault(lot["ticker"], {"ticker": lot["ticker"], "company_name": lot["company_name"], "units": 0, "cost": 0.0, "value": 0.0, "stop_total": 0.0, "target_total": 0.0, "last_signal_date": lot["signal_date"]})
        h["units"] += 1
        h["cost"] += lot["entry"]
        h["value"] += current
        h["stop_total"] += lot["entry"] * (1 - lot["stop_pct"] / 100)
        h["target_total"] += lot["target"]
        h["last_signal_date"] = max(h["last_signal_date"], lot["signal_date"])

    holdings = []
    for h in holdings_map.values():
        units = h["units"]
        avg_entry = h["cost"] / units
        avg_current = h["value"] / units
        holdings.append({
            "ticker": h["ticker"],
            "company_name": h["company_name"],
            "units": units,
            "weight_units": units,
            "avg_entry": round(avg_entry, 2),
            "current_price": round(avg_current, 2),
            "market_value": round(h["value"], 2),
            "return_pct": f"{(h['value'] / h['cost'] - 1) * 100:.2f}%" if h["cost"] > 0 else "0.00%",
            "avg_stop": round(h["stop_total"] / units, 2),
            "avg_target": round(h["target_total"] / units, 2),
            "last_signal_date": h["last_signal_date"].strftime("%Y-%m-%d"),
        })
    holdings.sort(key=lambda x: x["market_value"], reverse=True)
    total_invested = sum(lot["entry"] for lot in lots)
    net_value = sum(h["market_value"] for h in holdings)
    total_return = net_value / total_invested - 1 if total_invested > 0 else 0.0
    elapsed = max((end - start).days, 1)
    annualized = math.pow(1 + total_return, 365 / elapsed) - 1 if total_return > -1 else -1
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "price_source": "previous_close_signal_next_open_buy",
        "rule": f"전일 종가 기준 상위 {top_n}개 신호를 다음 영업일 시초가에 매수하고 종가로 평가하는 모의 포트폴리오",
        "recommendation_count": len(lots),
        "trade_count": len(lots),
        "summary": {"total_invested": round(total_invested, 2), "net_value": round(net_value, 2), "realized_cash": 0.0, "realized_pnl": 0.0, "total_return_pct": f"{total_return * 100:.2f}%", "annualized_return_pct": f"{annualized * 100:.2f}%", "open_positions": len(holdings), "open_units": len(lots), "sell_signal_count": 0},
        "holdings": holdings,
        "sell_signals": [],
        "equity_curve": equity_curve,
        "recommendation_weights": [{"ticker": h["ticker"], "company_name": h["company_name"], "units": h["units"]} for h in holdings],
    }


def result_dict(result: BacktestResult) -> dict[str, Any]:
    return {"period_months": result.period_months, "top_n": result.top_n, "start": result.start.strftime("%Y-%m-%d"), "end": result.end.strftime("%Y-%m-%d"), "total_return": round(result.total_return, 6), "cagr": round(result.cagr, 6), "mdd": round(result.mdd, 6), "trades": result.trades}


if __name__ == "__main__":
    raise SystemExit(main())
