#!/usr/bin/env python3
"""Optimize AI WIN top count plus sell-rule parameters and write dashboard files."""

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
OLD_OPTIMIZER = ROOT / "scripts" / "optimize_ai_win_count_and_portfolio.py"


def load_optimizer():
    name = "ai_win_base_optimizer"
    spec = importlib.util.spec_from_file_location(name, OLD_OPTIMIZER)
    if spec is None or spec.loader is None:
        raise RuntimeError("base optimizer not found")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def pct_list(text: str) -> list[float]:
    return [float(x.strip()) for x in text.split(",") if x.strip()]


def int_list(text: str) -> list[int]:
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize AI WIN grid strategy")
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--universe-size", type=int, default=180)
    parser.add_argument("--min-top-n", type=int, default=1)
    parser.add_argument("--max-top-n", type=int, default=8)
    parser.add_argument("--period-months", default="24,18,12")
    parser.add_argument("--stop-multipliers", default="1.6,2.0,2.5,3.0")
    parser.add_argument("--target-pcts", default="15,20,25,30")
    parser.add_argument("--trailing-trigger-pcts", default="8,12,16")
    parser.add_argument("--trailing-drop-pcts", default="6,9,12")
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()

    try:
        import FinanceDataReader as fdr
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "FinanceDataReader_missing", "next_action": ".venv/bin/python -m pip install finance-datareader", "error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False))
        return 2

    opt = load_optimizer()
    as_of = pd.to_datetime(args.as_of_date).date() if args.as_of_date else date.today()
    portfolio_start = pd.to_datetime(args.portfolio_start).date()
    periods = int_list(args.period_months)
    top_values = list(range(args.min_top_n, args.max_top_n + 1))
    stop_multipliers = pct_list(args.stop_multipliers)
    target_pcts = [x / 100 for x in pct_list(args.target_pcts)]
    trailing_trigger_pcts = [x / 100 for x in pct_list(args.trailing_trigger_pcts)]
    trailing_drop_pcts = [x / 100 for x in pct_list(args.trailing_drop_pcts)]

    listing = opt.load_listing(fdr)
    tickers = opt.select_universe(listing, args.universe_size)
    history_start = min(as_of - timedelta(days=max(periods) * 31 + 430), portfolio_start - timedelta(days=430))
    histories = opt.load_histories(fdr, tickers, history_start, as_of)
    if not histories:
        print(json.dumps({"ok": False, "reason": "no_price_history"}, ensure_ascii=False))
        return 2

    calendar = opt.trading_calendar(histories, history_start, as_of)
    original_make_signal_picks = opt.make_signal_picks
    original_sell_reason = opt.sell_reason
    results: list[dict[str, Any]] = []

    def install_params(stop_multiplier: float, target_pct: float, trailing_trigger_pct: float, trailing_drop_pct: float) -> None:
        def make_signal_picks(histories_arg, listing_arg, signal_day, top_n):
            picks = original_make_signal_picks(histories_arg, listing_arg, signal_day, top_n)
            for item in picks:
                price = float(item.get("current_price") or 0)
                vol60_pct = float(item.get("score_components", {}).get("vol60_pct") or 0)
                vol60 = vol60_pct / 100 if vol60_pct else float(item.get("stop_loss_pct") or 5.0) / 100
                stop_pct = min(max(vol60 / math.sqrt(252) * math.sqrt(5) * stop_multiplier, 0.035), 0.22)
                item["stop_loss_pct"] = round(stop_pct * 100, 2)
                item["stop_loss_price"] = round(price * (1 - stop_pct), 0) if price else 0
                item["target_price"] = round(price * (1 + target_pct), 0) if price else 0
                item["target_return_pct"] = round(target_pct * 100, 2)
                item["take_profit_trigger_pct"] = round(trailing_trigger_pct * 100, 2)
                item["take_profit_trailing_pct"] = round(trailing_drop_pct * 100, 2)
                item["sell_rule"] = {
                    "stop_multiplier": stop_multiplier,
                    "target_pct": target_pct,
                    "trailing_trigger_pct": trailing_trigger_pct,
                    "trailing_drop_pct": trailing_drop_pct,
                }
            return picks

        def sell_reason(df, lot, day):
            bar = opt.ohlc_for_date(df, day)
            if not bar:
                current = opt.close_on_or_before(df, day) or lot["entry"]
                lot["peak"] = max(float(lot.get("peak", lot["entry"])), current)
                return close_based_sell(lot, current, trailing_trigger_pct, trailing_drop_pct)
            high = bar["high"]
            low = bar["low"]
            close = bar["close"]
            lot["peak"] = max(float(lot.get("peak", lot["entry"])), high, close)
            if low <= lot["stop"]:
                return "손절가 이탈", float(lot["stop"])
            if high >= lot["target"]:
                return "목표가 도달", float(lot["target"])
            trailing_stop = float(lot["peak"]) * (1 - trailing_drop_pct)
            if lot["peak"] > lot["entry"] * (1 + trailing_trigger_pct) and low <= trailing_stop:
                return f"고점 대비 {trailing_drop_pct * 100:.0f}% 반락", trailing_stop
            return None, close

        opt.make_signal_picks = make_signal_picks
        opt.sell_reason = sell_reason

    try:
        for months in periods:
            start = as_of - timedelta(days=months * 31)
            for top_n in top_values:
                for stop_multiplier in stop_multipliers:
                    for target_pct in target_pcts:
                        for trailing_trigger_pct in trailing_trigger_pcts:
                            for trailing_drop_pct in trailing_drop_pcts:
                                install_params(stop_multiplier, target_pct, trailing_trigger_pct, trailing_drop_pct)
                                result = opt.run_backtest(histories, listing, calendar, start, as_of, top_n, months)
                                if not result:
                                    continue
                                result.update({
                                    "stop_multiplier": stop_multiplier,
                                    "target_pct": target_pct,
                                    "trailing_trigger_pct": trailing_trigger_pct,
                                    "trailing_drop_pct": trailing_drop_pct,
                                })
                                results.append(result)
    finally:
        opt.make_signal_picks = original_make_signal_picks
        opt.sell_reason = original_sell_reason

    if not results:
        print(json.dumps({"ok": False, "reason": "no_backtest_result"}, ensure_ascii=False))
        return 2

    best = max(results, key=lambda item: (selection_score(item), item["cagr"], item["total_return"], -item["top_n"]))
    install_params(best["stop_multiplier"], best["target_pct"], best["trailing_trigger_pct"], best["trailing_drop_pct"])
    try:
        portfolio = opt.simulate_portfolio(histories, listing, calendar, portfolio_start, as_of, int(best["top_n"]), include_history=True)
        history_items = portfolio.get("recommendation_history", [])
        latest_signal_day = opt.previous_trading_day(calendar, as_of) or as_of
        latest_buy_day = opt.next_trading_day(calendar, latest_signal_day) or as_of
        latest_picks = [opt.enrich_pick(x, latest_signal_day, latest_buy_day) for x in opt.make_signal_picks(histories, listing, latest_signal_day, int(best["top_n"]))]
    finally:
        opt.make_signal_picks = original_make_signal_picks
        opt.sell_reason = original_sell_reason

    strategy = {
        "source": "ai_win_realistic_backtest_intraday_sells_grid_optimized",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_period_months": best["period_months"],
        "selected_top_n": best["top_n"],
        "score_threshold": f"top {best['top_n']}",
        "stop_multiplier": best["stop_multiplier"],
        "target_return_pct": round(best["target_pct"] * 100, 2),
        "take_profit_trigger_pct": round(best["trailing_trigger_pct"] * 100, 2),
        "take_profit_trailing_pct": round(best["trailing_drop_pct"] * 100, 2),
        "best_summary": result_dict(best),
        "tested": [result_dict(x) for x in sorted(results, key=lambda item: (-selection_score(item), item["top_n"]))[:40]],
        "note": "전일 종가 신호, 다음 거래일 시초가 편입, 장중 고가/저가 기준 손절/목표가/트레일링 매도 조건까지 그리드로 최적화합니다.",
    }

    write_latest_files(latest_picks, latest_signal_day, latest_buy_day, int(best["top_n"]), strategy)
    write_history_file(history_items)
    (DASHBOARD / "adaptive_strategy.json").write_text(json.dumps(strategy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DASHBOARD / "portfolio_status.json").write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "selected_top_n": best["top_n"],
        "selected_period_months": best["period_months"],
        "stop_multiplier": best["stop_multiplier"],
        "target_return_pct": round(best["target_pct"] * 100, 2),
        "trailing_trigger_pct": round(best["trailing_trigger_pct"] * 100, 2),
        "trailing_drop_pct": round(best["trailing_drop_pct"] * 100, 2),
        "backtest_cagr_pct": round(best["cagr"] * 100, 2),
        "backtest_total_return_pct": round(best["total_return"] * 100, 2),
        "backtest_mdd_pct": round(best["mdd"] * 100, 2),
        "portfolio_return_pct": portfolio["summary"]["total_return_pct"],
        "tested_combinations": len(results),
    }, ensure_ascii=False, indent=2))
    return 0


def close_based_sell(lot: dict[str, Any], current: float, trailing_trigger_pct: float, trailing_drop_pct: float) -> tuple[str | None, float]:
    if current <= lot["stop"]:
        return "손절가 이탈", current
    if current >= lot["target"]:
        return "목표가 도달", current
    if lot["peak"] > lot["entry"] * (1 + trailing_trigger_pct) and current <= lot["peak"] * (1 - trailing_drop_pct):
        return f"고점 대비 {trailing_drop_pct * 100:.0f}% 반락", current
    return None, current


def selection_score(result: dict[str, Any]) -> float:
    cagr = float(result.get("cagr", 0.0))
    total_return = float(result.get("total_return", 0.0))
    mdd = float(result.get("mdd", 0.0))
    win_rate = float(result.get("win_rate", 0.0))
    trades = int(result.get("trades", 0))
    trade_penalty = 0.15 if trades < 20 else 0.0
    return cagr * 0.70 + total_return * 0.20 + mdd * 0.65 + win_rate * 0.10 - trade_penalty


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
        "stop_multiplier": result.get("stop_multiplier"),
        "target_return_pct": round(float(result.get("target_pct", 0.0)) * 100, 2),
        "trailing_trigger_pct": round(float(result.get("trailing_trigger_pct", 0.0)) * 100, 2),
        "trailing_drop_pct": round(float(result.get("trailing_drop_pct", 0.0)) * 100, 2),
        "selection_score": round(selection_score(result), 6),
    }


def write_latest_files(picks: list[dict[str, Any]], signal_day: date, buy_day: date, top_n: int, strategy: dict[str, Any]) -> None:
    payload = {
        "metadata": {
            "trigger_mode": "daily",
            "trade_date": signal_day.strftime("%Y%m%d"),
            "source": strategy["source"],
            "selected_top_n": top_n,
            "recommendation_policy": f"백테스트 최적 상위 {top_n}개",
            "signal_at": f"{signal_day:%Y-%m-%d} 종가",
            "buy_at": f"{buy_day:%Y-%m-%d} 시초가",
            "strategy": {
                "stop_multiplier": strategy["stop_multiplier"],
                "target_return_pct": strategy["target_return_pct"],
                "take_profit_trigger_pct": strategy["take_profit_trigger_pct"],
                "take_profit_trailing_pct": strategy["take_profit_trailing_pct"],
            },
        },
        "추천 후보": picks,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (DASHBOARD / "prism_latest_morning.json").write_text(text, encoding="utf-8")
    (DASHBOARD / "prism_latest_afternoon.json").write_text(text, encoding="utf-8")


def write_history_file(history_items: list[dict[str, Any]]) -> None:
    for item in history_items:
        sections = item.get("sections") or {}
        if "AI WIN 일간 추천 후보" in sections:
            item["sections"] = {"추천 후보": sections["AI WIN 일간 추천 후보"]}
    (DASHBOARD / "recommendation_history.json").write_text(json.dumps({
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": history_items,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
