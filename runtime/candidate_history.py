"""Persist PRISM candidate selections for paper validation feedback."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "runtime" / "candidate_history.sqlite3"
SCHEMA_PATH = ROOT / "db" / "candidate_performance_tracker.sql"


def record_prism_output(
    output_file: str | Path,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    selected_at: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_file)
    if not output_path.exists():
        return {"ok": False, "inserted": 0, "reason": f"output_not_found: {output_path}"}

    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "inserted": 0, "reason": f"json_load_failed: {exc.__class__.__name__}: {exc}"}

    rows = list(_candidate_rows(data, selected_at=selected_at or datetime.now().isoformat(timespec="seconds")))
    if not rows:
        return {"ok": True, "inserted": 0, "reason": "no_candidates"}

    target_db = Path(db_path)
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target_db) as connection:
        initialize_schema(connection)
        connection.executemany(
            """
            INSERT INTO candidate_performance_tracker (
                ticker,
                company_name,
                sector,
                trigger_type,
                trigger_mode,
                selected_at,
                signal_date,
                entry_decision,
                profit_score,
                risk_penalty,
                expected_value,
                buy_score,
                risk_reward_ratio,
                price_at_signal,
                target_price,
                stop_loss_price,
                agent_scores_json,
                score_reasons_json
            ) VALUES (
                :ticker,
                :company_name,
                :sector,
                :trigger_type,
                :trigger_mode,
                :selected_at,
                :signal_date,
                :entry_decision,
                :profit_score,
                :risk_penalty,
                :expected_value,
                :buy_score,
                :risk_reward_ratio,
                :price_at_signal,
                :target_price,
                :stop_loss_price,
                :agent_scores_json,
                :score_reasons_json
            )
            """,
            rows,
        )
    return {"ok": True, "inserted": len(rows), "db_path": str(target_db)}


def initialize_schema(connection: sqlite3.Connection) -> None:
    if SCHEMA_PATH.exists():
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    else:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_performance_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                trigger_type TEXT,
                trigger_mode TEXT,
                selected_at TEXT NOT NULL,
                entry_decision TEXT NOT NULL DEFAULT 'unknown',
                profit_score REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _candidate_rows(data: dict[str, Any], *, selected_at: str) -> Iterable[dict[str, Any]]:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    trigger_mode = str(metadata.get("trigger_mode") or "")
    signal_date = str(metadata.get("trade_date") or "")

    for trigger_type, value in data.items():
        if trigger_type == "metadata" or not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("code") or item.get("ticker") or "").strip()
            if not ticker:
                continue
            yield {
                "ticker": ticker,
                "company_name": _text(item.get("name") or item.get("company_name")),
                "sector": _text(item.get("sector")),
                "trigger_type": str(trigger_type),
                "trigger_mode": trigger_mode,
                "selected_at": selected_at,
                "signal_date": signal_date,
                "entry_decision": _text(item.get("decision") or item.get("entry_decision") or "candidate"),
                "profit_score": _float_or_none(item.get("profit_score")),
                "risk_penalty": _float_or_none(item.get("risk_penalty")),
                "expected_value": _float_or_none(item.get("expected_value")),
                "buy_score": _float_or_none(item.get("buy_score")),
                "risk_reward_ratio": _float_or_none(item.get("risk_reward_ratio")),
                "price_at_signal": _float_or_none(item.get("current_price")),
                "target_price": _float_or_none(item.get("target_price")),
                "stop_loss_price": _float_or_none(item.get("stop_loss_price")),
                "agent_scores_json": _json_text(
                    {
                        "agent_fit_score": item.get("agent_fit_score"),
                        "final_score": item.get("final_score"),
                        "rs_score": item.get("rs_score"),
                        "extension_score": item.get("extension_score"),
                    }
                ),
                "score_reasons_json": _json_text(item.get("profit_score_reasons")),
            }


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
