from __future__ import annotations

from runtime.secrets import (
    load_runtime_secrets,
    load_ssm_secret_values,
    parameter_name_to_env_name,
    public_secret_state,
)


class FakeSsmClient:
    def __init__(self, parameters: dict[str, str]) -> None:
        self.parameters = parameters
        self.requests: list[dict[str, object]] = []

    def get_parameters(self, **kwargs):
        self.requests.append(kwargs)
        requested = kwargs["Names"]
        return {
            "Parameters": [
                {"Name": name, "Value": self.parameters[name]}
                for name in requested
                if name in self.parameters
            ]
        }


def test_load_ssm_secret_values_maps_supported_parameters() -> None:
    client = FakeSsmClient(
        {
            "/agents-invest/openai/api-key": "openai-key",
            "/agents-invest/telegram/bot-token": "telegram-token",
            "/agents-invest/kis/app-secret": "CHANGE_ME",
        }
    )

    values = load_ssm_secret_values(client=client)

    assert values == {
        "OPENAI_API_KEY": "openai-key",
        "TELEGRAM_BOT_TOKEN": "telegram-token",
    }
    assert client.requests[0]["WithDecryption"] is True


def test_load_runtime_secrets_injects_without_returning_values() -> None:
    client = FakeSsmClient(
        {
            "/agents-invest/openai/api-key": "openai-key",
            "/agents-invest/telegram/chat-id": "12345",
        }
    )
    environ: dict[str, str] = {}

    result = load_runtime_secrets(enabled=True, client=client, environ=environ)

    assert result.ok is True
    assert result.source == "env+ssm_secrets"
    assert "OPENAI_API_KEY" in result.loaded_env_names
    assert "TELEGRAM_CHAT_ID" in result.loaded_env_names
    assert environ == {"OPENAI_API_KEY": "openai-key", "TELEGRAM_CHAT_ID": "12345"}


def test_load_runtime_secrets_disabled_reports_existing_env_only() -> None:
    result = load_runtime_secrets(enabled=False, environ={"OPENAI_API_KEY": "existing"})

    assert result.source == "env"
    assert result.loaded_env_names == ("OPENAI_API_KEY",)
    assert "TELEGRAM_BOT_TOKEN" in result.missing_env_names


def test_parameter_name_to_env_name_requires_prefix() -> None:
    assert parameter_name_to_env_name("/agents-invest/openai/api-key", "/agents-invest") == "OPENAI_API_KEY"
    assert parameter_name_to_env_name("/other/openai/api-key", "/agents-invest") is None


def test_public_secret_state_reports_presence_without_values() -> None:
    state = public_secret_state({"OPENAI_API_KEY": "secret", "KIS_APP_KEY": ""})

    assert state["OPENAI_API_KEY"] is True
    assert state["KIS_APP_KEY"] is False
