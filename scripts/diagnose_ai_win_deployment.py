#!/usr/bin/env python3
"""Diagnose whether the AI WIN grid strategy and dashboard patches are actually deployed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
FORBIDDEN_LABELS = [
    "AI WIN 전일종가 모멘텀 상위주",
    "AI WIN 일간 추천 후보",
]
EXPECTED_STRATEGY_SOURCE = "ai_win_realistic_backtest_intraday_sells_grid_optimized"
REQUIRED_INDEX_SCRIPTS = [
    "./app.js",
    "./candidate_render_patch.js",
    "./recommendation_history_patch.js",
    "./hide_repeated_candidate_label.js",
]


def main() -> int:
    issues: list[str] = []
    warnings: list[str] = []

    index = read_text(DASHBOARD / "index.html")
    app = read_text(DASHBOARD / "app.js")
    candidate_patch = read_text(DASHBOARD / "candidate_render_patch.js")
    hide_patch = read_text(DASHBOARD / "hide_repeated_candidate_label.js")
    strategy = read_json(DASHBOARD / "adaptive_strategy.json")
    latest = read_json(DASHBOARD / "prism_latest_morning.json")
    history = read_json(DASHBOARD / "recommendation_history.json")
    portfolio = read_json(DASHBOARD / "portfolio_status.json")

    for script in REQUIRED_INDEX_SCRIPTS:
        if script not in index:
            issues.append(f"index_missing_script: {script}")

    if not candidate_patch:
        issues.append("candidate_render_patch_missing")
    if not hide_patch:
        issues.append("hide_repeated_candidate_label_missing")

    source = strategy.get("source")
    if source != EXPECTED_STRATEGY_SOURCE:
        issues.append(f"strategy_source_not_current: {source}")
    if not strategy.get("selected_top_n"):
        issues.append("strategy_selected_top_n_missing")
    if len(strategy.get("tested", []) if isinstance(strategy.get("tested"), list) else []) < 20:
        issues.append(f"strategy_tested_rows_too_few: {len(strategy.get('tested', []) if isinstance(strategy.get('tested'), list) else [])}")
    for key in ("stop_multiplier", "target_return_pct", "take_profit_trigger_pct", "take_profit_trailing_pct"):
        if strategy.get(key) in (None, ""):
            issues.append(f"strategy_{key}_missing")

    latest_sections = [key for key in latest.keys() if key != "metadata"] if isinstance(latest, dict) else []
    forbidden_latest_sections = [key for key in latest_sections if key in FORBIDDEN_LABELS]
    if forbidden_latest_sections:
        issues.append(f"latest_has_forbidden_section_labels: {forbidden_latest_sections}")
    if not latest_sections:
        issues.append("latest_recommendation_sections_missing")

    latest_rows = flatten_latest(latest)
    if not latest_rows:
        issues.append("latest_recommendation_rows_missing")
    for label in FORBIDDEN_LABELS:
        if label in index:
            warnings.append(f"index_contains_forbidden_text: {label}")
        if label in app:
            warnings.append(f"app_contains_legacy_renderer_text: {label}")
        if any(label in json.dumps(row, ensure_ascii=False) for row in latest_rows):
            warnings.append(f"latest_rows_contain_forbidden_text: {label}")

    history_items = history.get("items") if isinstance(history.get("items"), list) else []
    if not history_items:
        issues.append("recommendation_history_missing")

    payload = {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "dashboard_files": {
            "index_has_candidate_patch": "./candidate_render_patch.js" in index,
            "index_has_hide_patch": "./hide_repeated_candidate_label.js" in index,
            "candidate_patch_exists": bool(candidate_patch),
            "hide_patch_exists": bool(hide_patch),
        },
        "strategy": {
            "source": source,
            "selected_top_n": strategy.get("selected_top_n"),
            "selected_period_months": strategy.get("selected_period_months"),
            "stop_multiplier": strategy.get("stop_multiplier"),
            "target_return_pct": strategy.get("target_return_pct"),
            "take_profit_trigger_pct": strategy.get("take_profit_trigger_pct"),
            "take_profit_trailing_pct": strategy.get("take_profit_trailing_pct"),
            "tested_rows": len(strategy.get("tested", []) if isinstance(strategy.get("tested"), list) else []),
            "best_summary": strategy.get("best_summary"),
        },
        "latest": {
            "metadata": latest.get("metadata") if isinstance(latest, dict) else None,
            "sections": latest_sections,
            "recommendations": [(row.get("code"), row.get("name")) for row in latest_rows[:10]],
        },
        "portfolio": {
            "summary": portfolio.get("summary") if isinstance(portfolio, dict) else None,
            "start_date": portfolio.get("start_date") if isinstance(portfolio, dict) else None,
            "end_date": portfolio.get("end_date") if isinstance(portfolio, dict) else None,
        },
        "history_days": [item.get("date") for item in history_items[-10:]],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def flatten_latest(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return rows
    for key, value in data.items():
        if key == "metadata" or not isinstance(value, list):
            continue
        rows.extend([row for row in value if isinstance(row, dict)])
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
