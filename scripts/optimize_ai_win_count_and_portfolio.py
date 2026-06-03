#!/usr/bin/env python3
"""Optimize AI WIN recommendation count with realistic portfolio simulation."""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECOMMENDATION = ROOT / "dashboard" / "prism_latest_morning.json"
DEFAULT_STRATEGY = ROOT / "dashboard" / "adaptive_strategy.json"
DEFAULT_PORTFOLIO = ROOT / "dashboard" / "portfolio_status.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize AI WIN count and rebuild portfolio")
    parser.add_argument("--recommendation-file", default=str(DEFAULT_RECOMMENDATION))
    parser.add_argument("--strategy-file", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--portfolio-file", default=str(DEFAULT_PORTFOLIO))
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--universe-size", type=int, default=180)
    parser.add_argument("--min-top-n", type=int, default=1)
    parser.add_argument("--max-top-n", type=int, default=8)
    parser.add_argument("--period-months", default="24,18,12,6,3")
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()

    try:
        import FinanceDataReader as fdr
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "FinanceDataReader_missing", "next_action": ".venv/bin/python -m pip install finance-datareader", "error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False))
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
    results: list[dict[str, Any]] = []
    for months in periods:
        start = as_of - timedelta(days=months * 31)
        for top_n in top_values:
            result = run_backtest(histories, listing, calendar, start, as_of, top_n, months)
            if result:
                results.append(result)

    if not results:
        print(json.dumps({"ok": False, "reason": "no_backtest_result"}, ensure_ascii=False))
        return 2

    best = choose_best_result(results)
    latest_signal_day = previous_trading_day(calendar, as_of) or as_of
    latest_buy_day = next_trading_day(calendar, latest_signal_day) or as_of
    latest_picks = [enrich_pick(x, latest_signal_day, latest_buy_day) for x in make_signal_picks(histories, listing, latest_signal_day, int(best["top_n"]))]
    rec_path = Path(args.recommendation_file)
    write_recommendation_file(rec_path, latest_picks, latest_signal_day, latest_buy_day, int(best["top_n"]))

    strategy = {
        "source": "ai_win_realistic_backtest_intraday_sells",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_period_months": best["period_months"],
        "selected_top_n": best["top_n"],
        "score_threshold": f"top {best['top_n']}",
        "stop_multiplier": 2.5,
        "take_profit_trigger_pct": 30.0,
        "take_profit_trailing_pct": 10.0,
        "best_summary": result_dict(best),
        "tested": [result_dict(x) for x in sorted(results, key=lambda item: (-selection_score(item), item["top_n"]))[:30]],
        "note": "전일 종가 신호, 다음 거래일 시초가 편입, 장중 고가/저가 기준 손절/목표가/트레일링 매도, 매도 당일 동일 종목 재진입 차단을 적용해 top-N을 고릅니다.",
    }
    Path(args.strategy_file).write_text(json.dumps(strategy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    portfolio = simulate_portfolio(histories, listing, calendar, portfolio_start, as_of, int(best["top_n"]), include_history=True)
    Path(args.portfolio_file).write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "selected_top_n": best["top_n"],
        "selected_period_months": best["period_months"],
        "backtest_cagr_pct": round(best["cagr"] * 100, 2),
        "backtest_total_return_pct": round(best["total_return"] * 100, 2),
        "backtest_mdd_pct": round(best["mdd"] * 100, 2),
        "portfolio_return_pct": portfolio["summary"]["total_return_pct"],
        "recommendation_file": str(rec_path),
        "strategy_file": str(args.strategy_file),
        "portfolio_file": str(args.portfolio_file),
    }, ensure_ascii=False, indent=2))
    return 0


def choose_best_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    return max(results, key=lambda item: (selection_score(item), item["cagr"], item["total_return"], -item["top_n"]))


def selection_score(result: dict[str, Any]) -> float:
    return float(result["cagr"]) + float(result["mdd"]) * 0.75 + float(result["win_rate"]) * 0.05


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


def run_backtest(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, calendar: list[date], start: date, end: date, top_n: int, period_months: int) -> dict[str, Any] | None:
    if len([d for d in calendar if start <= d <= end]) < 30:
        return None
    portfolio = simulate_portfolio(histories, listing, calendar, start, end, top_n, include_history=False)
    trades = int(portfolio["trade_count"])
    if trades == 0:
        return None
    summary = portfolio["summary"]
    return {
        "period_months": period_months,
        "top_n": top_n,
        "start": start,
        "end": end,
        "total_return": parse_pct(summary["total_return_pct"]) / 100,
        "cagr": parse_pct(summary["annualized_return_pct"]) / 100,
        "mdd": float(portfolio.get("max_drawdown", 0.0)),
        "trades": trades,
        "win_rate": float(portfolio.get("win_rate", 0.0)),
        "sell_count": int(summary.get("sell_signal_count", 0)),
    }


def simulate_portfolio(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, calendar: list[date], start: date, end: date, top_n: int, include_history: bool) -> dict[str, Any]:
    days = [d for d in calendar if start <= d <= end]
    lots: list[dict[str, Any]] = []
    sell_signals_raw: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    history_items: list[dict[str, Any]] = []
    realized_cash = 0.0
    realized_cost = 0.0
    wins = 0
    losses = 0

    for buy_day in days:
        signal_day = previous_trading_day(calendar, buy_day)
        if not signal_day:
            continue
        sold_today: set[str] = set()

        for lot in lots:
            if not lot.get("open", True):
                continue
            reason, exit_price = sell_reason(histories.get(lot["ticker"]), lot, buy_day)
            if not reason:
                continue
            lot["open"] = False
            lot["exit"] = exit_price
            lot["exit_date"] = buy_day
            realized_cash += exit_price
            realized_cost += lot["entry"]
            sold_today.add(lot["ticker"])
            if exit_price >= lot["entry"]:
                wins += 1
            else:
                losses += 1
            sell_signals_raw.append({
                "date": buy_day.strftime("%Y-%m-%d"),
                "ticker": lot["ticker"],
                "company_name": lot["company_name"],
                "reason": reason,
                "entry_date": lot["entry_date"].strftime("%Y-%m-%d"),
                "signal_date": lot["signal_date"].strftime("%Y-%m-%d"),
                "entry_price": round(lot["entry"], 2),
                "exit_price": round(exit_price, 2),
                "realized_return_pct": f"{(exit_price / lot['entry'] - 1) * 100:.2f}%",
            })

        picks = make_signal_picks(histories, listing, signal_day, top_n)
        if include_history:
            history_items.append({
                "date": buy_day.strftime("%Y-%m-%d"),
                "metadata": {
                    "trigger_mode": "daily",
                    "trade_date": buy_day.strftime("%Y%m%d"),
                    "date_label": buy_day.strftime("%Y-%m-%d"),
                    "signal_at": f"{signal_day:%Y-%m-%d} 종가",
                    "buy_at": f"{buy_day:%Y-%m-%d} 시초가",
                    "signal_basis": "전일 종가 기준",
                    "source": "ai_win_realistic_backtest_intraday_sells",
                    "recommendation_policy": f"실전형 백테스트 최적 상위 {top_n}개",
                },
                "sections": {"AI WIN 일간 추천 후보": [enrich_pick(x, signal_day, buy_day) for x in picks]},
            })

        for item in picks:
            if item["code"] in sold_today:
                continue
            df = histories.get(item["code"])
            entry = open_on_or_after(df, buy_day) if df is not None else None
            if not entry or entry <= 0:
                continue
            stop_pct = float(item.get("stop_loss_pct") or 5.0)
            lots.append({
                "ticker": item["code"],
                "company_name": item.get("name") or item["code"],
                "entry_date": buy_day,
                "signal_date": signal_day,
                "entry": float(entry),
                "stop": float(entry) * (1 - stop_pct / 100),
                "target": float(entry) * 1.3,
                "peak": float(entry),
                "open": True,
            })

        invested = sum(lot["entry"] for lot in lots)
        open_value = sum((close_on_or_before(histories.get(lot["ticker"]), buy_day) or lot["entry"]) for lot in lots if lot.get("open", True))
        net_value = open_value + realized_cash
        ret = net_value / invested - 1 if invested else 0.0
        equity_curve.append({
            "date": buy_day.strftime("%Y-%m-%d"),
            "invested": round(invested, 2),
            "net_value": round(net_value, 2),
            "return_pct": f"{ret * 100:.2f}%",
            "open_positions": len({l["ticker"] for l in lots if l.get("open", True)}),
            "open_units": len([l for l in lots if l.get("open", True)]),
        })

    holdings = build_holdings(lots, histories, end)
    total_cost = sum(lot["entry"] for lot in lots)
    open_value = sum(h["market_value"] for h in holdings)
    net_value = open_value + realized_cash
    total_return = net_value / total_cost - 1 if total_cost else 0.0
    elapsed = max((end - start).days, 1)
    annualized = math.pow(1 + total_return, 365 / elapsed) - 1 if total_return > -1 else -1
    max_drawdown = calculate_mdd(equity_curve)
    sell_signals = group_sell_signals(sell_signals_raw)
    recommendation_count = sum(len(next(iter(item.get("sections", {}).values()), [])) for item in history_items) if include_history else len(lots)

    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "price_source": "previous_close_signal_next_open_entry_intraday_sell_rules",
        "rule": f"전일 종가 기준 상위 {top_n}개 신호를 다음 거래일 시초가에 편입하고 장중 저가/고가 기준 손절/목표가/트레일링 매도를 반영",
        "recommendation_count": recommendation_count,
        "trade_count": len(lots),
        "max_drawdown": round(max_drawdown, 6),
        "win_rate": round(wins / max(wins + losses, 1), 6),
        "summary": {
            "total_invested": round(total_cost, 2),
            "net_value": round(net_value, 2),
            "realized_cash": round(realized_cash, 2),
            "realized_pnl": round(realized_cash - realized_cost, 2),
            "total_return_pct": f"{total_return * 100:.2f}%",
            "annualized_return_pct": f"{annualized * 100:.2f}%",
            "open_positions": len(holdings),
            "open_units": sum(h["units"] for h in holdings),
            "sell_signal_count": len(sell_signals),
        },
        "holdings": sorted(holdings, key=lambda x: x["market_value"], reverse=True),
        "sell_signals": sell_signals[-20:],
        "equity_curve": equity_curve[-30:] if len(equity_curve) > 30 else equity_curve,
        "equity_curve_window": "최근 30일" if len(equity_curve) > 30 else f"{start.strftime('%Y-%m-%d')}부터 현재까지",
        "recommendation_history": history_items[-30:],
    }


def build_holdings(lots: list[dict[str, Any]], histories: dict[str, pd.DataFrame], end: date) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for lot in lots:
        if not lot.get("open", True):
            continue
        current = close_on_or_before(histories.get(lot["ticker"]), end) or lot["entry"]
        g = grouped.setdefault(lot["ticker"], {"ticker": lot["ticker"], "company_name": lot["company_name"], "units": 0, "cost": 0.0, "value": 0.0, "stop": 0.0, "target": 0.0, "entry_dates": [], "last_signal_date": lot["signal_date"]})
        g["units"] += 1
        g["cost"] += lot["entry"]
        g["value"] += current
        g["stop"] += lot["stop"]
        g["target"] += lot["target"]
        g["entry_dates"].append(lot["entry_date"].strftime("%Y-%m-%d"))
        g["last_signal_date"] = max(g["last_signal_date"], lot["signal_date"])

    holdings = []
    for g in grouped.values():
        units = g["units"]
        holdings.append({
            "ticker": g["ticker"],
            "company_name": g["company_name"],
            "units": units,
            "weight_units": units,
            "entry_dates": g["entry_dates"],
            "avg_entry": round(g["cost"] / units, 2),
            "current_price": round(g["value"] / units, 2),
            "market_value": round(g["value"], 2),
            "return_pct": f"{(g['value'] / g['cost'] - 1) * 100:.2f}%",
            "avg_stop": round(g["stop"] / units, 2),
            "avg_target": round(g["target"] / units, 2),
            "last_signal_date": g["last_signal_date"].strftime("%Y-%m-%d"),
        })
    return holdings


def sell_reason(df: pd.DataFrame | None, lot: dict[str, Any], day: date) -> tuple[str | None, float]:
    bar = ohlc_for_date(df, day)
    if not bar:
        current = close_on_or_before(df, day) or lot["entry"]
        lot["peak"] = max(float(lot.get("peak", lot["entry"])), current)
        return close_based_sell_reason(lot, current)

    high = bar["high"]
    low = bar["low"]
    close = bar["close"]
    lot["peak"] = max(float(lot.get("peak", lot["entry"])), high, close)

    # Conservative same-day ordering: if both stop and target are touched, count the stop first.
    if low <= lot["stop"]:
        return "손절가 이탈", float(lot["stop"])
    if high >= lot["target"]:
        return "목표가 도달", float(lot["target"])
    trailing_stop = float(lot["peak"]) * 0.9
    if lot["peak"] > lot["entry"] * 1.12 and low <= trailing_stop:
        return "고점 대비 10% 반락", trailing_stop
    return None, close


def close_based_sell_reason(lot: dict[str, Any], current: float) -> tuple[str | None, float]:
    if current <= lot["stop"]:
        return "손절가 이탈", current
    if current >= lot["target"]:
        return "목표가 도달", current
    if lot["peak"] > lot["entry"] * 1.12 and current <= lot["peak"] * 0.9:
        return "고점 대비 10% 반락", current
    return None, current


def make_signal_picks(histories: dict[str, pd.DataFrame], listing: pd.DataFrame, signal_day: date, top_n: int) -> list[dict[str, Any]]:
    scored = score_universe(histories, listing, signal_day)
    if scored.empty:
        return []
    picks = scored.sort_values("ai_win_score", ascending=False).head(top_n)
    rows = []
    for rank, (ticker, row) in enumerate(picks.iterrows(), 1):
        latest = float(row["current_price"])
        stop_pct = min(max(float(row.get("vol60", 0.03)) / math.sqrt(252) * math.sqrt(5) * 2.5, 0.045), 0.18)
        target_price = latest * 1.3
        components = score_components(row)
        rows.append({
            "rank": rank,
            "code": ticker,
            "name": row.get("name") or ticker,
            "trigger_type": "AI WIN 전일종가 모멘텀 상위주",
            "current_price": round(latest, 0),
            "change_rate": round(float(row.get("mom20", 0.0)) * 100, 2),
            "profit_score": round(float(row["ai_win_score"]), 4),
            "adaptive_profit_score": round(float(row["ai_win_score"]), 4),
            "ai_win_score": round(float(row["ai_win_score"]), 4),
            "ai_win_score_100": round(float(row["ai_win_score_100"]), 2),
            "forward_quality_score": round(float(row["forward_quality_score"]), 4),
            "score_components": components,
            "recommendation_reason": recommendation_reason(components),
            "risk_note": risk_note(components),
            "stop_loss_pct": round(stop_pct * 100, 2),
            "stop_loss_price": round(latest * (1 - stop_pct), 0),
            "target_price": round(target_price, 0),
            "take_profit_trigger_pct": 30.0,
            "take_profit_trailing_pct": 10.0,
            "source": "ai_win_realistic_backtest_intraday_sells",
        })
    return rows


def score_components(row: pd.Series) -> dict[str, float]:
    return {
        "mom20_pct": round(float(row.get("mom20", 0.0)) * 100, 2),
        "mom60_pct": round(float(row.get("mom60", 0.0)) * 100, 2),
        "mom120_pct": round(float(row.get("mom120", 0.0)) * 100, 2),
        "trend_pct": round(float(row.get("trend", 0.0)) * 100, 2),
        "hit20_pct": round(float(row.get("hit20", 0.0)) * 100, 2),
        "turnover_change_pct": round(float(row.get("turnover_change", 0.0)) * 100, 2),
        "vol60_pct": round(float(row.get("vol60", 0.0)) * 100, 2),
        "drawdown_from_60d_peak_pct": round(float(row.get("drawdown_from_60d_peak", 0.0)) * 100, 2),
        "risk_score": round(float(row.get("risk_score", 0.0)), 4),
    }


def recommendation_reason(c: dict[str, float]) -> str:
    reasons = []
    if c["mom60_pct"] > 0:
        reasons.append(f"60일 모멘텀 {c['mom60_pct']:.1f}%")
    if c["mom120_pct"] > 0:
        reasons.append(f"120일 추세 {c['mom120_pct']:.1f}%")
    if c["turnover_change_pct"] > 0:
        reasons.append(f"최근 거래대금 {c['turnover_change_pct']:.1f}% 증가")
    if c["hit20_pct"] >= 50:
        reasons.append(f"20일 상승일 비율 {c['hit20_pct']:.0f}%")
    return " · ".join(reasons[:3]) if reasons else "상대 점수 우위"


def risk_note(c: dict[str, float]) -> str:
    notes = []
    if c["vol60_pct"] >= 55:
        notes.append("변동성 높음")
    if c["drawdown_from_60d_peak_pct"] <= -20:
        notes.append("60일 고점 대비 낙폭 큼")
    if c["mom20_pct"] < 0:
        notes.append("단기 모멘텀 약함")
    return " · ".join(notes) if notes else "주요 리스크 정상 범위"


def enrich_pick(item: dict[str, Any], signal_day: date, buy_day: date) -> dict[str, Any]:
    row = dict(item)
    price = float(row.get("current_price") or 0)
    stop_pct = float(row.get("stop_loss_pct") or 5.0)
    stop = float(row.get("stop_loss_price") or price * (1 - stop_pct / 100))
    target = float(row.get("target_price") or price * 1.3)
    row["previous_close_price"] = round(price, 0)
    row["signal_price"] = round(price, 0)
    row["signal_basis"] = "전일 종가 기준"
    row["signal_at"] = f"{signal_day:%Y-%m-%d} 종가"
    row["buy_at"] = f"{buy_day:%Y-%m-%d} 시초가"
    row["entry_plan"] = row["buy_at"]
    row["change_basis"] = "최근 1개월 모멘텀"
    row["score_basis"] = "AI WIN 원점수는 모멘텀, 추세, 거래대금 변화, 변동성, 낙폭 리스크를 합산한 상대 점수입니다."
    row["stop_loss_price"] = round(stop, 0)
    row["target_price"] = round(target, 0)
    row["target_return_pct"] = round((target / price - 1) * 100, 2) if price else 0.0
    return row


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


def next_trading_day(calendar: list[date], day: date) -> date | None:
    later = [d for d in calendar if d > day]
    return later[0] if later else None


def close_on_or_before(df: pd.DataFrame | None, day: date) -> float | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    sliced = df[df.index.date <= day]
    if sliced.empty:
        return None
    value = pd.to_numeric(sliced["Close"], errors="coerce").dropna()
    return float(value.iloc[-1]) if not value.empty else None


def ohlc_for_date(df: pd.DataFrame | None, day: date) -> dict[str, float] | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    rows = df[df.index.date == day]
    if rows.empty:
        return None
    row = rows.iloc[0]
    close = to_float(row.get("Close"))
    if close is None:
        return None
    open_ = to_float(row.get("Open")) or close
    high = to_float(row.get("High")) or max(open_, close)
    low = to_float(row.get("Low")) or min(open_, close)
    return {"open": open_, "high": high, "low": low, "close": close}


def open_on_or_after(df: pd.DataFrame | None, day: date) -> float | None:
    if df is None or df.empty:
        return None
    col = "Open" if "Open" in df.columns else "Close"
    sliced = df[df.index.date >= day]
    if sliced.empty:
        return None
    value = pd.to_numeric(sliced[col], errors="coerce").dropna()
    return float(value.iloc[0]) if not value.empty else None


def to_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def write_recommendation_file(path: Path, picks: list[dict[str, Any]], signal_day: date, buy_day: date, top_n: int) -> None:
    payload = {
        "metadata": {
            "trigger_mode": "morning",
            "trade_date": signal_day.strftime("%Y%m%d"),
            "source": "ai_win_realistic_backtest_intraday_sells",
            "selected_top_n": top_n,
            "recommendation_policy": f"실전형 백테스트 최적 상위 {top_n}개",
            "signal_at": f"{signal_day:%Y-%m-%d} 종가",
            "buy_at": f"{buy_day:%Y-%m-%d} 시초가",
            "note": "전일 종가까지의 데이터로 신호를 만들고 다음 영업일 시초가 매수를 가정합니다.",
        },
        "AI WIN 전일종가 모멘텀 상위주": picks,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def calculate_mdd(equity_curve: list[dict[str, Any]]) -> float:
    peak = None
    mdd = 0.0
    for row in equity_curve:
        value = float(row.get("net_value") or 0)
        if value <= 0:
            continue
        peak = value if peak is None else max(peak, value)
        mdd = min(mdd, value / peak - 1)
    return mdd


def parse_pct(value: Any) -> float:
    try:
        return float(str(value).replace("%", ""))
    except Exception:
        return 0.0


def group_sell_signals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["date"], row["ticker"], row["reason"])
        g = grouped.setdefault(key, {"date": row["date"], "ticker": row["ticker"], "company_name": row["company_name"], "reason": row["reason"], "entry_dates": [], "signal_dates": [], "units": 0, "realized_returns": []})
        g["entry_dates"].append(row["entry_date"])
        g["signal_dates"].append(row["signal_date"])
        g["units"] += 1
        g["realized_returns"].append(parse_pct(row["realized_return_pct"]))
    out = []
    for g in grouped.values():
        avg = sum(g["realized_returns"]) / len(g["realized_returns"])
        g["entry_dates"] = sorted(set(g["entry_dates"]))
        g["signal_dates"] = sorted(set(g["signal_dates"]))
        g["realized_return_pct"] = f"{avg:.2f}%"
        del g["realized_returns"]
        out.append(g)
    return sorted(out, key=lambda x: x["date"])


def result_dict(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "period_months": result["period_months"],
        "top_n": result["top_n"],
        "start": result["start"].strftime("%Y-%m-%d"),
        "end": result["end"].strftime("%Y-%m-%d"),
        "total_return": round(result["total_return"], 6),
        "cagr": round(result["cagr"], 6),
        "mdd": round(result["mdd"], 6),
        "trades": result["trades"],
        "win_rate": round(result["win_rate"], 6),
        "sell_count": result["sell_count"],
        "selection_score": round(selection_score(result), 6),
    }


if __name__ == "__main__":
    raise SystemExit(main())
