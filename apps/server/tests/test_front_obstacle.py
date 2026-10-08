from __future__ import annotations

import asyncio
import json

import pytest

from apris_server.front_obstacle import FrontObstacleObservationInput, FrontObstacleStateStore
from apris_server.models import DriveCommand, MoveCommand, TurnCommand
from apris_server.runtime import RoverRuntime, RuntimeConfig
from apris_server.simulator import DifferentialDriveSimulator, SimulatorConfig


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[dict] = asyncio.Queue()

    async def send_text(self, raw: str) -> None:
        await self.messages.put(json.loads(raw))


class NoisyTurnSimulator(DifferentialDriveSimulator):
    """Reports spurious forward velocity while retaining the real turn state."""

    def __init__(self, config: SimulatorConfig) -> None:
        super().__init__(config)
        self.stop_calls = 0

    async def state(self, command_age_ms: float | None = None):
        state = await super().state(command_age_ms)
        if state.velocity.wz == 0.0:
            return state
        return state.model_copy(
            update={
                "velocity": state.velocity.model_copy(update={"vx": 0.18}),
            }
        )

    async def stop(self) -> None:
        self.stop_calls += 1
        await super().stop()


def observation(
    state: str,
    health: str = "healthy",
) -> FrontObstacleObservationInput:
    return FrontObstacleObservationInput.model_validate(
        {
            "state": state,
            "perception_health": health,
            "source": "manual",
            "confidence": 1.0,
        }
    )


def test_front_obstacle_starts_unknown_and_requires_fresh_healthy_clear() -> None:
    store = FrontObstacleStateStore(stale_after_s=0.05)
    initial = store.snapshot(now=100.0)
    assert initial.state == "UNKNOWN"
    assert initial.perception_health == "unavailable"
    assert initial.stale is True

    clear = store.observe(observation("CLEAR"), received_at=100.0)
    assert clear.state == "CLEAR"
    assert clear.stale is False
    assert store.snapshot(now=100.06).state == "UNKNOWN"


def test_blocked_latches_until_fresh_clear_and_explicit_reason() -> None:
    store = FrontObstacleStateStore(stale_after_s=1.0)
    blocked = store.observe(observation("BLOCKED"), received_at=100.0)
    assert blocked.state == "BLOCKED"
    assert blocked.latched is True

    still_blocked = store.observe(observation("CLEAR"), received_at=100.1)
    assert still_blocked.observed_state == "CLEAR"
    assert still_blocked.state == "BLOCKED"
    assert still_blocked.latched is True

    cleared = store.clear_latch("operator verified path", now=100.2)
    assert cleared.state == "CLEAR"
    assert cleared.latched is False
    assert cleared.clear_reason == "operator verified path"


@pytest.mark.asyncio
async def test_unknown_rejects_forward_but_allows_turn() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(safety_hz=200.0, state_hz=50.0, motion_hz=100.0),
    )
    socket = CaptureSocket()
    client_id = await runtime.add_client(socket)
    runtime.owner_client_id = client_id
    await runtime.start()
    try:
        await runtime._start_move(
            client_id,
            MoveCommand(type="move", request_id="move-unknown", distance_m=0.1),
        )
        terminal = await socket.messages.get()
        while terminal.get("type") != "motion":
            terminal = await socket.messages.get()
        assert terminal["status"] == "failed"
        assert "front_obstacle_unknown" in terminal["detail"]
        assert runtime._motion_task is None

        await runtime._start_turn(
            client_id,
            TurnCommand(type="turn", request_id="turn-allowed", angle_deg=10.0),
        )
        task = runtime._motion_task
        assert task is not None
        await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
        assert (await simulator.state()).pose.yaw > 0.1
    finally:
        await runtime.remove_client(client_id)
        await runtime.close()


@pytest.mark.asyncio
async def test_owner_path_clearance_is_revoked_when_control_is_released() -> None:
    runtime = RoverRuntime(DifferentialDriveSimulator())
    socket = CaptureSocket()
    client_id = await runtime.add_client(socket)
    await runtime.handle_text(
        client_id,
        json.dumps(
            {
                "v": 1,
                "type": "client_hello",
                "client_kind": "service_app",
                "device_id": "phone-1",
                "session_id": "session-1",
                "app_version": "0.1.0",
                "build_id": "test",
            }
        ),
    )
    await runtime.handle_text(client_id, '{"v":1,"type":"acquire_control"}')

    await runtime.handle_text(
        client_id,
        '{"v":1,"type":"path_clearance","confirmed":true}',
    )
    clear = await runtime.front_obstacle_snapshot()
    assert clear.state == "CLEAR"
    assert clear.source == "manual"

    await runtime.handle_text(client_id, '{"v":1,"type":"release_control"}')
    revoked = await runtime.front_obstacle_snapshot()
    assert revoked.state == "UNKNOWN"
    assert revoked.perception_health == "unavailable"

    await runtime.handle_text(client_id, '{"v":1,"type":"acquire_control"}')
    await runtime.handle_text(
        client_id,
        '{"v":1,"type":"path_clearance","confirmed":true}',
    )
    await runtime.remove_client(client_id)
    disconnected = await runtime.front_obstacle_snapshot()
    assert disconnected.state == "UNKNOWN"
    await runtime.close()


@pytest.mark.asyncio
async def test_owner_path_clearance_expires_without_heartbeat() -> None:
    runtime = RoverRuntime(
        DifferentialDriveSimulator(),
        RuntimeConfig(safety_hz=200.0, path_clearance_ttl_s=0.05),
    )
    socket = CaptureSocket()
    await runtime.start()
    client_id = await runtime.add_client(socket)
    try:
        await runtime.handle_text(
            client_id,
            json.dumps(
                {
                    "v": 1,
                    "type": "client_hello",
                    "client_kind": "service_app",
                    "device_id": "phone-1",
                    "session_id": "session-1",
                    "app_version": "0.1.0",
                    "build_id": "test",
                }
            ),
        )
        await runtime.handle_text(client_id, '{"v":1,"type":"acquire_control"}')
        await runtime.handle_text(
            client_id,
            '{"v":1,"type":"path_clearance","confirmed":true}',
        )
        assert (await runtime.front_obstacle_snapshot()).state == "CLEAR"

        await asyncio.sleep(0.1)

        expired = await runtime.front_obstacle_snapshot()
        assert expired.state == "UNKNOWN"
        assert expired.perception_health == "unavailable"
    finally:
        await runtime.remove_client(client_id)
        await runtime.close()


@pytest.mark.asyncio
async def test_unknown_does_not_stop_turn_for_spurious_forward_telemetry() -> None:
    simulator = NoisyTurnSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(safety_hz=200.0, state_hz=50.0),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        baseline_stop_calls = simulator.stop_calls
        await runtime._drive(
            "test-client",
            DriveCommand(type="drive", vx=0.0, wz=0.5, ttl_ms=500, seq=1),
        )
        await asyncio.sleep(0.03)

        assert simulator.stop_calls == baseline_stop_calls
        assert (await simulator.state()).velocity.wz == pytest.approx(0.5)
        assert runtime.command_deadline is not None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_blocked_during_forward_stops_and_reports_run_continuable_reason() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(
            safety_hz=200.0,
            state_hz=50.0,
            motion_hz=100.0,
            front_obstacle_stale_after_s=2.0,
        ),
    )
    socket = CaptureSocket()
    client_id = await runtime.add_client(socket)
    runtime.owner_client_id = client_id
    await runtime.start()
    try:
        await runtime.ingest_front_obstacle(observation("CLEAR"))
        await runtime._start_move(
            client_id,
            MoveCommand(
                type="move",
                request_id="move-blocked",
                run_id="run-1",
                effect_id="effect-1",
                distance_m=1.0,
                speed_mps=0.30,
            ),
        )
        await asyncio.sleep(0.08)
        await runtime.ingest_front_obstacle(observation("BLOCKED"))

        terminal = None
        while terminal is None:
            message = await asyncio.wait_for(socket.messages.get(), timeout=1.0)
            if message.get("type") == "motion" and message.get("status") == "cancelled":
                terminal = message
        assert terminal["detail"] == "front_obstacle_blocked"
        assert terminal["run_id"] == "run-1"
        assert terminal["effect_id"] == "effect-1"
        state = await simulator.state()
        assert state.velocity.vx == 0.0
        assert state.pose.x < 0.1
        snapshot = await runtime.front_obstacle_snapshot()
        assert snapshot.state == "BLOCKED"
        assert snapshot.latched is True
    finally:
        await runtime.remove_client(client_id)
        await runtime.close()


@pytest.mark.asyncio
async def test_stale_clear_becomes_unknown_and_stops_forward() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(
            safety_hz=200.0,
            state_hz=50.0,
            motion_hz=100.0,
            front_obstacle_stale_after_s=0.05,
        ),
    )
    socket = CaptureSocket()
    client_id = await runtime.add_client(socket)
    runtime.owner_client_id = client_id
    await runtime.start()
    try:
        await runtime.ingest_front_obstacle(observation("CLEAR"))
        await runtime._start_move(
            client_id,
            MoveCommand(
                type="move",
                request_id="move-stale",
                distance_m=1.0,
                speed_mps=0.30,
            ),
        )
        terminal = None
        while terminal is None:
            message = await asyncio.wait_for(socket.messages.get(), timeout=1.0)
            if message.get("type") == "motion" and message.get("status") == "cancelled":
                terminal = message
        assert terminal["detail"] == "front_obstacle_unknown"
        snapshot = await runtime.front_obstacle_snapshot()
        assert snapshot.state == "UNKNOWN"
        assert snapshot.stale is True
        assert (await simulator.state()).velocity.vx == 0.0
    finally:
        await runtime.remove_client(client_id)
        await runtime.close()


@pytest.mark.asyncio
async def test_blocked_transition_stops_manual_forward_and_clears_ttl() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    runtime = RoverRuntime(
        simulator,
        RuntimeConfig(safety_hz=200.0, state_hz=50.0),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await runtime.ingest_front_obstacle(observation("CLEAR"))
        await runtime._drive(
            "test-client",
            DriveCommand(type="drive", vx=0.2, wz=0.0, ttl_ms=500, seq=1),
        )
        assert (await simulator.state()).velocity.vx > 0
        assert runtime.command_deadline is not None

        await runtime.ingest_front_obstacle(observation("BLOCKED"))
        assert (await simulator.state()).velocity.vx == 0.0
        assert runtime.command_deadline is None
        assert runtime.last_command_at is None
    finally:
        await runtime.close()
