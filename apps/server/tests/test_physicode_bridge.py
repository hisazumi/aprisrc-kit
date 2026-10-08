from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import pytest

from apris_server.front_obstacle import FrontObstacleObservationInput
from apris_server.physicode_bridge import BridgeConfig, BridgeError, PhysiCodeBridge
from apris_server.runtime import RoverRuntime, RuntimeConfig
from apris_server.simulator import DifferentialDriveSimulator, SimulatorConfig


class RuntimeClientSocket:
    def __init__(self, runtime: RoverRuntime) -> None:
        self.runtime = runtime
        self.client_id: str | None = None
        self.incoming: asyncio.Queue[str] = asyncio.Queue()

    async def start(self) -> RuntimeClientSocket:
        self.client_id = await self.runtime.add_client(self)
        return self

    async def send(self, message: str) -> None:
        assert self.client_id is not None
        await self.runtime.handle_text(self.client_id, message)

    async def recv(self) -> str:
        return await self.incoming.get()

    async def send_text(self, message: str) -> None:
        await self.incoming.put(message)

    async def close(self) -> None:
        if self.client_id is not None:
            await self.runtime.remove_client(self.client_id)
            self.client_id = None


class ScriptedWorldSocket:
    def __init__(
        self,
        run_id: str,
        effects: Sequence[str],
        *,
        disconnect_during_effect: bool = False,
    ) -> None:
        self.run_id = run_id
        self.effects = list(effects)
        self.disconnect_during_effect = disconnect_during_effect
        self.incoming: asyncio.Queue[str | Exception] = asyncio.Queue()
        self.results: list[dict[str, Any]] = []
        self.hello: dict[str, Any] | None = None
        self._next_effect = 0
        self._effect_delivered = False

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        if message["type"] == "world_hello":
            self.hello = message
            await self._queue(
                {"v": 1, "type": "world_ready", "run_id": self.run_id, "status": "READY"}
            )
            await self._queue_next_effect()
            return
        if message["type"] == "effect_result":
            self.results.append(message)
            if self._next_effect < len(self.effects):
                await self._queue_next_effect()
            else:
                status = {
                    "completed": "COMPLETED",
                    "failed": "FAILED",
                    "cancelled": "CANCELLED",
                }[message["status"]]
                await self._queue(
                    {
                        "v": 1,
                        "type": "run_finished",
                        "run_id": self.run_id,
                        "status": status,
                        "trace": self.effects[: self._next_effect],
                        "error": message.get("error"),
                    }
                )

    async def recv(self) -> str:
        if self.disconnect_during_effect and self._effect_delivered and self.incoming.empty():
            await asyncio.sleep(0.02)
            raise OSError("simulated PhysiCode disconnect")
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        message = json.loads(item)
        if message.get("type") == "effect":
            self._effect_delivered = True
        return item

    async def close(self) -> None:
        return None

    async def _queue_next_effect(self) -> None:
        effect_name = self.effects[self._next_effect]
        self._next_effect += 1
        await self._queue(
            {
                "v": 1,
                "type": "effect",
                "run_id": self.run_id,
                "effect_id": f"effect-{self._next_effect}",
                "step_id": f"step-{self._next_effect}",
                "name": effect_name,
                "args": [],
            }
        )

    async def _queue(self, message: dict[str, Any]) -> None:
        await self.incoming.put(json.dumps(message))


class ScriptedAprisSocket:
    def __init__(
        self,
        terminal_motion: dict[str, Any] | Exception | None = None,
        *,
        front_obstacle: dict[str, Any] | None = None,
    ) -> None:
        self.terminal_motion = terminal_motion
        self.front_obstacle = front_obstacle
        self.incoming: asyncio.Queue[str | Exception] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.incoming.put_nowait(
            json.dumps(
                {
                    "v": 1,
                    "type": "hello",
                    "supported_protocol_versions": [1],
                }
            )
        )

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        self.sent.append(message)
        if message["type"] == "acquire_control":
            await self._queue(
                {"v": 1, "type": "control", "is_owner": True, "estop_latched": False}
            )
        if message["type"] in {"move", "turn"}:
            await self._queue(
                {
                    "v": 1,
                    "type": "motion",
                    "request_id": message["request_id"],
                    "motion": message["type"],
                    "status": "started",
                    "detail": "",
                }
            )
            if isinstance(self.terminal_motion, Exception):
                await self.incoming.put(self.terminal_motion)
            elif self.terminal_motion is not None:
                await self._queue(
                    {**self.terminal_motion, "request_id": message["request_id"]}
                )
        if message["type"] == "read_front_obstacle":
            assert self.front_obstacle is not None
            await self._queue(
                {
                    "v": 1,
                    "type": "front_obstacle",
                    "request_id": message["request_id"],
                    "run_id": message.get("run_id"),
                    "effect_id": message.get("effect_id"),
                    "obstacle": self.front_obstacle,
                }
            )

    async def recv(self) -> str:
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        return None

    async def _queue(self, message: dict[str, Any]) -> None:
        await self.incoming.put(json.dumps(message))


def bridge_config(**overrides: Any) -> BridgeConfig:
    values = {
        "physicode_ws_url": "ws://physicode.test",
        "apris_ws_url": "ws://apris.test/ws",
        "run_id": "run-bridge-test",
        "driver_token": "secret",
        "world_id": "apris-simulator-1",
        "cell_size_m": 0.06,
        "turn_angle_deg": 15.0,
        "move_speed_mps": 0.30,
        "turn_speed_rad_s": 1.20,
        "motion_timeout_s": 3.0,
    }
    values.update(overrides)
    return BridgeConfig(**values)


async def started_runtime() -> tuple[RoverRuntime, DifferentialDriveSimulator]:
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
    await runtime.start()
    await runtime.ingest_front_obstacle(
        FrontObstacleObservationInput(
            state="CLEAR",
            perception_health="healthy",
            source="manual",
            confidence=1.0,
        )
    )
    return runtime, simulator


@pytest.mark.asyncio
async def test_bridge_moves_apris_simulator_end_to_end() -> None:
    runtime, simulator = await started_runtime()
    apris_socket = await RuntimeClientSocket(runtime).start()
    world_socket = ScriptedWorldSocket(
        "run-bridge-test", ["forward", "turn_right", "forward"]
    )
    try:
        terminal = await PhysiCodeBridge(bridge_config()).run_with_sockets(
            world_socket, apris_socket
        )
        assert terminal["status"] == "COMPLETED"
        assert [result["value"] for result in world_socket.results] == [
            "moved",
            None,
            "moved",
        ]
        assert all(result["status"] == "completed" for result in world_socket.results)
        assert world_socket.hello is not None
        assert set(world_socket.hello["capabilities"]) == {
            "forward",
            "backward",
            "turn_left",
            "turn_right",
            "front_blocked",
        }

        state = await simulator.state()
        assert state.pose.x == pytest.approx(0.118, abs=0.018)
        assert state.pose.y == pytest.approx(-0.016, abs=0.018)
        assert state.pose.yaw == pytest.approx(-0.262, abs=0.030)
        assert state.velocity.vx == 0.0
        assert state.velocity.wz == 0.0
        assert runtime.owner_client_id is None
        status = await runtime.status()
        assert status["adapter"]["state"]["pose"]["x"] == pytest.approx(0.118, abs=0.018)
        assert status["active_execution"]["last_motion"]["run_id"] == "run-bridge-test"
        assert status["active_execution"]["last_motion"]["effect_id"] == "effect-3"
        assert status["active_execution"]["last_motion"]["status"] == "completed"
    finally:
        await apris_socket.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_obstacle_cancellation_maps_to_completed_blocked() -> None:
    world_socket = ScriptedWorldSocket("run-bridge-test", ["forward"])
    apris_socket = ScriptedAprisSocket(
        {
            "v": 1,
            "type": "motion",
            "motion": "move",
            "status": "cancelled",
            "detail": "front_obstacle_blocked",
        }
    )
    terminal = await PhysiCodeBridge(bridge_config()).run_with_sockets(
        world_socket, apris_socket
    )
    assert terminal["status"] == "COMPLETED"
    assert world_socket.results[0]["status"] == "completed"
    assert world_socket.results[0]["value"] == "blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "health", "stale", "expected_status", "expected_value"),
    [
        ("BLOCKED", "healthy", False, "completed", True),
        ("CLEAR", "healthy", False, "completed", False),
        ("UNKNOWN", "unavailable", False, "failed", None),
        ("CLEAR", "healthy", True, "failed", None),
    ],
)
async def test_front_blocked_effect_preserves_three_state_semantics(
    state: str,
    health: str,
    stale: bool,
    expected_status: str,
    expected_value: bool | None,
) -> None:
    world_socket = ScriptedWorldSocket("run-bridge-test", ["front_blocked"])
    apris_socket = ScriptedAprisSocket(
        front_obstacle={
            "state": state,
            "observed_state": state,
            "perception_health": health,
            "source": "manual",
            "observed_at": 1.0,
            "heartbeat_at": 1.0,
            "observation_age_ms": 0.0,
            "heartbeat_age_ms": 0.0,
            "stale_after_ms": 5000.0,
            "stale": stale,
            "confidence": 1.0,
            "distance_m": None,
            "lateral_m": None,
            "latched": state == "BLOCKED",
            "latched_at": 1.0 if state == "BLOCKED" else None,
            "cleared_at": None,
            "clear_reason": None,
        }
    )
    terminal = await PhysiCodeBridge(bridge_config()).run_with_sockets(
        world_socket, apris_socket
    )
    result = world_socket.results[0]
    assert result["status"] == expected_status
    assert result["value"] is expected_value
    if expected_status == "failed":
        assert result["error"]["code"] == "perception_unavailable"
        assert terminal["status"] == "FAILED"
    else:
        assert terminal["status"] == "COMPLETED"
    assert world_socket.hello is not None
    assert "front_blocked" in world_socket.hello["capabilities"]


@pytest.mark.asyncio
async def test_front_blocked_effect_reads_runtime_authoritative_latch() -> None:
    runtime, _ = await started_runtime()
    await runtime.ingest_front_obstacle(
        FrontObstacleObservationInput(
            state="BLOCKED",
            perception_health="healthy",
            source="scenario",
            confidence=0.98,
            distance_m=0.25,
        )
    )
    apris_socket = await RuntimeClientSocket(runtime).start()
    world_socket = ScriptedWorldSocket("run-bridge-test", ["front_blocked"])
    try:
        terminal = await PhysiCodeBridge(bridge_config()).run_with_sockets(
            world_socket, apris_socket
        )
        assert terminal["status"] == "COMPLETED"
        assert world_socket.results[0]["status"] == "completed"
        assert world_socket.results[0]["value"] is True
        snapshot = await runtime.front_obstacle_snapshot()
        assert snapshot.state == "BLOCKED"
        assert snapshot.latched is True
    finally:
        await apris_socket.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_preexisting_runtime_obstacle_maps_forward_to_completed_blocked() -> None:
    runtime, simulator = await started_runtime()
    await runtime.ingest_front_obstacle(
        FrontObstacleObservationInput(
            state="BLOCKED",
            perception_health="healthy",
            source="scenario",
            confidence=1.0,
        )
    )
    apris_socket = await RuntimeClientSocket(runtime).start()
    world_socket = ScriptedWorldSocket("run-bridge-test", ["forward", "turn_left"])
    try:
        terminal = await PhysiCodeBridge(bridge_config()).run_with_sockets(
            world_socket, apris_socket
        )
        assert terminal["status"] == "COMPLETED"
        assert [result["value"] for result in world_socket.results] == ["blocked", None]
        assert all(result["status"] == "completed" for result in world_socket.results)
        state = await simulator.state()
        assert state.pose.x == pytest.approx(0.0, abs=0.01)
        assert state.pose.yaw > 0.1
    finally:
        await apris_socket.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_apris_disconnect_maps_active_effect_to_cancelled() -> None:
    world_socket = ScriptedWorldSocket("run-bridge-test", ["forward"])
    apris_socket = ScriptedAprisSocket(OSError("simulated APRIS disconnect"))
    terminal = await PhysiCodeBridge(bridge_config()).run_with_sockets(
        world_socket, apris_socket
    )
    assert terminal["status"] == "CANCELLED"
    assert world_socket.results[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_physicode_disconnect_stops_active_simulator_motion() -> None:
    runtime, simulator = await started_runtime()
    apris_socket = await RuntimeClientSocket(runtime).start()
    world_socket = ScriptedWorldSocket(
        "run-bridge-test",
        ["forward"],
        disconnect_during_effect=True,
    )
    config = bridge_config(cell_size_m=1.0)
    try:
        with pytest.raises(BridgeError, match="PhysiCode disconnected") as disconnected:
            await PhysiCodeBridge(config).run_with_sockets(world_socket, apris_socket)
        assert disconnected.value.code == "physicode_disconnected"
        state = await simulator.state()
        assert state.pose.x < 0.20
        assert state.velocity.vx == 0.0
        assert runtime.owner_client_id is None
    finally:
        await apris_socket.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_estop_cancels_effect_and_manual_control_cannot_take_over() -> None:
    runtime, simulator = await started_runtime()
    apris_socket = await RuntimeClientSocket(runtime).start()
    operator_socket = await RuntimeClientSocket(runtime).start()
    world_socket = ScriptedWorldSocket("run-bridge-test", ["forward"])
    bridge = PhysiCodeBridge(bridge_config(cell_size_m=1.0))
    bridge_task = asyncio.create_task(bridge.run_with_sockets(world_socket, apris_socket))
    try:
        while runtime._motion_task is None:  # noqa: ASYNC110 - observing runtime under test
            await asyncio.sleep(0.005)
        bridge_owner = runtime.owner_client_id
        await operator_socket.send(
            json.dumps(
                {
                    "v": 1,
                    "type": "client_hello",
                    "client_kind": "operator_console",
                    "device_id": "operator",
                    "session_id": "operator-session",
                    "app_version": "test",
                    "build_id": "test",
                }
            )
        )
        await operator_socket.send(json.dumps({"v": 1, "type": "acquire_control"}))
        assert runtime.owner_client_id == bridge_owner

        await runtime._estop("operator test")
        terminal = await asyncio.wait_for(bridge_task, timeout=1.0)
        assert terminal["status"] == "CANCELLED"
        assert world_socket.results[0]["status"] == "cancelled"
        state = await simulator.state()
        assert state.velocity.vx == 0.0
    finally:
        if not bridge_task.done():
            bridge_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await bridge_task
        await operator_socket.close()
        await apris_socket.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_bridge_task_cancellation_stops_and_releases_control() -> None:
    runtime, simulator = await started_runtime()
    apris_socket = await RuntimeClientSocket(runtime).start()
    world_socket = ScriptedWorldSocket("run-bridge-test", ["forward"])
    bridge_task = asyncio.create_task(
        PhysiCodeBridge(bridge_config(cell_size_m=1.0)).run_with_sockets(
            world_socket, apris_socket
        )
    )
    try:
        while runtime._motion_task is None:  # noqa: ASYNC110 - observing runtime under test
            await asyncio.sleep(0.005)
        status = await runtime.status()
        assert status["active_execution"]["run_id"] == "run-bridge-test"
        assert status["active_execution"]["effect_id"] == "effect-1"
        assert status["active_execution"]["motion"]["request_id"] == (
            "pc:run-bridge-test:effect-1"
        )
        bridge_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await bridge_task
        state = await simulator.state()
        assert state.velocity.vx == 0.0
        assert runtime.owner_client_id is None
    finally:
        await apris_socket.close()
        await runtime.close()
