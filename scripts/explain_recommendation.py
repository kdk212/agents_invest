#!/usr/bin/env python3
"""Explain why a ticker appeared in the dashboard recommendation history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY = ROOT / "dashboard" / "recommendation_history.json"
DEFAULT_LATEST = ROOT / "dashboard" / "prism_latest_morning.json"
GENERIC_LABELS = {"AI WIN 전일종가 모멘텀 상위주", "AI WIN 일간 추천 후보", "추천 후보"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain dashboard recommendation reasons")
    parser.add_argument("query", help="Ticker code or company name, for example 001820 or 삼화콘덴서")
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY))
    parser.add_argument("--latest-file", default=str(DEFAULT_LATEST))
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    rows = load_rows(Path(args.history_file), Path(args.latest_file))
    query = args.query.strip().lower()
    matches = [row for row in rows if query in str(row.get("code", "")).lower() or query in str(row.get("name", "")).lower() or query in str(row.get("company_name", "")).lower()]

    if not matches:
        print(json.dumps({"ok": False, "reason": "recommendation_not_found", "query": args.query, "searched_rows": len(rows)}, ensure_ascii=False, indent=2))
        return 1

    payload = {"ok": True, "query": args.query, "matches": [explain(row) for row in matches[-args.limit:]]}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def load_rows(history_path: Path, latest_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    history = read_json(history_path)
    for item in history.get("items", []) if isinstance(history.get("items"), list) else []:
        item_date = item.get("date")
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
        sections = item.get("sections", {}) if isinstance(item.get("sections"), dict) else {}
        for section_name, section_rows in sections.items():
            if not isinstance(section_rows, list):
                continue
            for row in section_rows:
                if isinstance(row, dict):
                    rows.append({"date": item_date, "section": section_name, "metadata": metadata, **row})

    latest = read_json(latest_path)
    metadata = latest.get("metadata", {}) if isinstance(latest.get("metadata"), dict) else {}
    for section_name, section_rows in latest.items():
        if section_name == "metadata" or not isinstance(section_rows, list):
            continue
        for row in section_rows:
            if isinstance(row, dict):
                rows.append({"date": metadata.get("date_label") or metadata.get("trade_date"), "section": section_name, "metadata": metadata, **row})
    return rows


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def clean_reason(row: dict[str, Any]) -> str:
    reason = str(row.get("recommendation_reason") or "").strip()
    if reason and reason not in GENERIC_LABELS:
        return reason
    trigger = str(row.get("trigger_type") or "").strip()
    if trigger and trigger not in GENERIC_LABELS:
        return trigger
    return "명확한 추천 사유가 기록되지 않았습니다. 점수 구성값만 참고하세요."


def explain(row: dict[str, Any]) -> dict[str, Any]:
    components = row.get("score_components") if isinstance(row.get("score_components"), dict) else {}
    strategy = row.get("sell_rule") if isinstance(row.get("sell_rule"), dict) else row.get("metadata", {}).get("strategy", {})
    return {
        "date": row.get("date"),
        "signal_at": row.get("signal_at") or row.get("metadata", {}).get("signal_at"),
        "buy_at": row.get("buy_at") or row.get("metadata", {}).get("buy_at"),
        "code": row.get("code") or row.get("ticker"),
        "name": row.get("name") or row.get("company_name"),
        "section": row.get("section"),
        "ai_win_score": row.get("ai_win_score") or row.get("adaptive_profit_score") or row.get("profit_score"),
        "previous_close_price": row.get("previous_close_price") or row.get("signal_price") or row.get("current_price"),
        "recommendation_reason": clean_reason(row),
        "risk_note": row.get("risk_note") or "기록된 별도 리스크 요약 없음",
        "score_components": components,
        "selected_sell_rule": strategy,
        "stop_loss_price": row.get("stop_loss_price"),
        "target_price": row.get("target_price"),
        "target_return_pct": row.get("target_return_pct"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
