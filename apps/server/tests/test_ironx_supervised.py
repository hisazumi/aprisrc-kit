"""Offline supervised profile tests; no real robot or ROS required."""

import asyncio
import json

import pytest
from test_ironx_command_bridge import module as bridge
from test_ironx_network_adapter import FakeRobot, endpoint
from websockets.asyncio.server import serve

from apris_server.ironx_gateway import IronXGateway
from apris_server.ironx_network_adapter import IronXNetworkAdapter
from apris_server.ironx_profile import load_profile
from apris_server.runtime import RoverRuntime


def test_profile_is_opt_in_and_validated(monkeypatch):
    monkeypatch.delenv("APRIS_IRONX_PROFILE", raising=False)
    assert load_profile().command_ms == 200
    monkeypatch.setenv("APRIS_IRONX_PROFILE", "typo")
    with pytest.raises(ValueError):
        load_profile()


def test_supervised_robot_deadline_and_replay():
    lease = bridge.CommandLease("supervised_low_speed")
    assert lease.accept(100, 100, 10, 0.15, 0, 0, 0, 0, 0)
    assert lease.output(17.99, True) == (0.15, 0)
    assert lease.output(18, True) == (0, 0)
    assert not lease.accept(100, 108, 18, 0.15, 0, 0, 0, 0, 0)
    assert lease.output(19, True) == (0, 0)


def test_unchanged_mailbox_never_renews_deadline(tmp_path):
    lease = bridge.CommandLease("supervised_low_speed")
    path = tmp_path / "command.json"
    mailbox = bridge.FileCommands(path, lease)
    mailbox.started = 99
    path.write_text(json.dumps(dict(id="one", monotonic=100, ttl_ms=8000, vx=0.1, wz=0)))
    mailbox.poll(100.5)
    assert lease.deadline == 108
    mailbox.poll(107.9)
    assert lease.deadline == 108
    assert lease.output(108, True) == (0, 0)
    mailbox.poll(109)
    assert lease.output(109, True) == (0, 0)


def test_supervised_telemetry_loss_and_manual_stop_remain_immediate():
    lease = bridge.CommandLease("supervised_low_speed")
    assert lease.accept(100, 100, 10, 0.1, 0, 0, 0, 0, 0)
    assert lease.output(10.1, False) == (0, 0)
    assert lease.accept(101, 101, 11, 0.1, 0, 0, 0, 0, 0)
    lease.latch("operator_stop")
    assert lease.output(11.1, True) == (0, 0)
    assert not lease.accept(102, 102, 12, 0.1, 0, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_profile_mismatch_cannot_drive(monkeypatch):
    monkeypatch.setenv("APRIS_IRONX_PROFILE", "supervised_low_speed")
    async with endpoint() as (adapter, requests, _):
        with pytest.raises(RuntimeError, match="profile mismatch"):
            await adapter.drive(0.1, 0, 0, ttl_ms=8000)
        assert not any(r["method"] == "drive" for r in requests)


@pytest.mark.asyncio
async def test_delayed_real_gateway_runtime_and_expiry(monkeypatch):
    monkeypatch.setenv("APRIS_IRONX_PROFILE", "supervised_low_speed")

    class DelayedGateway(IronXGateway):
        async def respond(self, session, raw):
            if json.loads(raw)["method"] in ("state", "drive"):
                await asyncio.sleep(0.4)
            return await super().respond(session, raw)

    robot = FakeRobot()
    gateway = DelayedGateway(robot, "test-token")
    await gateway.initialize()
    async with serve(gateway.handler, "127.0.0.1", 0,
                     process_request=gateway.authenticate) as server:
        adapter = IronXNetworkAdapter(
            f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", "test-token")
        await adapter.start()
        runtime = RoverRuntime(adapter)
        try:
            for _ in range(3):
                await runtime._apply_velocity(0.1, 0, 0, 500)
            assert len(robot.drives) == 3
            assert all(6000 < d[3] <= 8000 for d in robot.drives)
            assert not adapter.requires_rearm
            # Execute the robot-side watchdog with the actual delivered TTL.
            lease = bridge.CommandLease("supervised_low_speed")
            assert lease.accept(100, 100, 10, 0.1, 0, 0, 0, 0, 0)
            lease.deadline = min(lease.deadline, 10 + robot.drives[-1][3] / 1000)
            assert lease.output(11, True) == (0.1, 0)
            assert lease.output(20, True) == (0, 0)
            await adapter.emergency_stop("test")
            assert gateway.estopped
            with pytest.raises(RuntimeError):
                await adapter.drive(0.1, 0, 0)
        finally:
            await adapter.close()
