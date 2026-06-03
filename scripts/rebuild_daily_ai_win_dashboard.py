#!/usr/bin/env python3
"""Build daily AI WIN recommendation history and portfolio dashboard files.

Policy:
- One buy recommendation set per trading day.
- Signal uses previous trading-day close data.
- Entry uses recommendation day's open price.
- Sell signals show the exact recommendation/entry date that was sold.
- Same-day re-entry is blocked after a sell signal.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
OPTIMIZER = ROOT / "scripts" / "optimize_ai_win_count_and_portfolio.py"


def load_opt():
    name = "ai_win_optimizer"
    spec = importlib.util.spec_from_file_location(name, OPTIMIZER)
    if spec is None or spec.loader is None:
        raise RuntimeError("optimizer module not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def close_on_or_before(df, day: date) -> float | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    sliced = df[df.index.date <= day]
    if sliced.empty:
        return None
    values = pd.to_numeric(sliced["Close"], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else None


def open_on_or_after(df, day: date) -> float | None:
    if df is None or df.empty:
        return None
    column = "Open" if "Open" in df.columns else "Close"
    sliced = df[df.index.date >= day]
    if sliced.empty:
        return None
    values = pd.to_numeric(sliced[column], errors="coerce").dropna()
    return float(values.iloc[0]) if not values.empty else None


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
    row["score_basis"] = "AI WIN 점수는 해당일 전체 후보군 내 백분위입니다. 날짜별 최상위 종목은 100점이 될 수 있습니다."
    row["stop_loss_price"] = round(stop, 0)
    row["target_price"] = round(target, 0)
    row["target_return_pct"] = round((target / price - 1) * 100, 2) if price else 0.0
    return row


def make_recommendation_payload(signal_day: date, buy_day: date, picks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"metadata": {"trigger_mode": "daily", "trade_date": buy_day.strftime("%Y%m%d"), "date_label": buy_day.strftime("%Y-%m-%d"), "signal_at": f"{signal_day:%Y-%m-%d} 종가", "buy_at": f"{buy_day:%Y-%m-%d} 시초가", "signal_basis": "전일 종가 기준", "source": "ai_win_daily_public_fallback", "recommendation_policy": "하루 1회 AI WIN 추천", "score_basis": "AI WIN 점수는 해당일 전체 후보군 내 백분위입니다."}, "AI WIN 일간 추천 후보": [enrich_pick(x, signal_day, buy_day) for x in picks]}


def sell_reason(df, lot: dict[str, Any], day: date) -> tuple[str | None, float]:
    current = close_on_or_before(df, day) or lot["entry"]
    lot["peak"] = max(float(lot.get("peak", lot["entry"])), current)
    if current <= lot["stop"]:
        return "손절가 이탈", current
    if current >= lot["target"]:
        return "목표가 도달", current
    if lot["peak"] > lot["entry"] * 1.12 and current <= lot["peak"] * 0.9:
        return "고점 대비 10% 반락", current
    return None, current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--universe-size", type=int, default=180)
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()

    try:
        import FinanceDataReader as fdr
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "FinanceDataReader_missing", "next_action": ".venv/bin/python -m pip install finance-datareader", "error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False))
        return 2

    opt = load_opt()
    start = pd.to_datetime(args.portfolio_start).date()
    as_of = pd.to_datetime(args.as_of_date).date() if args.as_of_date else date.today()
    listing = opt.load_listing(fdr)
    tickers = opt.select_universe(listing, args.universe_size)
    histories = opt.load_histories(fdr, tickers, start - timedelta(days=430), as_of)
    calendar = opt.trading_calendar(histories, start - timedelta(days=20), as_of)
    days = [d for d in calendar if start <= d <= as_of]

    lots: list[dict[str, Any]] = []
    sell_signals_raw: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    history_items: list[dict[str, Any]] = []

    for buy_day in days:
        signal_day = opt.previous_trading_day(calendar, buy_day)
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
            sold_today.add(lot["ticker"])
            sell_signals_raw.append({"date": buy_day.strftime("%Y-%m-%d"), "ticker": lot["ticker"], "company_name": lot["company_name"], "reason": reason, "entry_date": lot["entry_date"].strftime("%Y-%m-%d"), "signal_date": lot["signal_date"].strftime("%Y-%m-%d"), "entry_price": round(lot["entry"], 2), "exit_price": round(exit_price, 2), "realized_return_pct": f"{(exit_price / lot['entry'] - 1) * 100:.2f}%"})

        picks = opt.make_signal_picks(histories, listing, signal_day, args.top_n)
        payload = make_recommendation_payload(signal_day, buy_day, picks)
        history_items.append({"date": buy_day.strftime("%Y-%m-%d"), "metadata": payload["metadata"], "sections": {"AI WIN 일간 추천 후보": payload["AI WIN 일간 추천 후보"]}})

        for item in picks:
            if item["code"] in sold_today:
                continue
            entry = open_on_or_after(histories.get(item["code"]), buy_day)
            if not entry:
                continue
            lots.append({"ticker": item["code"], "company_name": item.get("name") or item["code"], "entry_date": buy_day, "signal_date": signal_day, "entry": entry, "stop": entry * (1 - float(item.get("stop_loss_pct") or 5.0) / 100), "target": entry * 1.3, "peak": entry, "open": True})

        invested = sum(l["entry"] for l in lots)
        value = 0.0
        for lot in lots:
            if lot.get("open", True):
                value += close_on_or_before(histories.get(lot["ticker"]), buy_day) or lot["entry"]
            else:
                value += lot.get("exit", lot["entry"])
        ret = value / invested - 1 if invested else 0.0
        equity.append({"date": buy_day.strftime("%Y-%m-%d"), "invested": round(invested, 2), "net_value": round(value, 2), "return_pct": f"{ret * 100:.2f}%", "open_positions": len({l["ticker"] for l in lots if l.get("open", True)}), "open_units": len([l for l in lots if l.get("open", True)])})

    if history_items:
        latest = history_items[-1]
        latest_payload = {"metadata": latest["metadata"], **latest["sections"]}
        (DASHBOARD / "prism_latest_morning.json").write_text(json.dumps(latest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (DASHBOARD / "prism_latest_afternoon.json").write_text(json.dumps(latest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    grouped: dict[str, dict[str, Any]] = {}
    realized_cash = 0.0
    realized_cost = 0.0
    for lot in lots:
        if not lot.get("open", True):
            realized_cash += lot.get("exit", lot["entry"])
            realized_cost += lot["entry"]
            continue
        current = close_on_or_before(histories.get(lot["ticker"]), as_of) or lot["entry"]
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
        holdings.append({"ticker": g["ticker"], "company_name": g["company_name"], "units": units, "weight_units": units, "entry_dates": g["entry_dates"], "avg_entry": round(g["cost"] / units, 2), "current_price": round(g["value"] / units, 2), "market_value": round(g["value"], 2), "return_pct": f"{(g['value'] / g['cost'] - 1) * 100:.2f}%", "avg_stop": round(g["stop"] / units, 2), "avg_target": round(g["target"] / units, 2), "last_signal_date": g["last_signal_date"].strftime("%Y-%m-%d")})

    sell_signals = group_sell_signals(sell_signals_raw)
    total_cost = sum(l["entry"] for l in lots)
    net_value = sum(h["market_value"] for h in holdings) + realized_cash
    total_return = net_value / total_cost - 1 if total_cost else 0.0
    elapsed = max((as_of - start).days, 1)
    annualized = math.pow(1 + total_return, 365 / elapsed) - 1 if total_return > -1 else -1

    portfolio = {"updated_at": datetime.now().isoformat(timespec="seconds"), "start_date": start.strftime("%Y-%m-%d"), "end_date": as_of.strftime("%Y-%m-%d"), "price_source": "daily_signal_previous_close_next_open", "rule": f"하루 1회, 전일 종가 기준 상위 {args.top_n}개 추천을 다음 거래일 시초가에 편입", "recommendation_count": len(history_items) * args.top_n, "trade_count": len(lots), "summary": {"total_invested": round(total_cost, 2), "net_value": round(net_value, 2), "realized_cash": round(realized_cash, 2), "realized_pnl": round(realized_cash - realized_cost, 2), "total_return_pct": f"{total_return * 100:.2f}%", "annualized_return_pct": f"{annualized * 100:.2f}%", "open_positions": len(holdings), "open_units": sum(h["units"] for h in holdings), "sell_signal_count": len(sell_signals)}, "holdings": sorted(holdings, key=lambda x: x["market_value"], reverse=True), "sell_signals": sell_signals[-20:], "equity_curve": equity[-30:] if len(equity) > 30 else equity, "equity_curve_window": "최근 30일" if len(equity) > 30 else f"{start.strftime('%Y-%m-%d')}부터 현재까지", "recommendation_history": history_items[-30:]}

    (DASHBOARD / "portfolio_status.json").write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DASHBOARD / "recommendation_history.json").write_text(json.dumps({"updated_at": datetime.now().isoformat(timespec="seconds"), "items": history_items[-30:]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "dates": [x["date"] for x in history_items[-5:]], "portfolio_return_pct": portfolio["summary"]["total_return_pct"], "open_positions": portfolio["summary"]["open_positions"], "sell_signal_count": portfolio["summary"]["sell_signal_count"]}, ensure_ascii=False, indent=2))
    return 0


def group_sell_signals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["date"], row["ticker"], row["reason"])
        g = grouped.setdefault(key, {"date": row["date"], "ticker": row["ticker"], "company_name": row["company_name"], "reason": row["reason"], "entry_dates": [], "signal_dates": [], "units": 0, "realized_returns": []})
        g["entry_dates"].append(row["entry_date"])
        g["signal_dates"].append(row["signal_date"])
        g["units"] += 1
        g["realized_returns"].append(float(str(row["realized_return_pct"]).replace("%", "")))
    out = []
    for g in grouped.values():
        avg = sum(g["realized_returns"]) / len(g["realized_returns"])
        g["entry_dates"] = sorted(set(g["entry_dates"]))
        g["signal_dates"] = sorted(set(g["signal_dates"]))
        g["realized_return_pct"] = f"{avg:.2f}%"
        del g["realized_returns"]
        out.append(g)
    return sorted(out, key=lambda x: x["date"])


if __name__ == "__main__":
    raise SystemExit(main())
