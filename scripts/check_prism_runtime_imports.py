"""Smoke-check imported PRISM runtime modules without running a batch.

The upstream project can change dependencies over time. This check imports the
copied PRISM trigger runner so EC2 setup fails early with a clear missing-module
message instead of failing later inside the 24h service loop.
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
    parser = argparse.ArgumentParser(description="Smoke-check PRISM runtime imports")
    parser.add_argument("--prism-dir", default=str(DEFAULT_PRISM_DIR), help="path to copied PRISM checkout")
    parser.add_argument("--json", action="store_true", help="print JSON result")
    args = parser.parse_args(argv)

    result = check_imports(Path(args.prism_dir))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"prism_dir: {result['prism_dir']}")
        print(f"ready: {result['ready']}")
        if result["errors"]:
            print("errors:")
            for error in result["errors"]:
                print(f"- {error}")
    return 0 if result["ready"] else 2


def check_imports(prism_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    trigger = prism_dir / "trigger_batch.py"
    if not prism_dir.exists():
        errors.append(f"PRISM directory not found: {prism_dir}")
    if not trigger.exists():
        errors.append(f"trigger_batch.py not found: {trigger}")
    if errors:
        return {"prism_dir": str(prism_dir), "ready": False, "errors": errors}

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(prism_dir))
    try:
        importlib.import_module("trigger_batch")
    except ModuleNotFoundError as exc:
        missing = exc.name or "unknown"
        errors.append(f"missing python module: {missing}")
    except Exception as exc:
        errors.append(f"trigger_batch import failed: {exc.__class__.__name__}: {exc}")

    return {"prism_dir": str(prism_dir), "ready": not errors, "errors": errors}


if __name__ == "__main__":
    raise SystemExit(main())