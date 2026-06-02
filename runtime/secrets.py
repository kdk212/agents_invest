"""Load runtime secrets into process environment without exposing values."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

SECRET_PARAMETER_TO_ENV = {
    "openai/api-key": "OPENAI_API_KEY",
    "kis/app-key": "KIS_APP_KEY",
    "kis/app-secret": "KIS_APP_SECRET",
    "kis/account-no": "KIS_ACCOUNT_NO",
    "telegram/bot-token": "TELEGRAM_BOT_TOKEN",
    "telegram/chat-id": "TELEGRAM_CHAT_ID",
    "krx/id": "KRX_ID",
    "krx/pw": "KRX_PW",
}


@dataclass(frozen=True)
class SecretLoadResult:
    source: str
    loaded_env_names: tuple[str, ...]
    missing_env_names: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def load_runtime_secrets(
    *,
    enabled: bool,
    prefix: str = "/agents-invest",
    region: str = "ap-southeast-2",
    client: Any | None = None,
    environ: dict[str, str] | None = None,
    overwrite: bool = False,
) -> SecretLoadResult:
    """Load supported SecureString values from SSM into environment variables.

    Secret values are never returned. The result only reports variable names and
    errors so diagnostics can stay safe to print.
    """
    target_env = os.environ if environ is None else environ
    expected = tuple(SECRET_PARAMETER_TO_ENV.values())

    if not enabled:
        present = tuple(name for name in expected if target_env.get(name))
        missing = tuple(name for name in expected if not target_env.get(name))
        return SecretLoadResult("env", present, missing, ())

    try:
        values = load_ssm_secret_values(prefix=prefix, region=region, client=client)
    except Exception as exc:  # pragma: no cover - defensive deployment path
        present = tuple(name for name in expected if target_env.get(name))
        missing = tuple(name for name in expected if not target_env.get(name))
        return SecretLoadResult(
            "ssm_error",
            present,
            missing,
            (f"secret_load_failed: {exc.__class__.__name__}: {exc}",),
        )

    loaded: list[str] = []
    for env_name, value in values.items():
        if not value:
            continue
        if overwrite or not target_env.get(env_name):
            target_env[env_name] = value
        if target_env.get(env_name):
            loaded.append(env_name)

    loaded_set = set(loaded)
    present = tuple(name for name in expected if target_env.get(name) or name in loaded_set)
    missing = tuple(name for name in expected if name not in present)
    return SecretLoadResult("env+ssm_secrets", present, missing, ())


def load_ssm_secret_values(
    *,
    prefix: str = "/agents-invest",
    region: str = "ap-southeast-2",
    client: Any | None = None,
) -> dict[str, str]:
    normalized_prefix = normalize_prefix(prefix)
    ssm_client = client or build_ssm_client(region)
    names = [f"{normalized_prefix}/{suffix}" for suffix in SECRET_PARAMETER_TO_ENV]
    values: dict[str, str] = {}

    for chunk in chunked(names, 10):
        response = ssm_client.get_parameters(Names=list(chunk), WithDecryption=True)
        for parameter in response.get("Parameters", []):
            env_name = parameter_name_to_env_name(str(parameter.get("Name", "")), normalized_prefix)
            if env_name:
                raw_value = str(parameter.get("Value", ""))
                if raw_value and raw_value != "CHANGE_ME":
                    values[env_name] = raw_value
    return values


def build_ssm_client(region: str) -> Any:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on deployment environment
        raise RuntimeError("boto3 is required when loading SSM secrets") from exc
    return boto3.client("ssm", region_name=region)


def normalize_prefix(prefix: str) -> str:
    cleaned = str(prefix or "/agents-invest").strip()
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return cleaned.rstrip("/")


def parameter_name_to_env_name(name: str, prefix: str) -> str | None:
    if not name.startswith(f"{prefix}/"):
        return None
    suffix = name.removeprefix(f"{prefix}/").strip("/")
    return SECRET_PARAMETER_TO_ENV.get(suffix)


def chunked(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def public_secret_state(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    values = os.environ if environ is None else environ
    return {env_name: bool(values.get(env_name)) for env_name in SECRET_PARAMETER_TO_ENV.values()}
