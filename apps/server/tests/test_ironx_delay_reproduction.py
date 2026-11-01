"""Offline delay experiments and recovery regressions, not physical validation."""

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager

import pytest
from test_ironx_network_adapter import FakeRobot
from websockets.asyncio.server import serve

from apris_server.ironx_gateway import IronXGateway
from apris_server.ironx_network_adapter import IronXNetworkAdapter, OwnershipExpired


class DelayedGateway(IronXGateway):
    """Inject transport delay around the real request handler, never into production."""

    def __init__(self, robot):
        super().__init__(robot, "offline-test-token")
        self.request_delays = {}
        self.reply_delays = {}
        self.responses = []

    async def respond(self, session, raw):
        method = json.loads(raw)["method"]
        await asyncio.sleep(self.request_delays.get(method, 0))
        response = await super().respond(session, raw)
        await asyncio.sleep(self.reply_delays.get(method, 0))
        self.responses.append((method, response))
        return response


class StopGateRobot(FakeRobot):
    def __init__(self):
        super().__init__()
        self.hold_stop = False
        self.stop_entered = asyncio.Event()
        self.finish_stop = asyncio.Event()

    async def stop(self):
        if self.hold_stop:
            self.stop_entered.set()
            await self.finish_stop.wait()
        await super().stop()


@asynccontextmanager
async def offline_link():
    # Fixed loopback binding + ephemeral port: no real robot URL/config is read.
    robot = StopGateRobot()
    gateway = DelayedGateway(robot)
    await gateway.initialize()
    async with serve(gateway.handler, "127.0.0.1", 0,
                     process_request=gateway.authenticate) as server:
        adapter = IronXNetworkAdapter(
            f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", "offline-test-token")
        await adapter.start()
        watchdog = asyncio.create_task(gateway.watchdog())
        try:
            yield adapter, gateway, robot
        finally:
            robot.finish_stop.set()
            await adapter.close()
            watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watchdog


async def test_small_variable_reply_delays_complete_without_rearm():
    async with offline_link() as (adapter, gateway, robot):
        for delay in [0.01, 0.02, 0.04, 0.01, 0.02]:
            gateway.reply_delays["drive"] = delay
            await adapter.drive(0.10, 0, 0, ttl_ms=200)
            await asyncio.sleep(0.02)
        assert len(robot.drives) == 5
        assert all(0 < drive[3] <= 200 for drive in robot.drives)
        assert not adapter.requires_rearm
        assert not adapter._failed
        await adapter.stop()
        assert gateway.owner is None


async def test_delayed_state_reply_reproduces_ownership_expiry():
    async with offline_link() as (adapter, gateway, robot):
        await adapter.drive(0.10, 0, 0)
        # Invalidate the cached reply, then cross the 300 ms lease while reading state.
        await asyncio.sleep(0.16)
        gateway.reply_delays["state"] = 0.18
        with pytest.raises(OwnershipExpired):
            await adapter.drive(0.10, 0, 0)
        assert len(robot.drives) == 1
        assert gateway.owner is None
        trace = adapter.last_drive_diagnostics
        assert trace["rpcs"][-1]["gateway_error"]["code"] == "not_owner"
        assert not adapter._failed
        assert adapter.requires_rearm
        await adapter.stop()
        assert gateway.estopped
        assert not adapter._stop_unconfirmed
        with pytest.raises(RuntimeError, match="explicitly clear stop"):
            await adapter.drive(0.10, 0, 0)
        assert len(robot.drives) == 1


async def test_delayed_drive_during_stop_keeps_transport_and_confirms_stop():
    async with offline_link() as (adapter, gateway, robot):
        await adapter.drive(0.10, 0, 0)
        robot.hold_stop = True
        gateway.request_delays["drive"] = 0.36
        connection = adapter._socket
        # The real watchdog expires ownership while this request is in transit.
        with pytest.raises(RuntimeError, match="Stop confirmation in progress"):
            await adapter.drive(0.10, 0, 0)
        assert robot.stop_entered.is_set()
        assert len(robot.drives) == 1
        trace = adapter.last_drive_diagnostics
        assert trace["rpcs"][-1]["gateway_error"]["code"] == "stopping"
        assert trace["rpcs"][-1]["outcome"] == "gateway_stopping"
        assert not adapter._failed
        assert adapter._socket is connection
        assert adapter.requires_rearm
        assert adapter._stop_unconfirmed
        assert adapter.last_transport_error is None
        stopping = asyncio.create_task(adapter.stop())
        try:
            await asyncio.sleep(0.02)
            assert not stopping.done()
            assert adapter._stop_unconfirmed
        finally:
            robot.finish_stop.set()
            await asyncio.wait_for(stopping, 1)
        assert not adapter._stop_unconfirmed
        assert adapter._socket is connection
        assert gateway.estopped
        with pytest.raises(RuntimeError, match="explicitly clear stop"):
            await adapter.drive(0.10, 0, 0)
        assert len(robot.drives) == 1


async def test_state_reply_timeout_blocks_motion_and_does_not_replay():
    async with offline_link() as (adapter, gateway, robot):
        gateway.reply_delays["state"] = 0.40
        with pytest.raises(TimeoutError):
            await adapter.drive(0.10, 0, 0)
        assert not robot.drives
        assert adapter._failed
        assert adapter.requires_rearm
        with pytest.raises(RuntimeError, match="explicitly clear stop"):
            await adapter.drive(0.10, 0, 0)
        assert not robot.drives


async def test_stopping_rejection_without_ownership_does_not_request_robot_stop():
    async with offline_link() as (adapter, gateway, robot):
        gateway.ready = False
        stops = robot.stops
        with pytest.raises(RuntimeError, match="Stop confirmation in progress"):
            await adapter.drive(0.10, 0, 0)
        assert not adapter.requires_rearm
        assert not adapter._stop_unconfirmed
        # Acquisition refusal retains the pre-existing error path; no remote stop is sent.
        with pytest.raises(RuntimeError, match="physical stop not confirmed"):
            await adapter.stop()
        assert robot.stops == stops
        assert not robot.drives
