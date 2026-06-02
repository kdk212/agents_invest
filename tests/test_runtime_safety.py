from runtime import evaluate_startup_safety, load_runtime_settings
from runtime.preflight import main as preflight_main


def test_paper_mode_is_default_and_allowed():
    settings = load_runtime_settings({})
    safety = evaluate_startup_safety(settings)

    assert settings.trading_mode == "paper"
    assert safety.allowed
    assert safety.reasons == ("startup_safety_passed",)


def test_kill_switch_blocks_startup():
    settings = load_runtime_settings({"KILL_SWITCH": "true"})
    safety = evaluate_startup_safety(settings)

    assert not safety.allowed
    assert any("Kill Switch" in reason for reason in safety.reasons)


def test_live_mode_requires_production_and_paper_approval():
    settings = load_runtime_settings(
        {
            "APP_ENV": "paper",
            "TRADING_MODE": "live",
            "PAPER_VALIDATION_APPROVED": "false",
        }
    )
    safety = evaluate_startup_safety(settings)

    assert not safety.allowed
    assert any("APP_ENV=production" in reason for reason in safety.reasons)
    assert any("페이퍼트레이딩 검증 승인" in reason for reason in safety.reasons)


def test_live_mode_allowed_after_required_flags():
    settings = load_runtime_settings(
        {
            "APP_ENV": "production",
            "TRADING_MODE": "live",
            "PAPER_VALIDATION_APPROVED": "true",
            "KILL_SWITCH": "false",
        }
    )
    safety = evaluate_startup_safety(settings)

    assert safety.allowed
    assert safety.mode == "live"


def test_invalid_risk_limits_block_startup():
    settings = load_runtime_settings(
        {
            "MAX_DAILY_LOSS_PCT": "0",
            "MAX_POSITIONS": "0",
            "MAX_SECTOR_WEIGHT_PCT": "0",
        }
    )
    safety = evaluate_startup_safety(settings)

    assert not safety.allowed
    assert len(safety.reasons) == 3


def test_preflight_passes_in_default_paper_mode(monkeypatch):
    for key in ["APP_ENV", "TRADING_MODE", "KILL_SWITCH", "PAPER_VALIDATION_APPROVED"]:
        monkeypatch.delenv(key, raising=False)

    assert preflight_main(["--json"]) == 0


def test_preflight_fails_when_live_without_approval(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("PAPER_VALIDATION_APPROVED", "false")
    monkeypatch.setenv("KILL_SWITCH", "false")

    assert preflight_main(["--json"]) == 2
