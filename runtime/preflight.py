"""Preflight checks before running agents_invest on a server."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from optimization import ProfitScoringEngine, RiskGovernor
from optimization.paper_validator import PaperTrade, PaperTradingValidator
from runtime import evaluate_startup_safety, load_runtime_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run agents_invest preflight checks")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    settings = load_runtime_settings()
    safety = evaluate_startup_safety(settings)
    module_check = _check_modules()

    result = {
        "startup_safety": asdict(safety),
        "module_check": module_check,
        "ready": safety.allowed and module_check["ok"],
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text(result)

    return 0 if result["ready"] else 2


def _check_modules() -> dict[str, object]:
    try:
        scoring = ProfitScoringEngine().score_many([])
        risk = RiskGovernor()
        paper = PaperTradingValidator().validate([PaperTrade(ticker="TEST", return_pct=1.0)])
        return {
            "ok": True,
            "profit_scoring_empty_result": scoring,
            "risk_governor_class": risk.__class__.__name__,
            "paper_validator_total_trades": paper.total_trades,
        }
    except Exception as exc:  # pragma: no cover - defensive server check
        return {"ok": False, "error": str(exc)}


def _print_text(result: dict[str, object]) -> None:
    safety = result["startup_safety"]
    module_check = result["module_check"]
    print(f"ready: {result['ready']}")
    print(f"mode: {safety['mode']}")
    print(f"safety_allowed: {safety['allowed']}")
    print("safety_reasons:")
    for reason in safety["reasons"]:
        print(f"- {reason}")
    if safety["warnings"]:
        print("warnings:")
        for warning in safety["warnings"]:
            print(f"- {warning}")
    print(f"module_check_ok: {module_check['ok']}")
    if not module_check["ok"]:
        print(f"module_error: {module_check.get('error')}")


if __name__ == "__main__":
    sys.exit(main())
