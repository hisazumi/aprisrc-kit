import asyncio
import json
import time
from pathlib import Path

import pytest

from apris_server.control_contract import parse_control_message
from apris_server.runner_port_experiment import RunnerPort

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "runner-prototype/fixtures/control-v1.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_shared_control(case):
    if case["valid"]:
        assert parse_control_message(case["message"]) == case["message"]
    else:
        with pytest.raises(ValueError):
            parse_control_message(case["message"])


class Controls:
    def __init__(self, port):
        self.port = port
        self.counter = 0

    async def send(self, kind, **fields):
        self.counter += 1
        message = dict(
            protocolVersion=1,
            connectionEpoch=self.port.control_epoch,
            robotId="fake-only",
            requestId=str(self.counter),
            kind=kind,
            **fields,
        )
        return parse_control_message(
            await self.port.request(dict(action="control", message=message))
        )

    async def setup(self):
        op = await self.send("openOperator")
        self.operator = op["operatorId"]
        assert op["inhibited"]
        await self.send("recover", operatorId=self.operator, guardId=None, confirmed=True)
        return await self.send("openRun", operatorId=self.operator, runId="run")


@pytest.mark.asyncio
async def test_guard_survives_run_close_and_requires_matching_human_clearance():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        c = Controls(port)
        run = await c.setup()
        scope = dict(runId="run", runEpoch=run["runEpoch"])
        held = await c.send("acquireHandover", **scope)
        motion = dict(
            protocolVersion=1,
            connectionEpoch=run["runEpoch"],
            requestId="move",
            robotId="fake-only",
            runId="run",
            activityId="a",
            operationId="op",
            kind="startMotion",
            goal=dict(kind="move", distanceM=0.01, speedMps=0.1),
        )
        rejected = await port.request(
            dict(action="motion", session=run["runEpoch"], message=motion)
        )
        assert rejected["kind"] == "rejected" and not port.adapter.goals
        await c.send("closeRun", **scope)
        if port.io_tasks:
            await asyncio.wait(port.io_tasks, timeout=0.2)
        assert port.guard
        with pytest.raises(ValueError):
            await c.send("openRun", operatorId=c.operator, runId="next")
        with pytest.raises(ValueError, match="guard"):
            await c.send("clearHandover", operatorId=c.operator, guardId="stale", confirmed=True)
        await c.send(
            "clearHandover", operatorId=c.operator, guardId=held["guardId"], confirmed=True
        )
        new = await c.send("openRun", operatorId=c.operator, runId="next")
        with pytest.raises(ValueError, match="run"):
            await c.send("closeRun", **scope)
        assert port.session == new["runEpoch"]
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_operator_expiry_beats_heartbeat_and_keeps_guard():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        c = Controls(port)
        run = await c.setup()
        held = await c.send("acquireHandover", runId="run", runEpoch=run["runEpoch"])
        port.operator_deadline = 0
        with pytest.raises(ValueError, match="operator"):
            await c.send("operatorHeartbeat", operatorId=c.operator, sequence=1)
        assert port.session is None and port.inhibited
        assert port.guard_id == held["guardId"]
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_duplicate_heartbeat_does_not_renew_and_snapshot_has_no_lease_effect():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        c = Controls(port)
        run = await c.setup()
        await c.send("operatorHeartbeat", operatorId=c.operator, sequence=1)
        deadline = port.operator_deadline
        await c.send("operatorHeartbeat", operatorId=c.operator, sequence=1)
        assert port.operator_deadline == deadline
        lease = port.lease
        await c.send("snapshot")
        assert port.operator_deadline == deadline and port.lease == lease
        await c.send("runnerHeartbeat", runId="run", runEpoch=run["runEpoch"], sequence=1)
        assert port.lease >= lease
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_dedup_capacity_never_blocks_global_stop_or_snapshot():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        c = Controls(port)
        await c.setup()
        m = dict(
            protocolVersion=1,
            connectionEpoch=port.control_epoch,
            robotId="fake-only",
            requestId="repeat",
            kind="acquireHandover",
            runId="run",
            runEpoch=port.session,
        )
        held = await port.request(dict(action="control", message=m))
        assert await port.request(dict(action="control", message=m)) == held
        port.control_capacity = len(port.control_records)
        with pytest.raises(ValueError, match="capacity"):
            await c.send("openOperator")
        stopped = await c.send("globalStop")
        assert stopped["runEpoch"] is None and stopped["guardId"] == held["guardId"]
        assert (await c.send("snapshot"))["inhibited"]
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_recovery_requires_evidence_and_legacy_cannot_bypass_control_mode():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        c = Controls(port)
        operator = (await c.send("openOperator"))["operatorId"]
        port.adapter.evidence.clear()
        with pytest.raises(ValueError, match="evidence"):
            await c.send("recover", operatorId=operator, guardId=None, confirmed=True)
        for action in ["admit", "recover", "clear", "heartbeat"]:
            with pytest.raises(ValueError, match="control-mode"):
                await port.request(dict(action=action, confirmed=True))
        port.adapter.evidence.set()
        port.adapter.evidence_at = time.monotonic()
        await c.send("recover", operatorId=operator, guardId=None, confirmed=True)
    finally:
        await port.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["expiry", "stop"])
async def test_operator_expiry_interrupts_real_port_operation(cause):
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        c = Controls(port)
        run = await c.setup()
        await port.request(dict(action="fixture", front="CLEAR"))
        motion = dict(
            protocolVersion=1,
            connectionEpoch=run["runEpoch"],
            requestId="move",
            robotId="fake-only",
            runId="run",
            activityId="a",
            operationId="op",
            kind="startMotion",
            goal=dict(kind="move", distanceM=0.05, speedMps=0.1),
        )
        await port.request(dict(action="motion", session=run["runEpoch"], message=motion))
        async with asyncio.timeout(1):
            while not port.adapter.actuating:  # noqa: ASYNC110
                await asyncio.sleep(0.005)
        if cause == "expiry":
            port.operator_deadline = 0
            with pytest.raises(ValueError, match="run"):
                await c.send("runnerHeartbeat", runId="run", runEpoch=run["runEpoch"], sequence=1)
        else:
            reply = await c.send("globalStop")
            assert reply["stopPending"]  # Acceptance is not evidence of stop.
        if port.finishing:
            await port.finishing
        done = next(e for e in events if e.get("protocolVersion") == 1 and e["kind"] == "terminal")
        assert done["outcome"] == "interrupted"
        assert done["reason"] == (
            "operator-lease-expired" if cause == "expiry" else "operator-global-stop"
        )
        assert not port.adapter.actuating and port.inhibited
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_old_control_epoch_and_cached_close_cannot_close_new_run():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        c = Controls(port)
        run = await c.setup()
        close = dict(
            protocolVersion=1,
            connectionEpoch=port.control_epoch,
            requestId="close",
            robotId="fake-only",
            kind="closeRun",
            runId="run",
            runEpoch=run["runEpoch"],
        )
        with pytest.raises(ValueError, match="epoch"):
            await port.request(dict(action="control", message=dict(close, connectionEpoch="old")))
        reply = await port.request(dict(action="control", message=close))
        if port.io_tasks:
            await asyncio.wait(port.io_tasks, timeout=0.2)
        new = await c.send("openRun", operatorId=c.operator, runId="new")
        assert await port.request(dict(action="control", message=close)) == reply
        assert port.session == new["runEpoch"]
    finally:
        await port.close()
