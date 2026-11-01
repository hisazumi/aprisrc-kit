import asyncio
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import pytest

from apris_server.adapter import BoundedMotionExecutionError, BoundedMotionGoal
from apris_server.config import AppConfig
from apris_server.ironx_adapter import IronXAdapter
from apris_server.ironx_gateway import IronXGateway, Session
from apris_server.models import Capabilities, Pose, RoverState, Velocity

scripts = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location("ironx_mailbox", scripts / "ironx_command_bridge.py")
bridge_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge_module)
sys.path.pop(0)


def adapter(tmp_path):
    return IronXAdapter(
        tmp_path / "state.json", tmp_path / "command.json", tmp_path / "bridge.json"
    )


def state(x=0, yaw=0, vx=0, wz=0):
    return RoverState(
        timestamp=time.time(),
        connected=True,
        capabilities=Capabilities(),
        pose=Pose(x=x, y=0, yaw=yaw),
        velocity=Velocity(vx=vx, vy=0, wz=wz),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("vx", [0.04, 0.15, -0.15])
async def test_drive_mailbox_expiry_and_no_renewal(tmp_path, monkeypatch, vx):
    a = adapter(tmp_path)
    lease = bridge_module.CommandLease()
    mailbox = bridge_module.FileCommands(a.command_file, lease)

    async def current(*args):
        return state()

    monkeypatch.setattr(a, "state", current)
    await a.drive(vx, 0, 0.1, ttl_ms=100)
    data = json.loads(a.command_file.read_text())
    mailbox.poll(time.monotonic())
    assert lease.output(data["monotonic"] + 0.05, True) == (vx, 0.1)
    mailbox.poll(data["monotonic"] + 0.2)
    assert lease.output(data["monotonic"] + 0.2, True) == (0, 0)
    assert mailbox.accepted_id == data["id"]


async def test_two_second_ownership_does_not_extend_mailbox_motion(tmp_path, monkeypatch):
    a = adapter(tmp_path)
    lease = bridge_module.CommandLease()
    mailbox = bridge_module.FileCommands(a.command_file, lease)

    async def current(*args):
        return state()

    async def stop_without_physical_feedback():
        a._write(0, 0, 200)

    monkeypatch.setattr(a, "state", current)
    monkeypatch.setattr(a, "stop", stop_without_physical_feedback)
    now = [time.monotonic()]
    gateway = IronXGateway(a, "test-token", clock=lambda: now[0])
    await gateway.initialize()
    owner = Session()
    nonce = (await gateway.dispatch(owner, "acquire", {}))["nonce"]
    await gateway.dispatch(owner, "drive", {
        "nonce": nonce, "vx": 0.10, "vy": 0, "wz": 0, "ttl_ms": 200,
    })
    data = json.loads(a.command_file.read_text())
    assert 0 < data["ttl_ms"] <= 200
    mailbox.poll(time.monotonic())
    assert lease.output(data["monotonic"] + 0.01, True) == (0.10, 0)
    assert lease.output(data["monotonic"] + 0.21, True) == (0, 0)
    now[0] += 0.4
    await gateway.expire()
    assert gateway.owner is owner
    mailbox.poll(data["monotonic"] + 0.4)
    assert lease.output(data["monotonic"] + 0.4, True) == (0, 0)


@pytest.mark.parametrize("case", ["startup", "future", "expired", "nan", "invalid", "ttl"])
def test_mailbox_rejects_bad_commands(tmp_path, case):
    path = tmp_path / "cmd"
    lease = bridge_module.CommandLease()
    mailbox = bridge_module.FileCommands(path, lease)
    data = dict(id="a", monotonic=time.monotonic(), ttl_ms=200, vx=0.05, wz=0)
    if case == "startup":
        data["monotonic"] = mailbox.started - 1
    if case == "future":
        data["monotonic"] += 1
    if case == "expired":
        data["monotonic"] -= 1
    if case == "nan":
        data["vx"] = float("nan")
    if case == "ttl":
        data["ttl_ms"] = 1000
    path.write_text("{" if case == "invalid" else json.dumps(data))
    mailbox.poll(time.monotonic())
    assert lease.output(time.monotonic(), True) == (0, 0)
    assert mailbox.accepted_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vx,vy,wz", [(0.151, 0, 0), (0, 0.01, 0), (0, 0, 0.3), (float("nan"), 0, 0)]
)
async def test_invalid_drive_writes_zero(tmp_path, vx, vy, wz):
    a = adapter(tmp_path)
    with pytest.raises(ValueError):
        await a.drive(vx, vy, wz)
    assert json.loads(a.command_file.read_text())["vx"] == 0


@pytest.mark.asyncio
async def test_missing_bridge_fails_closed(tmp_path):
    a = adapter(tmp_path)
    await a.start()
    assert not (await a.state()).connected
    with pytest.raises(RuntimeError):
        await a.drive(0.01, 0, 0)
    with pytest.raises(RuntimeError):
        await a.close()
    assert not a.running
    assert a._lock is None


@pytest.mark.asyncio
async def test_single_mailbox_owner(tmp_path):
    a, b = adapter(tmp_path), adapter(tmp_path)
    await a.start()
    with pytest.raises(RuntimeError, match="owns"):
        await b.start()
    with pytest.raises(RuntimeError):
        await a.close()


@pytest.mark.asyncio
async def test_stop_waits_for_ack_and_multiple_stationary_observations(tmp_path, monkeypatch):
    a = adapter(tmp_path)
    calls = []

    async def current(*args):
        calls.append(1)
        return state(vx=0.04 if len(calls) < 3 else 0)

    monkeypatch.setattr(a, "state", current)
    monkeypatch.setattr(
        a,
        "_bridge",
        lambda: dict(command_id=json.loads(a.command_file.read_text())["id"], vx=0, wz=0),
    )
    await a.stop()
    assert len(calls) >= 6


def goal(kind="linear", target=0.03):
    return BoundedMotionGoal(
        "test",
        kind,
        target if kind == "linear" else None,
        target if kind == "rotate" else None,
        0.05,
        0.2,
        2000,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,target", [("linear", 0.03), ("linear", -0.03), ("rotate", 0.15), ("rotate", -0.15)]
)
async def test_bounded_motion_stops_before_completion(tmp_path, monkeypatch, kind, target):
    a = adapter(tmp_path)
    position = [0.0]
    commands = []
    stopped = []

    async def current(*args):
        return state(
            x=position[0] if kind == "linear" else 0, yaw=position[0] if kind == "rotate" else 0
        )

    async def drive(vx, vy, wz, **kwargs):
        commands.append((vx, wz))
        position[0] += math.copysign(
            0.01 if kind == "linear" else 0.04, vx if kind == "linear" else wz
        )

    async def stop():
        stopped.append(True)

    monkeypatch.setattr(a, "state", current)
    monkeypatch.setattr(a, "drive", drive)
    monkeypatch.setattr(a, "stop", stop)
    result = await a.execute_bounded_motion(goal(kind, target))
    assert result.status == "completed" and stopped and commands
    assert all(abs(vx) <= 0.05 and abs(wz) <= 0.2 for vx, wz in commands)


@pytest.mark.asyncio
async def test_cancellation_stops(tmp_path, monkeypatch):
    a = adapter(tmp_path)
    stopped = []

    async def current(*args):
        return state()

    async def drive(*args, **kwargs):
        await asyncio.sleep(10)

    async def stop():
        stopped.append(True)

    monkeypatch.setattr(a, "state", current)
    monkeypatch.setattr(a, "drive", drive)
    monkeypatch.setattr(a, "stop", stop)
    task = asyncio.create_task(a.execute_bounded_motion(goal()))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped and not a._busy


@pytest.mark.asyncio
async def test_stop_failure_never_completes(tmp_path, monkeypatch):
    a = adapter(tmp_path)

    async def current(*args):
        return state()

    async def stop():
        raise TimeoutError("stop not confirmed")

    monkeypatch.setattr(a, "state", current)
    monkeypatch.setattr(a, "stop", stop)
    with pytest.raises(BoundedMotionExecutionError, match="stop unconfirmed"):
        await a.execute_bounded_motion(goal(target=0))


def test_config_requires_distinct_local_paths(tmp_path):
    env = dict(
        APRIS_ADAPTER="ironx",
        APRIS_ROS2_STATE_FILE=str(tmp_path / "state"),
        APRIS_IRONX_COMMAND_FILE=str(tmp_path / "cmd"),
        APRIS_IRONX_BRIDGE_STATE_FILE=str(tmp_path / "bridge"),
    )
    assert AppConfig.from_environment(tmp_path, env).adapter_type == "ironx"
    with pytest.raises(ValueError):
        AppConfig.from_environment(tmp_path, dict(env, APRIS_DEPLOYMENT_PROFILE="hosted"))
    with pytest.raises(ValueError):
        AppConfig.from_environment(
            tmp_path, dict(env, APRIS_IRONX_COMMAND_FILE=env["APRIS_ROS2_STATE_FILE"])
        )
