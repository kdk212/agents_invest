"""AWS Systems Manager Parameter Store helpers for runtime settings."""

from __future__ import annotations

from typing import Any, Mapping


PARAMETER_TO_ENV = {
    "kill-switch": "KILL_SWITCH",
    "trading-mode": "TRADING_MODE",
    "paper-validation-approved": "PAPER_VALIDATION_APPROVED",
    "max-daily-loss-pct": "MAX_DAILY_LOSS_PCT",
    "max-positions": "MAX_POSITIONS",
    "max-same-sector": "MAX_SAME_SECTOR",
    "max-sector-weight-pct": "MAX_SECTOR_WEIGHT_PCT",
    "min-buy-score": "MIN_BUY_SCORE",
    "min-profit-score": "MIN_PROFIT_SCORE",
    "min-risk-reward": "MIN_RISK_REWARD",
    "max-expected-loss-pct": "MAX_EXPECTED_LOSS_PCT",
}


def load_ssm_parameter_overrides(
    *,
    prefix: str = "/agents-invest",
    region: str = "ap-southeast-2",
    client: Any | None = None,
) -> dict[str, str]:
    """Load supported runtime settings from SSM Parameter Store.

    Secret values such as API keys are intentionally not returned here. This loader
    only handles operational switches and risk thresholds that are safe to expose
    in startup diagnostics.
    """
    normalized_prefix = _normalize_prefix(prefix)
    ssm_client = client or _build_ssm_client(region)
    overrides: dict[str, str] = {}
    next_token: str | None = None

    while True:
        request: dict[str, Any] = {
            "Path": normalized_prefix,
            "Recursive": True,
            "WithDecryption": True,
        }
        if next_token:
            request["NextToken"] = next_token

        response = ssm_client.get_parameters_by_path(**request)
        for parameter in response.get("Parameters", []):
            env_key = _parameter_name_to_env_key(str(parameter.get("Name", "")), normalized_prefix)
            if env_key:
                overrides[env_key] = str(parameter.get("Value", ""))

        next_token = response.get("NextToken")
        if not next_token:
            break

    return overrides


def _build_ssm_client(region: str) -> Any:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on deployment environment
        raise RuntimeError("boto3 is required when ENABLE_SSM_SETTINGS=true") from exc

    return boto3.client("ssm", region_name=region)


def _normalize_prefix(prefix: str) -> str:
    cleaned = str(prefix or "/agents-invest").strip()
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return cleaned.rstrip("/")


def _parameter_name_to_env_key(name: str, prefix: str) -> str | None:
    if not name.startswith(f"{prefix}/"):
        return None
    leaf = name.removeprefix(f"{prefix}/").strip("/").split("/")[-1]
    return PARAMETER_TO_ENV.get(leaf)


def overlay_ssm_parameters(
    env: Mapping[str, str],
    *,
    prefix: str = "/agents-invest",
    region: str = "ap-southeast-2",
    client: Any | None = None,
) -> dict[str, str]:
    values = dict(env)
    values.update(load_ssm_parameter_overrides(prefix=prefix, region=region, client=client))
    return values
