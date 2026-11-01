"""Offline delay experiments and recovery regressions, not physical validation."""

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager

import pytest
from test_ironx_network_adapter import FakeRobot
from websockets.asyncio.server import serve

from apris_server.ironx_gateway import IronXGateway
from apris_server.ironx_network_adapter import (
    DriveNotSent,
    IronXNetworkAdapter,
    NonceRejected,
    OwnershipExpired,
)


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


async def test_fresh_owned_telemetry_avoids_slow_poll_blocking_drive():
    async with offline_link() as (adapter, gateway, robot):
        await adapter.drive(0.10, 0, 0)
        gateway.reply_delays["state"] = 0.32
        state_reads = sum(method == "state" for method, _ in gateway.responses)
        for _ in range(12):
            await asyncio.sleep(0.02)
            deadline = gateway.deadline
            received_at = adapter._received_at
            state = await adapter.state()
            assert state.connected
            assert gateway.deadline == deadline
            assert adapter._received_at == received_at
            await adapter.drive(0.10, 0, 0)
        assert sum(method == "state" for method, _ in gateway.responses) == state_reads
        assert len(robot.drives) == 13
        assert not adapter.requires_rearm
        assert gateway.owner is not None
        await adapter.stop()


async def test_owned_telemetry_cache_ages_out_and_refreshes():
    async with offline_link() as (adapter, gateway, _):
        await adapter.drive(0.10, 0, 0)
        state_reads = sum(method == "state" for method, _ in gateway.responses)
        await asyncio.sleep(0.12)
        assert (await adapter.state()).connected
        assert sum(method == "state" for method, _ in gateway.responses) == state_reads + 1
        await adapter.stop()


async def test_idle_state_never_uses_owned_motion_cache():
    async with offline_link() as (adapter, gateway, _):
        await adapter.drive(0.10, 0, 0)
        await adapter.stop()
        state_reads = sum(method == "state" for method, _ in gateway.responses)
        await adapter.state()
        assert sum(method == "state" for method, _ in gateway.responses) == state_reads + 1


async def test_two_second_owner_survives_400ms_gap_with_fresh_command():
    async with offline_link() as (adapter, gateway, robot):
        await adapter.drive(0.10, 0, 0)
        owner = gateway.owner
        await asyncio.sleep(0.4)
        assert gateway.owner is owner
        await adapter.drive(0.10, 0, 0)
        assert gateway.owner is owner
        assert len(robot.drives) == 2
        assert all(0 < drive[3] <= 200 for drive in robot.drives)
        assert not adapter.requires_rearm
        assert not adapter._failed
        await adapter.stop()


@pytest.mark.parametrize("delay", [0.04, 0.24])
async def test_rpc_queue_wait_consumes_ttl_before_sending(delay):
    async with offline_link() as (adapter, gateway, robot):
        await adapter.drive(0.10, 0, 0)
        connection = adapter._socket
        await adapter._rpc_lock.acquire()
        driving = asyncio.create_task(adapter.drive(0.10, 0, 0))
        try:
            await asyncio.sleep(delay)
        finally:
            adapter._rpc_lock.release()
        if delay < 0.2:
            await driving
            assert len(robot.drives) == 2
            assert robot.drives[-1][3] < 170
        else:
            with pytest.raises(DriveNotSent):
                await driving
            assert len(robot.drives) == 1
            assert gateway.owner is None
            assert not any(method == "drive" and "error" in reply
                           for method, reply in gateway.responses)
        assert adapter._socket is connection
        assert not adapter._failed
        assert not adapter.requires_rearm
        await adapter.stop()


@pytest.mark.parametrize("code", ["invalid_nonce", "expired_nonce"])
async def test_nonce_refusal_preserves_connection_and_requires_confirmed_stop(code):
    async with offline_link() as (adapter, gateway, robot):
        await adapter.drive(0.10, 0, 0)
        connection = adapter._socket
        if code == "invalid_nonce":
            adapter._next_drive[0]["nonce"] = "unknown-test-nonce"
        else:
            gateway.request_delays["drive"] = 0.22
        with pytest.raises(NonceRejected):
            await adapter.drive(0.10, 0, 0)
        assert adapter.last_drive_diagnostics["rpcs"][-1]["gateway_error"]["code"] == code
        assert adapter._socket is connection
        assert not adapter._failed
        assert adapter._stop_unconfirmed
        assert adapter.requires_rearm
        assert len(robot.drives) == 1
        await adapter.stop()
        assert gateway.estopped
        assert not adapter._stop_unconfirmed
        assert adapter._socket is connection
        with pytest.raises(RuntimeError, match="explicitly clear stop"):
            await adapter.drive(0.10, 0, 0)
        assert len(robot.drives) == 1


async def test_stop_while_drive_waits_for_rpc_does_not_send_motion():
    async with offline_link() as (adapter, gateway, robot):
        await adapter.drive(0.10, 0, 0)
        await adapter._rpc_lock.acquire()
        driving = asyncio.create_task(adapter.drive(0.10, 0, 0))
        await asyncio.sleep(0.01)
        stopping = asyncio.create_task(adapter.stop())
        try:
            await asyncio.sleep(0.01)
        finally:
            adapter._rpc_lock.release()
        with pytest.raises(DriveNotSent, match="superseded"):
            await driving
        await asyncio.wait_for(stopping, 1)
        assert len(robot.drives) == 1
        assert gateway.owner is None
        assert not adapter._failed


async def test_baseline_delayed_state_reply_reproduces_ownership_expiry(monkeypatch):
    monkeypatch.setattr("apris_server.ironx_gateway.OWNERSHIP_LEASE_SECONDS", 0.3)
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


async def test_delayed_drive_during_stop_keeps_transport_and_confirms_stop(monkeypatch):
    monkeypatch.setattr("apris_server.ironx_gateway.OWNERSHIP_LEASE_SECONDS", 0.3)
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
