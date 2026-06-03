#!/usr/bin/env python3
"""Rebuild dashboard files for twice-daily AI WIN operation.

Morning signal: previous trading-day close data -> morning/open entry.
Afternoon signal: same-day latest daily data proxy -> afternoon close proxy entry.

FinanceDataReader does not provide reliable noon intraday prices for all KRX
stocks, so the afternoon route is labelled as a proxy until a real intraday feed
is connected. The portfolio still records two entry sessions per trading day and
technical sell signals twice per day.
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
OPTIMIZER_PATH = ROOT / "scripts" / "optimize_ai_win_count_and_portfolio.py"
DASHBOARD = ROOT / "dashboard"


def load_optimizer():
    module_name = "ai_win_optimizer"
    spec = importlib.util.spec_from_file_location(module_name, OPTIMIZER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("optimizer module not found")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild twice-daily AI WIN dashboard portfolio")
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--universe-size", type=int, default=180)
    parser.add_argument("--top-n", type=int, default=None)
    args = parser.parse_args()

    try:
        import FinanceDataReader as fdr
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "FinanceDataReader_missing", "next_action": ".venv/bin/python -m pip install finance-datareader", "error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False))
        return 2

    opt = load_optimizer()
    as_of = pd.to_datetime(args.as_of_date).date() if args.as_of_date else date.today()
    start = pd.to_datetime(args.portfolio_start).date()
    top_n = args.top_n or read_selected_top_n()

    listing = opt.load_listing(fdr)
    tickers = opt.select_universe(listing, args.universe_size)
    histories = opt.load_histories(fdr, tickers, start - timedelta(days=430), as_of)
    calendar = opt.trading_calendar(histories, start - timedelta(days=20), as_of)
    days = [d for d in calendar if start <= d <= as_of]

    latest_day = days[-1] if days else as_of
    prev = opt.previous_trading_day(calendar, latest_day) or latest_day
    morning_picks = opt.make_signal_picks(histories, listing, prev, top_n)
    afternoon_picks = opt.make_signal_picks(histories, listing, latest_day, top_n)
    write_recommendations(DASHBOARD / "prism_latest_morning.json", "morning", prev, morning_picks, top_n, "전일 종가 기준")
    write_recommendations(DASHBOARD / "prism_latest_afternoon.json", "afternoon", latest_day, afternoon_picks, top_n, "당일 12시 기준 대체: 공개 일봉 최신가 프록시")

    lots: list[dict[str, Any]] = []
    sell_signals: list[dict[str, Any]] = []
    equity_curve = []

    for day in days:
        sessions = []
        prev_day = opt.previous_trading_day(calendar, day)
        if prev_day:
            sessions.append(("오전", prev_day, day, "Open"))
        sessions.append(("오후", day, day, "Close"))

        for session_name, signal_day, entry_day, entry_col in sessions:
            apply_sell_signals(histories, lots, sell_signals, day, session_name)
            picks = opt.make_signal_picks(histories, listing, signal_day, top_n)
            for item in picks:
                df = histories.get(item["code"])
                entry = price_on_or_after(df, entry_day, entry_col)
                if not entry or entry <= 0:
                    continue
                lots.append({
                    "ticker": item["code"],
                    "company_name": item.get("name") or item["code"],
                    "entry_date": entry_day,
                    "entry_session": session_name,
                    "signal_date": signal_day,
                    "entry": float(entry),
                    "stop": float(entry) * (1 - float(item.get("stop_loss_pct") or 5.0) / 100),
                    "target": float(entry) * 1.3,
                    "peak": float(entry),
                    "open": True,
                })

        invested = sum(lot["entry"] for lot in lots)
        value = sum(current_value(histories, lot, day) for lot in lots)
        ret = value / invested - 1 if invested > 0 else 0.0
        equity_curve.append({
            "date": day.strftime("%Y-%m-%d"),
            "invested": round(invested, 2),
            "net_value": round(value, 2),
            "return_pct": f"{ret * 100:.2f}%",
            "open_positions": len({lot["ticker"] for lot in lots if lot.get("open", True)}),
            "open_units": len([lot for lot in lots if lot.get("open", True)]),
        })

    apply_sell_signals(histories, lots, sell_signals, as_of, "종가검증")
    portfolio = build_portfolio_json(histories, lots, sell_signals, equity_curve, start, as_of, top_n)
    (DASHBOARD / "portfolio_status.json").write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "top_n": top_n,
        "rule": portfolio["rule"],
        "portfolio_return_pct": portfolio["summary"]["total_return_pct"],
        "annualized_return_pct": portfolio["summary"]["annualized_return_pct"],
        "sell_signal_count": portfolio["summary"]["sell_signal_count"],
        "open_positions": portfolio["summary"]["open_positions"],
        "open_units": portfolio["summary"]["open_units"],
    }, ensure_ascii=False, indent=2))
    return 0


def read_selected_top_n() -> int:
    path = DASHBOARD / "adaptive_strategy.json"
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("selected_top_n")
            if value:
                return int(value)
        except Exception:
            pass
    return 3


def write_recommendations(path: Path, mode: str, signal_day: date, picks: list[dict[str, Any]], top_n: int, basis: str) -> None:
    enriched = []
    for item in picks:
        row = dict(item)
        price = float(row.get("current_price") or 0)
        stop = float(row.get("stop_loss_price") or price * (1 - float(row.get("stop_loss_pct") or 5.0) / 100))
        target = float(row.get("target_price") or price * 1.3)
        row["signal_basis"] = basis
        row["signal_time"] = "09:00" if mode == "morning" else "12:00"
        row["change_basis"] = "최근 1개월 모멘텀"
        row["stop_loss_price"] = round(stop, 0)
        row["target_return_pct"] = round((target / price - 1) * 100, 2) if price else 0.0
        row["target_price"] = round(target, 0)
        enriched.append(row)
    payload = {
        "metadata": {
            "trigger_mode": mode,
            "trade_date": signal_day.strftime("%Y%m%d"),
            "signal_at": f"{signal_day.strftime('%Y-%m-%d')} {'09:00' if mode == 'morning' else '12:00'}",
            "signal_basis": basis,
            "source": "ai_win_twice_daily_public_fallback",
            "selected_top_n": top_n,
            "recommendation_policy": f"AI WIN 백테스트 최적 상위 {top_n}개, {basis}",
        },
        "AI WIN 추천 후보": enriched,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def price_on_or_after(df: pd.DataFrame | None, day: date, col: str) -> float | None:
    if df is None or df.empty:
        return None
    column = col if col in df.columns else "Close"
    sliced = df[df.index.date >= day]
    if sliced.empty:
        return None
    values = pd.to_numeric(sliced[column], errors="coerce").dropna()
    return float(values.iloc[0]) if not values.empty else None


def close_on_or_before(df: pd.DataFrame | None, day: date) -> float | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    sliced = df[df.index.date <= day]
    if sliced.empty:
        return None
    values = pd.to_numeric(sliced["Close"], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else None


def current_value(histories: dict[str, pd.DataFrame], lot: dict[str, Any], day: date) -> float:
    if not lot.get("open", True):
        return float(lot.get("exit", lot["entry"]))
    current = close_on_or_before(histories.get(lot["ticker"]), day) or lot["entry"]
    lot["peak"] = max(float(lot.get("peak", lot["entry"])), current)
    return current


def apply_sell_signals(histories: dict[str, pd.DataFrame], lots: list[dict[str, Any]], sell_signals: list[dict[str, Any]], day: date, session: str) -> None:
    for lot in lots:
        if not lot.get("open", True):
            continue
        df = histories.get(lot["ticker"])
        current = close_on_or_before(df, day) or lot["entry"]
        lot["peak"] = max(float(lot.get("peak", lot["entry"])), current)
        reason = None
        if current <= lot["stop"]:
            reason = "손절가 이탈"
        elif current >= lot["target"]:
            reason = "목표가 도달"
        elif lot["peak"] > lot["entry"] * 1.12 and current <= lot["peak"] * 0.9:
            reason = "고점 대비 10% 반락"
        elif technical_reversal(df, day):
            reason = "단기 모멘텀 약화"
        if not reason:
            continue
        lot["open"] = False
        lot["exit"] = current
        lot["exit_date"] = day
        lot["exit_session"] = session
        sell_signals.append({
            "date": f"{day.strftime('%Y-%m-%d')} {session}",
            "ticker": lot["ticker"],
            "company_name": lot["company_name"],
            "reason": reason,
            "entry_price": round(lot["entry"], 2),
            "exit_price": round(current, 2),
            "realized_return_pct": f"{(current / lot['entry'] - 1) * 100:.2f}%",
        })


def technical_reversal(df: pd.DataFrame | None, day: date) -> bool:
    if df is None or df.empty or "Close" not in df.columns:
        return False
    sliced = df[df.index.date <= day]
    if len(sliced) < 25:
        return False
    close = pd.to_numeric(sliced["Close"], errors="coerce").dropna()
    if len(close) < 25:
        return False
    latest = float(close.iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    mom5 = latest / float(close.iloc[-6]) - 1
    return latest < ma20 and mom5 < -0.04


def build_portfolio_json(histories: dict[str, pd.DataFrame], lots: list[dict[str, Any]], sell_signals: list[dict[str, Any]], equity_curve: list[dict[str, Any]], start: date, end: date, top_n: int) -> dict[str, Any]:
    holdings_map: dict[str, dict[str, Any]] = {}
    realized_cash = 0.0
    realized_cost = 0.0
    for lot in lots:
        if not lot.get("open", True):
            realized_cash += float(lot.get("exit", lot["entry"]))
            realized_cost += lot["entry"]
            continue
        current = close_on_or_before(histories.get(lot["ticker"]), end) or lot["entry"]
        h = holdings_map.setdefault(lot["ticker"], {"ticker": lot["ticker"], "company_name": lot["company_name"], "units": 0, "cost": 0.0, "value": 0.0, "stop": 0.0, "target": 0.0, "last_signal_date": lot["signal_date"]})
        h["units"] += 1
        h["cost"] += lot["entry"]
        h["value"] += current
        h["stop"] += lot["stop"]
        h["target"] += lot["target"]
        h["last_signal_date"] = max(h["last_signal_date"], lot["signal_date"])
    holdings = []
    for h in holdings_map.values():
        units = h["units"]
        holdings.append({
            "ticker": h["ticker"],
            "company_name": h["company_name"],
            "units": units,
            "weight_units": units,
            "avg_entry": round(h["cost"] / units, 2),
            "current_price": round(h["value"] / units, 2),
            "market_value": round(h["value"], 2),
            "return_pct": f"{(h['value'] / h['cost'] - 1) * 100:.2f}%" if h["cost"] else "0.00%",
            "avg_stop": round(h["stop"] / units, 2),
            "avg_target": round(h["target"] / units, 2),
            "last_signal_date": h["last_signal_date"].strftime("%Y-%m-%d"),
        })
    holdings.sort(key=lambda x: x["market_value"], reverse=True)
    total_cost = sum(lot["entry"] for lot in lots)
    open_value = sum(h["market_value"] for h in holdings)
    net_value = open_value + realized_cash
    total_return = net_value / total_cost - 1 if total_cost else 0.0
    elapsed = max((end - start).days, 1)
    annualized = math.pow(1 + total_return, 365 / elapsed) - 1 if total_return > -1 else -1
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "price_source": "twice_daily_public_daily_proxy",
        "rule": f"오전은 전일 종가 기준, 오후는 당일 12시 공개데이터 프록시 기준 상위 {top_n}개를 하루 2회 편입하고 매도 신호도 2회 점검",
        "recommendation_count": len(lots),
        "trade_count": len(lots),
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
        "holdings": holdings,
        "sell_signals": sell_signals[-20:],
        "equity_curve": equity_curve,
        "recommendation_weights": [{"ticker": h["ticker"], "company_name": h["company_name"], "units": h["units"]} for h in holdings],
    }


if __name__ == "__main__":
    raise SystemExit(main())
