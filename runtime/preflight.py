"""Preflight checks before running agents_invest on a server."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from optimization import ProfitScoringEngine, RiskGovernor
from optimization.paper_validator import PaperTrade, PaperTradingValidator
from runtime import evaluate_startup_safety, load_runtime_secrets, load_runtime_settings, public_secret_state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run agents_invest preflight checks")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--allow-missing-secrets",
        action="store_true",
        help="return success when only runtime secrets are missing; use for install/dashboard checks, not live trading",
    )
    args = parser.parse_args(argv)

    settings = load_runtime_settings()
    secret_result = load_runtime_secrets(
        enabled=settings.ssm_settings_enabled,
        prefix=settings.ssm_parameter_prefix,
        region=settings.aws_region,
    )
    safety = evaluate_startup_safety(settings)
    module_check = _check_modules()
    ready = safety.allowed and secret_result.ok and module_check["ok"]
    install_ready = safety.allowed and module_check["ok"] and secret_result.ok
    if args.allow_missing_secrets:
        install_ready = safety.allowed and module_check["ok"]

    result = {
        "startup_safety": asdict(safety),
        "secret_check": _public_secret_result(secret_result),
        "secret_env_present": public_secret_state(),
        "module_check": module_check,
        "ready": ready,
        "install_ready": install_ready,
        "missing_secrets_allowed": bool(args.allow_missing_secrets),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text(result)

    return 0 if (result["ready"] or result["install_ready"]) else 2


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


def _public_secret_result(secret_result) -> dict[str, object]:
    return {
        "ok": secret_result.ok,
        "source": secret_result.source,
        "loaded_env_names": list(secret_result.loaded_env_names),
        "missing_env_names": list(secret_result.missing_env_names),
        "errors": list(secret_result.errors),
    }


def _print_text(result: dict[str, object]) -> None:
    safety = result["startup_safety"]
    module_check = result["module_check"]
    secret_check = result["secret_check"]
    print(f"ready: {result['ready']}")
    print(f"install_ready: {result['install_ready']}")
    print(f"missing_secrets_allowed: {result['missing_secrets_allowed']}")
    print(f"mode: {safety['mode']}")
    print(f"safety_allowed: {safety['allowed']}")
    print("safety_reasons:")
    for reason in safety["reasons"]:
        print(f"- {reason}")
    if safety["warnings"]:
        print("warnings:")
        for warning in safety["warnings"]:
            print(f"- {warning}")
    print(f"secret_check_ok: {secret_check['ok']}")
    print(f"secret_source: {secret_check['source']}")
    if secret_check["missing_env_names"]:
        print("missing_secret_env_names:")
        for name in secret_check["missing_env_names"]:
            print(f"- {name}")
    if secret_check["errors"]:
        print("secret_errors:")
        for error in secret_check["errors"]:
            print(f"- {error}")
    print(f"module_check_ok: {module_check['ok']}")
    if not module_check["ok"]:
        print(f"module_error: {module_check.get('error')}")


if __name__ == "__main__":
    sys.exit(main())