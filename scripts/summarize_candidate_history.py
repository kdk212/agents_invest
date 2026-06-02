"""Print a safe summary of recorded PRISM candidate history."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from runtime.candidate_history import DEFAULT_DB_PATH, initialize_schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize PRISM candidate history")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="candidate history SQLite path")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)

    summary = build_summary(Path(args.db_path))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"db_path: {summary['db_path']}")
        print(f"exists: {summary['exists']}")
        print(f"total_candidates: {summary['total_candidates']}")
        print(f"latest_selected_at: {summary['latest_selected_at']}")
        print("top_triggers:")
        for row in summary["top_triggers"]:
            print(f"- {row['trigger_type']}: {row['sample_count']}")
    return 0


def build_summary(db_path: Path) -> dict[str, object]:
    if not db_path.exists():
        return {
            "db_path": str(db_path),
            "exists": False,
            "total_candidates": 0,
            "latest_selected_at": None,
            "top_triggers": [],
        }

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        initialize_schema(connection)
        total = connection.execute("SELECT COUNT(*) AS count FROM candidate_performance_tracker").fetchone()["count"]
        latest = connection.execute("SELECT MAX(selected_at) AS value FROM candidate_performance_tracker").fetchone()["value"]
        top_triggers = [
            dict(row)
            for row in connection.execute(
                """
                SELECT trigger_type, COUNT(*) AS sample_count
                FROM candidate_performance_tracker
                GROUP BY trigger_type
                ORDER BY sample_count DESC, trigger_type ASC
                LIMIT 8
                """
            ).fetchall()
        ]
    return {
        "db_path": str(db_path),
        "exists": True,
        "total_candidates": int(total),
        "latest_selected_at": latest,
        "top_triggers": top_triggers,
    }


if __name__ == "__main__":
    raise SystemExit(main())