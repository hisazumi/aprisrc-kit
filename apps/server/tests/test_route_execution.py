import asyncio
import math
from contextlib import suppress

import pytest
from test_runtime_localization import prepare, until

from apris_server.runner_port_experiment import RunnerPort
from apris_server.runtime_localization import demo_localization
from apris_server.simulator import SimulatorFaults


async def begin(port):
    c = await prepare(port)
    run = await c.send("openRun", operatorId=c.operator, runId="route-run")
    request = dict(
        controlEpoch=port.control_epoch,
        runId="route-run",
        runEpoch=run["runEpoch"],
        requestId="route-request",
        method="route",
        targetId="start-to-desk",
    )

    async def heartbeat():
        for seq in range(1, 400):
            await port.request(dict(action="fixture", front="CLEAR"))
            await c.send("operatorHeartbeat", operatorId=c.operator, sequence=seq)
            if port.session:
                await c.send(
                    "runnerHeartbeat", runId="route-run", runEpoch=run["runEpoch"], sequence=seq
                )
            await asyncio.sleep(0.05)

    task = asyncio.create_task(heartbeat())
    await port.request(dict(action="fixture", front="CLEAR"))
    job = await port.request(dict(action="routeStart", message=request))
    return request, job, task


async def cleanup(port, task):
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await port.close()


@pytest.mark.asyncio
async def test_l_route_arrives_with_stop_evidence_and_duplicate_never_restarts():
    events = []
    port = RunnerPort(events.append, backend="simulator", localization=demo_localization())
    await port.start()
    task = None
    try:
        request, job, task = await begin(port)
        duplicate = await port.request(dict(action="routeStart", message=request))
        assert duplicate["id"] == job["id"]
        await asyncio.wait_for(asyncio.shield(port.routes.task), 35)
        final = port.routes.snapshot()

        assert final["status"] == "completed", (
            final["reason"],
            final["actions"],
            port.localization.estimator.snapshot().model_dump(),
        )
        assert final["actions"] > 2
        state = port.localization.estimator.snapshot()
        assert state.mapPose.xM > 0.08 and state.mapPose.yM > 0.08
        error = math.hypot(state.mapPose.xM - 0.16, state.mapPose.yM - 0.16)
        assert error + state.quality.positionErrorM <= port.routes.profile.arrivalM
        assert not port.adapter.actuating and port.adapter.evidence.is_set()
        assert (await port.request(dict(action="routeStart", message=request))) == final
        await asyncio.sleep(0.05)
        assert not port.adapter.actuating
    finally:
        if task:
            await cleanup(port, task)
        else:
            await port.close()


@pytest.mark.asyncio
async def test_cancel_is_scoped_and_fences_competing_motion():
    port = RunnerPort(lambda _: None, backend="simulator", localization=demo_localization())
    await port.start()
    request, job, task = await begin(port)
    try:
        await until(lambda: port.adapter.actuating)
        with pytest.raises(ValueError, match="route-owns-motion"):
            await port.request(dict(action="motion", session=port.session, message={}))
        with pytest.raises(ValueError, match="stale-route"):
            await port.request(
                dict(action="routeCancel", message=dict(id="old", runEpoch=port.session))
            )
        await port.request(
            dict(action="routeCancel", message=dict(id=job["id"], runEpoch=request["runEpoch"]))
        )
        await asyncio.wait_for(asyncio.shield(port.routes.task), 2)
        assert port.routes.snapshot()["status"] == "cancelled"
        assert port.session is None and not port.adapter.actuating and port.inhibited
    finally:
        await cleanup(port, task)


@pytest.mark.asyncio
async def test_quality_failure_interrupts_route_without_next_segment():
    port = RunnerPort(lambda _: None, backend="simulator", localization=demo_localization())
    await port.start()
    request, job, task = await begin(port)
    try:
        await until(lambda: port.adapter.actuating)
        await port.adapter.set_faults(SimulatorFaults(encoder_fault=True))
        await asyncio.wait_for(asyncio.shield(port.routes.task), 2)
        result = port.routes.snapshot()
        assert result["status"] == "interrupted", result
        actions = result["actions"]
        await port.adapter.clear_faults()
        await asyncio.sleep(0.1)
        assert port.routes.snapshot()["actions"] == actions
        assert not port.adapter.actuating and port.session is None
    finally:
        await cleanup(port, task)


@pytest.mark.asyncio
async def test_large_valid_marker_correction_stops_route_instead_of_skipping_waypoint():
    import time

    port = RunnerPort(lambda _: None, backend="simulator", localization=demo_localization())
    await port.start()
    request, job, task = await begin(port)
    try:
        await until(lambda: port.adapter.actuating)
        await asyncio.sleep(0.04)
        loc = port.localization
        s = loc.estimator.snapshot()
        p = s.mapPose
        x, y = p.xM + 0.2, p.yM
        co, si = math.cos(p.yawRad), math.sin(p.yawRad)
        obs = dict(
            **loc.estimator.scope.model_dump(),
            clockId=s.clockId,
            clockEpoch=s.clockEpoch,
            receivedTime=time.monotonic(),
            captureTime=s.sampleTime,
            sequence=1,
            clockUncertaintyS=0.0,
            sourceId="simulator-marker",
            sessionEpoch=loc.source_epoch,
            observationId="correction",
            family="example-square",
            markerId=1,
            frameId="base",
            relativePose=dict(
                xM=-co * x - si * y,
                yM=si * x - co * y,
                zM=0.8,
                rollRad=0.0,
                pitchRad=0.0,
                yawRad=-p.yawRad,
            ),
            confidence=0.95,
            poseAmbiguous=False,
            provenance="simulated",
        )
        assert (await port.request(dict(action="localizationObservation", observation=obs)))[
            "applied"
        ]
        await asyncio.wait_for(asyncio.shield(port.routes.task), 2)
        assert port.routes.snapshot()["reason"] == "route-large-correction"
        assert port.routes.snapshot()["status"] == "failed"
        assert port.routes.snapshot()["actions"] == 1
        assert not port.adapter.actuating
    finally:
        await cleanup(port, task)
