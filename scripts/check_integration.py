"""Verify that PRISM-INSIGHT and optimization add-ons are present.

Usage:
    python scripts/check_integration.py
    python scripts/check_integration.py --json
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
    "db/candidate_performance_tracker.sql",
]

EXPECTED_UPSTREAM_FILES = [
    "prism-insight/README.md",
    "prism-insight/README_ko.md",
    "prism-insight/LICENSE",
    "prism-insight/trigger_batch.py",
    "prism-insight/stock_tracking_agent.py",
]

LIKELY_AGENT_PATHS = [
    "prism-insight/cores/agents/trading_agents.py",
    "prism-insight/cores/agents",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check PRISM-INSIGHT integration status")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    result = build_report()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return 0 if result["ready_for_adapter_wiring"] else 2


def build_report() -> dict[str, object]:
    root_missing = missing_paths(REQUIRED_ROOT_FILES)
    upstream_missing = missing_paths(EXPECTED_UPSTREAM_FILES)
    agent_paths_found = [path for path in LIKELY_AGENT_PATHS if (ROOT / path).exists()]

    return {
        "repo_root": str(ROOT),
        "optimization_modules_present": not root_missing,
        "optimization_missing": root_missing,
        "upstream_present": not upstream_missing,
        "upstream_missing": upstream_missing,
        "agent_paths_found": agent_paths_found,
        "ready_for_adapter_wiring": not root_missing and not upstream_missing,
        "next_steps": next_steps(root_missing, upstream_missing),
    }


def missing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if not (ROOT / path).exists()]


def next_steps(root_missing: list[str], upstream_missing: list[str]) -> list[str]:
    steps: list[str] = []
    if root_missing:
        steps.append("optimization/runtime/db 보완 파일이 누락되었습니다. kdk212/agents_invest 최신 main을 pull 하세요.")
    if upstream_missing:
        steps.append("PRISM-INSIGHT 원본이 아직 prism-insight/ 하위 폴더에 없습니다. scripts/integrate_prism_insight.*를 실행하세요.")
    if not root_missing and not upstream_missing:
        steps.extend(
            [
                "prism-insight/trigger_batch.py에 enrich_candidates_with_profit_scores()를 연결하세요.",
                "prism-insight/stock_tracking_agent.py에 apply_risk_governor_to_scenario()를 연결하세요.",
                "python -m runtime.preflight --json 및 python -m pytest -q를 실행하세요.",
            ]
        )
    return steps


def print_report(result: dict[str, object]) -> None:
    print(f"repo_root: {result['repo_root']}")
    print(f"optimization_modules_present: {result['optimization_modules_present']}")
    print(f"upstream_present: {result['upstream_present']}")
    print(f"ready_for_adapter_wiring: {result['ready_for_adapter_wiring']}")

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

    print("next_steps:")
    for step in result["next_steps"]:
        print(f"- {step}")


if __name__ == "__main__":
    raise SystemExit(main())
