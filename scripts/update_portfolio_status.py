#!/usr/bin/env python3
"""Export recommendation-driven paper portfolio status for the dashboard."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_runtime_env() -> None:
    env_path = ROOT / "config" / "runtime.env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_runtime_env()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PRISM_DIR = ROOT / "prism-insight"
if PRISM_DIR.exists() and str(PRISM_DIR) not in sys.path:
    sys.path.insert(0, str(PRISM_DIR))

from runtime.portfolio_tracker import DEFAULT_START_DATE, update_portfolio_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Update dashboard portfolio_status.json")
    parser.add_argument("--start-date", default=os.getenv("PORTFOLIO_START_DATE", DEFAULT_START_DATE))
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--output", default=str(ROOT / "dashboard" / "portfolio_status.json"))
    args = parser.parse_args()

    payload = update_portfolio_status(
        start_date=args.start_date,
        end_date=args.end_date,
        output_path=args.output,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
