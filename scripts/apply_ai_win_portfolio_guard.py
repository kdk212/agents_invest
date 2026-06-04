#!/usr/bin/env python3
"""Re-select an AI WIN grid candidate with a live portfolio guard.

The grid optimizer ranks by long lookback performance. This pass keeps that
backtest ranking, but avoids a selected rule that is already damaging the
portfolio from the configured operating start date.
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
BASE_OPTIMIZER = ROOT / "scripts" / "optimize_ai_win_count_and_portfolio.py"
STRATEGY_FILE = DASHBOARD / "adaptive_strategy.json"


def load_optimizer():
    name = "ai_win_guard_base_optimizer"
    spec = importlib.util.spec_from_file_location(name, BASE_OPTIMIZER)
    if spec is None or spec.loader is None:
        raise RuntimeError("base optimizer not found")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply live portfolio guard to AI WIN strategy")
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--universe-size", type=int, default=80)
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--min-live-return-pct", type=float, default=-8.0)
    args = parser.parse_args()

    try:
        import FinanceDataReader as fdr
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "FinanceDataReader_missing", "error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False))
        return 2

    if not STRATEGY_FILE.exists():
        print(json.dumps({"ok": False, "reason": "adaptive_strategy_missing"}, ensure_ascii=False))
        return 2

    strategy = json.loads(STRATEGY_FILE.read_text(encoding="utf-8"))
    tested = strategy.get("tested") if isinstance(strategy.get("tested"), list) else []
    if not tested:
        print(json.dumps({"ok": False, "reason": "tested_candidates_missing"}, ensure_ascii=False))
        return 2

    opt = load_optimizer()
    as_of = pd.to_datetime(args.as_of_date).date() if args.as_of_date else date.today()
    portfolio_start = pd.to_datetime(args.portfolio_start).date()
    max_period = max(int(row.get("period_months") or 12) for row in tested)
    history_start = min(as_of - timedelta(days=max_period * 31 + 430), portfolio_start - timedelta(days=430))

    listing = opt.load_listing(fdr)
    tickers = opt.select_universe(listing, args.universe_size)
    histories = opt.load_histories(fdr, tickers, history_start, as_of)
    if not histories:
        print(json.dumps({"ok": False, "reason": "no_price_history"}, ensure_ascii=False))
        return 2
    calendar = opt.trading_calendar(histories, history_start, as_of)

    original_make_signal_picks = opt.make_signal_picks
    original_sell_reason = opt.sell_reason

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
                item.pop("trigger_type", None)
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

    evaluated: list[dict[str, Any]] = []
    try:
        for row in tested:
            top_n = int(row.get("top_n") or 1)
            stop_multiplier = float(row.get("stop_multiplier") or 2.5)
            target_pct = float(row.get("target_return_pct") or 15.0) / 100
            trailing_trigger_pct = float(row.get("trailing_trigger_pct") or 12.0) / 100
            trailing_drop_pct = float(row.get("trailing_drop_pct") or 6.0) / 100
            install_params(stop_multiplier, target_pct, trailing_trigger_pct, trailing_drop_pct)
            portfolio = opt.simulate_portfolio(histories, listing, calendar, portfolio_start, as_of, top_n, include_history=True)
            live_return = parse_pct(portfolio.get("summary", {}).get("total_return_pct")) / 100
            candidate = dict(row)
            candidate["live_portfolio_return"] = live_return
            candidate["live_portfolio"] = portfolio
            candidate["guard_score"] = guard_score(candidate)
            evaluated.append(candidate)
    finally:
        opt.make_signal_picks = original_make_signal_picks
        opt.sell_reason = original_sell_reason

    viable = [row for row in evaluated if row["live_portfolio_return"] >= args.min_live_return_pct / 100]
    pool = viable or evaluated
    selected = max(pool, key=lambda row: (row["guard_score"], row.get("cagr", 0), row.get("total_return", 0), -int(row.get("top_n") or 1)))

    top_n = int(selected.get("top_n") or 1)
    stop_multiplier = float(selected.get("stop_multiplier") or 2.5)
    target_pct = float(selected.get("target_return_pct") or 15.0) / 100
    trailing_trigger_pct = float(selected.get("trailing_trigger_pct") or 12.0) / 100
    trailing_drop_pct = float(selected.get("trailing_drop_pct") or 6.0) / 100
    install_params(stop_multiplier, target_pct, trailing_trigger_pct, trailing_drop_pct)
    try:
        portfolio = opt.simulate_portfolio(histories, listing, calendar, portfolio_start, as_of, top_n, include_history=True)
        history_items = portfolio.get("recommendation_history", [])
        latest_signal_day = opt.previous_trading_day(calendar, as_of) or as_of
        latest_buy_day = opt.next_trading_day(calendar, latest_signal_day) or as_of
        latest_picks = [opt.enrich_pick(x, latest_signal_day, latest_buy_day) for x in opt.make_signal_picks(histories, listing, latest_signal_day, top_n)]
    finally:
        opt.make_signal_picks = original_make_signal_picks
        opt.sell_reason = original_sell_reason

    for row in latest_picks:
        row.pop("trigger_type", None)
    for item in history_items:
        sections = item.get("sections") or {}
        cleaned_rows = []
        for values in sections.values():
            if isinstance(values, list):
                for row in values:
                    if isinstance(row, dict):
                        row.pop("trigger_type", None)
                        cleaned_rows.append(row)
        item["sections"] = {"추천 후보": cleaned_rows}

    strategy.update({
        "source": "ai_win_realistic_backtest_intraday_sells_grid_optimized_guarded",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_period_months": selected.get("period_months"),
        "selected_top_n": top_n,
        "score_threshold": f"top {top_n}",
        "stop_multiplier": stop_multiplier,
        "target_return_pct": round(target_pct * 100, 2),
        "take_profit_trigger_pct": round(trailing_trigger_pct * 100, 2),
        "take_profit_trailing_pct": round(trailing_drop_pct * 100, 2),
        "best_summary": result_dict(selected),
        "tested": [result_dict(row) for row in sorted(evaluated, key=lambda row: (-row["guard_score"], -row.get("cagr", 0)))[:40]],
        "portfolio_guard": {
            "portfolio_start": portfolio_start.strftime("%Y-%m-%d"),
            "min_live_return_pct": args.min_live_return_pct,
            "evaluated_count": len(evaluated),
            "viable_count": len(viable),
            "selected_live_return_pct": round(selected["live_portfolio_return"] * 100, 2),
            "note": "장기 백테스트 점수와 운영 시작일 이후 포트폴리오 성과를 함께 보며, 현재 손실이 과도한 조합을 피합니다.",
        },
    })

    write_latest_files(latest_picks, latest_signal_day, latest_buy_day, top_n, strategy)
    (DASHBOARD / "recommendation_history.json").write_text(json.dumps({"updated_at": datetime.now().isoformat(timespec="seconds"), "items": history_items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STRATEGY_FILE.write_text(json.dumps(strategy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DASHBOARD / "portfolio_status.json").write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "source": strategy["source"],
        "selected_top_n": top_n,
        "selected_period_months": strategy.get("selected_period_months"),
        "target_return_pct": strategy.get("target_return_pct"),
        "live_portfolio_return_pct": portfolio.get("summary", {}).get("total_return_pct"),
        "evaluated_count": len(evaluated),
        "viable_count": len(viable),
        "recommendations": [(row.get("code"), row.get("name")) for row in latest_picks],
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


def parse_pct(value: Any) -> float:
    try:
        return float(str(value).replace("%", ""))
    except Exception:
        return 0.0


def guard_score(row: dict[str, Any]) -> float:
    cagr = float(row.get("cagr") or 0.0)
    total_return = float(row.get("total_return") or 0.0)
    mdd = float(row.get("mdd") or 0.0)
    win_rate = float(row.get("win_rate") or 0.0)
    live_return = float(row.get("live_portfolio_return") or 0.0)
    top_n = int(row.get("top_n") or 1)
    concentration_penalty = 0.03 if top_n == 1 else 0.0
    live_loss_penalty = abs(min(live_return, 0.0)) * 1.2
    return cagr * 0.45 + total_return * 0.12 + mdd * 0.35 + win_rate * 0.08 + live_return * 0.55 - live_loss_penalty - concentration_penalty


def result_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "period_months": row.get("period_months"),
        "top_n": row.get("top_n"),
        "start": row.get("start"),
        "end": row.get("end"),
        "total_return": row.get("total_return"),
        "cagr": row.get("cagr"),
        "mdd": row.get("mdd"),
        "trades": row.get("trades"),
        "win_rate": row.get("win_rate"),
        "sell_count": row.get("sell_count"),
        "stop_multiplier": row.get("stop_multiplier"),
        "target_return_pct": row.get("target_return_pct"),
        "trailing_trigger_pct": row.get("trailing_trigger_pct"),
        "trailing_drop_pct": row.get("trailing_drop_pct"),
        "live_portfolio_return": round(float(row.get("live_portfolio_return") or 0.0), 6),
        "guard_score": round(float(row.get("guard_score") or 0.0), 6),
    }


def write_latest_files(picks: list[dict[str, Any]], signal_day: date, buy_day: date, top_n: int, strategy: dict[str, Any]) -> None:
    payload = {
        "metadata": {
            "trigger_mode": "daily",
            "trade_date": signal_day.strftime("%Y%m%d"),
            "source": strategy["source"],
            "selected_top_n": top_n,
            "recommendation_policy": f"백테스트+운영가드 최적 상위 {top_n}개",
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


if __name__ == "__main__":
    raise SystemExit(main())
