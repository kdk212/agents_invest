"""Safe entrypoint for agents_invest runtime.

This runner is deliberately conservative. It validates runtime safety first and
only provides a placeholder loop until the upstream PRISM-INSIGHT runner is
merged and wired through the optimization adapters.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict

from runtime import evaluate_startup_safety, load_runtime_secrets, load_runtime_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="agents_invest safe runtime runner")
    parser.add_argument("--once", action="store_true", help="run startup checks once and exit")
    parser.add_argument("--interval-seconds", type=int, default=60, help="sleep interval for placeholder loop")
    args = parser.parse_args(argv)

    settings = load_runtime_settings()
    secret_result = _load_secrets_for_settings(settings)
    safety = evaluate_startup_safety(settings)
    print(
        json.dumps(
            {
                "settings": _public_settings(settings),
                "secrets": _public_secret_result(secret_result),
                "safety": asdict(safety),
            },
            ensure_ascii=False,
        )
    )

    if not safety.allowed or not secret_result.ok:
        return 2

    if args.once:
        return 0

    while True:
        settings = load_runtime_settings()
        secret_result = _load_secrets_for_settings(settings)
        safety = evaluate_startup_safety(settings)
        if not safety.allowed or not secret_result.ok:
            print(
                json.dumps(
                    {
                        "status": "runtime_safety_blocked",
                        "settings": _public_settings(settings),
                        "secrets": _public_secret_result(secret_result),
                        "safety": asdict(safety),
                    },
                    ensure_ascii=False,
                )
            )
            return 2

        print(
            json.dumps(
                {
                    "status": "waiting_for_prism_insight_integration",
                    "mode": settings.trading_mode,
                    "settings_source": settings.settings_source,
                    "secret_source": secret_result.source,
                    "secret_env_loaded": list(secret_result.loaded_env_names),
                },
                ensure_ascii=False,
            )
        )
        time.sleep(max(5, args.interval_seconds))


def _load_secrets_for_settings(settings):
    return load_runtime_secrets(
        enabled=settings.ssm_settings_enabled,
        prefix=settings.ssm_parameter_prefix,
        region=settings.aws_region,
    )


def _public_settings(settings) -> dict[str, object]:
    public = asdict(settings)
    return {key: value for key, value in public.items() if "secret" not in key and "key" not in key}


def _public_secret_result(secret_result) -> dict[str, object]:
    return {
        "ok": secret_result.ok,
        "source": secret_result.source,
        "loaded_env_names": list(secret_result.loaded_env_names),
        "missing_env_names": list(secret_result.missing_env_names),
        "errors": list(secret_result.errors),
    }


if __name__ == "__main__":
    sys.exit(main())
