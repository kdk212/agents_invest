from __future__ import annotations

import os

from runtime.settings import load_runtime_env_file, load_runtime_settings, select_runtime_env_file


def test_load_runtime_env_file_parses_simple_values(tmp_path) -> None:
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "# local settings\n"
        "TRADING_MODE=paper\n"
        "TELEGRAM_ENABLED=false\n"
        "TELEGRAM_CHAT_ID='12345'\n"
        "BROKEN_LINE\n",
        encoding="utf-8",
    )
    errors: list[str] = []

    values = load_runtime_env_file(env_file, errors=errors)

    assert values["TRADING_MODE"] == "paper"
    assert values["TELEGRAM_ENABLED"] == "false"
    assert values["TELEGRAM_CHAT_ID"] == "12345"
    assert errors == [f"env_file_invalid_line:{env_file}:5"]


def test_load_runtime_settings_reads_env_file_without_overriding_process_env(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "TRADING_MODE=live\n"
        "KILL_SWITCH=true\n"
        "TELEGRAM_ENABLED=false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.delenv("KILL_SWITCH", raising=False)

    settings = load_runtime_settings(env_file=env_file, include_remote=False)

    assert settings.trading_mode == "paper"
    assert settings.kill_switch is True
    assert settings.telegram_enabled is False
    assert settings.settings_source == "env_file+env"
    assert os.environ["KILL_SWITCH"] == "true"


def test_custom_runtime_env_file_path_from_environment(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text("KILL_SWITCH=true\nTELEGRAM_ENABLED=false\n", encoding="utf-8")
    monkeypatch.setenv("AGENTS_INVEST_ENV_FILE", str(env_file))
    monkeypatch.delenv("KILL_SWITCH", raising=False)
    monkeypatch.delenv("TELEGRAM_ENABLED", raising=False)

    settings = load_runtime_settings(include_remote=False)

    assert settings.kill_switch is True
    assert settings.telegram_enabled is False
    assert select_runtime_env_file(os.environ) == str(env_file)
