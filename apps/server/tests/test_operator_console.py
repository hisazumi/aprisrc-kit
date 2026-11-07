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
        for _ in range(41):
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


def test_service_questions_reject_invalid_choices_and_do_not_clear_guard():
    with client_for(create_console(TOKEN)) as client:
        state = client.get("/api/state").json()
        operator = control(client, state, "openOperator").json()["operatorId"]
        control(client, state, "recover", operatorId=operator, guardId=None, confirmed=True)
        run = client.post(
            "/api/service/start", json=dict(controlEpoch=state["controlEpoch"], operatorId=operator)
        ).json()
        prompt = dict(id="q", message="Load?", choices=["Done"], stationary=True)
        bad = client.post(
            "/api/service/prompt",
            json=dict(runEpoch=run["runEpoch"], prompt={**prompt, "choices": ["Done", "Done"]}),
        )
        assert bad.status_code == 400
        control(client, state, "acquireHandover", runId=run["runId"], runEpoch=run["runEpoch"])
        assert (
            client.post(
                "/api/service/prompt", json=dict(runEpoch=run["runEpoch"], prompt=prompt)
            ).status_code
            == 200
        )
        view = client.post("/api/service/view", json={}).json()["viewId"]
        answer = dict(viewId=view, runEpoch=run["runEpoch"], questionId="q", value="Done")
        assert (
            client.post("/api/service/answer", json={**answer, "value": "Other"}).status_code == 409
        )
        assert (
            client.post("/api/service/answer", json={**answer, "humanClear": True}).status_code
            == 409
        )
        assert client.post("/api/service/answer", json=answer).status_code == 200
        assert client.get("/api/service/state").json()["guardId"]
        assert (
            client.post(
                "/api/service/consume", json=dict(runEpoch=run["runEpoch"], questionId="q")
            ).status_code
            == 409
        )
        assert client.get("/app").status_code == 200
        assert client.get("/console/service.js").status_code == 200


def test_service_result_is_scoped_and_retained_after_run_end():
    with client_for(create_console(TOKEN)) as client:
        state = client.get("/api/state").json()
        operator = control(client, state, "openOperator").json()["operatorId"]
        control(client, state, "recover", operatorId=operator, guardId=None, confirmed=True)
        run = client.post(
            "/api/service/start", json=dict(controlEpoch=state["controlEpoch"], operatorId=operator)
        ).json()
        result = dict(runEpoch=run["runEpoch"], status="completed", reason="service-completed")
        assert client.post("/api/service/finish", json=result).status_code == 409
        control(client, state, "closeRun", runId=run["runId"], runEpoch=run["runEpoch"])
        assert client.get("/api/service/state").json()["result"]["status"] == "interrupted"
        assert (
            client.post("/api/service/finish", json={**result, "runEpoch": "old"}).status_code
            == 409
        )
        assert client.post("/api/service/finish", json=result).status_code == 200
        snapshot = client.get("/api/service/state").json()
        assert not snapshot["live"]
        assert snapshot["result"] == dict(status="completed", reason="service-completed")
        assert (
            client.post("/api/service/finish", json={**result, "status": "failed"}).status_code
            == 409
        )


def test_browser_lease_tolerates_one_second_heartbeats_but_motion_ttl_stays_short():
    app = create_console(TOKEN)
    with client_for(app) as client:
        state = client.get("/api/state").json()
        operator = control(client, state, "openOperator").json()["operatorId"]
        for sequence in (1, 2):
            time.sleep(1)
            assert (
                control(
                    client, state, "operatorHeartbeat", operatorId=operator, sequence=sequence
                ).status_code
                == 200
            )
        assert app.state.port.command_ttl_s == 0.25
        assert app.state.port.lease_s == 0.4
        control(client, state, "recover", operatorId=operator, guardId=None, confirmed=True)
        run = control(client, state, "openRun", operatorId=operator, runId="ttl-test").json()
        client.post("/api/front", json={"clear": True})
        command = dict(
            protocolVersion=1,
            connectionEpoch=run["runEpoch"],
            requestId="m",
            robotId="fake-only",
            runId="ttl-test",
            activityId="a",
            operationId="m",
            kind="startMotion",
            goal=dict(kind="move", distanceM=0.3, speedMps=0.1),
        )
        assert client.post("/api/motion", json=command).json()["kind"] == "accepted"
        time.sleep(0.35)
        snapshot = client.get("/api/state").json()
        assert snapshot["control"]["operatorId"] == operator
        assert snapshot["session"] is None
        assert snapshot["state"]["velocity"]["vx"] == 0
        assert any(e.get("reason") == "command-ttl" for e in snapshot["events"])


def test_managed_launch_requires_recovery_and_reports_missing_node():
    with client_for(create_console(TOKEN, node="/missing/apris-node")) as client:
        state = client.get("/api/state").json()
        operator = control(client, state, "openOperator").json()["operatorId"]
        command = dict(controlEpoch=state["controlEpoch"], operatorId=operator)
        assert client.post("/api/service/launch", json=command).status_code == 409
        control(client, state, "recover", operatorId=operator, guardId=None, confirmed=True)
        assert client.post("/api/service/launch", json=command).status_code == 200
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = client.get("/api/state").json()["serviceProcess"]
            if not result["active"]:
                break
            time.sleep(0.02)
        assert result["status"] == "failed"
        assert "FileNotFoundError" in result["reason"]
        assert client.get("/api/state").json()["session"] is None


def test_localization_mode_requires_operator_placement_then_separate_recovery():
    with client_for(create_console(TOKEN, localization=True)) as client:
        state = client.get("/api/state").json()
        assert state["localization"]["blocked"]
        assert client.get("/console").text.find("localization-panel") >= 0
        operator = control(client, state, "openOperator").json()["operatorId"]
        payload = dict(
            controlEpoch=state["controlEpoch"],
            operatorId=operator,
            localizationEpoch=state["localization"]["localizationEpoch"],
            candidateId="start-placement",
            confirmed=True,
        )
        assert (
            client.post(
                "/api/localization/initialize", json=payload | {"operatorId": "old"}
            ).status_code
            == 409
        )
        assert (
            control(
                client, state, "recover", operatorId=operator, guardId=None, confirmed=True
            ).status_code
            == 409
        )
        # Wait for a healthy estimated sample; no truth injection and no motion command.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            response = client.post("/api/localization/initialize", json=payload)
            if response.status_code == 200:
                break
            time.sleep(0.01)
        assert response.status_code == 200, response.text
        assert not response.json()["blocked"]
        assert client.post("/api/localization/initialize", json=payload).status_code == 409
        state = client.get("/api/state").json()
        assert state["control"]["inhibited"] and state["session"] is None
        assert (
            control(
                client, state, "recover", operatorId=operator, guardId=None, confirmed=True
            ).status_code
            == 200
        )
        run = control(client, state, "openRun", operatorId=operator, runId="localized-run")
        assert run.status_code == 200
        payload["localizationEpoch"] = state["localization"]["localizationEpoch"]
        assert client.post("/api/localization/initialize", json=payload).status_code == 409
        assert client.post("/api/localization/observation", json={"drive": 1}).status_code == 409
        state = client.get("/api/state").json()
        assert state["localization"]["binding"]["map"] == state["localization"]["map"]
        route = client.post(
            "/api/route/start",
            json=dict(
                controlEpoch=state["controlEpoch"],
                runId="localized-run",
                runEpoch=state["session"],
                requestId="route-api-test",
                method="route",
                targetId="start-to-desk",
            ),
        )
        assert route.status_code == 200, route.text
        job = route.json()
        assert (
            client.post(
                "/api/route/cancel", json=dict(id="old", runEpoch=state["session"])
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/route/cancel", json=dict(id=job["id"], runEpoch=job["runEpoch"])
            ).status_code
            == 200
        )
