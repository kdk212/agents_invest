"""Install pykrx-backed krx_data_client shim into copied PRISM runtime."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRISM_DIR = ROOT / "prism-insight"
SOURCE = ROOT / "runtime" / "prism_krx_data_client.py"
TARGET_NAME = "krx_data_client.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install PRISM krx_data_client compatibility shim")
    parser.add_argument("--prism-dir", default=str(DEFAULT_PRISM_DIR), help="path to copied PRISM checkout")
    parser.add_argument("--check", action="store_true", help="fail if shim is not installed")
    args = parser.parse_args(argv)

    prism_dir = Path(args.prism_dir).resolve()
    target = prism_dir / TARGET_NAME

    if not SOURCE.exists():
        raise SystemExit(f"compat source missing: {SOURCE}")
    if not prism_dir.exists():
        raise SystemExit(f"PRISM directory missing: {prism_dir}")

    source_text = SOURCE.read_text(encoding="utf-8")
    target_text = target.read_text(encoding="utf-8") if target.exists() else ""
    installed = target_text == source_text

    if args.check:
        if not installed:
            raise SystemExit(f"KRX compatibility shim is not installed: {target}")
        print(f"ok: {target}")
        return 0

    if installed:
        print(f"ok: {target} already installed")
        return 0

    shutil.copyfile(SOURCE, target)
    print(f"installed: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
