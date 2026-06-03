#!/usr/bin/env python3
"""Build daily AI WIN recommendation history and portfolio dashboard files."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
OPTIMIZER = ROOT / "scripts" / "optimize_ai_win_count_and_portfolio.py"
STRATEGY = DASHBOARD / "adaptive_strategy.json"


def load_opt():
    name = "ai_win_optimizer"
    spec = importlib.util.spec_from_file_location(name, OPTIMIZER)
    if spec is None or spec.loader is None:
        raise RuntimeError("optimizer module not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_selected_top_n(explicit: int | None, default: int = 5) -> int:
    if explicit is not None:
        return explicit
    if not STRATEGY.exists():
        return default
    try:
        data = json.loads(STRATEGY.read_text(encoding="utf-8"))
        value = int(data.get("selected_top_n") or default)
        return max(1, min(value, 12))
    except Exception:
        return default


def write_latest_files(history_items: list[dict[str, Any]]) -> None:
    if not history_items:
        return
    latest = history_items[-1]
    payload = {"metadata": latest.get("metadata", {}), **latest.get("sections", {})}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (DASHBOARD / "prism_latest_morning.json").write_text(text, encoding="utf-8")
    (DASHBOARD / "prism_latest_afternoon.json").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--top-n", type=int, default=None)
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
    top_n = load_selected_top_n(args.top_n)

    listing = opt.load_listing(fdr)
    tickers = opt.select_universe(listing, args.universe_size)
    histories = opt.load_histories(fdr, tickers, start - timedelta(days=430), as_of)
    if not histories:
        print(json.dumps({"ok": False, "reason": "no_price_history"}, ensure_ascii=False))
        return 2
    calendar = opt.trading_calendar(histories, start - timedelta(days=20), as_of)

    portfolio = opt.simulate_portfolio(histories, listing, calendar, start, as_of, top_n, include_history=True)
    history_items = portfolio.get("recommendation_history", [])
    write_latest_files(history_items)

    (DASHBOARD / "portfolio_status.json").write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DASHBOARD / "recommendation_history.json").write_text(json.dumps({"updated_at": datetime.now().isoformat(timespec="seconds"), "items": history_items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "top_n": top_n, "dates": [x.get("date") for x in history_items[-5:]], "portfolio_return_pct": portfolio["summary"]["total_return_pct"], "open_positions": portfolio["summary"]["open_positions"], "sell_signal_count": portfolio["summary"]["sell_signal_count"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
