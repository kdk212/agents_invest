"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


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

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @property
    def is_paper(self) -> bool:
        return self.trading_mode == "paper"


def load_runtime_settings(env: Mapping[str, str] | None = None) -> RuntimeSettings:
    values = env or os.environ
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
    )


def _as_str(env: Mapping[str, str], key: str, default: str) -> str:
    return str(env.get(key, default)).strip().lower()


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
