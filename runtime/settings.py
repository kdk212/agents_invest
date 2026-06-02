"""Runtime configuration loaded from environment variables and optional SSM overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .ssm import load_ssm_parameter_overrides

DEFAULT_RUNTIME_ENV_FILE = Path("config/runtime.env")
RUNTIME_ENV_FILE_ENV = "AGENTS_INVEST_ENV_FILE"


@dataclass(frozen=True)
class RuntimeSettings:
    app_env: str
    trading_mode: str
    aws_region: str
    kill_switch: bool
    paper_validation_approved: bool
    max_daily_loss_pct: float
    max_positions: int
    max_same_sector: int
    max_sector_weight_pct: float
    min_buy_score: float
    min_profit_score: float
    min_risk_reward: float
    max_expected_loss_pct: float
    telegram_enabled: bool
    cloudwatch_enabled: bool
    ssm_settings_enabled: bool
    ssm_parameter_prefix: str
    settings_source: str
    settings_errors: tuple[str, ...]

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @property
    def is_paper(self) -> bool:
        return self.trading_mode == "paper"


def load_runtime_settings(
    env: Mapping[str, str] | None = None,
    *,
    include_remote: bool = True,
    parameter_client: Any | None = None,
    env_file: str | Path | None = DEFAULT_RUNTIME_ENV_FILE,
) -> RuntimeSettings:
    settings_errors: list[str] = []
    settings_source = "env"

    if env is None:
        selected_env_file = select_runtime_env_file(os.environ, env_file)
        values = load_runtime_env_file(selected_env_file, errors=settings_errors)
        if values:
            settings_source = "env_file+env"
            apply_runtime_env_defaults(values)
        values.update(os.environ)
    else:
        values = dict(env)

    ssm_settings_enabled = _as_bool(values, "ENABLE_SSM_SETTINGS", False)
    ssm_parameter_prefix = _as_text(values, "SSM_PARAMETER_PREFIX", "/agents-invest")
    aws_region = _as_str(values, "AWS_REGION", "ap-southeast-2")

    if include_remote and ssm_settings_enabled:
        try:
            values.update(
                load_ssm_parameter_overrides(
                    prefix=ssm_parameter_prefix,
                    region=aws_region,
                    client=parameter_client,
                )
            )
            settings_source = f"{settings_source}+ssm"
        except Exception as exc:  # pragma: no cover - exercised with fake client in tests
            settings_errors.append(f"ssm_load_failed: {exc.__class__.__name__}: {exc}")
            settings_source = f"{settings_source}+ssm_error"

    return RuntimeSettings(
        app_env=_as_str(values, "APP_ENV", "paper"),
        trading_mode=_as_str(values, "TRADING_MODE", "paper"),
        aws_region=_as_str(values, "AWS_REGION", "ap-southeast-2"),
        kill_switch=_as_bool(values, "KILL_SWITCH", False),
        paper_validation_approved=_as_bool(values, "PAPER_VALIDATION_APPROVED", False),
        max_daily_loss_pct=_as_float(values, "MAX_DAILY_LOSS_PCT", 3.0),
        max_positions=_as_int(values, "MAX_POSITIONS", 10),
        max_same_sector=_as_int(values, "MAX_SAME_SECTOR", 3),
        max_sector_weight_pct=_as_float(values, "MAX_SECTOR_WEIGHT_PCT", 30.0),
        min_buy_score=_as_float(values, "MIN_BUY_SCORE", 7.0),
        min_profit_score=_as_float(values, "MIN_PROFIT_SCORE", 60.0),
        min_risk_reward=_as_float(values, "MIN_RISK_REWARD", 1.2),
        max_expected_loss_pct=_as_float(values, "MAX_EXPECTED_LOSS_PCT", 7.0),
        telegram_enabled=_as_bool(values, "TELEGRAM_ENABLED", True),
        cloudwatch_enabled=_as_bool(values, "CLOUDWATCH_ENABLED", False),
        ssm_settings_enabled=ssm_settings_enabled,
        ssm_parameter_prefix=ssm_parameter_prefix,
        settings_source=settings_source,
        settings_errors=tuple(settings_errors),
    )


def select_runtime_env_file(
    env: Mapping[str, str],
    fallback: str | Path | None = DEFAULT_RUNTIME_ENV_FILE,
) -> str | Path | None:
    explicit_path = str(env.get(RUNTIME_ENV_FILE_ENV, "")).strip()
    return explicit_path or fallback


def load_runtime_env_file(
    path: str | Path | None = DEFAULT_RUNTIME_ENV_FILE,
    *,
    errors: list[str] | None = None,
) -> dict[str, str]:
    if path is None:
        return {}

    env_path = Path(path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    try:
        for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                if errors is not None:
                    errors.append(f"env_file_invalid_line:{env_path}:{line_number}")
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                if errors is not None:
                    errors.append(f"env_file_empty_key:{env_path}:{line_number}")
                continue
            values[key] = _strip_env_value(value.strip())
    except OSError as exc:
        if errors is not None:
            errors.append(f"env_file_load_failed:{env_path}:{exc.__class__.__name__}:{exc}")
    return values


def apply_runtime_env_defaults(values: Mapping[str, str]) -> None:
    for key, value in values.items():
        os.environ.setdefault(key, value)


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _as_str(env: Mapping[str, str], key: str, default: str) -> str:
    return str(env.get(key, default)).strip().lower()


def _as_text(env: Mapping[str, str], key: str, default: str) -> str:
    return str(env.get(key, default)).strip() or default


def _as_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_float(env: Mapping[str, str], key: str, default: float) -> float:
    try:
        return float(env.get(key, default))
    except (TypeError, ValueError):
        return default


def _as_int(env: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(float(env.get(key, default)))
    except (TypeError, ValueError):
        return default
