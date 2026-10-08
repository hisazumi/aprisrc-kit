from pathlib import Path

import pytest
from pydantic import ValidationError

from apris_server.config import AppConfig


def test_default_config_selects_simulator_without_rover_credential() -> None:
    config = AppConfig.from_environment(Path("/repo"), {})
    assert config.adapter_type == "simulator"
    assert config.rover_id is None
    assert config.rover_token_value() is None
    assert config.assistant_api_key_value() is None
    assert config.assistant_model == "gpt-6-luna"
    assert config.log_directory == Path("/repo/.runtime/logs")


def test_websocket_rover_requires_id_and_secret_token() -> None:
    with pytest.raises(ValidationError, match="APRIS_ROVER_ID"):
        AppConfig.from_environment(
            Path("/repo"),
            {"APRIS_ADAPTER": "websocket_rover", "APRIS_ROVER_TOKEN": "secret"},
        )
    with pytest.raises(ValidationError, match="APRIS_ROVER_TOKEN"):
        AppConfig.from_environment(
            Path("/repo"),
            {"APRIS_ADAPTER": "websocket_rover", "APRIS_ROVER_ID": "ugv02-1"},
        )

    config = AppConfig.from_environment(
        Path("/repo"),
        {
            "APRIS_ADAPTER": "websocket_rover",
            "APRIS_ROVER_ID": "ugv02-1",
            "APRIS_ROVER_TOKEN": "secret",
            "APRIS_DEPLOYMENT_PROFILE": "edge",
        },
    )
    assert config.adapter_type == "websocket_rover"
    assert config.rover_id == "ugv02-1"
    assert config.rover_token_value() == "secret"
    assert "secret" not in repr(config)


def test_assistant_key_is_secret_and_model_is_configurable() -> None:
    config = AppConfig.from_environment(
        Path("/repo"),
        {"OPENAI_API_KEY": "assistant-secret", "APRIS_ASSISTANT_MODEL": "test-model"},
    )

    assert config.assistant_api_key_value() == "assistant-secret"
    assert config.assistant_model == "test-model"
    assert "assistant-secret" not in repr(config)


def test_unknown_adapter_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig.from_environment(Path("/repo"), {"APRIS_ADAPTER": "serial_rover"})


def test_factory_http_requires_private_host_and_rejects_hosted_profile() -> None:
    with pytest.raises(ValidationError, match="APRIS_FACTORY_HTTP_HOST"):
        AppConfig.from_environment(Path("/repo"), {"APRIS_ADAPTER": "factory_http"})
    with pytest.raises(ValidationError, match="private or loopback"):
        AppConfig.from_environment(
            Path("/repo"),
            {
                "APRIS_ADAPTER": "factory_http",
                "APRIS_FACTORY_HTTP_HOST": "8.8.8.8",
            },
        )
    with pytest.raises(ValidationError, match="not allowed in the hosted profile"):
        AppConfig.from_environment(
            Path("/repo"),
            {
                "APRIS_ADAPTER": "factory_http",
                "APRIS_FACTORY_HTTP_HOST": "192.168.1.20",
                "APRIS_DEPLOYMENT_PROFILE": "hosted",
            },
        )

    config = AppConfig.from_environment(
        Path("/repo"),
        {
            "APRIS_ADAPTER": "factory_http",
            "APRIS_FACTORY_HTTP_HOST": "192.168.1.20",
            "APRIS_FACTORY_HTTP_PORT": "8080",
        },
    )
    assert config.adapter_type == "factory_http"
    assert str(config.factory_http_host) == "192.168.1.20"
    assert config.factory_http_port == 8080
