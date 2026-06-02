"""Verify that PRISM-INSIGHT and optimization add-ons are present and wired.

Usage:
    python scripts/check_integration.py
    python scripts/check_integration.py --json
    python scripts/check_integration.py --allow-missing-upstream
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ROOT_FILES = [
    "optimization/profit_scoring.py",
    "optimization/risk_governor.py",
    "optimization/paper_validator.py",
    "optimization/adapters.py",
    "runtime/preflight.py",
    "runtime/ssm.py",
    "db/candidate_performance_tracker.sql",
]

EXPECTED_UPSTREAM_FILES = [
    "prism-insight/README.md",
    "prism-insight/README_ko.md",
    "prism-insight/LICENSE",
    "prism-insight/trigger_batch.py",
    "prism-insight/stock_tracking_agent.py",
    "prism-insight/cores/agents/trading_agents.py",
]

PATCH_MARKERS = {
    "prism-insight/trigger_batch.py": (
        "enrich_trigger_dataframe_with_profit_scores(",
        'score_column = "profit_score"',
        'stock_info["profit_score"]',
        'stock_info["expected_value"]',
    ),
    "prism-insight/stock_tracking_agent.py": (
        "apply_risk_governor_to_scenario(",
        "### agents_invest Profit Context",
        "trigger_profit_context",
        "profit_score': stock.get('profit_score'",
    ),
    "prism-insight/cores/agents/trading_agents.py": (
        "agents_invest Profit Optimization Addendum",
        "risk_governor_context",
    ),
}

LIKELY_AGENT_PATHS = [
    "prism-insight/cores/agents/trading_agents.py",
    "prism-insight/cores/agents",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check PRISM-INSIGHT integration status")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--allow-missing-upstream",
        action="store_true",
        help="return success when local optimization modules are ready but prism-insight/ has not been imported yet",
    )
    args = parser.parse_args(argv)

    result = build_report()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return 0 if is_success(result, allow_missing_upstream=args.allow_missing_upstream) else 2


def is_success(result: dict[str, object], *, allow_missing_upstream: bool = False) -> bool:
    if result["fully_wired"]:
        return True
    return bool(
        allow_missing_upstream
        and result["optimization_modules_present"]
        and not result["upstream_present"]
    )


def build_report() -> dict[str, object]:
    root_missing = missing_paths(REQUIRED_ROOT_FILES)
    upstream_missing = missing_paths(EXPECTED_UPSTREAM_FILES)
    agent_paths_found = [path for path in LIKELY_AGENT_PATHS if (ROOT / path).exists()]
    patch_status = marker_status(PATCH_MARKERS)

    ready_for_adapter_wiring = not root_missing and not upstream_missing
    fully_wired = bool(ready_for_adapter_wiring and all(patch_status.values()))

    return {
        "repo_root": str(ROOT),
        "optimization_modules_present": not root_missing,
        "optimization_missing": root_missing,
        "upstream_present": not upstream_missing,
        "upstream_missing": upstream_missing,
        "agent_paths_found": agent_paths_found,
        "patch_status": patch_status,
        "ready_for_adapter_wiring": ready_for_adapter_wiring,
        "fully_wired": fully_wired,
        "next_steps": next_steps(root_missing, upstream_missing, patch_status),
    }


def missing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if not (ROOT / path).exists()]


def marker_status(markers: dict[str, tuple[str, ...]]) -> dict[str, bool]:
    status: dict[str, bool] = {}
    for path, required_markers in markers.items():
        target = ROOT / path
        text = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else ""
        status[path] = bool(text and all(marker in text for marker in required_markers))
    return status


def next_steps(root_missing: list[str], upstream_missing: list[str], patch_status: dict[str, bool]) -> list[str]:
    steps: list[str] = []
    if root_missing:
        steps.append("optimization/runtime/db 보완 파일이 누락되었습니다. kdk212/agents_invest 최신 main을 pull 하세요.")
    if upstream_missing:
        steps.append("PRISM-INSIGHT 원본이 아직 prism-insight/ 하위 폴더에 없습니다. scripts/integrate_prism_insight.*를 실행하세요.")
    if not root_missing and not upstream_missing:
        unwired = [path for path, wired in patch_status.items() if not wired]
        if unwired:
            steps.append("python scripts/patch_prism_adapters.py 를 실행해 다음 파일을 보강 연결하세요: " + ", ".join(unwired))
        else:
            steps.append("adapter wiring markers are present. python -m runtime.preflight --json 및 python -m pytest -q를 실행하세요.")
    return steps


def print_report(result: dict[str, object]) -> None:
    print(f"repo_root: {result['repo_root']}")
    print(f"optimization_modules_present: {result['optimization_modules_present']}")
    print(f"upstream_present: {result['upstream_present']}")
    print(f"ready_for_adapter_wiring: {result['ready_for_adapter_wiring']}")
    print(f"fully_wired: {result['fully_wired']}")

    if result["optimization_missing"]:
        print("optimization_missing:")
        for path in result["optimization_missing"]:
            print(f"- {path}")

    if result["upstream_missing"]:
        print("upstream_missing:")
        for path in result["upstream_missing"]:
            print(f"- {path}")

    if result["agent_paths_found"]:
        print("agent_paths_found:")
        for path in result["agent_paths_found"]:
            print(f"- {path}")

    print("patch_status:")
    for path, wired in result["patch_status"].items():
        print(f"- {path}: {wired}")

    print("next_steps:")
    for step in result["next_steps"]:
        print(f"- {step}")


if __name__ == "__main__":
    raise SystemExit(main())
