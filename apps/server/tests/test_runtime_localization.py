import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from test_control_contract import Controls
from test_motion_contract import result, start, wire
from test_motion_interlock import manual

from apris_server.runner_port_experiment import RunnerPort
from apris_server.runtime_localization import demo_localization
from apris_server.simulator import SimulatorFaults


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():  # noqa: ASYNC110 - poll independent runtime transitions
            await asyncio.sleep(0.01)


async def prepare(port):
    c = Controls(port)
    c.operator = (await c.send("openOperator"))["operatorId"]
    await until(lambda: port.localization.last_sample is not None)
    await port.request(
        dict(
            action="localize",
            controlEpoch=port.control_epoch,
            operatorId=c.operator,
            localizationEpoch=port.localization.epoch,
            candidateId="start-placement",
            confirmed=True,
        )
    )
    await c.send("recover", operatorId=c.operator, guardId=None, confirmed=True)
    return c


@pytest.mark.asyncio
async def test_initialization_required_and_map_bound_until_run_ends():
    port = RunnerPort(lambda _: None, backend="simulator", localization=demo_localization())
    await port.start()
    try:
        with pytest.raises(ValueError):
            await port.request(dict(action="admit"))
        c = await prepare(port)
        run = await c.send("openRun", operatorId=c.operator, runId="run")
        state = await port.request(dict(action="snapshot"))
        assert state["localization"]["snapshot"]["quality"]["status"] == "tracking"
        assert state["localization"]["binding"]["runId"] == run["runEpoch"]
        with pytest.raises(ValueError, match="localization-busy"):
            await port.request(
                dict(
                    action="localize",
                    controlEpoch=port.control_epoch,
                    operatorId=c.operator,
                    localizationEpoch=port.localization.epoch,
                    candidateId="start-placement",
                    confirmed=True,
                )
            )
        await c.send("closeRun", runId="run", runEpoch=run["runEpoch"])
        assert port.localization.binding is None
    finally:
        await port.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        SimulatorFaults(encoder_fault=True),
        SimulatorFaults(stale_state_ms=1500),
        SimulatorFaults(state_latency_ms=400),
    ],
)
async def test_quality_loss_stops_motion_revokes_run_and_never_auto_recovers(fault):
    events = []
    port = RunnerPort(events.append, backend="simulator", localization=demo_localization())
    port.operator_lease_s = port.lease_s = 3.0
    port.command_ttl_s = 2.0
    await port.start()
    try:
        c = await prepare(port)
        run = await c.send("openRun", operatorId=c.operator, runId="run")
        session = run["runEpoch"]
        await port.request(dict(action="fixture", front="CLEAR"))
        await wire(
            port, session, dict(start(session), goal=dict(kind="move", distanceM=0.3, speedMps=0.1))
        )
        await until(lambda: port.adapter.actuating)
        await port.adapter.set_faults(fault)
        terminal = await result(events)
        assert terminal["outcome"] == "interrupted"
        assert terminal["reason"].startswith("localization-")
        assert terminal["evidence"]["kind"] == "simulated"
        assert not port.adapter.actuating and port.session is None
        assert port.inhibited and port.runtime.motion_interlock.blocked
        await port.adapter.clear_faults()
        await asyncio.sleep(0.1)
        assert port.inhibited and port.localization.blocked
        with pytest.raises(ValueError):
            await c.send("recover", operatorId=c.operator, guardId=None, confirmed=True)
        await until(lambda: not port.io_tasks)
        await until(
            lambda: (
                port.localization.last_sample is not None
                and time.monotonic() - port.localization.last_sample.sampleTime < 0.1
                and port.localization.last_sample.sensorStatus == "ok"
            )
        )
        await port.request(
            dict(
                action="localize",
                controlEpoch=port.control_epoch,
                operatorId=c.operator,
                localizationEpoch=port.localization.epoch,
                candidateId="start-placement",
                confirmed=True,
            )
        )
        assert port.session is None and port.inhibited
        await c.send("recover", operatorId=c.operator, guardId=None, confirmed=True)
        assert not port.adapter.actuating
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_monitor_stall_and_manual_entrypoints_cannot_bypass_hold():
    port = RunnerPort(lambda _: None, backend="simulator", localization=demo_localization())
    port.operator_lease_s = 3.0
    await port.start()
    try:
        await prepare(port)
        client, socket = await manual(port.runtime)
        # The shared authority protects a non-runner owner too.
        await port.runtime.handle_text(client, '{"type":"drive","vx":-0.1,"wz":0,"seq":1}')
        assert port.adapter.actuating
        gate = asyncio.Event()
        original = port.adapter.localization_state
        port.adapter.localization_state = AsyncMock(side_effect=gate.wait)
        await until(lambda: port.localization.blocked)
        await until(lambda: not port.adapter.actuating and not port.io_tasks)
        client, socket = await manual(port.runtime)
        await port.runtime.handle_text(client, '{"type":"drive","vx":-0.1,"wz":0,"seq":2}')
        assert any(m.get("code") == "motion_inhibited" for m in socket.messages)
        port.adapter.localization_state = original
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_reset_of_adapter_is_detected_even_when_pose_does_not_jump():
    port = RunnerPort(lambda _: None, backend="simulator", localization=demo_localization())
    await port.start()
    try:
        await prepare(port)
        old = port.localization.epoch
        await port.adapter.reset_pose()
        await until(lambda: port.localization.blocked)
        assert port.localization.reason == "odometry-epoch-changed"
        assert port.localization.epoch == old
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_missing_stop_evidence_is_not_reported_as_success():
    events = []
    port = RunnerPort(events.append, backend="simulator", localization=demo_localization())
    port.operator_lease_s = port.lease_s = 3.0
    port.command_ttl_s = 2.0
    await port.start()
    try:
        c = await prepare(port)
        run = await c.send("openRun", operatorId=c.operator, runId="run")
        session = run["runEpoch"]
        await port.request(dict(action="fixture", front="CLEAR"))
        await wire(
            port, session, dict(start(session), goal=dict(kind="move", distanceM=0.3, speedMps=0.1))
        )
        await until(lambda: port.adapter.actuating)
        original = port.adapter.stop

        async def stop_without_evidence():
            await original()
            port.adapter.evidence.clear()

        port.adapter.stop = stop_without_evidence
        await port.adapter.set_faults(SimulatorFaults(encoder_fault=True))
        terminal = await result(events)
        assert terminal["outcome"] == "stop-unconfirmed"
        assert terminal["evidence"]["kind"] == "unknown"
        assert port.inhibited and port.localization.blocked
        port.adapter.stop = original
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_monitor_does_not_wait_for_request_lock_or_late_admission():
    events = []
    port = RunnerPort(events.append, backend="simulator", localization=demo_localization())
    port.operator_lease_s = port.lease_s = 3.0
    port.command_ttl_s = 2.0
    await port.start()
    try:
        c = await prepare(port)
        run = await c.send("openRun", operatorId=c.operator, runId="run")
        session = run["runEpoch"]
        await port.request(dict(action="fixture", front="CLEAR"))
        port.adapter.drive = AsyncMock(wraps=port.adapter.drive)
        await port.adapter.set_faults(SimulatorFaults(state_latency_ms=1000))
        task = asyncio.create_task(
            wire(
                port,
                session,
                dict(start(session), goal=dict(kind="move", distanceM=0.3, speedMps=0.1)),
            )
        )
        await until(lambda: port.localization.blocked)
        assert not task.done()  # watchdog fenced while command admission was awaiting I/O
        assert not port.adapter.drive.called
        await asyncio.wait_for(task, 2)
        await asyncio.sleep(0.05)
        assert not port.adapter.drive.called and port.session is None
    finally:
        await port.adapter.clear_faults()
        await port.close()


@pytest.mark.asyncio
async def test_observation_scope_cannot_survive_explicit_reinitialization():
    port = RunnerPort(lambda _: None, backend="simulator", localization=demo_localization())
    port.operator_lease_s = 3.0
    await port.start()
    try:
        c = await prepare(port)
        await asyncio.sleep(0.04)
        loc = port.localization
        current = loc.estimator.snapshot()
        observation = dict(
            **loc.estimator.scope.model_dump(),
            clockId=current.clockId,
            clockEpoch=current.clockEpoch,
            receivedTime=time.monotonic(),
            captureTime=current.sampleTime,
            sequence=1,
            clockUncertaintyS=0.0,
            sourceId="simulator-marker",
            sessionEpoch=loc.source_epoch,
            observationId="test-marker",
            family="example-square",
            markerId=1,
            frameId="base",
            relativePose=dict(xM=0.0, yM=0.0, zM=0.8, rollRad=0.0, pitchRad=0.0, yawRad=0.0),
            confidence=0.95,
            poseAmbiguous=False,
            provenance="simulated",
        )
        reply = await port.request(dict(action="localizationObservation", observation=observation))
        assert reply["applied"]
        old_epoch = loc.epoch
        await port.request(
            dict(
                action="localize",
                controlEpoch=port.control_epoch,
                operatorId=c.operator,
                localizationEpoch=old_epoch,
                candidateId="start-placement",
                confirmed=True,
            )
        )
        assert loc.epoch != old_epoch
        reply = await port.request(dict(action="localizationObservation", observation=observation))
        assert reply == dict(applied=False, reason="scope-mismatch")
        assert port.session is None
    finally:
        await port.close()
