from __future__ import annotations

import pytest

from scripts.configure_runtime_secrets import (
    ConfigurationError,
    collect_runtime_secret_values,
    parameter_name,
    put_runtime_secret_parameters,
    validate_secret_values,
)


def test_collect_runtime_secret_values_requires_openai_by_default() -> None:
    with pytest.raises(ConfigurationError):
        collect_runtime_secret_values({}, non_interactive=True)


def test_collect_runtime_secret_values_reads_environment_values() -> None:
    values = collect_runtime_secret_values(
        {
            "OPENAI_API_KEY": "openai-key",
            "TELEGRAM_BOT_TOKEN": "telegram-token",
            "TELEGRAM_CHAT_ID": "12345",
        },
        non_interactive=True,
    )

    assert values == {
        "OPENAI_API_KEY": "openai-key",
        "TELEGRAM_BOT_TOKEN": "telegram-token",
        "TELEGRAM_CHAT_ID": "12345",
    }


def test_collect_runtime_secret_values_can_require_every_supported_secret() -> None:
    with pytest.raises(ConfigurationError):
        collect_runtime_secret_values(
            {"OPENAI_API_KEY": "openai-key"},
            non_interactive=True,
            require_all=True,
        )


def test_validate_secret_values_rejects_multiline_values() -> None:
    with pytest.raises(ConfigurationError):
        validate_secret_values({"OPENAI_API_KEY": "line1\nline2"})


def test_put_runtime_secret_parameters_writes_secure_parameters() -> None:
    class FakeSsmClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, str | bool]] = []

        def put_parameter(self, **kwargs: str | bool) -> None:
            self.calls.append(kwargs)

    client = FakeSsmClient()

    put_runtime_secret_parameters(
        {
            "OPENAI_API_KEY": "openai-key",
            "KIS_APP_KEY": "kis-app-key",
            "TELEGRAM_CHAT_ID": "12345",
        },
        prefix="agents-invest",
        client=client,
    )

    assert client.calls == [
        {
            "Name": "/agents-invest/openai/api-key",
            "Type": "SecureString",
            "Value": "openai-key",
            "Overwrite": True,
        },
        {
            "Name": "/agents-invest/kis/app-key",
            "Type": "SecureString",
            "Value": "kis-app-key",
            "Overwrite": True,
        },
        {
            "Name": "/agents-invest/telegram/chat-id",
            "Type": "SecureString",
            "Value": "12345",
            "Overwrite": True,
        },
    ]


def test_parameter_name_normalizes_prefix() -> None:
    assert parameter_name("agents-invest", "openai/api-key") == "/agents-invest/openai/api-key"
    assert parameter_name("/agents-invest/", "/kis/app-secret") == "/agents-invest/kis/app-secret"
