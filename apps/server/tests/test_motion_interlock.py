import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from apris_server.models import DriveCommand
from apris_server.runner_port_experiment import PortFakeAdapter, RunnerPort
from apris_server.runtime import RoverRuntime
from apris_server.simulator import DifferentialDriveSimulator


class Socket:
    def __init__(self):
        self.messages = []

    async def send_text(self, text):
        self.messages.append(json.loads(text))


async def manual(runtime):
    socket = Socket()
    client = await runtime.add_client(socket)
    await runtime.handle_text(
        client,
        json.dumps(
            dict(
                type="client_hello",
                client_kind="service_app",
                device_id="manual-test",
                session_id="manual",
                app_version="test",
                build_id="test",
            )
        ),
    )
    await runtime.handle_text(client, '{"type":"acquire_control"}')
    assert runtime.owner_client_id == client
    return client, socket


@pytest.mark.asyncio
async def test_runner_guard_blocks_new_manual_owner_on_all_motion_paths_but_not_stop():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        session = await port.request(dict(action="admit"))
        await port.request(dict(action="hold", session=session))
        await port.request(dict(action="revoke"))
        if port.io_tasks:
            await asyncio.wait(port.io_tasks, timeout=0.5)
        client, socket = await manual(port.runtime)
        port.adapter.drive = AsyncMock(wraps=port.adapter.drive)
        port.adapter.stop = AsyncMock(wraps=port.adapter.stop)
        for m in [
            dict(type="drive", vx=-0.1, wz=0, seq=1),
            dict(type="move", request_id="move", distance_m=-0.01, speed_mps=0.1),
            dict(type="turn", request_id="turn", angle_deg=5, speed_rad_s=0.7),
        ]:
            await port.runtime.handle_text(client, json.dumps(m))
        await asyncio.sleep(0.02)
        assert not port.adapter.drive.called and not port.adapter.goals
        assert any("motion_inhibited" in str(m) for m in socket.messages)
        await port.runtime.handle_text(client, '{"type":"stop"}')
        await port.runtime.handle_text(client, '{"type":"estop"}')
        await port.runtime.handle_text(client, '{"type":"clear_estop"}')
        assert port.adapter.stop.called
        assert port.runtime.motion_interlock.blocked
        assert (await port.runtime.status())["control"]["motion_interlock"]["blocked"]
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_guard_release_cannot_erase_independent_inhibition():
    port = RunnerPort(lambda _: None)
    await port.start()
    try:
        session = await port.request(dict(action="admit"))
        await port.request(dict(action="hold", session=session))
        port.inhibited = True
        await port.request(dict(action="clear", session=session, confirmed=True))
        assert port.runtime.motion_interlock.blocked
        port.inhibited = False
        assert not port.runtime.motion_interlock.blocked
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_delayed_manual_drive_is_fenced_even_after_guard_is_released():
    adapter = DifferentialDriveSimulator()
    runtime = RoverRuntime(adapter)
    await runtime.start()
    try:
        client, _ = await manual(runtime)
        entered, release = asyncio.Event(), asyncio.Event()
        original = runtime._cancel_motion

        async def delayed(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)

        runtime._cancel_motion = delayed
        adapter.drive = AsyncMock(wraps=adapter.drive)
        task = asyncio.create_task(
            runtime._drive(client, DriveCommand(type="drive", vx=-0.1, wz=0))
        )
        await entered.wait()
        token = runtime.motion_interlock.hold("handover")
        runtime.motion_interlock.release(token)
        release.set()
        await task
        assert not adapter.drive.called
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_handover_rejects_adapter_io_already_in_flight():
    port = RunnerPort(lambda _: None)
    await port.start()
    release = asyncio.Event()
    try:
        session = await port.request(dict(action="admit"))
        entered = asyncio.Event()

        async def blocked_drive(*args, **kwargs):
            entered.set()
            await release.wait()

        port.adapter.drive = blocked_drive
        task = asyncio.create_task(
            port.runtime._drive(port.client, DriveCommand(type="drive", vx=-0.1, wz=0))
        )
        await entered.wait()
        with pytest.raises(ValueError, match="stationary|pending"):
            await port.request(dict(action="hold", session=session))
        release.set()
        await task
    finally:
        release.set()
        await port.close()


@pytest.mark.asyncio
async def test_port_can_share_runtime_without_closing_other_clients():
    runtime = RoverRuntime(PortFakeAdapter())
    await runtime.start()
    port = RunnerPort(lambda _: None, runtime=runtime)
    await port.start()
    try:
        client, _ = await manual(runtime)
        await port.close()
        assert client in runtime.clients
        assert runtime.owner_client_id == client
        assert not runtime._closing
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_pending_disconnect_io_blocks_a_new_manual_owner():
    port = RunnerPort(lambda _: None)
    await port.start()
    release = asyncio.Event()
    try:
        await port.request(dict(action="admit"))
        entered = asyncio.Event()
        original = port.adapter.stop

        async def blocked_stop():
            entered.set()
            await release.wait()
            await original()

        port.adapter.stop = blocked_stop
        await port.request(dict(action="revoke"))
        await entered.wait()
        client, _ = await manual(port.runtime)
        port.adapter.drive = AsyncMock(wraps=port.adapter.drive)
        await port.runtime.handle_text(client, '{"type":"drive","vx":-0.1,"wz":0,"seq":1}')
        assert not port.adapter.drive.called
        assert "runner-stop-io" in port.runtime.motion_interlock.snapshot()["reasons"]
        release.set()
        if port.io_tasks:
            await asyncio.wait(port.io_tasks, timeout=0.5)
    finally:
        release.set()
        await port.close()


@pytest.mark.asyncio
async def test_delayed_bounded_motion_is_fenced_after_admission_check():
    runtime = RoverRuntime(PortFakeAdapter())
    await runtime.start()
    release = asyncio.Event()
    try:
        client, socket = await manual(runtime)
        entered = asyncio.Event()
        original = runtime.adapter.state

        async def delayed_state():
            entered.set()
            await release.wait()
            return await original()

        runtime.adapter.state = delayed_state
        task = asyncio.create_task(
            runtime.handle_text(
                client,
                '{"type":"turn","request_id":"turn","angle_deg":5,"speed_rad_s":0.7}',
            )
        )
        await entered.wait()
        hold = runtime.motion_interlock.hold("handover")
        runtime.motion_interlock.release(hold)
        release.set()
        await task
        if runtime._motion_task:
            await runtime._motion_task
        assert not runtime.adapter.goals
        assert any("motion_inhibited" in str(m) for m in socket.messages)
    finally:
        release.set()
        await runtime.close()


def test_shared_port_rejects_unqualified_adapter():
    with pytest.raises(ValueError, match="fake-adapter"):
        RunnerPort(lambda _: None, runtime=RoverRuntime(DifferentialDriveSimulator()))


@pytest.mark.asyncio
async def test_legacy_disconnect_stop_blocks_new_owner_until_io_finishes():
    runtime = RoverRuntime(DifferentialDriveSimulator())
    await runtime.start()
    release = asyncio.Event()
    try:
        old, _ = await manual(runtime)
        entered = asyncio.Event()
        original = runtime.adapter.stop

        async def delayed_stop():
            entered.set()
            await release.wait()
            await original()

        runtime.adapter.stop = delayed_stop
        cleanup = asyncio.create_task(runtime.remove_client(old))
        await entered.wait()
        new, _ = await manual(runtime)
        runtime.adapter.drive = AsyncMock(wraps=runtime.adapter.drive)
        await runtime.handle_text(new, '{"type":"drive","vx":-0.1,"wz":0,"seq":1}')
        assert not runtime.adapter.drive.called
        release.set()
        await cleanup
    finally:
        release.set()
        await runtime.close()
