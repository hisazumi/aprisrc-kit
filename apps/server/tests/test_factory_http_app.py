from __future__ import annotations

import importlib
import time
from typing import Any

from fastapi.testclient import TestClient

from apris_server.app import app


class AppFactoryTransport:
    def __init__(self) -> None:
        self.commands: list[dict[str, Any]] = []

    async def send(
        self,
        command: dict[str, Any],
        *,
        allow_empty_response: bool = False,
    ) -> dict[str, Any] | None:
        del allow_empty_response
        self.commands.append(dict(command))
        return (
            {
                "T": 1001,
                "L": 0.0,
                "R": 0.0,
                "odl": 0,
                "odr": 0,
                "v": 1230,
            }
            if command["T"] == 130
            else None
        )


def test_factory_http_app_is_ready_and_routes_manual_rotation(monkeypatch) -> None:
    transport = AppFactoryTransport()
    app_module = importlib.import_module("apris_server.app")
    monkeypatch.setattr(
        app_module,
        "UrllibFactoryHttpTransport",
        lambda host, port: transport,
    )
    monkeypatch.setenv("APRIS_ADAPTER", "factory_http")
    monkeypatch.setenv("APRIS_FACTORY_HTTP_HOST", "127.0.0.1")

    with TestClient(app) as client:
        readiness = client.get("/api/readyz")
        assert readiness.status_code == 200
        assert readiness.json()["adapter"]["type"] == "factory_http"
        assert readiness.json()["adapter"]["state"]["battery_percent"] is None
        assert client.get("/api/simulator/scenarios").status_code == 409
        assert client.put("/api/simulator/pose", json={"x": 0, "y": 0, "yaw": 0}).status_code == 409

        with client.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "hello"
            assert websocket.receive_json()["type"] == "control"
            websocket.send_json(
                {
                    "v": 1,
                    "type": "client_hello",
                    "client_kind": "operator_console",
                    "device_id": "factory-http-test",
                    "session_id": "factory-http-test",
                    "app_version": "test",
                    "build_id": "test",
                }
            )
            websocket.send_json({"v": 1, "type": "acquire_control"})
            websocket.send_json(
                {
                    "v": 1,
                    "type": "drive",
                    "vx": 0.0,
                    "vy": 0.0,
                    "wz": 0.5,
                    "ttl_ms": 100,
                    "seq": 1,
                }
            )
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                rotation_sent = any(
                    command.get("L", 0) < 0 < command.get("R", 0)
                    for command in transport.commands
                )
                if rotation_sent:
                    break
                time.sleep(0.01)
            else:
                raise AssertionError("manual rotation did not reach factory HTTP transport")

    stop_commands = [
        command
        for command in transport.commands
        if command == {"T": 1, "L": 0, "R": 0}
    ]
    assert len(stop_commands) >= 4
