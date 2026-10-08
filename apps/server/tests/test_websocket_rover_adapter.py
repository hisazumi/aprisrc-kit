from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any, cast

import pytest
from fastapi import WebSocket

from apris_server.adapter import BoundedMotionGoal
from apris_server.fake_rover import FakeEsp32Rover
from apris_server.front_obstacle import FrontObstacleObservationInput
from apris_server.models import MoveCommand, TurnCommand
from apris_server.physicode_bridge import BridgeConfig, PhysiCodeBridge
from apris_server.rover_protocol import (
    RoverCapabilities,
    RoverCommandAck,
    RoverHello,
    RoverSafetyLimits,
    StartMotion,
    server_rover_command_adapter,
)
from apris_server.rover_registry import RoverRegistry, RoverUnavailableError
from apris_server.runtime import RoverRuntime, RuntimeConfig
from apris_server.structured_log import StructuredLog
from apris_server.websocket_rover_adapter import (
    WebSocketRoverAdapter,
    WebSocketRoverAdapterConfig,
)


class MemoryWebSocket:
    def __init__(self) -> None:
        self.commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.closed = False

    async def send_json(self, payload: dict[str, Any]) -> None:
        if self.closed:
            raise RuntimeError("memory websocket is closed")
        await self.commands.put(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        del code, reason
        self.closed = True


class RuntimeClientSocket:
    def __init__(self, runtime: RoverRuntime) -> None:
        self.runtime = runtime
        self.client_id: str | None = None
        self.incoming: asyncio.Queue[str] = asyncio.Queue()

    async def start(self):
        self.client_id = await self.runtime.add_client(self)
        return self

    async def send(self, message: str) -> None:
        if self.client_id is None:
            raise RuntimeError("runtime client socket is not started")
        await self.runtime.handle_text(self.client_id, message)

    async def recv(self) -> str:
        return await self.incoming.get()

    async def send_text(self, message: str) -> None:
        await self.incoming.put(message)

    async def close(self) -> None:
        if self.client_id is not None:
            await self.runtime.remove_client(self.client_id)
            self.client_id = None


class SingleTurnWorldSocket:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.incoming: asyncio.Queue[str] = asyncio.Queue()
        self.result: dict[str, Any] | None = None

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        if message["type"] == "world_hello":
            await self.incoming.put(
                json.dumps(
                    {
                        "v": 1,
                        "type": "world_ready",
                        "run_id": self.run_id,
                        "status": "READY",
                    }
                )
            )
            await self.incoming.put(
                json.dumps(
                    {
                        "v": 1,
                        "type": "effect",
                        "run_id": self.run_id,
                        "effect_id": "effect-turn-1",
                        "step_id": "step-turn-1",
                        "name": "turn_left",
                        "args": [],
                    }
                )
            )
        elif message["type"] == "effect_result":
            self.result = message
            await self.incoming.put(
                json.dumps(
                    {
                        "v": 1,
                        "type": "run_finished",
                        "run_id": self.run_id,
                        "status": "COMPLETED",
                        "trace": ["turn_left"],
                        "error": None,
                    }
                )
            )

    async def recv(self) -> str:
        return await self.incoming.get()

    async def close(self) -> None:
        return None


class FakeRoverAgent:
    def __init__(
        self,
        registry: RoverRegistry,
        websocket: MemoryWebSocket,
        fake: FakeEsp32Rover,
        *,
        auto_complete: bool = True,
        heartbeat_enabled: bool = True,
    ) -> None:
        self.registry = registry
        self.websocket = websocket
        self.fake = fake
        self.auto_complete = auto_complete
        self.heartbeat_enabled = heartbeat_enabled
        self.command_types: list[str] = []
        self.drop_next_velocity_acks = 0
        self.x_m = 0.0
        self.yaw_rad = 0.0
        self._task: asyncio.Task[None] | None = None
        self._last_heartbeat_at = 0.0

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while True:
            now = time.time()
            if self.heartbeat_enabled and now - self._last_heartbeat_at >= 0.05:
                await self._emit(self.fake.heartbeat(now_ms=round(now * 1000.0)))
                self._last_heartbeat_at = now
            try:
                payload = await asyncio.wait_for(self.websocket.commands.get(), timeout=0.01)
            except TimeoutError:
                await self._tick()
                continue

            command = server_rover_command_adapter.validate_python(payload)
            self.command_types.append(command.type)
            messages = self.fake.apply(command, now_ms=round(time.time() * 1000.0))
            for message in messages:
                if (
                    command.type == "set_velocity"
                    and isinstance(message, RoverCommandAck)
                    and self.drop_next_velocity_acks > 0
                ):
                    self.drop_next_velocity_acks -= 1
                    continue
                await self._emit(message)
            await self._emit_telemetry()

            if isinstance(command, StartMotion) and self.auto_complete:
                await asyncio.sleep(0.02)
                if command.kind == "linear":
                    self.x_m += command.distance_m or 0.0
                else:
                    self.yaw_rad += command.angle_rad or 0.0
                terminal = self.fake.complete_motion()
                await self._emit(terminal)
                await self._emit_telemetry()

    async def _tick(self) -> None:
        messages = self.fake.tick(now_ms=round(time.time() * 1000.0))
        for message in messages:
            await self._emit(message)
        if messages:
            await self._emit_telemetry()

    async def _emit_telemetry(self) -> None:
        await self._emit(
            self.fake.telemetry(
                now_ms=round(time.time() * 1000.0),
                x_m=self.x_m,
                yaw_rad=self.yaw_rad,
            )
        )

    async def _emit(self, message) -> None:
        await self.registry.handle(
            self.fake.hello.rover_id,
            self.fake._required_epoch(),
            message,
        )


async def connected_fake(
    *,
    auto_complete: bool = True,
    heartbeat_enabled: bool = True,
    heartbeat_interval_ms: int = 100,
    structured_log: StructuredLog | None = None,
) -> tuple[RoverRegistry, WebSocketRoverAdapter, FakeEsp32Rover, FakeRoverAgent]:
    registry = RoverRegistry(
        "test-token",
        structured_log=structured_log,
        heartbeat_interval_ms=heartbeat_interval_ms,
        clock_uncertainty_limit_ms=50,
    )
    websocket = MemoryWebSocket()
    hello = RoverHello(
        protocol_versions=[1],
        rover_id="fake-ugv02",
        boot_id="boot-1",
        firmware_version="test",
        build_id="test",
        hardware_revision="test",
        capabilities=RoverCapabilities(),
        safety_limits=RoverSafetyLimits(
            max_linear_speed_mps=0.08,
            max_angular_speed_rad_s=0.5,
            max_distance_m=1.0,
            max_angle_rad=3.2,
            max_motion_duration_ms=10_000,
            max_lease_ms=500,
        ),
    )
    welcome = await registry.connect(
        cast(WebSocket, websocket),
        hello,
        server_version="test",
        build_id="test",
        instance_id="test",
    )
    fake = FakeEsp32Rover(hello)
    fake.connect(welcome)
    await registry.handle(
        hello.rover_id,
        welcome.connection_epoch,
        fake.heartbeat(now_ms=round(time.time() * 1000.0), clock_uncertainty_ms=5.0),
    )
    await registry.handle(
        hello.rover_id,
        welcome.connection_epoch,
        fake.telemetry(now_ms=round(time.time() * 1000.0)),
    )
    agent = FakeRoverAgent(
        registry,
        websocket,
        fake,
        auto_complete=auto_complete,
        heartbeat_enabled=heartbeat_enabled,
    )
    agent.start()
    adapter = WebSocketRoverAdapter(
        registry,
        hello.rover_id,
        WebSocketRoverAdapterConfig(
            command_ttl_ms=500,
            command_ack_timeout_s=0.2,
            desired_motion_lease_ms=500,
            telemetry_stale_after_s=0.5,
        ),
    )
    return registry, adapter, fake, agent


async def wait_until(predicate, timeout_s: float = 1.0) -> None:
    wake = asyncio.Event()
    async with asyncio.timeout(timeout_s):
        while not predicate():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wake.wait(), timeout=0.005)


@pytest.mark.asyncio
async def test_adapter_dispatches_bounded_motion_and_clamps_manual_velocity() -> None:
    registry, adapter, fake, agent = await connected_fake()
    try:
        result = await adapter.execute_bounded_motion(
            BoundedMotionGoal(
                motion_id="motion-1",
                kind="linear",
                distance_m=0.2,
                angle_rad=None,
                max_linear_speed_mps=0.3,
                max_angular_speed_rad_s=1.2,
                max_duration_ms=5_000,
            )
        )
        assert result.status == "completed"
        assert fake.motor_stopped is True
        assert (await adapter.state()).pose.x == pytest.approx(0.2)

        await adapter.drive(0.3, 0.0, 1.0, ttl_ms=500)
        await wait_until(lambda: not fake.motor_stopped)
        assert fake.linear_velocity_mps == pytest.approx(0.08)
        assert fake.angular_velocity_rad_s == pytest.approx(0.5)
        await adapter.stop()
        assert fake.motor_stopped is True
        assert agent.command_types[:3] == ["start_motion", "set_velocity", "stop"]
    finally:
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_terminal_motion_wins_race_with_lease_renewal() -> None:
    registry, adapter, fake, agent = await connected_fake(auto_complete=False)
    try:
        operation = asyncio.create_task(
            adapter.execute_bounded_motion(
                BoundedMotionGoal(
                    motion_id="motion-terminal-renew-race",
                    kind="rotate",
                    distance_m=None,
                    angle_rad=-0.25,
                    max_linear_speed_mps=0.08,
                    max_angular_speed_rad_s=0.2,
                    max_duration_ms=5_000,
                )
            )
        )
        await wait_until(lambda: fake.active_motion is not None)

        terminal = fake.complete_motion()
        assert terminal.status == "completed"

        result = await asyncio.wait_for(operation, timeout=1.0)
        assert result.status == "completed"
        assert "renew_motion_lease" in agent.command_types
        assert fake.motor_stopped is True
    finally:
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_runtime_uses_device_bounded_motion_without_velocity_streaming() -> None:
    registry, adapter, fake, agent = await connected_fake()
    runtime = RoverRuntime(
        adapter,
        RuntimeConfig(safety_hz=100.0, state_hz=50.0, motion_hz=100.0),
    )
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await runtime.ingest_front_obstacle(
            FrontObstacleObservationInput(
                state="CLEAR",
                perception_health="healthy",
                source="manual",
                confidence=1.0,
            )
        )
        await runtime._start_move(
            "test-client",
            MoveCommand(
                type="move",
                request_id="move-1",
                distance_m=0.2,
                speed_mps=0.3,
            ),
        )
        assert runtime._motion_task is not None
        await asyncio.wait_for(asyncio.shield(runtime._motion_task), timeout=2.0)
        assert (await adapter.state()).pose.x == pytest.approx(0.2)

        await runtime._start_turn(
            "test-client",
            TurnCommand(
                type="turn",
                request_id="turn-1",
                angle_deg=30.0,
                speed_rad_s=1.2,
            ),
        )
        assert runtime._motion_task is not None
        await asyncio.wait_for(asyncio.shield(runtime._motion_task), timeout=2.0)
        assert (await adapter.state()).pose.yaw == pytest.approx(0.5236, abs=0.001)
        assert agent.command_types.count("start_motion") == 2
        assert "set_velocity" not in agent.command_types
        assert fake.motor_stopped is True
    finally:
        await runtime.close()
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_runtime_cancel_reaches_fake_rover_and_stops() -> None:
    registry, adapter, fake, agent = await connected_fake(auto_complete=False)
    runtime = RoverRuntime(adapter, RuntimeConfig(safety_hz=100.0, state_hz=50.0))
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await runtime.ingest_front_obstacle(
            FrontObstacleObservationInput(
                state="CLEAR",
                perception_health="healthy",
                source="manual",
                confidence=1.0,
            )
        )
        await runtime._start_move(
            "test-client",
            MoveCommand(
                type="move",
                request_id="cancel-me",
                distance_m=0.5,
                speed_mps=0.08,
            ),
        )
        for _ in range(50):
            if fake.active_motion is not None:
                break
            await asyncio.sleep(0.01)
        assert fake.active_motion is not None
        await runtime._cancel_motion("test cancellation")
        assert fake.motor_stopped is True
        assert "cancel_motion" in agent.command_types
        assert "stop" in agent.command_types
    finally:
        await runtime.close()
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_runtime_estop_is_latched_and_cleared_on_both_layers() -> None:
    registry, adapter, fake, agent = await connected_fake()
    runtime = RoverRuntime(adapter, RuntimeConfig(safety_hz=100.0, state_hz=50.0))
    runtime.owner_client_id = "test-client"
    await runtime.start()
    try:
        await adapter.drive(0.08, 0.0, 0.0, ttl_ms=500)
        await wait_until(lambda: not fake.motor_stopped)
        assert fake.motor_stopped is False
        await runtime._estop("test estop")
        assert runtime.estop_latched is True
        assert fake.estop_latched is True
        assert fake.motor_stopped is True

        await runtime._clear_estop("test-client")
        assert runtime.estop_latched is False
        assert fake.estop_latched is False
        assert fake.motor_stopped is True
        assert "estop" in agent.command_types
        assert "clear_estop" in agent.command_types
    finally:
        await runtime.close()
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_stale_heartbeat_blocks_refresh_and_local_velocity_lease_stops() -> None:
    registry, adapter, fake, agent = await connected_fake(heartbeat_enabled=False)
    try:
        await adapter.drive(0.08, 0.0, 0.0, ttl_ms=500)
        await wait_until(lambda: not fake.motor_stopped)
        assert fake.motor_stopped is False
        await asyncio.sleep(0.32)
        with pytest.raises(RoverUnavailableError, match="heartbeat is stale"):
            await adapter.drive(0.08, 0.0, 0.0, ttl_ms=500)
        await asyncio.sleep(0.22)
        assert fake.motor_stopped is True
    finally:
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_velocity_refresh_coalesces_after_ack_timeout_without_injected_stop() -> None:
    registry, adapter, fake, agent = await connected_fake()
    adapter.config.command_ack_timeout_s = 0.05
    agent.drop_next_velocity_acks = 1
    try:
        await adapter.drive(0.0, 0.0, -0.2, ttl_ms=500)
        await wait_until(lambda: agent.command_types.count("set_velocity") == 1)

        for angular in (-0.25, -0.30, -0.35):
            await adapter.drive(0.0, 0.0, angular, ttl_ms=500)

        await wait_until(lambda: agent.command_types.count("set_velocity") == 2)
        await wait_until(lambda: fake.angular_velocity_rad_s == pytest.approx(-0.35))

        assert "stop" not in agent.command_types
        assert fake.motor_stopped is False

        await adapter.stop()
        assert fake.motor_stopped is True
        assert agent.command_types.count("stop") == 1
    finally:
        await adapter.close()
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_registry_logs_command_rtt_and_telemetry_values(tmp_path) -> None:
    structured_log = StructuredLog(tmp_path)
    registry, adapter, fake, agent = await connected_fake(structured_log=structured_log)
    try:
        await adapter.drive(0.0, 0.0, -0.2, ttl_ms=500)
        await wait_until(lambda: not fake.motor_stopped)
        await adapter.stop()

        entries = structured_log.recent(200, include_state=True)
        sent = [
            entry
            for entry in entries
            if entry["category"] == "rover_connection"
            and entry["name"] == "command_sent"
            and entry["data"]["command_type"] == "set_velocity"
        ]
        acknowledged = [
            entry
            for entry in entries
            if entry["category"] == "rover_connection"
            and entry["name"] == "command_acknowledged"
            and entry["data"]["command_type"] == "set_velocity"
        ]
        telemetry = [
            entry
            for entry in entries
            if entry["category"] == "rover_connection"
            and entry["name"] == "rover_message"
            and entry["data"]["type"] == "telemetry"
        ]

        assert len(sent) == 1
        assert len(acknowledged) == 1
        assert acknowledged[0]["data"]["latency_ms"] >= 0
        assert any(entry["data"]["angular_velocity_rad_s"] == -0.2 for entry in telemetry)
    finally:
        await adapter.close()
        await agent.close()
        await registry.close()
        structured_log.close()


@pytest.mark.asyncio
async def test_unsafe_clock_uncertainty_blocks_motion_but_not_stop() -> None:
    registry, adapter, fake, agent = await connected_fake(heartbeat_enabled=False)
    try:
        await registry.handle(
            fake.hello.rover_id,
            fake._required_epoch(),
            fake.heartbeat(
                now_ms=round(time.time() * 1000.0),
                clock_uncertainty_ms=100.0,
            ),
        )
        with pytest.raises(RoverUnavailableError, match="clock uncertainty"):
            await adapter.drive(0.08, 0.0, 0.0, ttl_ms=500)
        await adapter.stop()
        assert fake.motor_stopped is True
        assert agent.command_types == ["stop"]
    finally:
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_stale_telemetry_and_sensor_faults_degrade_adapter_state() -> None:
    registry, adapter, fake, agent = await connected_fake(heartbeat_enabled=True)
    try:
        await asyncio.sleep(0.52)
        stale = await adapter.state()
        assert stale.connected is False
        assert stale.pose_quality.age_ms >= 500.0
    finally:
        await agent.close()
        await registry.close()

    registry, adapter, fake, agent = await connected_fake(heartbeat_enabled=False)
    try:
        await registry.handle(
            fake.hello.rover_id,
            fake._required_epoch(),
            fake.telemetry(
                now_ms=round(time.time() * 1000.0),
                fault_codes=["encoder_fault", "imu_fault"],
            ),
        )
        faulted = await adapter.state()
        assert faulted.connected is True
        assert faulted.pose_quality.source == "unavailable"
        assert faulted.pose_quality.encoder_status == "fault"
        assert faulted.pose_quality.imu_status == "fault"
        assert faulted.pose_quality.anomalies == ["encoder_fault", "imu_fault"]
    finally:
        await agent.close()
        await registry.close()


@pytest.mark.asyncio
async def test_physicode_bridge_turn_effect_reaches_fake_rover() -> None:
    registry, adapter, fake, agent = await connected_fake()
    runtime = RoverRuntime(
        adapter,
        RuntimeConfig(safety_hz=100.0, state_hz=50.0, motion_hz=100.0),
    )
    await runtime.start()
    apris_socket = await RuntimeClientSocket(runtime).start()
    world_socket = SingleTurnWorldSocket("run-rover-e2e")
    bridge = PhysiCodeBridge(
        BridgeConfig(
            physicode_ws_url="ws://physicode.test",
            apris_ws_url="ws://apris.test/ws",
            run_id="run-rover-e2e",
            driver_token="test-token",
            world_id="apris-fake-rover",
            turn_angle_deg=30.0,
            turn_speed_rad_s=1.2,
            motion_timeout_s=3.0,
        )
    )
    try:
        terminal = await bridge.run_with_sockets(world_socket, apris_socket)
        assert terminal["status"] == "COMPLETED"
        assert world_socket.result is not None
        assert world_socket.result["status"] == "completed"
        assert world_socket.result["value"] is None
        assert agent.command_types.count("start_motion") == 1
        assert "set_velocity" not in agent.command_types
        assert agent.yaw_rad == pytest.approx(0.5236, abs=0.001)
        assert fake.motor_stopped is True
        assert runtime.owner_client_id is None
    finally:
        await apris_socket.close()
        await runtime.close()
        await agent.close()
        await registry.close()
