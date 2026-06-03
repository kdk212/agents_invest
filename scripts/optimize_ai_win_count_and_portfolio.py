#!/usr/bin/env python3
"""Optimize AI WIN recommendation count and rebuild dashboard portfolio.

This public-data fallback is intentionally independent from KRX direct login. It
uses FinanceDataReader OHLCV, tests top-N recommendation counts across recent
24/18/12 month windows, writes dashboard/adaptive_strategy.json, trims the
latest recommendation file to the selected count, and rebuilds the mock
portfolio from 2026-06-01.
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
    periods = [int(x.strip()) for x in args.period_months.split(",") if x.strip()]
    top_values = list(range(args.min_top_n, args.max_top_n + 1))

    listing = load_listing(fdr)
    tickers = select_universe(listing, args.universe_size)
    histories = load_histories(fdr, tickers, as_of - timedelta(days=max(periods) * 31 + 430), as_of)
    if not histories:
        print(json.dumps({"ok": False, "reason": "no_price_history"}, ensure_ascii=False))
        return 2

    results: list[BacktestResult] = []
    for months in periods:
        start = as_of - timedelta(days=months * 31)
        for top_n in top_values:
            result = run_backtest(histories, listing, start, as_of, top_n)
            if result:
                results.append(result)

    if not results:
        print(json.dumps({"ok": False, "reason": "no_backtest_result"}, ensure_ascii=False))
        return 2

    best = max(results, key=lambda item: (item.cagr, item.total_return, -item.top_n))
    rec_path = Path(args.recommendation_file)
    rec_data = json.loads(rec_path.read_text(encoding="utf-8"))
    trim_recommendations(rec_data, best.top_n)
    rec_path.write_text(json.dumps(rec_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
        "note": "추천 개수 3~8개와 최근 24/18/12개월 구간을 공개 OHLCV로 비교해 CAGR이 가장 높은 조합을 선택합니다.",
    }
    Path(args.strategy_file).write_text(json.dumps(strategy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    portfolio = build_portfolio(rec_data, histories, pd.to_datetime(args.portfolio_start).date(), as_of, best.top_n)
    Path(args.portfolio_file).write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "selected_top_n": best.top_n,
        "selected_period_months": best.period_months,
        "backtest_cagr_pct": round(best.cagr * 100, 2),
        "backtest_total_return_pct": round(best.total_return * 100, 2),
        "portfolio_return_pct": portfolio["summary"]["total_return_pct"],
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


def run_backtest(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, start: date, end: date, top_n: int) -> BacktestResult | None:
    calendar = sorted({idx.date() for df in histories.values() for idx in df.index if start <= idx.date() <= end})
    if len(calendar) < 40:
        return None
    value = 1.0
    peak = 1.0
    mdd = 0.0
    trades = 0
    step = 5
    for i in range(0, len(calendar) - step, step):
        day = calendar[i]
        next_day = calendar[i + step]
        scored = score_universe(histories, listing, day)
        if scored.empty:
            continue
        picks = scored.sort_values("ai_win_score", ascending=False).head(top_n)
        returns = []
        for ticker in picks.index:
            df = histories.get(ticker)
            if df is None:
                continue
            before = close_on_or_before(df, day)
            after = close_on_or_before(df, next_day)
            if before and after and before > 0:
                returns.append(after / before - 1)
        if not returns:
            continue
        value *= 1 + float(np.mean(returns))
        peak = max(peak, value)
        mdd = min(mdd, value / peak - 1)
        trades += len(returns)
    if trades == 0:
        return None
    days = max((end - start).days, 1)
    total_return = value - 1
    cagr = math.pow(value, 365 / days) - 1 if value > 0 else -1
    return BacktestResult(period_months=round((end - start).days / 30), top_n=top_n, start=start, end=end, total_return=total_return, cagr=cagr, mdd=mdd, trades=trades)


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
    return {
        "code": ticker,
        "name": name,
        "current_price": latest,
        "mom20": float(mom20),
        "mom60": float(mom60),
        "mom120": float(mom120),
        "trend": float(trend),
        "vol60": vol60,
        "hit20": hit20,
        "pullback_resilience": pullback_resilience,
        "acceleration": acceleration,
        "turnover_change": turnover_change,
        "drawdown_from_60d_peak": drawdown,
        "risk_score": float(risk_score),
    }


def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.replace([np.inf, -np.inf], np.nan).copy()
    out["forward_quality_score"] = (
        0.22 * zscore(out["hit20"])
        + 0.18 * zscore(out["pullback_resilience"])
        + 0.18 * zscore(out["acceleration"])
        + 0.12 * zscore(out["turnover_change"].clip(-1, 5))
        - 0.22 * zscore(out["risk_score"])
        - 0.18 * zscore(out["drawdown_from_60d_peak"].abs())
    )
    out["ai_win_score"] = (
        0.20 * zscore(out["mom20"])
        + 0.30 * zscore(out["mom60"])
        + 0.20 * zscore(out["mom120"])
        + 0.15 * zscore(out["trend"])
        - 0.15 * zscore(out["vol60"])
        + out["forward_quality_score"]
    )
    out["ai_win_score_100"] = (out["ai_win_score"].rank(pct=True) * 100).clip(0, 100)
    return out


def zscore(series: pd.Series) -> pd.Series:
    clean = series.replace([np.inf, -np.inf], np.nan)
    std = clean.std(skipna=True)
    if std is None or pd.isna(std) or math.isclose(float(std), 0.0):
        return pd.Series(0.0, index=series.index)
    return (clean - clean.mean(skipna=True)) / std


def close_on_or_before(df: pd.DataFrame, day: date) -> float | None:
    sliced = df[df.index.date <= day]
    if sliced.empty:
        return None
    value = pd.to_numeric(sliced["Close"], errors="coerce").dropna()
    if value.empty:
        return None
    return float(value.iloc[-1])


def trim_recommendations(data: dict[str, Any], top_n: int) -> None:
    for key, value in list(data.items()):
        if key == "metadata" or not isinstance(value, list):
            continue
        value.sort(key=lambda x: x.get("ai_win_score_100") or x.get("adaptive_profit_score") or x.get("profit_score") or 0, reverse=True)
        data[key] = value[:top_n]
    meta = data.setdefault("metadata", {})
    meta["selected_top_n"] = top_n
    meta["recommendation_policy"] = f"AI WIN backtest optimized top {top_n}"


def flatten_recommendations(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, value in data.items():
        if key == "metadata" or not isinstance(value, list):
            continue
        for item in value:
            row = dict(item)
            row.setdefault("trigger_type", key)
            rows.append(row)
    rows.sort(key=lambda x: x.get("ai_win_score_100") or x.get("adaptive_profit_score") or x.get("profit_score") or 0, reverse=True)
    deduped = []
    seen = set()
    for row in rows:
        code = str(row.get("code") or row.get("ticker") or "").zfill(6)
        if not code or code in seen:
            continue
        seen.add(code)
        row["code"] = code
        deduped.append(row)
    return deduped


def business_days(start: date, end: date) -> list[date]:
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def build_portfolio(data: dict[str, Any], histories: dict[str, pd.DataFrame], start: date, end: date, top_n: int) -> dict[str, Any]:
    picks = flatten_recommendations(data)[:top_n]
    days = business_days(start, end)
    holdings = []
    total_invested = 0.0
    net_value = 0.0
    for item in picks:
        code = item["code"]
        entry = float(item.get("current_price") or item.get("price") or item.get("close") or item.get("price_at_signal") or 0)
        if entry <= 0:
            continue
        current = close_on_or_before(histories.get(code, pd.DataFrame()), end) or entry
        units = len(days)
        invested = entry * units
        value = current * units
        total_invested += invested
        net_value += value
        stop_pct = float(item.get("stop_loss_pct") or 5.0)
        target = float(item.get("target_price") or entry * 1.3)
        holdings.append({
            "ticker": code,
            "company_name": item.get("name") or item.get("company_name") or code,
            "units": units,
            "weight_units": units,
            "avg_entry": round(entry, 2),
            "current_price": round(current, 2),
            "market_value": round(value, 2),
            "return_pct": f"{((current / entry) - 1) * 100:.2f}%",
            "avg_stop": round(entry * (1 - stop_pct / 100), 2),
            "avg_target": round(target, 2),
            "last_signal_date": end.strftime("%Y-%m-%d"),
        })
    total_return = net_value / total_invested - 1 if total_invested > 0 else 0.0
    elapsed = max((end - start).days, 1)
    annualized = math.pow(1 + total_return, 365 / elapsed) - 1 if total_return > -1 else -1
    equity_curve = []
    for day in days:
        day_value = 0.0
        day_invested = 0.0
        for item in picks:
            code = item["code"]
            entry = float(item.get("current_price") or item.get("price") or item.get("close") or item.get("price_at_signal") or 0)
            if entry <= 0:
                continue
            current = close_on_or_before(histories.get(code, pd.DataFrame()), day) or entry
            units = days.index(day) + 1
            day_invested += entry * units
            day_value += current * units
        day_return = day_value / day_invested - 1 if day_invested > 0 else 0.0
        equity_curve.append({
            "date": day.strftime("%Y-%m-%d"),
            "invested": round(day_invested, 2),
            "net_value": round(day_value, 2),
            "return_pct": f"{day_return * 100:.2f}%",
            "open_positions": len(holdings),
            "open_units": sum(h["units"] for h in holdings),
        })
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "price_source": "ai_win_public_fallback_backtest",
        "rule": f"백테스트로 선택된 상위 {top_n}개 추천주를 2026-06-01부터 매 영업일 1단위씩 편입한 모의 포트폴리오",
        "recommendation_count": len(picks) * len(days),
        "trade_count": len(picks) * len(days),
        "summary": {
            "total_invested": round(total_invested, 2),
            "net_value": round(net_value, 2),
            "realized_cash": 0.0,
            "realized_pnl": 0.0,
            "total_return_pct": f"{total_return * 100:.2f}%",
            "annualized_return_pct": f"{annualized * 100:.2f}%",
            "open_positions": len(holdings),
            "open_units": sum(h["units"] for h in holdings),
            "sell_signal_count": 0,
        },
        "holdings": holdings,
        "sell_signals": [],
        "equity_curve": equity_curve,
        "recommendation_weights": [{"ticker": h["ticker"], "company_name": h["company_name"], "units": h["units"]} for h in holdings],
    }


def result_dict(result: BacktestResult) -> dict[str, Any]:
    return {
        "period_months": result.period_months,
        "top_n": result.top_n,
        "start": result.start.strftime("%Y-%m-%d"),
        "end": result.end.strftime("%Y-%m-%d"),
        "total_return": round(result.total_return, 6),
        "cagr": round(result.cagr, 6),
        "mdd": round(result.mdd, 6),
        "trades": result.trades,
    }


if __name__ == "__main__":
    raise SystemExit(main())
