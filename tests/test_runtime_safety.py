from runtime import evaluate_startup_safety, load_runtime_settings
from runtime.preflight import main as preflight_main
from runtime.ssm import load_ssm_parameter_overrides


class FakeSSMClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get_parameters_by_path(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages.pop(0)


class BrokenSSMClient:
    def get_parameters_by_path(self, **kwargs):
        raise RuntimeError("ssm unavailable")


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


def test_ssm_loader_maps_supported_operational_parameters():
    client = FakeSSMClient(
        [
            {
                "Parameters": [
                    {"Name": "/agents-invest/kill-switch", "Value": "true"},
                    {"Name": "/agents-invest/trading-mode", "Value": "paper"},
                    {"Name": "/agents-invest/openai/api-key", "Value": "secret"},
                    {"Name": "/other/kill-switch", "Value": "false"},
                ]
            }
        ]
    )

    overrides = load_ssm_parameter_overrides(client=client)

    assert overrides == {"KILL_SWITCH": "true", "TRADING_MODE": "paper"}
    assert client.calls[0]["WithDecryption"] is True


def test_ssm_settings_override_environment_values():
    client = FakeSSMClient(
        [
            {
                "Parameters": [
                    {"Name": "/agents-invest/kill-switch", "Value": "true"},
                    {"Name": "/agents-invest/max-positions", "Value": "4"},
                ]
            }
        ]
    )
    settings = load_runtime_settings(
        {"ENABLE_SSM_SETTINGS": "true", "KILL_SWITCH": "false", "MAX_POSITIONS": "10"},
        parameter_client=client,
    )
    safety = evaluate_startup_safety(settings)

    assert settings.settings_source == "env+ssm"
    assert settings.kill_switch is True
    assert settings.max_positions == 4
    assert not safety.allowed
    assert any("Kill Switch" in reason for reason in safety.reasons)


def test_live_mode_blocks_when_ssm_settings_fail():
    settings = load_runtime_settings(
        {
            "APP_ENV": "production",
            "TRADING_MODE": "live",
            "PAPER_VALIDATION_APPROVED": "true",
            "KILL_SWITCH": "false",
            "ENABLE_SSM_SETTINGS": "true",
        },
        parameter_client=BrokenSSMClient(),
    )
    safety = evaluate_startup_safety(settings)

    assert settings.settings_source == "env+ssm_error"
    assert not safety.allowed
    assert any("원격 설정 로딩 실패" in reason for reason in safety.reasons)


def test_paper_mode_warns_when_ssm_settings_fail():
    settings = load_runtime_settings(
        {"ENABLE_SSM_SETTINGS": "true"},
        parameter_client=BrokenSSMClient(),
    )
    safety = evaluate_startup_safety(settings)

    assert safety.allowed
    assert any("원격 설정 로딩 실패" in warning for warning in safety.warnings)


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
    for key in [
        "APP_ENV",
        "TRADING_MODE",
        "KILL_SWITCH",
        "PAPER_VALIDATION_APPROVED",
        "ENABLE_SSM_SETTINGS",
    ]:
        monkeypatch.delenv(key, raising=False)

    assert preflight_main(["--json"]) == 0


def test_preflight_fails_when_live_without_approval(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("PAPER_VALIDATION_APPROVED", "false")
    monkeypatch.setenv("KILL_SWITCH", "false")
    monkeypatch.delenv("ENABLE_SSM_SETTINGS", raising=False)

    assert preflight_main(["--json"]) == 2
