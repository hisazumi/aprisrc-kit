import asyncio
import json
import time
from contextlib import asynccontextmanager

import pytest
from websockets.asyncio.server import serve

from apris_server.adapter import BoundedMotionGoal
from apris_server.config import AppConfig
from apris_server.ironx_adapter import IronXAdapter
from apris_server.ironx_gateway import IronXGateway
from apris_server.ironx_network_adapter import IronXNetworkAdapter
from apris_server.models import Capabilities, Pose, PoseEstimateQuality, RoverState, Velocity


def snapshot():
    return RoverState(
        timestamp=time.time(),
        connected=True,
        pose=Pose(x=0, y=0, yaw=0),
        velocity=Velocity(vx=0, vy=0, wz=0),
        capabilities=Capabilities(),
        pose_quality=PoseEstimateQuality(age_ms=1),
    ).model_dump(mode="json")


class FakeRobot:
    def __init__(self):
        self.drives = []
        self.stops = 0

    async def state(self):
        return RoverState.model_validate(snapshot())

    async def drive(self, vx, vy, wz, *, ttl_ms):
        self.drives.append((vx, vy, wz, ttl_ms))

    async def stop(self):
        self.stops += 1


async def test_local_validation_cannot_extend_network_command_ttl(tmp_path, monkeypatch):
    adapter = IronXAdapter(tmp_path / "state", tmp_path / "command", tmp_path / "bridge")

    async def slow_state():
        await asyncio.sleep(0.02)
        return RoverState.model_validate(snapshot())

    monkeypatch.setattr(adapter, "state", slow_state)
    with pytest.raises(RuntimeError, match="expired"):
        await adapter.drive(0.04, 0, 0, ttl_ms=1)
    command = json.loads((tmp_path / "command").read_text())
    assert command["vx"] == 0


async def test_stop_during_bounded_telemetry_cannot_restart_motion(monkeypatch):
    adapter = IronXNetworkAdapter("ws://unused", "test-token")
    reading, resume = asyncio.Event(), asyncio.Event()
    calls = []

    async def state(*args):
        calls.append("state")
        if len(calls) == 2:
            reading.set()
            await resume.wait()
        return RoverState.model_validate(snapshot())

    async def rpc(*args, **kwargs):
        calls.append(args[0])
        raise AssertionError("No command may follow stop")

    monkeypatch.setattr(adapter, "state", state)
    monkeypatch.setattr(adapter, "_rpc", rpc)
    task = asyncio.create_task(
        adapter.execute_bounded_motion(
            BoundedMotionGoal("motion", "linear", 0.1, None, 0.04, 0.1, 5000)
        )
    )
    await reading.wait()
    await adapter.stop()
    resume.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["state", "state"]


async def test_real_gateway_two_clients_and_handoff():
    robot = FakeRobot()
    gateway = IronXGateway(robot, "test-token")
    await gateway.initialize()
    async with serve(
        gateway.handler, "127.0.0.1", 0, process_request=gateway.authenticate
    ) as server:
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        first, second = [IronXNetworkAdapter(url, "test-token") for _ in range(2)]
        await first.start()
        await second.start()
        try:
            await first.drive(0.15, 0, 0)
            assert robot.drives[-1][:2] == (0.15, 0)
            stops = robot.stops
            await second.stop()
            assert robot.stops == stops
            with pytest.raises(RuntimeError):
                await second.drive(0.04, 0, 0)
            assert robot.stops == stops
            assert len(robot.drives) == 1
            await first.stop()
            assert robot.stops == stops + 1
            third = IronXNetworkAdapter(url, "test-token")
            await third.start()
            try:
                await third.drive(0, 0, 0.1)
                assert len(robot.drives) == 2
                await third.stop()
            finally:
                await third.close()
        finally:
            await first.close()
            await second.close()


async def test_real_gateway_expiry_rejects_same_client_resume():
    robot = FakeRobot()
    gateway = IronXGateway(robot, "test-token")
    await gateway.initialize()
    async with serve(
        gateway.handler, "127.0.0.1", 0, process_request=gateway.authenticate
    ) as server:
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        adapter = IronXNetworkAdapter(url, "test-token")
        await adapter.start()
        try:
            await adapter.drive(0.04, 0, 0)
            await asyncio.sleep(0.31)
            await gateway.expire()
            assert gateway.owner is None
            with pytest.raises(RuntimeError):
                await adapter.drive(0.04, 0, 0)
            assert len(robot.drives) == 1
            assert not (await adapter.state()).connected
        finally:
            await adapter.close()


@asynccontextmanager
async def endpoint(
    *, delay_method=None, bad_id=False, deny_acquire=False, delay_s=0.4, delayed_request=None,
    drive_snapshot=False
):
    requests = []
    headers = []

    async def handler(ws):
        headers.append(ws.request.headers["Authorization"])
        try:
            async for raw in ws:
                request = json.loads(raw)
                requests.append(request)
                method = request["method"]
                if method == delay_method:
                    if delayed_request is not None:
                        delayed_request.set()
                    await asyncio.sleep(delay_s)
                reply = {"id": "wrong" if bad_id else request["id"], "result": {}}
                if method == "state":
                    reply["result"] = {"state": snapshot(), "nonce": "fresh"}
                if method == "drive" and drive_snapshot:
                    reply["result"] = {"state": snapshot(), "nonce": "next"}
                if method == "acquire" and deny_acquire:
                    reply = {"id": request["id"], "error": "busy"}
                await ws.send(json.dumps(reply))
        except Exception:
            pass

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        adapter = IronXNetworkAdapter(f"ws://127.0.0.1:{port}", "test-token")
        await adapter.start()
        try:
            yield adapter, requests, headers
        finally:
            await adapter.close()


async def test_network_state_motion_release_and_no_local_files():
    async with endpoint() as (adapter, requests, headers):
        assert (await adapter.state()).connected
        assert headers == ["Bearer test-token"]
        await adapter.drive(0.04, 0, 0, ttl_ms=1000)
        drive = next(r for r in requests if r["method"] == "drive")
        assert 0 < drive["params"].pop("ttl_ms") <= 200
        assert drive["params"] == {"vx": 0.04, "vy": 0, "wz": 0, "nonce": "fresh"}
        await adapter.stop()
        assert requests[-1]["method"] == "release"
        assert not adapter._owned


async def test_cancelled_motion_state_read_does_not_disconnect_or_drive():
    entered = asyncio.Event()
    async with endpoint(delay_method="state", delay_s=0.1, delayed_request=entered) as (
        adapter,
        requests,
        _,
    ):
        motion = asyncio.create_task(adapter.drive(0.04, 0, 0))
        await asyncio.wait_for(entered.wait(), 1)
        motion.cancel()
        with pytest.raises(asyncio.CancelledError):
            await motion
        await adapter.stop()
        assert not adapter._failed
        assert not adapter.requires_rearm
        assert not any(r["method"] == "drive" for r in requests)
        assert requests[-1]["method"] == "release"


async def test_repeated_cancellation_waits_for_stop_confirmation():
    entered = asyncio.Event()
    async with endpoint(delay_method="release", delay_s=0.1, delayed_request=entered) as (
        adapter,
        requests,
        _,
    ):
        await adapter.drive(0.04, 0, 0)
        stopping = asyncio.create_task(adapter.stop())
        await asyncio.wait_for(entered.wait(), 1)
        stopping.cancel()
        await asyncio.sleep(0.01)
        stopping.cancel()
        assert not stopping.done()
        with pytest.raises(RuntimeError, match="stopped"):
            await adapter.drive(0.04, 0, 0)
        with pytest.raises(asyncio.CancelledError):
            await stopping
        assert not adapter._owned
        assert not adapter._failed
        assert not adapter.requires_rearm
        assert adapter._pending_stops == 0
        assert (await adapter.state()).connected
        await adapter.stop()
        assert sum(r["method"] == "release" for r in requests) == 1


async def test_cancelled_stop_timeout_still_faults(monkeypatch):
    async with endpoint(delay_method="release", delay_s=0.1) as (adapter, _, _):
        await adapter.drive(0.04, 0, 0)
        rpc = adapter._rpc
        entered = asyncio.Event()

        async def short_deadline(method, params=None, *, deadline_s=0.25):
            if method == "release":
                entered.set()
                deadline_s = 0.03
            return await rpc(method, params, deadline_s=deadline_s)

        monkeypatch.setattr(adapter, "_rpc", short_deadline)
        stopping = asyncio.create_task(adapter.stop())
        await entered.wait()
        stopping.cancel()
        with pytest.raises(TimeoutError):
            await stopping
        assert adapter._failed
        assert adapter.requires_rearm
        assert adapter._pending_stops == 0


async def test_idle_client_does_not_stop_other_owner():
    async with endpoint() as (adapter, requests, _):
        await adapter.stop()
        assert requests == []


async def test_client_lock_wait_consumes_drive_ttl():
    async with endpoint() as (adapter, requests, _):
        await adapter._command_lock.acquire()
        task = asyncio.create_task(adapter.drive(0.04, 0, 0, ttl_ms=20))
        await asyncio.sleep(0.04)
        adapter._command_lock.release()
        with pytest.raises(RuntimeError, match="expired"):
            await task
        assert not any(r["method"] == "drive" for r in requests)


async def test_timeout_latches_and_never_replays_drive():
    async with endpoint(delay_method="drive", delay_s=1.1) as (adapter, requests, _):
        with pytest.raises(TimeoutError):
            await adapter.drive(0.04, 0, 0)
        assert not (await adapter.state()).connected
        with pytest.raises(RuntimeError, match="explicitly clear stop"):
            await adapter.drive(0.04, 0, 0)
        assert len([r for r in requests if r["method"] == "drive"]) == 1
        with pytest.raises(RuntimeError, match="not confirmed"):
            await adapter.stop()


async def test_bad_response_id_marks_disconnected():
    async with endpoint(bad_id=True) as (adapter, _, _):
        assert not (await adapter.state()).connected
        assert adapter._failed


async def test_busy_robot_never_receives_drive():
    async with endpoint(deny_acquire=True) as (adapter, requests, _):
        with pytest.raises(RuntimeError, match="busy"):
            await adapter.drive(0.04, 0, 0)
        assert not any(r["method"] == "drive" for r in requests)


async def test_cancelled_status_consumer_does_not_close_connection():
    async with endpoint(delay_method="state") as (adapter, _, _):
        task = asyncio.create_task(adapter.state())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.45)
        assert not adapter._failed
        assert adapter._socket is not None


async def test_cancelled_lock_waiter_does_not_abort_other_rpc():
    async with endpoint(delay_method="state") as (adapter, _, _):
        first = asyncio.create_task(adapter._rpc("state", deadline_s=1))
        await asyncio.sleep(0.02)
        second = asyncio.create_task(adapter._rpc("state"))
        await asyncio.sleep(0.02)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        await first
        assert not adapter._failed


async def test_simultaneous_state_reads_share_one_request():
    async with endpoint(delay_method="state") as (adapter, requests, _):
        await asyncio.gather(*(adapter.state() for _ in range(8)))
        assert len(requests) == 1
        assert not adapter._failed


async def test_idle_reconnect_restores_only_telemetry():
    async with endpoint() as (adapter, requests, _):
        await adapter._socket.close()
        assert not (await adapter.state()).connected
        adapter._retry_at = 0
        assert (await adapter.state()).connected
        assert all(r["method"] == "state" for r in requests)
        assert not adapter.requires_rearm


async def test_drive_fault_reconnect_requires_explicit_rearm():
    async with endpoint(delay_method="drive", delay_s=1.1) as (adapter, requests, _):
        with pytest.raises(TimeoutError):
            await adapter.drive(0.04, 0, 0)
        adapter._retry_at = 0
        assert (await adapter.state()).connected
        assert adapter.requires_rearm
        with pytest.raises(RuntimeError):
            await adapter.drive(0.04, 0, 0)
        assert len([r for r in requests if r["method"] == "drive"]) == 1
        await adapter.clear_emergency_stop()
        assert not adapter.requires_rearm


async def test_delayed_drive_ack_does_not_extend_command_or_disconnect():
    async with endpoint(delay_method="drive", delay_s=0.3) as (adapter, requests, _):
        await adapter.drive(0.04, 0, 0)
        drives = [r for r in requests if r["method"] == "drive"]
        assert len(drives) == 1
        assert 0 < drives[0]["params"]["ttl_ms"] <= 200
        assert not adapter._failed
        assert not adapter.requires_rearm
        await adapter.stop()
        assert requests[-1]["method"] == "release"


async def test_fresh_drive_reply_saves_one_round_trip_and_stop_discards_it():
    async with endpoint(drive_snapshot=True) as (adapter, requests, _):
        await adapter.drive(0.04, 0, 0)
        await adapter.drive(0.04, 0, 0)
        assert [r["method"] for r in requests] == ["acquire", "state", "drive", "drive"]
        assert requests[-1]["params"]["nonce"] == "next"
        assert requests[-1]["params"]["ttl_ms"] <= 200
        await adapter.stop()
        assert adapter._next_drive is None
        await adapter.drive(0.04, 0, 0)
        assert [r["method"] for r in requests[-3:]] == ["acquire", "state", "drive"]


async def test_old_drive_reply_is_not_reused():
    async with endpoint(drive_snapshot=True) as (adapter, requests, _):
        await adapter.drive(0.04, 0, 0)
        await asyncio.sleep(0.11)
        await adapter.drive(0.04, 0, 0)
        assert [r["method"] for r in requests[-2:]] == ["state", "drive"]


async def test_reconnect_must_confirm_stop_even_without_ownership():
    async with endpoint(delay_method="drive", delay_s=1.1) as (adapter, requests, _):
        with pytest.raises(TimeoutError):
            await adapter.drive(0.04, 0, 0)
        assert adapter._stop_unconfirmed
        adapter._retry_at = 0
        await adapter.state()
        assert not adapter._owned
        await adapter.stop()
        assert requests[-1]["method"] == "emergency_stop"
        assert not adapter._stop_unconfirmed
        assert adapter.requires_rearm
        assert adapter._estop
        with pytest.raises(RuntimeError):
            await adapter.drive(0.04, 0, 0)


async def test_recovery_stop_timeout_cannot_claim_confirmation():
    async with endpoint(delay_method="emergency_stop", delay_s=0.1) as (adapter, _, _):
        adapter._stop_unconfirmed = True
        rpc = adapter._rpc

        async def quick(method, params=None, **kwargs):
            return await rpc(method, params, deadline_s=0.02)

        adapter._rpc = quick
        with pytest.raises(TimeoutError):
            await adapter.stop()
        assert adapter._stop_unconfirmed
        assert adapter.requires_rearm


async def test_emergency_stop_with_state_polling_keeps_connection():
    async with endpoint(delay_method="emergency_stop") as (adapter, requests, _):
        task = asyncio.create_task(adapter.emergency_stop("test"))
        await asyncio.sleep(0.02)
        await asyncio.gather(*(adapter.state() for _ in range(5)))
        await task
        assert not adapter._failed
        assert adapter._estop
        assert adapter.requires_rearm
        await adapter.clear_emergency_stop()
        assert not adapter._estop


async def test_polling_during_stop_does_not_interrupt_confirmation():
    async with endpoint(delay_method="release") as (adapter, requests, _):
        await adapter.drive(0.04, 0, 0)
        task = asyncio.create_task(adapter.stop())
        await asyncio.sleep(0.02)
        assert not (await adapter.state()).connected
        await task
        assert not adapter._failed
        assert requests[-1]["method"] == "release"


@pytest.mark.parametrize("vx,vy,wz", [(0.151, 0, 0), (0, 0.01, 0), (0, 0, 0.3)])
async def test_invalid_velocity_never_drives(vx, vy, wz):
    async with endpoint() as (adapter, requests, _):
        with pytest.raises(ValueError):
            await adapter.drive(vx, vy, wz)
        assert not any(r["method"] == "drive" for r in requests)


def test_network_configuration(tmp_path):
    config = AppConfig.from_environment(
        tmp_path,
        {
            "APRIS_ADAPTER": "ironx_network",
            "APRIS_IRONX_URL": "ws://robot:8766",
            "APRIS_IRONX_TOKEN": "secret",
        },
    )
    assert config.ironx_token.get_secret_value() == "secret"
    assert "secret" not in repr(config)
    assert config.ros2_state_file is None


@pytest.mark.parametrize("url", ["http://robot", "ws://user:pw@robot", "ws://robot/?token=x"])
def test_invalid_network_configuration(tmp_path, url):
    with pytest.raises(ValueError):
        AppConfig.from_environment(
            tmp_path,
            {
                "APRIS_ADAPTER": "ironx_network",
                "APRIS_IRONX_URL": url,
                "APRIS_IRONX_TOKEN": "secret",
            },
        )
