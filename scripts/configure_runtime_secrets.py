"""Configure runtime secrets for local or AWS execution.

This helper stores OpenAI, KIS, Telegram, and optional KRX direct-login secrets
without printing plaintext values. Local runs write an env file. AWS runs write
SSM SecureString values.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.configure_telegram import ConfigurationError, merge_env_text, normalize_prefix

DEFAULT_ENV_PATH = Path("config/runtime.env")
DEFAULT_PREFIX = "/agents-invest"
DEFAULT_REGION = "ap-southeast-2"

SECRET_SPECS = (
    ("OPENAI_API_KEY", "openai/api-key", "OpenAI API key", True),
    ("KIS_APP_KEY", "kis/app-key", "KIS app key", False),
    ("KIS_APP_SECRET", "kis/app-secret", "KIS app secret", False),
    ("KIS_ACCOUNT_NO", "kis/account-no", "KIS account number", False),
    ("TELEGRAM_BOT_TOKEN", "telegram/bot-token", "Telegram bot token", False),
    ("TELEGRAM_CHAT_ID", "telegram/chat-id", "Telegram chat id", False),
    ("KRX_ID", "krx/id", "KRX direct login id", False),
    ("KRX_PW", "krx/pw", "KRX direct login password", False),
)

LOCAL_DEFAULTS = {
    "TELEGRAM_ENABLED": "true",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure runtime secrets")
    parser.add_argument(
        "--target",
        choices=("local", "ssm", "both"),
        default="local",
        help="where to store runtime secrets",
    )
    parser.add_argument("--env-path", default=str(DEFAULT_ENV_PATH), help="local env file path")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region for SSM writes")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="SSM parameter prefix")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="read secret values from environment only",
    )
    parser.add_argument(
        "--include-optional-empty",
        action="store_true",
        help="require every supported secret instead of only values provided in the environment",
    )
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        values = collect_runtime_secret_values(
            os.environ,
            non_interactive=args.non_interactive,
            require_all=args.include_optional_empty,
        )
        if args.target in {"local", "both"}:
            local_values = dict(LOCAL_DEFAULTS)
            local_values.update(values)
            write_local_env(Path(args.env_path), local_values)
            print(f"saved runtime secrets to {args.env_path}")
        if args.target in {"ssm", "both"}:
            put_runtime_secret_parameters(
                values,
                region=args.region,
                prefix=args.prefix,
                dry_run=args.dry_run,
            )
            print(f"saved runtime secrets to SSM under {normalize_prefix(args.prefix)}")
        print("stored variables: " + ", ".join(sorted(values)))
    except ConfigurationError as exc:
        print(f"configuration failed: {exc}", file=sys.stderr)
        return 2
    return 0


def collect_runtime_secret_values(
    env: Mapping[str, str],
    *,
    non_interactive: bool = False,
    require_all: bool = False,
) -> dict[str, str]:
    values: dict[str, str] = {}

    for env_name, _suffix, label, required_by_default in SECRET_SPECS:
        value = str(env.get(env_name, "")).strip()
        required = require_all or required_by_default
        if not value and not non_interactive:
            prompt = f"{label}"
            if not required:
                prompt += " (blank to skip)"
            prompt += ": "
            value = getpass.getpass(prompt).strip()
        if value:
            values[env_name] = value
        elif required:
            raise ConfigurationError(f"{env_name} is required")

    validate_secret_values(values)
    if not values:
        raise ConfigurationError("at least one secret value is required")
    return values


def validate_secret_values(values: Mapping[str, str]) -> None:
    supported = {env_name for env_name, *_rest in SECRET_SPECS}
    for key, value in values.items():
        if key not in supported and key not in LOCAL_DEFAULTS:
            raise ConfigurationError(f"unsupported secret key: {key}")
        if any(ch in str(value) for ch in "\r\n"):
            raise ConfigurationError(f"{key} must be a single line")


def write_local_env(path: Path, updates: Mapping[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merge_env_text(text, updates), encoding="utf-8")


def put_runtime_secret_parameters(
    values: Mapping[str, str],
    *,
    region: str = DEFAULT_REGION,
    prefix: str = DEFAULT_PREFIX,
    dry_run: bool = False,
    client: Any | None = None,
) -> None:
    validate_secret_values(values)
    if dry_run:
        return

    suffix_by_env = {env_name: suffix for env_name, suffix, *_rest in SECRET_SPECS}
    ssm_client = client or build_ssm_client(region)
    for env_name, value in values.items():
        suffix = suffix_by_env[env_name]
        ssm_client.put_parameter(
            Name=parameter_name(prefix, suffix),
            Type="SecureString",
            Value=value,
            Overwrite=True,
        )


def build_ssm_client(region: str) -> Any:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on deployment environment
        raise ConfigurationError("boto3 is required for --target ssm; install agents-invest[aws]") from exc
    return boto3.client("ssm", region_name=region)


def parameter_name(prefix: str, suffix: str) -> str:
    return f"{normalize_prefix(prefix)}/{suffix.strip('/')}"


if __name__ == "__main__":
    raise SystemExit(main())
