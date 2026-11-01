import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from apris_server.front_obstacle import FrontObstacleObservationInput
from apris_server.models import DriveCommand, MoveCommand, TurnCommand
from apris_server.runtime import RoverRuntime, RuntimeConfig
from apris_server.simulator import DifferentialDriveSimulator, SimulatorConfig, SimulatorFaults


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["stop", "release", "disconnect", "clearance"])
async def test_operator_stop_failure_latches_without_dropping_cleanup(action):
    adapter = DifferentialDriveSimulator()
    adapter.stop = AsyncMock(side_effect=RuntimeError("connection lost"))
    runtime = RoverRuntime(adapter)
    runtime.owner_client_id = "operator"
    runtime.command_deadline = 123
    runtime.last_command_at = 100
    runtime.broadcast = AsyncMock()
    runtime._broadcast_control = AsyncMock()
    runtime._revoke_path_clearance = AsyncMock()
    if action == "stop":
        await runtime._stop("operator", "test")
    elif action == "release":
        await runtime._release_control("operator")
    elif action == "disconnect":
        await runtime.remove_client("operator")
    else:
        runtime._commanded_vx = 0.1
        await runtime._enforce_front_obstacle(await runtime.front_obstacle_snapshot())
    assert runtime.estop_latched
    assert runtime.command_deadline is None
    assert runtime.last_command_at is None
    events = [call.args[0] for call in runtime.broadcast.call_args_list]
    assert any(event.event == "stop_unconfirmed" for event in events)
    assert not any(event.event in ("stopped", "forward_motion_stopped")
                   or event.detail == "Rover stopped" for event in events)
    if action in ("release", "disconnect"):
        assert runtime.owner_client_id is None
        runtime._revoke_path_clearance.assert_awaited_once()


class DisconnectingClientSocket:
    def __init__(self) -> None:
        self.disconnected = False

    async def send_text(self, message: str) -> None:
        del message
        if self.disconnected:
            raise WebSocketDisconnect()


class FailingDriveSimulator(DifferentialDriveSimulator):
    def __init__(self) -> None:
        super().__init__()
        self.stop_calls = 0

    async def drive(
        self,
        vx: float,
        vy: float,
        wz: float,
        *,
        ttl_ms: int = 500,
    ) -> None:
        del vx, vy, wz, ttl_ms
        raise ConnectionResetError("ambiguous adapter command failure")

    async def stop(self) -> None:
        self.stop_calls += 1
        await super().stop()


class FailingStopOnceSimulator(DifferentialDriveSimulator):
    def __init__(self) -> None:
        super().__init__(SimulatorConfig(update_hz=200.0))
        self.fail_next_stop = True
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1
        if self.fail_next_stop:
            self.fail_next_stop = False
            raise TimeoutError("stop acknowledgement timed out")
        await super().stop()


async def set_front_clear(runtime: RoverRuntime) -> None:
    await runtime.ingest_front_obstacle(
        FrontObstacleObservationInput(
            state="CLEAR",
            perception_health="healthy",
            source="manual",
            confidence=1.0,
        )
    )


@pytest.mark.asyncio
async def test_speed_is_clamped_and_ttl_stops_rover() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=100.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(max_vx=0.3, max_wz=1.2, safety_hz=100.0, state_hz=20.0),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await set_front_clear(runtime)
        await runtime._drive(
            "test-client",
            DriveCommand(type="drive", vx=4.0, vy=0.0, wz=5.0, ttl_ms=100, seq=1),
        )
        moving = await simulator.state()
        assert moving.velocity.vx == pytest.approx(0.3)
        assert moving.velocity.wz == pytest.approx(1.2)

        await asyncio.sleep(0.16)
        stopped = await simulator.state()
        assert stopped.velocity.vx == 0.0
        assert stopped.velocity.wz == 0.0
        assert runtime.last_command_at is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_estop_is_latched() -> None:
    simulator = DifferentialDriveSimulator()
    runtime = RoverRuntime(simulator)
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await runtime._estop("test")
        await runtime._drive(
            "test-client",
            DriveCommand(type="drive", vx=0.2, vy=0.0, wz=0.0, ttl_ms=500, seq=1),
        )
        assert (await simulator.state()).velocity.vx == 0.0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_emergency_stop_and_reset_keep_local_latch(monkeypatch) -> None:
    simulator = DifferentialDriveSimulator()
    runtime = RoverRuntime(simulator)
    runtime.owner_client_id = "test-client"

    async def unavailable(*args):
        raise ConnectionError("offline")

    monkeypatch.setattr(simulator, "emergency_stop", unavailable)
    monkeypatch.setattr(simulator, "clear_emergency_stop", unavailable)
    await runtime._estop("test disconnect")
    assert runtime.estop_latched
    await runtime._clear_estop("test-client")
    assert runtime.estop_latched
    assert runtime.command_deadline is None


async def wait_for_motion(runtime: RoverRuntime) -> None:
    task = runtime._motion_task
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), timeout=3.0)


@pytest.mark.asyncio
async def test_move_and_turn_use_pose_feedback() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(
            safety_hz=200.0,
            state_hz=50.0,
            motion_hz=100.0,
            move_tolerance_m=0.004,
            turn_tolerance_rad=0.008,
        ),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await set_front_clear(runtime)
        await runtime._start_move(
            "test-client",
            MoveCommand(
                type="move",
                request_id="move-1",
                distance_m=0.06,
                speed_mps=0.30,
            ),
        )
        await wait_for_motion(runtime)
        after_move = await simulator.state()
        assert after_move.pose.x == pytest.approx(0.06, abs=0.012)
        assert after_move.velocity.vx == 0.0

        await runtime._start_turn(
            "test-client",
            TurnCommand(
                type="turn",
                request_id="turn-1",
                angle_deg=15.0,
                speed_rad_s=1.20,
            ),
        )
        await wait_for_motion(runtime)
        after_turn = await simulator.state()
        assert after_turn.pose.yaw == pytest.approx(0.262, abs=0.025)
        assert after_turn.velocity.wz == 0.0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_stop_cancels_active_motion() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(safety_hz=200.0, state_hz=50.0, motion_hz=100.0),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await set_front_clear(runtime)
        await runtime._start_move(
            "test-client",
            MoveCommand(
                type="move",
                request_id="move-long",
                distance_m=1.0,
                speed_mps=0.30,
            ),
        )
        await asyncio.sleep(0.06)
        await runtime._stop("test-client", "test stop")

        assert runtime._motion_task is None
        stopped = await simulator.state()
        assert stopped.velocity.vx == 0.0
        assert stopped.pose.x < 0.10
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_dropped_drive_command_still_expires_safely() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(safety_hz=200.0, state_hz=50.0),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await set_front_clear(runtime)
        await simulator.set_faults(SimulatorFaults(drop_next_commands=1))
        await runtime._drive(
            "test-client",
            DriveCommand(type="drive", vx=0.2, vy=0.0, wz=0.0, ttl_ms=100, seq=1),
        )
        assert (await simulator.state()).velocity.vx == 0.0

        await asyncio.sleep(0.15)
        assert runtime.last_command_at is None
        assert (await simulator.state()).velocity.vx == 0.0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_readiness_fails_when_motion_critical_loop_stops() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=100.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(safety_hz=100.0, state_hz=100.0),
    )
    await runtime.start()
    try:
        assert (await runtime.status())["ready"] is True
        task = runtime._tasks["state"]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        status = await runtime.status()
        assert status["ready"] is False
        assert status["loops"]["state"]["running"] is False
        assert status["loops"]["state"]["error"] == "loop cancelled unexpectedly"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_disconnected_client_does_not_stop_state_broadcast_loop() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=100.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(safety_hz=100.0, state_hz=100.0),
    )
    socket = DisconnectingClientSocket()
    await runtime.start()
    client_id = await runtime.add_client(socket)
    try:
        socket.disconnected = True
        await asyncio.sleep(0.03)

        status = await runtime.status()
        assert status["ready"] is True
        assert status["loops"]["state"]["running"] is True
        assert status["loops"]["state"]["error"] is None
    finally:
        await runtime.remove_client(client_id)
        await runtime.close()


@pytest.mark.asyncio
async def test_drive_transport_failure_stops_and_does_not_escape_runtime() -> None:
    adapter = FailingDriveSimulator()
    runtime = RoverRuntime(adapter)
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await runtime._drive(
            "test-client",
            DriveCommand(type="drive", vx=-0.05, vy=0.0, wz=0.0, ttl_ms=300, seq=1),
        )

        assert adapter.stop_calls == 1
        assert runtime.last_sequence == 1
        assert runtime.last_command_at is None
        assert runtime.command_deadline is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_safety_loop_recovers_after_stop_transport_failure() -> None:
    adapter = FailingStopOnceSimulator()
    runtime = RoverRuntime(
        adapter,
        RuntimeConfig(safety_hz=100.0, state_hz=100.0),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await runtime._drive(
            "test-client",
            DriveCommand(type="drive", vx=-0.05, vy=0.0, wz=0.0, ttl_ms=100, seq=1),
        )

        async with asyncio.timeout(1.0):
            while True:
                status = await runtime.status()
                safety = status["loops"]["safety"]
                if safety["restart_count"] == 1 and safety["healthy"]:
                    break
                await asyncio.sleep(0.01)

        assert adapter.stop_calls >= 2
        assert status["ready"] is True
        assert safety["running"] is True
        assert safety["error"] is None
    finally:
        await runtime.close()
