#!/usr/bin/env python3
"""Check that GitHub workflows are manual-only by default.

This repository intentionally keeps CI/import workflows on workflow_dispatch so routine
commits do not generate run-failed email noise.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW_DIR = ROOT / ".github" / "workflows"
FORBIDDEN_TRIGGERS = {"push", "pull_request", "schedule", "workflow_run", "pages_build"}
ALLOWED_TRIGGERS = {"workflow_dispatch"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify GitHub workflows are manual-only")
    parser.add_argument("--workflow-dir", default=str(DEFAULT_WORKFLOW_DIR))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check_workflows(Path(args.workflow_dir))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)
    return 0 if result["ok"] else 1


def check_workflows(workflow_dir: Path) -> dict[str, Any]:
    files = sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]) if workflow_dir.exists() else []
    issues: list[dict[str, Any]] = []
    workflows: list[dict[str, Any]] = []

    for path in files:
        text = path.read_text(encoding="utf-8")
        triggers = workflow_triggers(text)
        forbidden = sorted(trigger for trigger in triggers if trigger in FORBIDDEN_TRIGGERS)
        missing_manual = "workflow_dispatch" not in triggers
        workflows.append({"file": str(path), "triggers": sorted(triggers)})
        if forbidden or missing_manual:
            issues.append(
                {
                    "file": str(path),
                    "triggers": sorted(triggers),
                    "forbidden_triggers": forbidden,
                    "missing_workflow_dispatch": missing_manual,
                }
            )

    return {
        "ok": not issues,
        "workflow_dir": str(workflow_dir),
        "checked_count": len(files),
        "allowed_triggers": sorted(ALLOWED_TRIGGERS),
        "forbidden_triggers": sorted(FORBIDDEN_TRIGGERS),
        "issues": issues,
        "workflows": workflows,
    }


def workflow_triggers(text: str) -> set[str]:
    lines = text.splitlines()
    on_line = find_on_line(lines)
    if on_line is None:
        return set()

    line_no, line = on_line
    value = line.split(":", 1)[1].strip()
    if value:
        return parse_inline_triggers(value)

    triggers: set[str] = set()
    for raw in lines[line_no + 1 :]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            break
        if indent == 2:
            key = raw.strip().split(":", 1)[0].strip()
            if key:
                triggers.add(key)
    return triggers


def find_on_line(lines: list[str]) -> tuple[int, str] | None:
    for i, line in enumerate(lines):
        if re.match(r"^on\s*:", line):
            return i, line
    return None


def parse_inline_triggers(value: str) -> set[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return {part.strip().strip('"\'') for part in value[1:-1].split(",") if part.strip()}
    return {value.strip().strip('"\'')}


def print_text(result: dict[str, Any]) -> None:
    print("== GitHub workflow trigger check ==")
    print(f"checked_count={result['checked_count']}")
    for issue in result["issues"]:
        print(f"FAIL {issue['file']}: triggers={issue['triggers']}")
    if result["ok"]:
        print("OK all workflows are manual-only")


if __name__ == "__main__":
    raise SystemExit(main())
