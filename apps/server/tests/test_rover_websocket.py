from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from apris_server.app import app


def hello(rover_id: str = "ugv02-test", versions: list[int] | None = None) -> dict:
    return {
        "v": 1,
        "type": "rover_hello",
        "protocol_versions": versions or [1],
        "rover_id": rover_id,
        "boot_id": "boot-test-1",
        "firmware_version": "0.1.0-test",
        "build_id": "fake-rover-test",
        "hardware_revision": "test-hardware",
        "capabilities": {
            "bounded_motion": True,
            "velocity_control": True,
            "encoders": True,
            "imu": True,
            "battery": True,
        },
        "safety_limits": {
            "max_linear_speed_mps": 0.08,
            "max_angular_speed_rad_s": 0.5,
            "max_distance_m": 1.0,
            "max_angle_rad": 3.2,
            "max_motion_duration_ms": 10_000,
            "max_lease_ms": 500,
        },
    }


def auth_headers(token: str = "test-rover-secret") -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def test_rover_websocket_requires_configured_valid_credential(monkeypatch) -> None:
    monkeypatch.delenv("APRIS_ROVER_TOKEN", raising=False)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/rover"):
                pass
        assert exc_info.value.code == 4403

    monkeypatch.setenv("APRIS_ROVER_TOKEN", "test-rover-secret")
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/ws/rover", headers=auth_headers("wrong-token")
            ):
                pass
        assert exc_info.value.code == 4401


def test_rover_registers_epoch_and_is_visible_in_status(monkeypatch) -> None:
    monkeypatch.setenv("APRIS_ROVER_TOKEN", "test-rover-secret")
    with TestClient(app) as client:
        with client.websocket_connect("/ws/rover", headers=auth_headers()) as websocket:
            websocket.send_json(hello())
            welcome = websocket.receive_json()
            assert welcome["type"] == "rover_welcome"
            assert welcome["protocol_version"] == 1
            epoch = welcome["connection_epoch"]

            websocket.send_json(
                {
                    "v": 1,
                    "type": "heartbeat",
                    "rover_id": "ugv02-test",
                    "boot_id": "boot-test-1",
                    "connection_epoch": epoch,
                    "seq": 0,
                    "sent_at_ms": 1_000,
                    "clock_offset_ms": 0.0,
                    "clock_uncertainty_ms": 10.0,
                    "motor_state": "stopped",
                    "estop_latched": False,
                    "active_motion_id": None,
                }
            )
            status = client.get("/api/status").json()["rovers"]
            assert status["credential_configured"] is True
            assert status["connected_count"] == 1
            assert status["items"][0]["rover_id"] == "ugv02-test"
            assert status["items"][0]["connection_epoch"] == epoch
            assert status["items"][0]["last_rover_seq"] == 0
            assert status["items"][0]["heartbeat"]["motor_state"] == "stopped"

        disconnected = client.get("/api/status").json()["rovers"]
        assert disconnected["connected_count"] == 0
        assert disconnected["items"][0]["connected"] is False


def test_duplicate_rover_and_unsupported_version_are_rejected(monkeypatch) -> None:
    monkeypatch.setenv("APRIS_ROVER_TOKEN", "test-rover-secret")
    with TestClient(app) as client:
        with client.websocket_connect("/ws/rover", headers=auth_headers()) as first:
            first.send_json(hello())
            assert first.receive_json()["type"] == "rover_welcome"

            with client.websocket_connect("/ws/rover", headers=auth_headers()) as duplicate:
                duplicate.send_json(hello())
                error = duplicate.receive_json()
                assert error["code"] == "duplicate_rover_id"
                try:
                    duplicate.receive_json()
                except WebSocketDisconnect as exc:
                    assert exc.code == 4409

        with client.websocket_connect("/ws/rover", headers=auth_headers()) as unsupported:
            unsupported.send_json(hello(versions=[2]))
            error = unsupported.receive_json()
            assert error["code"] == "unsupported_protocol_version"


def test_non_increasing_rover_sequence_closes_session(monkeypatch) -> None:
    monkeypatch.setenv("APRIS_ROVER_TOKEN", "test-rover-secret")
    with TestClient(app) as client:
        with client.websocket_connect("/ws/rover", headers=auth_headers()) as websocket:
            websocket.send_json(hello())
            epoch = websocket.receive_json()["connection_epoch"]
            heartbeat = {
                "v": 1,
                "type": "heartbeat",
                "rover_id": "ugv02-test",
                "boot_id": "boot-test-1",
                "connection_epoch": epoch,
                "seq": 0,
                "sent_at_ms": 1_000,
                "clock_offset_ms": 0.0,
                "clock_uncertainty_ms": 10.0,
                "motor_state": "stopped",
                "estop_latched": False,
                "active_motion_id": None,
            }
            websocket.send_json(heartbeat)
            websocket.send_json(heartbeat)
            error = websocket.receive_json()
            assert error["code"] == "non_increasing_rover_sequence"
            try:
                websocket.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code == 4400
