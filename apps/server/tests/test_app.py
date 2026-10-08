import time

from fastapi.testclient import TestClient

from apris_server.app import app
from apris_server.assistant import AssistantIntentInterpreter


def test_simulator_scene_origin_preserves_course_marker_geometry() -> None:
    with TestClient(app) as client:
        response = client.put("/api/simulator/pose", json={"x": -0.8, "y": -0.15, "yaw": 0})
        assert response.status_code == 200
        state = client.get("/api/status").json()["adapter"]["state"]
        with client.websocket_connect("/ws") as websocket:
            course_state = receive_type(websocket, "state")["state"]
            assert course_state["pose"] == {"x": -0.8, "y": -0.15, "yaw": 0.0}
        assert state["velocity"] == {"vx": 0.0, "vy": 0.0, "wz": 0.0}
        marker = client.post("/api/simulator/events", json={
            "kind": "marker",
            "payload": {"status": "detected", "confidence": 0.96, "marker_id": 1,
                        "relative_x_m": 0.8, "relative_y_m": 0.15},
        }).json()
        assert marker["accepted"] is True
        assert marker["payload"]["pose_correction"]["innovation_m"] < 0.001
        invalid = client.put("/api/simulator/pose", json={"x": 100, "y": 0, "yaw": 0})
        assert invalid.status_code == 422


def test_simulator_marker_scene_updates_fusion_and_restores_defaults() -> None:
    with TestClient(app) as client:
        scene = {"x": 0, "y": 0, "yaw": 0,
                 "markers": [{"id": 1, "x_m": 1.5, "y_m": 0.2}]}
        assert client.put("/api/simulator/pose", json=scene).status_code == 200
        event = client.post("/api/simulator/events", json={
            "kind": "marker", "payload": {"status": "detected", "confidence": 0.96,
                "marker_id": 1, "relative_x_m": 1.5, "relative_y_m": 0.2},
        }).json()
        assert event["accepted"] is True
        assert event["payload"]["pose_correction"]["innovation_m"] < 0.001
        for markers in [[{"id": 99, "x_m": 0, "y_m": 0}], scene["markers"] * 2,
                        [{"id": 1, "x_m": 11, "y_m": 0}]]:
            invalid = client.put("/api/simulator/pose", json={**scene, "markers": markers})
            assert invalid.status_code == 422
        assert client.put("/api/simulator/pose", json={"x": 0, "y": 0, "yaw": 0}).status_code == 200
        assert app.state.rover_runtime.pose_fusion.markers[1].x_m == 0


def test_simulator_scene_reset_cancels_motion_and_preserves_estop() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            receive_type(websocket, "hello")
            register_client(websocket)
            websocket.send_json({"v": 1, "type": "acquire_control"})
            while not receive_type(websocket, "control")["is_owner"]:
                pass
            websocket.send_json({"v": 1, "type": "turn", "request_id": "scene-turn",
                                 "angle_deg": 90, "speed_rad_s": 0.35})
            receive_motion(websocket, "scene-turn", "started")
            client.put("/api/simulator/pose", json={"x": 0, "y": 0, "yaw": 0})
            receive_motion(websocket, "scene-turn", "cancelled")
            websocket.send_json({"v": 1, "type": "estop", "reason": "test"})
            while not receive_type(websocket, "control")["estop_latched"]:
                pass
            client.put("/api/simulator/pose", json={"x": -0.8, "y": 0, "yaw": 0})
            status = client.get("/api/status").json()
            assert status["control"]["estop_latched"] is True
            assert status["adapter"]["state"]["velocity"]["vx"] == 0


def receive_type(websocket, expected: str, attempts: int = 12) -> dict:
    for _ in range(attempts):
        message = websocket.receive_json()
        if message["type"] == expected:
            return message
    raise AssertionError(f"did not receive message type {expected!r}")


def receive_motion(websocket, request_id: str, status: str, attempts: int = 50) -> dict:
    for _ in range(attempts):
        message = websocket.receive_json()
        if (
            message["type"] == "motion"
            and message["request_id"] == request_id
            and message["status"] == status
        ):
            return message
    raise AssertionError(f"did not receive {status!r} for motion {request_id!r}")


def register_client(websocket, client_kind: str = "development_lab") -> None:
    websocket.send_json(
        {
            "v": 1,
            "type": "client_hello",
            "client_kind": client_kind,
            "device_id": "test-device",
            "session_id": "test-session",
            "app_version": "0.1.0-test",
            "build_id": "test-build",
        }
    )


def set_front_clear(client: TestClient) -> None:
    response = client.put(
        "/api/simulator/front-obstacle",
        json={
            "state": "CLEAR",
            "perception_health": "healthy",
            "source": "manual",
            "confidence": 1.0,
        },
    )
    assert response.status_code == 200


def test_health_and_websocket_drive_ttl_flow() -> None:
    with TestClient(app) as client:
        set_front_clear(client)
        assert client.get("/api/livez").json() == {"status": "alive"}
        readiness = client.get("/api/readyz")
        assert readiness.status_code == 200
        assert readiness.json()["ready"] is True
        assert all(loop["healthy"] for loop in readiness.json()["loops"].values())

        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "adapter": "simulator"}

        with client.websocket_connect("/ws") as websocket:
            hello = websocket.receive_json()
            assert hello["type"] == "hello"
            assert hello["capabilities"]["lateral_motion"] is False
            assert websocket.receive_json()["type"] == "control"
            register_client(websocket)

            websocket.send_json({"v": 1, "type": "acquire_control"})
            control = receive_type(websocket, "control")
            assert control["is_owner"] is True

            websocket.send_json(
                {
                    "v": 1,
                    "type": "drive",
                    "vx": 0.3,
                    "vy": 0.0,
                    "wz": 0.0,
                    "ttl_ms": 100,
                    "seq": 1,
                }
            )
            moving = receive_type(websocket, "state")
            assert moving["state"]["velocity"]["vx"] == 0.3

            expired = receive_type(websocket, "event")
            assert expired["event"] == "command_ttl_expired"
            stopped = receive_type(websocket, "state")
            assert stopped["state"]["velocity"]["vx"] == 0.0
            assert stopped["state"]["command_age_ms"] is None

        log_entries = client.get(
            "/api/simulator/logs",
            params={"limit": 200, "include_state": True},
        ).json()["entries"]
        categories = {entry["category"] for entry in log_entries}
        assert {"client_message", "adapter_command", "state", "server_event"} <= categories


def test_assistant_interpret_endpoint_uses_bounded_intent() -> None:
    with TestClient(app) as client:
        status = client.get("/api/assistant/status")
        assert status.status_code == 200
        assert status.json()["mode"] in ("rules", "openai")

        response = client.post(
            "/api/assistant/interpret",
            json={"text": "止まって"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["action"] == "stop"
        assert payload["destination"] is None
        assert payload["follow_distance"] == "normal"

        app.state.assistant_interpreter = AssistantIntentInterpreter(None)
        registered = client.post(
            "/api/assistant/interpret",
            json={
                "text": "荷物を運ぶのを手伝って",
                "intents": [
                    {
                        "id": "carry_help",
                        "description": "Follow a person while carrying an item.",
                        "examples": ["荷物を運ぶのを手伝って"],
                        "keywords": ["運ん", "手伝って"],
                        "response": "Okay. I will help you carry it.",
                    }
                ],
            },
        )
        assert registered.status_code == 200
        assert registered.json()["action"] == "carry_help"

        rejected = client.post("/api/assistant/interpret", json={"text": ""})
        assert rejected.status_code == 422


def test_websocket_high_level_motion_flow() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        set_front_clear(client)
        assert websocket.receive_json()["type"] == "hello"
        assert websocket.receive_json()["type"] == "control"
        register_client(websocket)
        websocket.send_json({"v": 1, "type": "acquire_control"})
        assert receive_type(websocket, "control")["is_owner"] is True

        websocket.send_json(
            {
                "v": 1,
                "type": "move",
                "request_id": "e2e-move",
                "distance_m": 0.05,
                "speed_mps": 0.30,
            }
        )
        receive_motion(websocket, "e2e-move", "started")
        receive_motion(websocket, "e2e-move", "completed")
        moved = receive_type(websocket, "state")
        assert moved["state"]["pose"]["x"] > 0.03
        assert moved["state"]["velocity"]["vx"] == 0.0

        websocket.send_json(
            {
                "v": 1,
                "type": "turn",
                "request_id": "e2e-turn",
                "angle_deg": 10.0,
                "speed_rad_s": 1.20,
            }
        )
        receive_motion(websocket, "e2e-turn", "started")
        receive_motion(websocket, "e2e-turn", "completed")
        turned = receive_type(websocket, "state")
        assert turned["state"]["pose"]["yaw"] > 0.12
        assert turned["state"]["velocity"]["wz"] == 0.0


def test_simulator_front_obstacle_api_keeps_latch_until_explicit_clear() -> None:
    with TestClient(app) as client:
        initial = client.get("/api/status").json()["front_obstacle"]
        assert initial["state"] == "UNKNOWN"
        assert initial["perception_health"] == "unavailable"

        blocked = client.put(
            "/api/simulator/front-obstacle",
            json={
                "state": "BLOCKED",
                "perception_health": "healthy",
                "source": "manual",
                "confidence": 0.95,
                "distance_m": 0.3,
            },
        )
        assert blocked.status_code == 200
        assert blocked.json()["front_obstacle"]["latched"] is True

        observed_clear = client.put(
            "/api/simulator/front-obstacle",
            json={
                "state": "CLEAR",
                "perception_health": "healthy",
                "source": "manual",
                "confidence": 1.0,
            },
        ).json()["front_obstacle"]
        assert observed_clear["observed_state"] == "CLEAR"
        assert observed_clear["state"] == "BLOCKED"

        cleared = client.post(
            "/api/simulator/front-obstacle/clear",
            json={"reason": "operator verified path"},
        )
        assert cleared.status_code == 200
        snapshot = cleared.json()["front_obstacle"]
        assert snapshot["state"] == "CLEAR"
        assert snapshot["latched"] is False
        assert snapshot["clear_reason"] == "manual: operator verified path"


def test_simulator_scenario_api_injects_and_replays_inputs() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json()["type"] == "hello"
        assert websocket.receive_json()["type"] == "control"
        register_client(websocket)

        scenarios = client.get("/api/simulator/scenarios")
        assert scenarios.status_code == 200
        scenario_ids = {item["id"] for item in scenarios.json()["scenarios"]}
        assert {
            "perception-inputs",
            "perception-loss",
            "fault-injection-demo",
            "front-obstacle-latch",
            "mobile-receptionist",
            "service-passerby",
            "service-person-enters-frame",
        } <= scenario_ids

        injected = client.post(
            "/api/simulator/events",
            json={
                "kind": "marker",
                "payload": {
                    "confidence": 0.9,
                    "marker_id": 1,
                    "relative_x_m": 0.5,
                    "relative_y_m": 0.0,
                },
            },
        )
        assert injected.status_code == 200
        event = receive_type(websocket, "perception_event")
        assert event["kind"] == "marker"
        assert event["source"] == "manual"
        assert event["accepted"] is True
        assert event["payload"]["pose_correction"]["applied"] is True

        applied = client.put(
            "/api/simulator/faults",
            json={"battery_percent": 15, "drop_next_commands": 1},
        )
        assert applied.status_code == 200
        assert applied.json()["faults"]["battery_percent"] == 15

        logs = client.get("/api/simulator/logs", params={"limit": 100}).json()
        assert logs["filename"].endswith(".jsonl")
        assert any(entry["category"] == "scenario_event" for entry in logs["entries"])
        assert any(entry["category"] == "simulator_faults" for entry in logs["entries"])

        replay = client.post("/api/simulator/logs/replay", json={"speed": 100})
        assert replay.status_code == 202
        replayed_event = receive_type(websocket, "perception_event", attempts=30)
        assert replayed_event["kind"] == "marker"
        assert replayed_event["source"] == "replay"


def test_json_scenario_runs_in_declared_order() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json()["type"] == "hello"
        assert websocket.receive_json()["type"] == "control"
        register_client(websocket)

        started = client.post("/api/simulator/scenarios/perception-inputs/run")
        assert started.status_code == 202

        received = []
        for _ in range(60):
            event = websocket.receive_json()
            if event["type"] in ("perception_event", "scenario_event"):
                received.append(event["kind"])
            if len(received) == 3:
                break
        assert received == ["person", "marker", "voice_intent"]


def test_front_obstacle_scenario_reproduces_latch_and_explicit_clear() -> None:
    with TestClient(app) as client:
        started = client.post("/api/simulator/scenarios/front-obstacle-latch/run")
        assert started.status_code == 202
        time.sleep(0.9)

        status = client.get("/api/simulator/status").json()
        assert status["active_id"] is None
        obstacle = status["front_obstacle"]
        assert obstacle["state"] == "CLEAR"
        assert obstacle["latched"] is False
        assert obstacle["clear_reason"] == (
            "scenario: scenario verified a fresh clear path"
        )
        logs = client.get("/api/simulator/logs", params={"limit": 200}).json()["entries"]
        obstacle_events = [entry for entry in logs if entry["category"] == "front_obstacle"]
        assert any(entry["data"]["state"] == "BLOCKED" for entry in obstacle_events)
        assert any(entry["name"] == "latch_cleared" for entry in obstacle_events)


def test_websocket_validates_perception_without_control_ownership() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json()["type"] == "hello"
        assert websocket.receive_json()["type"] == "control"
        register_client(websocket, "service_app")

        websocket.send_json(
            {
                "v": 1,
                "type": "perception_observation",
                "observation_id": "person-1",
                "kind": "person",
                "status": "detected",
                "confidence": 0.92,
                "captured_at": time.time(),
                "source": "camera",
                "payload": {
                    "person_id": "p1",
                    "center_x": 0.5,
                    "center_y": 0.5,
                    "width": 0.2,
                    "height": 0.4,
                },
            }
        )
        accepted = receive_type(websocket, "perception_event")
        assert accepted["status"] == "detected"
        assert accepted["accepted"] is True

        websocket.send_json(
            {
                "v": 1,
                "type": "perception_observation",
                "observation_id": "marker-low-confidence",
                "kind": "marker",
                "status": "detected",
                "confidence": 0.1,
                "captured_at": time.time(),
                "source": "camera",
                "payload": {"marker_id": 1, "relative_x_m": 0.5, "relative_y_m": 0.0},
            }
        )
        rejected = receive_type(websocket, "perception_event")
        assert rejected["status"] == "rejected"
        assert rejected["accepted"] is False
        assert rejected["reason"] == "confidence_too_low"


def test_status_reports_registered_client_and_active_control() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["supported_protocol_versions"] == [1]
        assert websocket.receive_json()["type"] == "control"
        register_client(websocket, "operator_console")
        websocket.send_json({"v": 1, "type": "acquire_control"})
        assert receive_type(websocket, "control")["is_owner"] is True

        status = client.get("/api/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["ready"] is True
        assert payload["server"]["deployment_profile"] == "development"
        assert payload["adapter"]["type"] == "simulator"
        assert payload["control"]["owner_client_id"] == hello["client_id"]
        registered = next(
            item for item in payload["clients"] if item["client_id"] == hello["client_id"]
        )
        assert registered["client_kind"] == "operator_console"
        assert registered["device_id"] == "test-device"
        assert payload["config"]["effective_safety_limits"]["max_vx_mps"] == 0.3


def test_unregistered_client_cannot_acquire_control() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json()["type"] == "hello"
        assert websocket.receive_json()["type"] == "control"
        websocket.send_json({"v": 1, "type": "acquire_control"})
        error = receive_type(websocket, "error")
        assert error["code"] == "client_not_registered"


def test_readyz_fails_closed_when_a_required_loop_is_unhealthy() -> None:
    with TestClient(app) as client:
        runtime = app.state.rover_runtime
        runtime._loop_health["state"].error = "test failure"
        response = client.get("/api/readyz")
        assert response.status_code == 503
        assert response.json()["ready"] is False
        assert response.json()["recent_fault"] == "test failure"
