from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from ipaddress import IPv4Address
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_profile: Literal["development", "edge", "hosted"] = "development"
    adapter_type: Literal["simulator", "websocket_rover", "factory_http", "ros2_readonly"] = (
        "simulator"
    )
    ros2_state_file: Path | None = None
    rover_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    rover_token: SecretStr | None = None
    assistant_api_key: SecretStr | None = None
    assistant_model: str = Field(default="gpt-6-luna", min_length=1, max_length=100)
    factory_http_host: IPv4Address | None = None
    factory_http_port: int = Field(default=80, ge=1, le=65535)
    instance_id: str
    build_id: str = "development"
    log_directory: Path

    @model_validator(mode="after")
    def selected_adapter_has_required_configuration(self) -> AppConfig:
        if self.adapter_type == "ros2_readonly":
            if self.deployment_profile == "hosted" or self.ros2_state_file is None:
                raise ValueError("ros2_readonly needs a local APRIS_ROS2_STATE_FILE")
        if self.adapter_type == "websocket_rover":
            if self.rover_id is None:
                raise ValueError("APRIS_ROVER_ID is required for websocket_rover adapter")
            if self.rover_token is None or not self.rover_token.get_secret_value():
                raise ValueError("APRIS_ROVER_TOKEN is required for websocket_rover adapter")
        if self.adapter_type == "factory_http":
            if self.deployment_profile == "hosted":
                raise ValueError("factory_http adapter is not allowed in the hosted profile")
            if self.factory_http_host is None:
                raise ValueError("APRIS_FACTORY_HTTP_HOST is required for factory_http adapter")
            if not (self.factory_http_host.is_private or self.factory_http_host.is_loopback):
                raise ValueError(
                    "APRIS_FACTORY_HTTP_HOST must be a private or loopback IPv4 address"
                )
        return self

    @classmethod
    def from_environment(
        cls,
        repository_root: Path,
        environment: Mapping[str, str] | None = None,
    ) -> AppConfig:
        values = environment if environment is not None else os.environ
        return cls(
            deployment_profile=values.get("APRIS_DEPLOYMENT_PROFILE", "development"),
            adapter_type=values.get("APRIS_ADAPTER", "simulator"),
            ros2_state_file=values.get("APRIS_ROS2_STATE_FILE"),
            rover_id=values.get("APRIS_ROVER_ID"),
            rover_token=(
                SecretStr(values["APRIS_ROVER_TOKEN"]) if values.get("APRIS_ROVER_TOKEN") else None
            ),
            assistant_api_key=(
                SecretStr(values["OPENAI_API_KEY"]) if values.get("OPENAI_API_KEY") else None
            ),
            assistant_model=values.get("APRIS_ASSISTANT_MODEL", "gpt-6-luna"),
            factory_http_host=values.get("APRIS_FACTORY_HTTP_HOST"),
            factory_http_port=values.get("APRIS_FACTORY_HTTP_PORT", "80"),
            instance_id=values.get("APRIS_INSTANCE_ID", uuid.uuid4().hex),
            build_id=values.get("APRIS_BUILD_ID", "development"),
            log_directory=Path(values.get("APRIS_LOG_DIR", repository_root / ".runtime" / "logs")),
        )

    def rover_token_value(self) -> str | None:
        return self.rover_token.get_secret_value() if self.rover_token is not None else None

    def assistant_api_key_value(self) -> str | None:
        return (
            self.assistant_api_key.get_secret_value()
            if self.assistant_api_key is not None
            else None
        )
