"""Startup safety checks for paper/live trading modes."""

from __future__ import annotations

from dataclasses import dataclass

from .settings import RuntimeSettings


@dataclass(frozen=True)
class SafetyCheck:
    allowed: bool
    mode: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def evaluate_startup_safety(settings: RuntimeSettings) -> SafetyCheck:
    blockers: list[str] = []
    warnings: list[str] = []

    if settings.trading_mode not in {"paper", "live"}:
        blockers.append(f"지원하지 않는 TRADING_MODE: {settings.trading_mode}")

    if settings.kill_switch:
        blockers.append("Kill Switch가 활성화되어 신규 실행을 차단함")

    if settings.is_live:
        _evaluate_live_mode(settings, blockers, warnings)
    else:
        _evaluate_paper_mode(settings, warnings)

    if settings.max_daily_loss_pct <= 0:
        blockers.append("MAX_DAILY_LOSS_PCT는 0보다 커야 함")

    if settings.max_positions <= 0:
        blockers.append("MAX_POSITIONS는 1 이상이어야 함")

    if settings.max_sector_weight_pct <= 0:
        blockers.append("MAX_SECTOR_WEIGHT_PCT는 0보다 커야 함")

    return SafetyCheck(
        allowed=not blockers,
        mode=settings.trading_mode,
        reasons=tuple(blockers or ("startup_safety_passed",)),
        warnings=tuple(warnings),
    )


def _evaluate_live_mode(
    settings: RuntimeSettings,
    blockers: list[str],
    warnings: list[str],
) -> None:
    if settings.app_env != "production":
        blockers.append("live 모드는 APP_ENV=production에서만 허용")

    if not settings.paper_validation_approved:
        blockers.append("페이퍼트레이딩 검증 승인 전 live 모드 차단")

    if settings.max_daily_loss_pct > 3.0:
        warnings.append("live 모드 일일 손실 한도가 3%를 초과함")

    if settings.max_positions > 10:
        warnings.append("live 모드 최대 보유 종목 수가 10개를 초과함")


def _evaluate_paper_mode(settings: RuntimeSettings, warnings: list[str]) -> None:
    if settings.app_env == "production":
        warnings.append("APP_ENV=production이지만 TRADING_MODE=paper로 실행됨")
