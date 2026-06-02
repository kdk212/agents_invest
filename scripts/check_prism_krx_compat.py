"""Smoke-check PRISM's local krx_data_client compatibility shim.

This checks the exact import path used by copied PRISM without requiring
KRX_ID/KRX_PW. It intentionally performs only small pykrx calls so operators can
separate data-access problems from the full PRISM batch runtime.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRISM_DIR = ROOT / "prism-insight"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check PRISM KRX compatibility shim")
    parser.add_argument("--prism-dir", default=str(DEFAULT_PRISM_DIR), help="path to copied PRISM checkout")
    parser.add_argument("--json", action="store_true", help="print JSON result")
    args = parser.parse_args(argv)

    result = check_krx_compat(Path(args.prism_dir))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ready: {result['ready']}")
        print(f"module_file: {result.get('module_file', '')}")
        if result.get("trade_date"):
            print(f"trade_date: {result['trade_date']}")
        if result.get("sample_rows") is not None:
            print(f"sample_rows: {result['sample_rows']}")
        for error in result["errors"]:
            print(f"error: {error}")
    return 0 if result["ready"] else 2


def check_krx_compat(prism_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    module_file = ""
    trade_date = ""
    sample_rows: int | None = None

    if not prism_dir.exists():
        return {"ready": False, "module_file": module_file, "errors": [f"PRISM directory missing: {prism_dir}"]}

    sys.path.insert(0, str(prism_dir))
    try:
        krx = importlib.import_module("krx_data_client")
        module_file = str(getattr(krx, "__file__", ""))
    except Exception as exc:
        return {
            "ready": False,
            "module_file": module_file,
            "errors": [f"krx_data_client import failed: {exc.__class__.__name__}: {exc}"],
        }

    if str(prism_dir) not in module_file:
        errors.append(f"krx_data_client is not loaded from PRISM copy: {module_file}")

    try:
        trade_date = str(krx.get_nearest_business_day_in_a_week("20260603", prev=True))
    except Exception as exc:
        errors.append(f"business-day lookup failed: {exc.__class__.__name__}: {exc}")

    if trade_date:
        try:
            df = krx.get_market_ohlcv_by_ticker(trade_date, market="ALL")
            sample_rows = int(len(df))
            if df.empty:
                errors.append(f"OHLCV lookup returned empty data for {trade_date}")
            for column in ("Open", "High", "Low", "Close", "Volume", "Amount"):
                if column not in df.columns:
                    errors.append(f"OHLCV column missing: {column}")
        except Exception as exc:
            errors.append(f"OHLCV lookup failed: {exc.__class__.__name__}: {exc}")

    return {
        "ready": not errors,
        "module_file": module_file,
        "trade_date": trade_date,
        "sample_rows": sample_rows,
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
