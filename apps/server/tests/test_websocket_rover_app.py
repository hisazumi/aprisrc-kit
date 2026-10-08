from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from apris_server.app import app


def receive_type(websocket, expected: str, attempts: int = 50) -> dict:
    for _ in range(attempts):
        message = websocket.receive_json()
        if message["type"] == expected:
            return message
    raise AssertionError(f"did not receive message type {expected!r}")


def rover_hello() -> dict:
    return {
        "v": 1,
        "type": "rover_hello",
        "protocol_versions": [1],
        "rover_id": "ugv02-app-e2e",
        "boot_id": "boot-app-e2e",
        "firmware_version": "fake-app-e2e",
        "build_id": "fake-app-e2e",
        "hardware_revision": "fake",
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


def heartbeat(epoch: str, seq: int) -> dict:
    return {
        "v": 1,
        "type": "heartbeat",
        "rover_id": "ugv02-app-e2e",
        "boot_id": "boot-app-e2e",
        "connection_epoch": epoch,
        "seq": seq,
        "sent_at_ms": round(time.time() * 1000.0),
        "clock_offset_ms": 0.0,
        "clock_uncertainty_ms": 5.0,
        "motor_state": "stopped",
        "estop_latched": False,
        "active_motion_id": None,
    }


def telemetry(epoch: str, seq: int, *, yaw: float = 0.0) -> dict:
    return {
        "v": 1,
        "type": "telemetry",
        "rover_id": "ugv02-app-e2e",
        "boot_id": "boot-app-e2e",
        "connection_epoch": epoch,
        "seq": seq,
        "measured_at_ms": round(time.time() * 1000.0),
        "linear_velocity_mps": 0.0,
        "angular_velocity_rad_s": 0.0,
        "odometry_x_m": 0.0,
        "odometry_y_m": 0.0,
        "odometry_yaw_rad": yaw,
        "battery_percent": 90.0,
        "motor_state": "stopped",
        "fault_codes": [],
    }


def configure_websocket_adapter(monkeypatch) -> None:
    monkeypatch.setenv("APRIS_ADAPTER", "websocket_rover")
    monkeypatch.setenv("APRIS_ROVER_ID", "ugv02-app-e2e")
    monkeypatch.setenv("APRIS_ROVER_TOKEN", "app-e2e-secret")
    monkeypatch.setenv("APRIS_INSTANCE_ID", "app-e2e-instance")


def test_websocket_rover_mode_is_not_ready_until_rover_connects(monkeypatch) -> None:
    configure_websocket_adapter(monkeypatch)
    with TestClient(app) as client:
        initial = client.get("/api/readyz")
        assert initial.status_code == 503
        assert initial.json()["adapter"]["type"] == "websocket_rover"

        simulator_only = client.get("/api/simulator/scenarios")
        assert simulator_only.status_code == 409
        assert simulator_only.json()["detail"]["code"] == "simulator_only"


def test_real_rover_and_client_websockets_complete_bounded_turn(monkeypatch) -> None:
    configure_websocket_adapter(monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws/rover",
            headers={"authorization": "Bearer app-e2e-secret"},
        ) as rover_socket:
            rover_socket.send_json(rover_hello())
            welcome = rover_socket.receive_json()
            assert welcome["type"] == "rover_welcome"
            epoch = welcome["connection_epoch"]
            rover_socket.send_json(heartbeat(epoch, 0))
            rover_socket.send_json(telemetry(epoch, 1))

            readiness = client.get("/api/readyz")
            assert readiness.status_code == 200
            assert readiness.json()["adapter"]["connected"] is True
            assert "app-e2e-secret" not in json.dumps(readiness.json())

            with client.websocket_connect("/ws") as client_socket:
                assert client_socket.receive_json()["type"] == "hello"
                assert client_socket.receive_json()["type"] == "control"
                client_socket.send_json(
                    {
                        "v": 1,
                        "type": "client_hello",
                        "client_kind": "physicode_bridge",
                        "device_id": "app-e2e-bridge",
                        "session_id": "run-app-e2e",
                        "app_version": "test",
                        "build_id": "test",
                    }
                )
                client_socket.send_json({"v": 1, "type": "acquire_control"})
                assert receive_type(client_socket, "control")["is_owner"] is True

                client_socket.send_json(
                    {
                        "v": 1,
                        "type": "turn",
                        "request_id": "turn-app-e2e",
                        "run_id": "run-app-e2e",
                        "effect_id": "effect-app-e2e",
                        "angle_deg": 30.0,
                        "speed_rad_s": 0.5,
                    }
                )
                started = receive_type(client_socket, "motion")
                assert started["status"] == "started"

                command = rover_socket.receive_json()
                assert command["type"] == "start_motion"
                assert command["kind"] == "rotate"
                assert command["angle_rad"] == 0.5235987755982988
                rover_socket.send_json(
                    {
                        "v": 1,
                        "type": "command_ack",
                        "rover_id": "ugv02-app-e2e",
                        "boot_id": "boot-app-e2e",
                        "connection_epoch": epoch,
                        "seq": 2,
                        "command_id": command["command_id"],
                        "status": "accepted",
                        "detail": "",
                    }
                )
                rover_socket.send_json(
                    {
                        "v": 1,
                        "type": "motion_status",
                        "rover_id": "ugv02-app-e2e",
                        "boot_id": "boot-app-e2e",
                        "connection_epoch": epoch,
                        "seq": 3,
                        "motion_id": command["motion_id"],
                        "status": "running",
                        "progress": 0.5,
                        "reason": None,
                        "motor_stopped": False,
                    }
                )
                rover_socket.send_json(telemetry(epoch, 4, yaw=command["angle_rad"]))
                rover_socket.send_json(
                    {
                        "v": 1,
                        "type": "motion_status",
                        "rover_id": "ugv02-app-e2e",
                        "boot_id": "boot-app-e2e",
                        "connection_epoch": epoch,
                        "seq": 5,
                        "motion_id": command["motion_id"],
                        "status": "completed",
                        "progress": 1.0,
                        "reason": None,
                        "motor_stopped": True,
                    }
                )
                completed = receive_type(client_socket, "motion")
                assert completed["request_id"] == "turn-app-e2e"
                assert completed["status"] == "completed"

                client_socket.send_json({"v": 1, "type": "release_control"})
                stop = rover_socket.receive_json()
                assert stop["type"] == "stop"
                rover_socket.send_json(
                    {
                        "v": 1,
                        "type": "command_ack",
                        "rover_id": "ugv02-app-e2e",
                        "boot_id": "boot-app-e2e",
                        "connection_epoch": epoch,
                        "seq": 6,
                        "command_id": stop["command_id"],
                        "status": "accepted",
                        "detail": "",
                    }
                )
                assert receive_type(client_socket, "control")["is_owner"] is False
