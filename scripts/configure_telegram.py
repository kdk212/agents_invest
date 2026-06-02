"""Configure Telegram alert secrets for local or AWS runtime.

This helper intentionally avoids printing secret values. For local paper runs it
writes config/runtime.env. For EC2/AWS runs it stores the values in Systems
Manager Parameter Store as SecureString values.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Any, Mapping

DEFAULT_ENV_PATH = Path("config/runtime.env")
DEFAULT_PREFIX = "/agents-invest"
DEFAULT_REGION = "ap-southeast-2"
TELEGRAM_BOT_TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_KEY = "TELEGRAM_CHAT_ID"


class ConfigurationError(ValueError):
    """Raised when a required secret value is missing or unsafe to write."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure Telegram alert secrets")
    parser.add_argument(
        "--target",
        choices=("local", "ssm", "both"),
        default="local",
        help="where to store Telegram values",
    )
    parser.add_argument("--env-path", default=str(DEFAULT_ENV_PATH), help="local env file path")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region for SSM writes")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="SSM parameter prefix")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="read TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment only",
    )
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        values = collect_telegram_values(os.environ, non_interactive=args.non_interactive)
        if args.target in {"local", "both"}:
            write_local_env(Path(args.env_path), values)
            print(f"saved Telegram settings to {args.env_path}")
        if args.target in {"ssm", "both"}:
            put_telegram_parameters(
                values,
                region=args.region,
                prefix=args.prefix,
                dry_run=args.dry_run,
            )
            print(f"saved Telegram settings to SSM under {normalize_prefix(args.prefix)}/telegram")
    except ConfigurationError as exc:
        print(f"configuration failed: {exc}", file=sys.stderr)
        return 2
    return 0


def collect_telegram_values(
    env: Mapping[str, str],
    *,
    non_interactive: bool = False,
) -> dict[str, str]:
    bot_token = env.get(TELEGRAM_BOT_TOKEN_KEY, "").strip()
    chat_id = env.get(TELEGRAM_CHAT_ID_KEY, "").strip()

    if not bot_token and not non_interactive:
        bot_token = getpass.getpass("Telegram bot token: ").strip()
    if not chat_id and not non_interactive:
        chat_id = input("Telegram chat id: ").strip()

    values = {
        "TELEGRAM_ENABLED": "true",
        TELEGRAM_BOT_TOKEN_KEY: bot_token,
        TELEGRAM_CHAT_ID_KEY: chat_id,
    }
    validate_values(values)
    return values


def validate_values(values: Mapping[str, str]) -> None:
    for key in (TELEGRAM_BOT_TOKEN_KEY, TELEGRAM_CHAT_ID_KEY):
        value = str(values.get(key, "")).strip()
        if not value:
            raise ConfigurationError(f"{key} is required")
        if any(ch in value for ch in "\r\n"):
            raise ConfigurationError(f"{key} must be a single line")


def write_local_env(path: Path, updates: Mapping[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merge_env_text(text, updates), encoding="utf-8")


def merge_env_text(text: str, updates: Mapping[str, str]) -> str:
    remaining = dict(updates)
    lines: list[str] = []

    for line in text.splitlines():
        key = parse_env_key(line)
        if key in remaining:
            lines.append(f"{key}={remaining.pop(key)}")
        else:
            lines.append(line)

    if remaining and lines and lines[-1].strip():
        lines.append("")
    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    return "\n".join(lines).rstrip() + "\n"


def parse_env_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def put_telegram_parameters(
    values: Mapping[str, str],
    *,
    region: str = DEFAULT_REGION,
    prefix: str = DEFAULT_PREFIX,
    dry_run: bool = False,
    client: Any | None = None,
) -> None:
    parameters = {
        parameter_name(prefix, "telegram/bot-token"): values[TELEGRAM_BOT_TOKEN_KEY],
        parameter_name(prefix, "telegram/chat-id"): values[TELEGRAM_CHAT_ID_KEY],
    }
    if dry_run:
        return

    ssm_client = client or build_ssm_client(region)
    for name, value in parameters.items():
        ssm_client.put_parameter(
            Name=name,
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


def normalize_prefix(prefix: str) -> str:
    cleaned = str(prefix or DEFAULT_PREFIX).strip()
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return cleaned.rstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
