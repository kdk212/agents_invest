#!/usr/bin/env python3
"""Run recent-period backtests and write adaptive PRISM strategy parameters."""

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

from runtime.prism_adaptive_strategy import optimize_and_write_strategy


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize adaptive PRISM scoring by rolling backtest")
    parser.add_argument("--end", default=None, help="Backtest end date YYYYMMDD or YYYY-MM-DD; default latest business day")
    parser.add_argument("--periods", default="24,18,12", help="Comma-separated month windows to compare")
    parser.add_argument("--top-n", type=int, default=None, help="Maximum portfolio positions")
    parser.add_argument("--universe-size", type=int, default=None, help="Top liquid universe size")
    parser.add_argument("--strategy-path", default=str(ROOT / "runtime" / "adaptive_strategy.json"))
    parser.add_argument("--dashboard-strategy-path", default=str(ROOT / "dashboard" / "adaptive_strategy.json"))
    args = parser.parse_args()

    periods = tuple(int(part.strip()) for part in args.periods.split(",") if part.strip())
    result = optimize_and_write_strategy(
        end=args.end,
        periods_months=periods,
        top_n=args.top_n,
        universe_size=args.universe_size,
        strategy_path=args.strategy_path,
        dashboard_strategy_path=args.dashboard_strategy_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
