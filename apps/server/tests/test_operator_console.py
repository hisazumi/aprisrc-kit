import time
import uuid

from fastapi.testclient import TestClient

from apris_server.operator_console import create_console

TOKEN = "test-console-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Origin": "http://127.0.0.1:8766"}


def client_for(app):
    return TestClient(app, base_url="http://127.0.0.1:8766", headers=HEADERS)


def control(client, state, kind, **fields):
    return client.post(
        "/api/control",
        json=dict(
            protocolVersion=1,
            connectionEpoch=state["controlEpoch"],
            requestId=uuid.uuid4().hex,
            robotId="fake-only",
            kind=kind,
            **fields,
        ),
    )


def test_boundary_requires_token_origin_host_and_bounded_body():
    with client_for(create_console(TOKEN)) as client:
        assert client.get("/console").status_code == 200
        assert client.get("/api/state", headers={"Authorization": ""}).status_code == 401
        assert client.get("/api/state", headers={"Host": "evil.example"}).status_code == 403
        assert (
            client.post(
                "/api/control", headers={"Origin": "https://evil.example"}, json={}
            ).status_code
            == 403
        )
        assert client.post("/api/control", content="x" * 66000).status_code == 413
        assert client.post("/api/control", json={"action": "admit"}).status_code == 409
        assert client.get("/api/state").json()["backend"] == "simulator"


def test_explicit_recovery_and_guard_survive_browser_lease_loss():
    with client_for(create_console(TOKEN)) as client:
        state = client.get("/api/state").json()
        opened = control(client, state, "openOperator").json()
        operator = opened["operatorId"]
        assert opened["inhibited"]
        assert (
            control(client, state, "openRun", operatorId=operator, runId="run").status_code == 409
        )
        assert (
            control(
                client, state, "recover", operatorId=operator, guardId=None, confirmed=True
            ).status_code
            == 200
        )
        run = control(client, state, "openRun", operatorId=operator, runId="run").json()
        guard = control(
            client, state, "acquireHandover", runId="run", runEpoch=run["runEpoch"]
        ).json()
        assert guard["guardId"]
        assert (
            control(
                client,
                state,
                "clearHandover",
                operatorId=operator,
                guardId="old-question",
                confirmed=True,
            ).status_code
            == 409
        )
        # Read-only reconnect/polling must not renew operator or runner leases.
        for _ in range(7):
            time.sleep(0.08)
            snapshot = client.get("/api/state").json()
        assert snapshot["session"] is None
        assert snapshot["guard"]
        assert snapshot["inhibited"]
        assert snapshot["control"]["operatorId"] is None
        assert snapshot["state"]["velocity"]["vx"] == 0
        new_operator = control(client, state, "openOperator").json()["operatorId"]
        assert (
            control(
                client, state, "recover", operatorId=new_operator, guardId=None, confirmed=True
            ).status_code
            == 409
        )
        assert (
            control(
                client,
                state,
                "recover",
                operatorId=new_operator,
                guardId=guard["guardId"],
                confirmed=True,
            ).status_code
            == 200
        )


def test_restart_epoch_invalidates_old_commands_and_global_stop_is_available():
    with client_for(create_console(TOKEN)) as client:
        old = client.get("/api/state").json()
    with client_for(create_console(TOKEN)) as client:
        state = client.get("/api/state").json()
        assert state["controlEpoch"] != old["controlEpoch"]
        assert control(client, old, "openOperator").status_code == 409
        assert control(client, state, "globalStop").status_code == 200
        assert client.get("/api/state").json()["inhibited"]


def test_motion_uses_runtime_and_global_stop_then_recovery_never_replays():
    with client_for(create_console(TOKEN)) as client:
        state = client.get("/api/state").json()
        operator = control(client, state, "openOperator").json()["operatorId"]
        control(client, state, "recover", operatorId=operator, guardId=None, confirmed=True)
        run = control(client, state, "openRun", operatorId=operator, runId="run").json()
        assert client.post("/api/front", json={"clear": True}).status_code == 200
        command = dict(
            protocolVersion=1,
            connectionEpoch=run["runEpoch"],
            requestId="move",
            robotId="fake-only",
            runId="run",
            activityId="a",
            operationId="move",
            kind="startMotion",
            goal=dict(kind="move", distanceM=0.3, speedMps=0.1),
        )
        assert client.post("/api/motion", json=command).json()["kind"] == "accepted"
        time.sleep(0.12)
        assert control(client, state, "globalStop").status_code == 200
        time.sleep(0.08)
        stopped = client.get("/api/state").json()
        assert 0 < stopped["state"]["pose"]["x"] < 0.1
        assert stopped["state"]["velocity"]["vx"] == 0
        assert stopped["inhibited"]
        assert client.post("/api/motion", json=command).status_code == 409
        assert (
            control(
                client, state, "recover", operatorId=operator, guardId=None, confirmed=True
            ).status_code
            == 200
        )
        time.sleep(0.08)
        recovered = client.get("/api/state").json()
        assert recovered["session"] is None
        assert recovered["state"]["pose"] == stopped["state"]["pose"]
