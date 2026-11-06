import asyncio
import json
from pathlib import Path

import pytest

from apris_server.motion_contract import parse_motion_message
from apris_server.runner_port_experiment import RunnerPort

FIXTURES = Path(__file__).resolve().parents[2] / "runner-prototype/fixtures/motion-v1.json"


@pytest.mark.parametrize("case", json.loads(FIXTURES.read_text()), ids=lambda c: c["name"])
def test_shared_contract(case):
    if case["valid"]:
        assert parse_motion_message(case["message"]) == case["message"]
    else:
        with pytest.raises(ValueError):
            parse_motion_message(case["message"])


def start(session, **changes):
    return dict(
        protocolVersion=1,
        connectionEpoch=session,
        requestId="r1",
        robotId="fake-only",
        runId="run",
        activityId="a",
        operationId="o1",
        kind="startMotion",
        goal=dict(kind="move", distanceM=0.01, speedMps=0.1),
        **changes,
    )


async def wire(port, session, message):
    return await port.request(dict(action="motion", session=session, message=message))


async def result(events):
    async with asyncio.timeout(2):
        while not any(  # noqa: ASYNC110 - poll the existing port event callback in tests
            e.get("protocolVersion") == 1 and e["kind"] == "terminal" for e in events
        ):
            await asyncio.sleep(0.005)
    return next(e for e in events if e.get("protocolVersion") == 1 and e["kind"] == "terminal")


@pytest.mark.asyncio
async def test_port_start_retry_terminal_and_turn_conversion():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        await port.request(dict(action="fixture", front="CLEAR"))
        session = await port.request(dict(action="admit"))
        command = start(session)
        accepted = await wire(port, session, command)
        assert accepted["kind"] == "accepted"
        assert await wire(port, session, command) == accepted
        done = await result(events)
        assert parse_motion_message(done)["outcome"] == "completed"
        assert await wire(port, session, command) == done
        assert len(port.adapter.goals) == 1
        events.clear()
        turn = dict(
            command,
            requestId="r2",
            operationId="o2",
            goal=dict(kind="turn", angleRad=0.07, speedRadS=0.7),
        )
        await wire(port, session, turn)
        old_cancel = {k: v for k, v in command.items() if k != "goal"}
        old_cancel.update(
            kind="cancelMotion", requestId="old-cancel", generation=accepted["generation"]
        )
        with pytest.raises(ValueError, match="stale-motion"):
            await wire(port, session, old_cancel)
        assert (await result(events))["outcome"] == "completed"
        assert port.adapter.goals[-1].angle_rad == pytest.approx(0.07)
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_port_cancel_scope_ack_and_rejected_tombstone():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        await port.request(dict(action="fixture", front="CLEAR"))
        session = await port.request(dict(action="admit"))
        command = start(session)
        command["goal"]["distanceM"] = 0.05
        accepted = await wire(port, session, command)
        cancel = {k: v for k, v in command.items() if k != "goal"}
        cancel.update(kind="cancelMotion", requestId="cancel", generation=accepted["generation"])
        with pytest.raises(ValueError):
            await wire(port, session, dict(cancel, activityId="wrong"))
        busy = dict(command, operationId="busy", requestId="busy")
        rejected = await wire(port, session, busy)
        assert rejected["kind"] == "rejected"
        ack = await wire(port, session, cancel)
        assert parse_motion_message(ack)["kind"] == "commandAck"
        assert (await result(events))["outcome"] == "cancelled"
        assert await wire(port, session, busy) == rejected
        with pytest.raises(ValueError, match="conflict"):
            await wire(
                port, session, dict(command, goal=dict(kind="move", distanceM=0.03, speedMps=0.1))
            )
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_port_capacity_and_invalid_values_do_not_actuate():
    port = RunnerPort(lambda _: None)
    port.motion_capacity = 1
    await port.start()
    try:
        session = await port.request(dict(action="admit"))
        command = start(session)
        with pytest.raises(ValueError):
            await wire(
                port, session, dict(command, goal=dict(kind="move", distanceM=True, speedMps=0.1))
            )
        await wire(port, session, command)
        with pytest.raises(ValueError, match="capacity"):
            await wire(port, session, dict(command, requestId="new", operationId="new"))
    finally:
        await port.close()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True])
def test_nonfinite_and_boolean_numbers(value):
    command = start("epoch")
    command["goal"]["distanceM"] = value
    with pytest.raises(ValueError):
        parse_motion_message(command)


@pytest.mark.asyncio
async def test_expiry_before_renew_and_old_epoch_rejection():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        session = await port.request(dict(action="admit"))
        command = start(session)
        with pytest.raises(ValueError, match="epoch"):
            await wire(port, session, dict(command, connectionEpoch="old"))
        await port.request(dict(action="fixture", front="CLEAR"))
        accepted = await wire(port, session, command)
        renew = {k: v for k, v in command.items() if k != "goal"}
        renew.update(kind="renewMotion", requestId="renew", generation=accepted["generation"])
        assert (await wire(port, session, renew))["kind"] == "commandAck"
        ttl = port.operation["ttl"]
        assert (await wire(port, session, renew))["kind"] == "commandAck"
        assert port.operation["ttl"] == ttl  # Retry cannot renew again.
        port.operation["ttl"] = 0
        with pytest.raises(ValueError, match="revoked-session"):
            await wire(port, session, dict(renew, requestId="late"))
        assert (await result(events))["outcome"] == "interrupted"
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_renew_while_finishing_acknowledges_without_extending_ttl():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        session = await port.request(dict(action="admit"))
        await port.request(dict(action="fixture", front="CLEAR", evidenceDelay=0.1))
        command = start(session)
        accepted = await wire(port, session, command)
        port._finish("cancelled", "test-finishing")
        ttl = port.operation["ttl"]
        renew = {k: v for k, v in command.items() if k != "goal"}
        renew.update(kind="renewMotion", requestId="late-renew", generation=accepted["generation"])
        assert (await wire(port, session, renew))["kind"] == "commandAck"
        assert port.operation["ttl"] == ttl
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_oversized_stdin_frame_closes_without_parsing_remaining_commands():
    import sys

    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "apris_server.runner_port_experiment",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            child.communicate(b"x" * 70000 + b'\n{"id":1,"action":"admit"}\n'),
            timeout=3,
        )
        messages = [json.loads(line) for line in stdout.splitlines()]
        assert messages == [dict(kind="reply", id=None, ok=False, error="invalid-frame-size")]
        assert child.returncode == 0, stderr.decode()
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
