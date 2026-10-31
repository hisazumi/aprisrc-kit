import asyncio
import contextlib
import json

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from apris_server.ironx_gateway import IronXGateway, Session, parse_args
from apris_server.models import Capabilities, Pose, RoverState, Velocity


class FakeAdapter:
    def __init__(self):
        self.stops = 0
        self.drives = []
        self.fail_stop = False
        self.fail_drive = False
        self.stop_gate = None
        self.drive_gate = None
        self.drive_started = asyncio.Event()
        self.stop_started = asyncio.Event()
        self.stop_confirmed = asyncio.Event()
        self.estopped = False

    async def state(self):
        return RoverState(
            timestamp=123,
            connected=True,
            capabilities=Capabilities(),
            pose=Pose(x=0, y=0, yaw=0),
            velocity=Velocity(vx=0, vy=0, wz=0),
        )

    async def drive(self, vx, vy, wz, *, ttl_ms):
        self.drive_started.set()
        if self.drive_gate:
            await self.drive_gate.wait()
        if self.fail_drive:
            raise RuntimeError("drive failed")
        self.drives.append((vx, vy, wz, ttl_ms))

    async def stop(self):
        self.stops += 1
        self.stop_started.set()
        if self.stop_gate:
            await self.stop_gate.wait()
        if self.fail_stop:
            raise TimeoutError("stop failed")
        self.stop_confirmed.set()

    async def emergency_stop(self, reason):
        self.estopped = True
        await self.stop()

    async def clear_emergency_stop(self):
        await self.stop()
        self.estopped = False


@pytest.fixture
async def setup():
    adapter = FakeAdapter()
    now = [10.0]
    gateway = IronXGateway(adapter, "test-token", clock=lambda: now[0])
    await gateway.initialize()
    adapter.stop_started.clear()
    return gateway, adapter, now, Session(), Session()


async def rpc(gateway, session, method, **params):
    return await gateway.respond(session, json.dumps(dict(id=1, method=method, params=params)))


def drive_params(nonce, **extra):
    return dict(nonce=nonce, vx=0.02, vy=0, wz=0.1, ttl_ms=300) | extra


async def acquire(gateway, session):
    return (await rpc(gateway, session, "acquire"))["result"]["nonce"]


async def test_multiple_nonces_single_use_and_ttl(setup):
    g, a, now, owner, _ = setup
    first = await acquire(g, owner)
    second = (await rpc(g, owner, "state"))["result"]["nonce"]
    now[0] += 0.1
    assert "result" in await rpc(g, owner, "drive", **drive_params(first))
    assert 198 <= a.drives[-1][3] <= 200
    assert "result" in await rpc(g, owner, "drive", **drive_params(second))
    assert (await rpc(g, owner, "drive", **drive_params(first)))["error"]["code"] == (
        "invalid_nonce"
    )
    assert g.owner is None


async def test_short_ttl_expires_even_while_nonce_is_fresh(setup):
    g, a, now, owner, _ = setup
    nonce = await acquire(g, owner)
    now[0] += 0.12
    result = await rpc(g, owner, "drive", **drive_params(nonce, ttl_ms=50))
    assert "error" in result
    assert a.drives == []
    assert g.owner is None


async def test_owner_isolation_and_nonowner_stop(setup):
    g, a, _, owner, other = setup
    nonce = await acquire(g, owner)
    assert "error" in await rpc(g, other, "acquire")
    assert "error" in await rpc(g, other, "drive", **drive_params(nonce))
    assert "error" in await rpc(g, other, "release")
    assert "error" in await rpc(g, other, "clear_emergency_stop")
    assert (await rpc(g, other, "stop"))["result"] is None
    assert a.stops == 1 and g.owner is owner


async def test_state_and_reacquire_do_not_renew_lease(setup):
    g, a, now, owner, other = setup
    await acquire(g, owner)
    deadline = g.deadline
    for _ in range(3):
        now[0] += 0.09
        await rpc(g, owner, "state")
        await acquire(g, owner)
        assert g.deadline == deadline
    now[0] += 0.04
    await g.expire()
    assert g.owner is None and a.stops == 2
    assert "result" in await rpc(g, other, "acquire")


@pytest.mark.parametrize("operation", ["release", "disconnect", "expire"])
async def test_reacquire_waits_for_confirmed_stop(setup, operation):
    g, a, now, owner, other = setup
    await acquire(g, owner)
    a.stop_gate = asyncio.Event()
    if operation == "release":
        task = asyncio.create_task(rpc(g, owner, "release"))
    elif operation == "disconnect":
        task = asyncio.create_task(g.disconnect(owner))
    else:
        now[0] += 0.31
        task = asyncio.create_task(g.expire())
    await a.stop_started.wait()
    assert (await rpc(g, other, "acquire"))["error"]["code"] == "stopping"
    state = (await rpc(g, other, "state"))["result"]["state"]
    assert not state["connected"]
    assert "gateway_stopping" in state["pose_quality"]["anomalies"]
    a.stop_gate.set()
    await task
    assert "result" in await rpc(g, other, "acquire")


async def test_stop_failure_latches_and_state_reports_fault(setup):
    g, a, _, owner, other = setup
    await acquire(g, owner)
    a.fail_stop = True
    assert (await rpc(g, owner, "release"))["error"]["code"] == "stop_unconfirmed"
    a.fail_stop = False
    assert "error" in await rpc(g, other, "acquire")
    assert "error" in await rpc(g, other, "clear_emergency_stop")
    state = (await rpc(g, other, "state"))["result"]["state"]
    assert not state["connected"]
    assert "gateway_stop_unconfirmed" in state["pose_quality"]["anomalies"]


async def test_emergency_any_client_clear_only_without_other_owner(setup):
    g, a, _, owner, other = setup
    old = await acquire(g, owner)
    assert "result" in await rpc(g, other, "emergency_stop", reason="test")
    assert a.estopped and g.owner is None
    assert not (await rpc(g, owner, "state"))["result"]["state"]["connected"]
    assert "result" in await rpc(g, other, "clear_emergency_stop")
    assert not a.estopped
    await acquire(g, owner)
    assert "error" in await rpc(g, owner, "drive", **drive_params(old))


async def test_stop_bypasses_inflight_drive(setup):
    g, a, _, owner, _ = setup
    nonce = await acquire(g, owner)
    a.drive_gate = asyncio.Event()
    drive = asyncio.create_task(rpc(g, owner, "drive", **drive_params(nonce)))
    await a.drive_started.wait()
    result = await asyncio.wait_for(rpc(g, owner, "release"), 0.5)
    assert "result" in result
    assert (await drive)["error"]["code"] == "superseded"
    assert not a.drives and g.owner is None


async def test_failed_drive_does_not_renew(setup):
    g, a, now, owner, _ = setup
    nonce = await acquire(g, owner)
    deadline = g.deadline
    now[0] += 0.1
    a.fail_drive = True
    assert "error" in await rpc(g, owner, "drive", **drive_params(nonce))
    assert g.deadline == deadline and g.owner is None and a.stops == 2


async def test_expired_nonce_even_with_newer_successful_drive(setup):
    g, a, now, owner, _ = setup
    old = await acquire(g, owner)
    now[0] += 0.2
    fresh = (await rpc(g, owner, "state"))["result"]["nonce"]
    await rpc(g, owner, "drive", **drive_params(fresh))
    now[0] += 0.11
    assert (await rpc(g, owner, "drive", **drive_params(old)))["error"]["code"] == ("expired_nonce")
    assert len(a.drives) == 1


@pytest.mark.parametrize(
    "extra",
    [{"vx": True}, {"vy": 1}, {"wz": 1}, {"ttl_ms": 0}, {"vx": float("nan")}, {"vx": 0.151}],
)
async def test_invalid_drive_fails_closed(setup, extra):
    g, a, _, owner, _ = setup
    nonce = await acquire(g, owner)
    assert "error" in await rpc(g, owner, "drive", **drive_params(nonce, **extra))
    assert not a.drives and g.owner is None


@pytest.mark.parametrize(
    "raw", ["{", "[]", '{"id":true,"method":"state"}', '{"id":1,"method":"state","params":[]}']
)
async def test_invalid_requests(setup, raw):
    g, _, _, owner, _ = setup
    assert "error" in await g.respond(owner, raw)


async def test_no_bounded_motion_endpoint(setup):
    g, _, _, owner, _ = setup
    assert (await rpc(g, owner, "execute_bounded_motion"))["error"]["code"] == ("method_not_found")


async def test_startup_stop_failure_prevents_acquire():
    adapter = FakeAdapter()
    adapter.fail_stop = True
    gateway = IronXGateway(adapter, "test-token")
    with pytest.raises(TimeoutError):
        await gateway.initialize()
    assert "error" in await rpc(gateway, Session(), "acquire")


async def test_nonce_cannot_cross_connections(setup):
    g, a, _, owner, other = setup
    await acquire(g, owner)
    nonce = (await rpc(g, other, "state"))["result"]["nonce"]
    assert (await rpc(g, owner, "drive", **drive_params(nonce)))["error"]["code"] == (
        "invalid_nonce"
    )
    assert not a.drives


async def test_disconnect_waits_for_inflight_release(setup):
    g, a, _, owner, _ = setup
    await acquire(g, owner)
    a.stop_gate = asyncio.Event()
    release = asyncio.create_task(rpc(g, owner, "release"))
    await a.stop_started.wait()
    disconnect = asyncio.create_task(g.disconnect(owner))
    await asyncio.sleep(0)
    assert not disconnect.done()
    a.stop_gate.set()
    await asyncio.gather(release, disconnect)
    assert not g.fault


def test_cli_requires_token_and_distinct_files(monkeypatch):
    monkeypatch.setenv("APRIS_IRONX_GATEWAY_TOKEN", "test")
    for key, value in (
        ("APRIS_ROS2_STATE_FILE", "/tmp/state"),
        ("APRIS_IRONX_COMMAND_FILE", "/tmp/command"),
        ("APRIS_IRONX_BRIDGE_STATE_FILE", "/tmp/bridge"),
    ):
        monkeypatch.setenv(key, value)
    assert parse_args([]).port == 8766
    assert parse_args([]).host == "127.0.0.1"
    with pytest.raises(SystemExit):
        parse_args(["--command-file", "/tmp/state"])
    monkeypatch.delenv("APRIS_IRONX_GATEWAY_TOKEN")
    with pytest.raises(SystemExit):
        parse_args([])


async def test_websocket_auth_protocol_watchdog_and_disconnect():
    adapter = FakeAdapter()
    gateway = IronXGateway(adapter, "test-token")
    await gateway.initialize()
    watcher = asyncio.create_task(gateway.watchdog())
    try:
        async with serve(
            gateway.handler, "127.0.0.1", 0, process_request=gateway.authenticate
        ) as server:
            uri = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                with pytest.raises(InvalidStatus) as error:
                    async with connect(uri, additional_headers=headers):
                        pass
                assert error.value.response.status_code == 401
            headers = {"Authorization": "Bearer test-token"}

            async def call(ws, method, **params):
                await ws.send(json.dumps(dict(id="wire", method=method, params=params)))
                response = json.loads(await ws.recv())
                assert response["id"] == "wire"
                return response

            async with connect(uri, additional_headers=headers) as ws:
                nonce = (await call(ws, "acquire"))["result"]["nonce"]
                await call(ws, "state")
                assert "result" in await call(ws, "drive", **drive_params(nonce))
                async with connect(uri, additional_headers=headers) as other:
                    assert "error" in await call(other, "acquire")
                    assert "result" in await call(other, "stop")
                    assert gateway.owner is not None
                for _ in range(8):
                    await call(ws, "state")
                    await asyncio.sleep(0.05)
                assert gateway.owner is None and adapter.stops >= 2
                await call(ws, "acquire")
                adapter.stop_confirmed.clear()
            await asyncio.wait_for(adapter.stop_confirmed.wait(), 1)
            assert gateway.owner is None
            assert adapter.stops >= 3
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher
