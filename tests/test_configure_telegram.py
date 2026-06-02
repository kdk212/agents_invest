from __future__ import annotations

import pytest

from scripts.configure_telegram import (
    ConfigurationError,
    collect_telegram_values,
    merge_env_text,
    parameter_name,
)


def test_merge_env_text_replaces_and_appends_values() -> None:
    original = "APP_ENV=paper\nTELEGRAM_ENABLED=false\n# keep me\n"

    merged = merge_env_text(
        original,
        {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "token-value",
            "TELEGRAM_CHAT_ID": "12345",
        },
    )

    assert "APP_ENV=paper" in merged
    assert "TELEGRAM_ENABLED=true" in merged
    assert "TELEGRAM_BOT_TOKEN=token-value" in merged
    assert "TELEGRAM_CHAT_ID=12345" in merged
    assert "# keep me" in merged


def test_collect_values_non_interactive_requires_env_values() -> None:
    with pytest.raises(ConfigurationError):
        collect_telegram_values({}, non_interactive=True)


def test_collect_values_non_interactive_reads_env_values() -> None:
    values = collect_telegram_values(
        {
            "TELEGRAM_BOT_TOKEN": "token-value",
            "TELEGRAM_CHAT_ID": "12345",
        },
        non_interactive=True,
    )

    assert values == {
        "TELEGRAM_ENABLED": "true",
        "TELEGRAM_BOT_TOKEN": "token-value",
        "TELEGRAM_CHAT_ID": "12345",
    }


def test_parameter_name_normalizes_prefix() -> None:
    assert parameter_name("agents-invest", "telegram/bot-token") == "/agents-invest/telegram/bot-token"
    assert parameter_name("/agents-invest/", "/telegram/chat-id") == "/agents-invest/telegram/chat-id"
