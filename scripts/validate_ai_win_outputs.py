#!/usr/bin/env python3
"""Validate generated AI WIN dashboard output files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AI WIN dashboard output files")
    parser.add_argument("--portfolio-start", default="2026-06-01")
    parser.add_argument("--dashboard-dir", default=str(DASHBOARD))
    args = parser.parse_args()

    dashboard = Path(args.dashboard_dir)
    portfolio = read_json(dashboard / "portfolio_status.json")
    strategy = read_json(dashboard / "adaptive_strategy.json")
    history = read_json(dashboard / "recommendation_history.json")
    latest = read_json(dashboard / "prism_latest_morning.json")

    issues: list[str] = []
    warnings: list[str] = []

    curve = portfolio.get("equity_curve") if isinstance(portfolio.get("equity_curve"), list) else []
    if portfolio.get("start_date") != args.portfolio_start:
        issues.append(f"portfolio_start_mismatch: expected {args.portfolio_start}, got {portfolio.get('start_date')}")
    if "intraday_sell_rules" not in str(portfolio.get("price_source", "")):
        issues.append(f"portfolio_price_source_not_intraday: {portfolio.get('price_source')}")
    if not curve:
        issues.append("equity_curve_missing")
    else:
        last_curve_date = curve[-1].get("date") if isinstance(curve[-1], dict) else None
        if portfolio.get("end_date") != last_curve_date:
            issues.append(f"portfolio_end_date_curve_mismatch: end_date={portfolio.get('end_date')}, last_curve_date={last_curve_date}")
    if not isinstance(portfolio.get("summary"), dict):
        issues.append("portfolio_summary_missing")

    if "intraday_sells" not in str(strategy.get("source", "")):
        issues.append(f"strategy_source_not_intraday: {strategy.get('source')}")
    if not strategy.get("selected_top_n"):
        issues.append("selected_top_n_missing")
    if not isinstance(strategy.get("tested"), list) or not strategy.get("tested"):
        warnings.append("backtest_tested_rows_missing")

    history_items = history.get("items") if isinstance(history.get("items"), list) else []
    if not history_items:
        issues.append("recommendation_history_missing")
    else:
        first_date = history_items[0].get("date")
        if first_date != args.portfolio_start:
            warnings.append(f"first_recommendation_date_is_{first_date}_not_{args.portfolio_start}")
        candidate_rows = flatten_history(history_items)
        if not candidate_rows:
            issues.append("recommendation_rows_missing")
        else:
            missing_reason = [row for row in candidate_rows if not row.get("recommendation_reason")]
            missing_prev_close = [row for row in candidate_rows if not (row.get("previous_close_price") or row.get("signal_price"))]
            if missing_reason:
                issues.append(f"recommendation_reason_missing_count={len(missing_reason)}")
            if missing_prev_close:
                issues.append(f"previous_close_missing_count={len(missing_prev_close)}")

    latest_rows = flatten_latest(latest)
    if latest and not latest_rows:
        issues.append("latest_recommendation_rows_missing")

    payload = {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "portfolio": {
            "start_date": portfolio.get("start_date"),
            "end_date": portfolio.get("end_date"),
            "price_source": portfolio.get("price_source"),
            "summary": portfolio.get("summary", {}),
            "equity_curve_rows": len(curve),
            "first_curve_date": curve[0].get("date") if curve and isinstance(curve[0], dict) else None,
            "last_curve_date": curve[-1].get("date") if curve and isinstance(curve[-1], dict) else None,
        },
        "strategy": {
            "source": strategy.get("source"),
            "selected_top_n": strategy.get("selected_top_n"),
            "best_summary": strategy.get("best_summary"),
        },
        "recommendations": {
            "history_days": [item.get("date") for item in history_items[-10:]],
            "latest_count": len(latest_rows),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{exc.__class__.__name__}: {exc}"}


def flatten_history(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        sections = item.get("sections") if isinstance(item.get("sections"), dict) else {}
        for value in sections.values():
            if isinstance(value, list):
                rows.extend([row for row in value if isinstance(row, dict)])
    return rows


def flatten_latest(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in data.items():
        if key == "metadata" or not isinstance(value, list):
            continue
        rows.extend([row for row in value if isinstance(row, dict)])
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
