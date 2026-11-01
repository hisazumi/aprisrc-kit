from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass
from typing import Any, Literal

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from .adapter import BoundedMotionGoal, DeviceBoundedMotionAdapter, RoverAdapter
from .front_obstacle import (
    FrontObstacleObservationInput,
    FrontObstacleStateStore,
)
from .models import (
    AcquireControl,
    CancelMotion,
    ClearEmergencyStop,
    ClientHello,
    ControlMessage,
    DriveCommand,
    EmergencyStop,
    ErrorMessage,
    EventMessage,
    FrontObstacleMessage,
    FrontObstacleSnapshot,
    HelloMessage,
    MotionMessage,
    MoveCommand,
    PathClearance,
    PerceptionEventMessage,
    PerceptionObservation,
    ReadFrontObstacle,
    ReleaseControl,
    ResetPose,
    ScenarioEventMessage,
    StateMessage,
    StopCommand,
    TurnCommand,
    client_message_adapter,
)
from .perception import (
    MarkerCorrectionResult,
    MarkerPayload,
    ObservationValidator,
    PoseFusion,
    event_payload,
    validation_reason,
)
from .structured_log import StructuredLog


@dataclass(slots=True)
class RuntimeConfig:
    max_vx: float = 0.30
    max_vy: float = 0.0
    max_wz: float = 1.20
    state_hz: float = 10.0
    safety_hz: float = 20.0
    motion_hz: float = 20.0
    motion_ttl_ms: int = 500
    move_tolerance_m: float = 0.015
    turn_tolerance_rad: float = math.radians(1.5)
    adapter_status_timeout_s: float = 0.5
    front_obstacle_stale_after_s: float = 5.0
    path_clearance_ttl_s: float = 1.0


@dataclass(frozen=True, slots=True)
class RuntimeMetadata:
    instance_id: str = "unknown"
    deployment_profile: Literal["development", "edge", "hosted"] = "development"
    app_version: str = "0.1.0"
    build_id: str = "unknown"
    adapter_type: str = "unknown"


@dataclass(slots=True)
class LoopHealth:
    name: str
    running: bool = False
    started_at: float | None = None
    last_tick_at: float | None = None
    last_success_at: float | None = None
    error: str | None = None
    restart_count: int = 0


@dataclass(slots=True)
class ClientConnection:
    websocket: WebSocket
    connected_at: float
    last_seen_at: float
    registration: ClientHello | None = None


class RoverRuntime:
    def __init__(
        self,
        adapter: RoverAdapter,
        config: RuntimeConfig | None = None,
        structured_log: StructuredLog | None = None,
        pose_fusion: PoseFusion | None = None,
        metadata: RuntimeMetadata | None = None,
    ) -> None:
        self.adapter = adapter
        self.config = config or RuntimeConfig()
        self.log = structured_log
        self.pose_fusion = pose_fusion or PoseFusion({})
        self.metadata = metadata or RuntimeMetadata(adapter_type=type(adapter).__name__)
        self.observation_validator = ObservationValidator()
        self.front_obstacle = FrontObstacleStateStore(
            stale_after_s=self.config.front_obstacle_stale_after_s
        )
        self._front_obstacle_lock = asyncio.Lock()
        self._last_front_obstacle_signature: tuple[object, ...] | None = None
        self._path_clearance_lock = asyncio.Lock()
        self._path_clearance_client_id: str | None = None
        self._path_clearance_deadline: float | None = None
        self.clients: dict[str, ClientConnection] = {}
        self.owner_client_id: str | None = None
        self.estop_latched = False
        self.command_deadline: float | None = None
        self.last_command_at: float | None = None
        self._commanded_vx = 0.0
        self.last_sequence = -1
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._loop_health = {
            "safety": LoopHealth("safety"),
            "state": LoopHealth("state"),
        }
        self._loop_ready = {name: asyncio.Event() for name in self._loop_health}
        self._started_at: float | None = None
        self._closing = False
        self._motion_task: asyncio.Task[None] | None = None
        self._motion_client_id: str | None = None
        self._motion_request_id: str | None = None
        self._motion_kind: str | None = None
        self._motion_run_id: str | None = None
        self._motion_effect_id: str | None = None
        self._motion_forward = False
        self._last_motion: dict[str, Any] | None = None

    async def start(self) -> None:
        self._closing = False
        await self.adapter.start()
        self._started_at = time.time()
        if self.log:
            self.log.record("lifecycle", "runtime_started")
        self._tasks = {
            "safety": asyncio.create_task(
                self._supervise_loop("safety", self._safety_loop),
                name="rover-safety-loop",
            ),
            "state": asyncio.create_task(
                self._supervise_loop("state", self._state_loop),
                name="rover-state-loop",
            ),
        }
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(*(event.wait() for event in self._loop_ready.values())),
                timeout=1.0,
            )

    async def close(self) -> None:
        self._closing = True
        await self._cancel_motion("server shutdown", notify=False)
        await self._stop_adapter("server shutdown")
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        await self.adapter.close()
        if self.log:
            self.log.record("lifecycle", "runtime_stopped")

    async def add_client(self, websocket: WebSocket) -> str:
        client_id = uuid.uuid4().hex[:8]
        now = time.time()
        async with self._lock:
            self.clients[client_id] = ClientConnection(
                websocket=websocket,
                connected_at=now,
                last_seen_at=now,
            )
        if self.log:
            self.log.record("connection", "client_connected", {"client_id": client_id})
        state = await self.adapter.state()
        await self._send(
            client_id,
            HelloMessage(
                client_id=client_id,
                capabilities=state.capabilities,
                server_version=self.metadata.app_version,
                build_id=self.metadata.build_id,
                instance_id=self.metadata.instance_id,
            ),
        )
        await self._send_control(client_id)
        return client_id

    async def remove_client(self, client_id: str) -> None:
        owner_disconnected = False
        async with self._lock:
            self.clients.pop(client_id, None)
            if self.owner_client_id == client_id:
                self.owner_client_id = None
                self.command_deadline = None
                self.last_command_at = None
                owner_disconnected = True
        if owner_disconnected:
            await self._cancel_motion("controller disconnected")
            confirmed = await self._operator_stop("controller disconnected")
            await self._revoke_path_clearance(client_id)
            await self.broadcast(EventMessage(event="owner_disconnected", detail=(
                "Rover stopped" if confirmed else "Physical stop unconfirmed"
            )))
            await self._broadcast_control()
        if self.log:
            self.log.record("connection", "client_disconnected", {"client_id": client_id})

    async def handle_text(self, client_id: str, raw: str) -> None:
        try:
            message = client_message_adapter.validate_json(raw)
        except ValidationError as exc:
            await self._error(client_id, "invalid_message", str(exc))
            return

        connection = self.clients.get(client_id)
        if connection is None:
            return
        connection.last_seen_at = time.time()

        if isinstance(message, ClientHello):
            await self._register_client(client_id, message)
            return
        if connection.registration is None and not isinstance(message, EmergencyStop):
            await self._error(
                client_id,
                "client_not_registered",
                "Send client_hello before other client messages",
            )
            return

        if self.log:
            self.log.record(
                "client_message",
                message.type,
                {"client_id": client_id, "message": message.model_dump(mode="json")},
            )

        if isinstance(message, AcquireControl):
            await self._acquire_control(client_id)
        elif isinstance(message, ReleaseControl):
            await self._release_control(client_id)
        elif isinstance(message, DriveCommand):
            await self._drive(client_id, message)
        elif isinstance(message, StopCommand):
            await self._stop(client_id, message.reason)
        elif isinstance(message, MoveCommand):
            await self._start_move(client_id, message)
        elif isinstance(message, TurnCommand):
            await self._start_turn(client_id, message)
        elif isinstance(message, CancelMotion):
            await self._cancel_motion_for_client(client_id)
        elif isinstance(message, EmergencyStop):
            await self._estop(message.reason)
        elif isinstance(message, ClearEmergencyStop):
            await self._clear_estop(client_id)
        elif isinstance(message, ResetPose):
            await self._reset_pose(client_id)
        elif isinstance(message, ReadFrontObstacle):
            await self._send_front_obstacle(
                client_id,
                request_id=message.request_id,
                run_id=message.run_id,
                effect_id=message.effect_id,
            )
        elif isinstance(message, PathClearance):
            await self._set_path_clearance(client_id, message.confirmed)
        elif isinstance(message, PerceptionObservation):
            if message.source not in ("camera", "recorded"):
                await self._error(
                    client_id,
                    "invalid_perception_source",
                    "Browser observations must use camera or recorded source",
                )
                return
            await self.ingest_perception(message)

    async def _register_client(self, client_id: str, message: ClientHello) -> None:
        connection = self.clients.get(client_id)
        if connection is None:
            return
        if connection.registration is not None:
            await self._error(client_id, "client_already_registered", "client_hello was repeated")
            return
        connection.registration = message
        if self.log:
            self.log.record(
                "connection",
                "client_registered",
                {
                    "client_id": client_id,
                    **message.model_dump(mode="json"),
                },
            )

    async def _acquire_control(self, client_id: str) -> None:
        async with self._lock:
            if self.owner_client_id not in (None, client_id):
                owner = self.owner_client_id
            else:
                self.owner_client_id = client_id
                self.last_sequence = -1
                owner = None
        if owner is not None:
            await self._error(client_id, "control_busy", "Another client has control")
            return
        await self._broadcast_control()

    async def _release_control(self, client_id: str) -> None:
        if not await self._require_owner(client_id):
            return
        await self._cancel_motion("control released")
        confirmed = await self._operator_stop("control released")
        await self._revoke_path_clearance(client_id)
        async with self._lock:
            self.owner_client_id = None
            self.command_deadline = None
            self.last_command_at = None
        await self._broadcast_control()
        await self.broadcast(EventMessage(event="control_released", detail=(
            "Rover stopped" if confirmed else "Physical stop unconfirmed"
        )))

    async def _set_path_clearance(self, client_id: str, confirmed: bool) -> None:
        if not await self._require_owner(client_id):
            return
        connection = self.clients.get(client_id)
        if connection is None or connection.registration is None:
            return
        if connection.registration.client_kind not in (
            "service_app",
            "operator_console",
            "development_lab",
        ):
            await self._error(
                client_id,
                "path_clearance_not_allowed",
                "This client kind cannot confirm a clear path",
            )
            return
        if not confirmed:
            await self._revoke_path_clearance(client_id)
            return
        async with self._path_clearance_lock:
            self._path_clearance_client_id = client_id
            self._path_clearance_deadline = time.monotonic() + self.config.path_clearance_ttl_s
            await self.ingest_front_obstacle(
                FrontObstacleObservationInput(
                    state="CLEAR",
                    perception_health="healthy",
                    source="manual",
                    confidence=1.0,
                )
            )

    async def _revoke_path_clearance(self, client_id: str) -> None:
        async with self._path_clearance_lock:
            if self._path_clearance_client_id != client_id:
                return
            self._path_clearance_client_id = None
            self._path_clearance_deadline = None
            await self._publish_revoked_path_clearance()

    async def _expire_path_clearance(self, now: float) -> None:
        async with self._path_clearance_lock:
            if self._path_clearance_deadline is None or now < self._path_clearance_deadline:
                return
            self._path_clearance_client_id = None
            self._path_clearance_deadline = None
            await self._publish_revoked_path_clearance()

    async def _publish_revoked_path_clearance(self) -> None:
        snapshot = await self.front_obstacle_snapshot()
        if snapshot.source != "manual" or snapshot.observed_state != "CLEAR":
            return
        await self.ingest_front_obstacle(
            FrontObstacleObservationInput(
                state="UNKNOWN",
                perception_health="unavailable",
                source="manual",
            )
        )

    async def _drive(self, client_id: str, command: DriveCommand) -> None:
        if not await self._require_owner(client_id):
            return
        if self.estop_latched:
            await self._error(client_id, "estop_latched", "Clear emergency stop before driving")
            return
        if command.seq <= self.last_sequence:
            await self._error(client_id, "stale_command", "Drive sequence must increase")
            return
        if command.vx > 0:
            obstacle = await self.front_obstacle_snapshot()
            if obstacle.state != "CLEAR":
                code = (
                    "front_obstacle_blocked"
                    if obstacle.state == "BLOCKED"
                    else "front_obstacle_unknown"
                )
                await self._cancel_motion(code)
                await self._operator_stop(code)
                await self._clear_command_deadline()
                await self._error(
                    client_id,
                    code,
                    "Forward drive requires a fresh healthy CLEAR observation",
                )
                return

        await self._cancel_motion("manual drive")
        vx = max(-self.config.max_vx, min(self.config.max_vx, command.vx))
        vy = max(-self.config.max_vy, min(self.config.max_vy, command.vy))
        wz = max(-self.config.max_wz, min(self.config.max_wz, command.wz))
        self.last_sequence = command.seq
        try:
            await self._apply_velocity(vx, vy, wz, command.ttl_ms)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await self._stop_adapter("drive command failed")
            await self._clear_command_deadline()
            if self.log:
                self.log.record(
                    "adapter_command",
                    "drive_failed",
                    {"error": type(exc).__name__},
                )
            await self._error(
                client_id,
                "adapter_command_failed",
                "Drive command failed and a stop was attempted",
            )

    async def _stop(self, client_id: str, reason: str) -> None:
        if not await self._require_owner(client_id):
            return
        await self._cancel_motion(reason)
        confirmed = await self._operator_stop(reason)
        async with self._lock:
            self.command_deadline = None
            self.last_command_at = None
        if confirmed:
            await self.broadcast(EventMessage(event="stopped", detail=reason))

    async def _estop(self, reason: str) -> None:
        async with self._lock:
            self.estop_latched = True
            self.command_deadline = None
            self.last_command_at = None
        await self._broadcast_control()
        await self._cancel_motion("emergency stop")
        try:
            await self.adapter.emergency_stop(reason)
        except Exception:
            await self.broadcast(
                EventMessage(
                    event="emergency_stop_unconfirmed",
                    detail="Emergency stop remains latched; robot acknowledgement unavailable",
                )
            )
            return
        if self.log:
            self.log.record("adapter_command", "emergency_stop", {"reason": reason})
        async with self._lock:
            self.estop_latched = True
            self.command_deadline = None
            self.last_command_at = None
        await self.broadcast(EventMessage(event="emergency_stop", detail=reason))
        await self._broadcast_control()

    async def _clear_estop(self, client_id: str) -> None:
        if not await self._require_owner(client_id):
            return
        try:
            await self.adapter.clear_emergency_stop()
        except Exception:
            await self._error(
                client_id, "clear_estop_failed", "Stop remains latched; retry after reconnection"
            )
            return
        async with self._lock:
            self.estop_latched = False
        await self.broadcast(EventMessage(event="emergency_stop_cleared"))
        await self._broadcast_control()

    async def _reset_pose(self, client_id: str) -> None:
        if not await self._require_owner(client_id):
            return
        await self._cancel_motion("pose reset")
        await self._stop_adapter("pose reset")
        await self.adapter.reset_pose()
        self.pose_fusion.reset()
        if self.log:
            self.log.record("adapter_command", "reset_pose")
        async with self._lock:
            self.command_deadline = None
            self.last_command_at = None
        await self.broadcast(EventMessage(event="pose_reset"))

    async def ingest_perception(
        self,
        observation: PerceptionObservation,
    ) -> PerceptionEventMessage:
        reason = self.observation_validator.validate_common(observation)
        payload = None
        if reason is None:
            try:
                payload = self.observation_validator.payload(observation)
            except ValidationError as exc:
                reason = validation_reason(exc)

        correction: MarkerCorrectionResult | None = None
        if (
            reason is None
            and isinstance(payload, MarkerPayload)
            and observation.status == "detected"
        ):
            raw_state = await self.adapter.state()
            correction = self.pose_fusion.correct(
                raw_state.pose,
                payload,
                observation.confidence,
            )
            if not correction.applied:
                reason = correction.reason

        accepted = reason is None
        normalized_payload = (
            event_payload(payload, correction) if payload is not None else observation.payload
        )
        message = PerceptionEventMessage(
            event_id=observation.observation_id,
            kind=observation.kind,
            status=observation.status if accepted else "rejected",
            confidence=observation.confidence,
            captured_at=observation.captured_at,
            source=observation.source,
            payload=normalized_payload,
            accepted=accepted,
            reason=reason or "",
        )
        if self.log:
            self.log.record(
                "perception_observation",
                observation.kind,
                {
                    "observation": observation.model_dump(mode="json"),
                    "accepted": accepted,
                    "reason": reason,
                    "payload": normalized_payload,
                },
            )
        await self.broadcast(message)
        return message

    async def reset_pose_estimate(self) -> None:
        self.pose_fusion.reset()

    async def front_obstacle_snapshot(self) -> FrontObstacleSnapshot:
        async with self._front_obstacle_lock:
            return self.front_obstacle.snapshot()

    async def ingest_front_obstacle(
        self,
        observation: FrontObstacleObservationInput,
    ) -> FrontObstacleSnapshot:
        async with self._front_obstacle_lock:
            snapshot = self.front_obstacle.observe(observation)
        await self._publish_front_obstacle(snapshot, event="observation")
        await self._enforce_front_obstacle(snapshot)
        return snapshot

    async def clear_front_obstacle_latch(self, reason: str) -> FrontObstacleSnapshot:
        async with self._front_obstacle_lock:
            snapshot = self.front_obstacle.clear_latch(reason)
        await self._publish_front_obstacle(snapshot, event="latch_cleared")
        return snapshot

    async def _send_front_obstacle(
        self,
        client_id: str,
        *,
        request_id: str | None = None,
        run_id: str | None = None,
        effect_id: str | None = None,
    ) -> None:
        await self._send(
            client_id,
            FrontObstacleMessage(
                request_id=request_id,
                run_id=run_id,
                effect_id=effect_id,
                obstacle=await self.front_obstacle_snapshot(),
            ),
        )

    async def _publish_front_obstacle(
        self,
        snapshot: FrontObstacleSnapshot,
        *,
        event: str,
    ) -> None:
        signature = (
            snapshot.state,
            snapshot.observed_state,
            snapshot.perception_health,
            snapshot.source,
            snapshot.stale,
            snapshot.latched,
            snapshot.clear_reason,
        )
        if signature == self._last_front_obstacle_signature and event == "freshness_check":
            return
        self._last_front_obstacle_signature = signature
        payload = snapshot.model_dump(mode="json")
        if self.log:
            self.log.record("front_obstacle", event, payload)
        await self.broadcast(FrontObstacleMessage(obstacle=snapshot))

    async def _enforce_front_obstacle(self, snapshot: FrontObstacleSnapshot) -> None:
        if snapshot.state == "CLEAR":
            return
        reason = (
            "front_obstacle_blocked" if snapshot.state == "BLOCKED" else "front_obstacle_unknown"
        )
        if self._motion_task is not None and self._motion_forward:
            await self._cancel_motion(reason)
            return
        async with self._lock:
            forward_commanded = self._commanded_vx > 0.0
        if forward_commanded:
            confirmed = await self._operator_stop(reason)
            await self._clear_command_deadline()
            if confirmed:
                await self.broadcast(EventMessage(event="forward_motion_stopped", detail=reason))

    async def _apply_velocity(self, vx: float, vy: float, wz: float, ttl_ms: int) -> None:
        await self.adapter.drive(vx, vy, wz, ttl_ms=ttl_ms)
        if self.log:
            self.log.record(
                "adapter_command",
                "drive_requested",
                {"vx": vx, "vy": vy, "wz": wz, "ttl_ms": ttl_ms},
            )
        now = time.monotonic()
        async with self._lock:
            self._commanded_vx = vx
            self.last_command_at = now
            self.command_deadline = now + ttl_ms / 1000.0

    async def _start_move(self, client_id: str, command: MoveCommand) -> None:
        if not await self._motion_allowed(
            client_id,
            command.request_id,
            "move",
            command.run_id,
            command.effect_id,
        ):
            return
        if command.distance_m > 0:
            obstacle = await self.front_obstacle_snapshot()
            if obstacle.state != "CLEAR":
                status = "cancelled" if obstacle.state == "BLOCKED" else "failed"
                detail = (
                    "front_obstacle_blocked"
                    if obstacle.state == "BLOCKED"
                    else "front_obstacle_unknown: perception_unavailable"
                )
                rejected = MotionMessage(
                    request_id=command.request_id,
                    run_id=command.run_id,
                    effect_id=command.effect_id,
                    motion="move",
                    status=status,
                    detail=detail,
                )
                self._last_motion = rejected.model_dump(mode="json")
                await self._send(client_id, rejected)
                if self.log:
                    self.log.record(
                        "motion_safety",
                        "forward_rejected",
                        {
                            **rejected.model_dump(mode="json"),
                            "front_obstacle": obstacle.model_dump(mode="json"),
                        },
                    )
                return
        await self._cancel_motion("replaced by a new motion")
        self._start_motion_task(
            client_id,
            command.request_id,
            "move",
            command.run_id,
            command.effect_id,
            self._run_move(command),
            forward=command.distance_m > 0,
        )

    async def _start_turn(self, client_id: str, command: TurnCommand) -> None:
        if not await self._motion_allowed(
            client_id,
            command.request_id,
            "turn",
            command.run_id,
            command.effect_id,
        ):
            return
        await self._cancel_motion("replaced by a new motion")
        self._start_motion_task(
            client_id,
            command.request_id,
            "turn",
            command.run_id,
            command.effect_id,
            self._run_turn(command),
        )

    async def _motion_allowed(
        self,
        client_id: str,
        request_id: str,
        kind: str,
        run_id: str | None,
        effect_id: str | None,
    ) -> bool:
        if not await self._require_owner(client_id):
            await self._send(
                client_id,
                MotionMessage(
                    request_id=request_id,
                    run_id=run_id,
                    effect_id=effect_id,
                    motion=kind,
                    status="failed",
                    detail="Acquire control before starting a motion",
                ),
            )
            return False
        if self.estop_latched:
            await self._send(
                client_id,
                MotionMessage(
                    request_id=request_id,
                    run_id=run_id,
                    effect_id=effect_id,
                    motion=kind,
                    status="failed",
                    detail="Clear emergency stop before starting a motion",
                ),
            )
            return False
        state = await self.adapter.state()
        if not state.connected:
            await self._send(
                client_id,
                MotionMessage(
                    request_id=request_id,
                    run_id=run_id,
                    effect_id=effect_id,
                    motion=kind,
                    status="failed",
                    detail="The selected rover is not connected and healthy",
                ),
            )
            return False
        if not state.capabilities.pose:
            await self._send(
                client_id,
                MotionMessage(
                    request_id=request_id,
                    run_id=run_id,
                    effect_id=effect_id,
                    motion=kind,
                    status="failed",
                    detail="This rover does not provide pose feedback",
                ),
            )
            return False
        return True

    def _start_motion_task(
        self,
        client_id: str,
        request_id: str,
        kind: str,
        run_id: str | None,
        effect_id: str | None,
        operation: Coroutine[Any, Any, None],
        *,
        forward: bool = False,
    ) -> None:
        self._motion_client_id = client_id
        self._motion_request_id = request_id
        self._motion_kind = kind
        self._motion_run_id = run_id
        self._motion_effect_id = effect_id
        self._motion_forward = forward
        self._motion_task = asyncio.create_task(
            self._run_motion(client_id, request_id, kind, run_id, effect_id, operation),
            name=f"rover-{kind}-{request_id}",
        )

    async def _run_motion(
        self,
        client_id: str,
        request_id: str,
        kind: str,
        run_id: str | None,
        effect_id: str | None,
        operation: Coroutine[Any, Any, None],
    ) -> None:
        current_task = asyncio.current_task()
        try:
            await self._send(
                client_id,
                MotionMessage(
                    request_id=request_id,
                    run_id=run_id,
                    effect_id=effect_id,
                    motion=kind,
                    status="started",
                ),
            )
            await self.broadcast(EventMessage(event="motion_started", detail=kind))
            await operation
            if not isinstance(self.adapter, DeviceBoundedMotionAdapter):
                await self._stop_adapter("motion completed")
            await self._clear_command_deadline()
            completed = MotionMessage(
                request_id=request_id,
                run_id=run_id,
                effect_id=effect_id,
                motion=kind,
                status="completed",
            )
            self._last_motion = completed.model_dump(mode="json")
            await self._send(client_id, completed)
            await self.broadcast(EventMessage(event="motion_completed", detail=kind))
        except asyncio.CancelledError:
            await self._stop_adapter("motion cancelled")
            await self._clear_command_deadline()
            raise
        except Exception as exc:
            await self._stop_adapter("motion failed")
            await self._clear_command_deadline()
            failed = MotionMessage(
                request_id=request_id,
                run_id=run_id,
                effect_id=effect_id,
                motion=kind,
                status="failed",
                detail=str(exc),
            )
            self._last_motion = failed.model_dump(mode="json")
            await self._send(client_id, failed)
            await self.broadcast(EventMessage(event="motion_failed", detail=f"{kind}: {exc}"))
        finally:
            if self._motion_task is current_task:
                self._motion_task = None
                self._motion_client_id = None
                self._motion_request_id = None
                self._motion_kind = None
                self._motion_run_id = None
                self._motion_effect_id = None
                self._motion_forward = False

    async def _run_move(self, command: MoveCommand) -> None:
        if isinstance(self.adapter, DeviceBoundedMotionAdapter):
            timeout_s = max(3.0, abs(command.distance_m) / command.speed_mps * 2.5 + 2.0)
            await self.adapter.execute_bounded_motion(
                BoundedMotionGoal(
                    motion_id=self._bounded_motion_id(command.request_id),
                    kind="linear",
                    distance_m=command.distance_m,
                    angle_rad=None,
                    max_linear_speed_mps=command.speed_mps,
                    max_angular_speed_rad_s=self.config.max_wz,
                    max_duration_ms=round(timeout_s * 1000.0),
                    run_id=command.run_id,
                    effect_id=command.effect_id,
                    request_id=command.request_id,
                )
            )
            return
        initial = await self.adapter.state()
        start_x = initial.pose.x
        start_y = initial.pose.y
        target = abs(command.distance_m)
        direction = math.copysign(1.0, command.distance_m)
        timeout_at = time.monotonic() + max(3.0, target / command.speed_mps * 2.5 + 2.0)
        period = 1.0 / self.config.motion_hz

        while True:
            state = await self.adapter.state()
            travelled = math.hypot(state.pose.x - start_x, state.pose.y - start_y)
            remaining = target - travelled
            if remaining <= self.config.move_tolerance_m:
                return
            if time.monotonic() >= timeout_at:
                raise TimeoutError("move did not reach its target before timeout")

            speed = min(command.speed_mps, max(0.04, remaining * 1.4))
            await self._apply_velocity(
                direction * speed,
                0.0,
                0.0,
                self.config.motion_ttl_ms,
            )
            await asyncio.sleep(period)

    async def _run_turn(self, command: TurnCommand) -> None:
        if isinstance(self.adapter, DeviceBoundedMotionAdapter):
            angle_rad = math.radians(command.angle_deg)
            timeout_s = max(3.0, abs(angle_rad) / command.speed_rad_s * 2.5 + 2.0)
            await self.adapter.execute_bounded_motion(
                BoundedMotionGoal(
                    motion_id=self._bounded_motion_id(command.request_id),
                    kind="rotate",
                    distance_m=None,
                    angle_rad=angle_rad,
                    max_linear_speed_mps=self.config.max_vx,
                    max_angular_speed_rad_s=command.speed_rad_s,
                    max_duration_ms=round(timeout_s * 1000.0),
                    run_id=command.run_id,
                    effect_id=command.effect_id,
                    request_id=command.request_id,
                )
            )
            return
        state = await self.adapter.state()
        previous_yaw = state.pose.yaw
        accumulated = 0.0
        target = abs(math.radians(command.angle_deg))
        direction = math.copysign(1.0, command.angle_deg)
        timeout_at = time.monotonic() + max(3.0, target / command.speed_rad_s * 2.5 + 2.0)
        period = 1.0 / self.config.motion_hz

        while True:
            state = await self.adapter.state()
            yaw_delta = math.atan2(
                math.sin(state.pose.yaw - previous_yaw),
                math.cos(state.pose.yaw - previous_yaw),
            )
            accumulated += yaw_delta
            previous_yaw = state.pose.yaw
            remaining = target - direction * accumulated
            if remaining <= self.config.turn_tolerance_rad:
                return
            if time.monotonic() >= timeout_at:
                raise TimeoutError("turn did not reach its target before timeout")

            speed = min(command.speed_rad_s, max(0.10, remaining * 1.6))
            await self._apply_velocity(
                0.0,
                0.0,
                direction * speed,
                self.config.motion_ttl_ms,
            )
            await asyncio.sleep(period)

    def _bounded_motion_id(self, request_id: str) -> str:
        correlation = "\x1f".join(
            (
                self._motion_run_id or "",
                self._motion_effect_id or "",
                request_id,
            )
        )
        return hashlib.sha256(correlation.encode()).hexdigest()[:32]

    async def _cancel_motion_for_client(self, client_id: str) -> None:
        if not await self._require_owner(client_id):
            return
        if not await self._cancel_motion("mission cancelled"):
            await self.broadcast(EventMessage(event="motion_idle"))

    async def _cancel_motion(self, reason: str, notify: bool = True) -> bool:
        task = self._motion_task
        if task is None or task.done() or task is asyncio.current_task():
            return False
        client_id = self._motion_client_id
        request_id = self._motion_request_id
        kind = self._motion_kind
        run_id = self._motion_run_id
        effect_id = self._motion_effect_id
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if notify and client_id and request_id and kind:
            cancelled = MotionMessage(
                request_id=request_id,
                run_id=run_id,
                effect_id=effect_id,
                motion=kind,
                status="cancelled",
                detail=reason,
            )
            self._last_motion = cancelled.model_dump(mode="json")
            await self._send(client_id, cancelled)
            await self.broadcast(EventMessage(event="motion_cancelled", detail=reason))
        return True

    async def _clear_command_deadline(self) -> None:
        async with self._lock:
            self.command_deadline = None
            self.last_command_at = None

    async def _require_owner(self, client_id: str) -> bool:
        if self.owner_client_id == client_id:
            return True
        await self._error(client_id, "not_controller", "Acquire control before sending commands")
        return False

    async def _safety_loop(self) -> None:
        period = 1.0 / self.config.safety_hz
        while True:
            await asyncio.sleep(period)
            expired = False
            now = time.monotonic()
            async with self._lock:
                if self.command_deadline is not None and now >= self.command_deadline:
                    self.command_deadline = None
                    self.last_command_at = None
                    expired = True
            if expired:
                await self._cancel_motion("command TTL expired")
                confirmed = await self._operator_stop("command TTL expired")
                await self.broadcast(
                    EventMessage(event="command_ttl_expired", detail=(
                        "Rover stopped" if confirmed else "Physical stop unconfirmed"
                    ))
                )
            await self._expire_path_clearance(now)
            obstacle = await self.front_obstacle_snapshot()
            await self._publish_front_obstacle(obstacle, event="freshness_check")
            await self._enforce_front_obstacle(obstacle)
            self._mark_loop_success("safety")

    async def _state_loop(self) -> None:
        period = 1.0 / self.config.state_hz
        while True:
            await asyncio.sleep(period)
            age_ms = None
            if self.last_command_at is not None:
                age_ms = (time.monotonic() - self.last_command_at) * 1000.0
            state = await self.adapter.state(command_age_ms=age_ms)
            if getattr(self.adapter, "requires_rearm", False) and not self.estop_latched:
                self.estop_latched = True
                await self._broadcast_control()
            state = self.pose_fusion.apply(state)
            if self.log:
                self.log.record("state", "rover_state", state.model_dump(mode="json"))
            await self.broadcast(StateMessage(state=state))
            self._mark_loop_success("state")

    async def _supervise_loop(
        self,
        name: str,
        operation_factory: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        health = self._loop_health[name]
        health.running = True
        health.started_at = time.time()
        health.error = None
        try:
            while True:
                try:
                    await operation_factory()
                    health.error = "loop exited unexpectedly"
                except asyncio.CancelledError:
                    if not self._closing:
                        health.error = "loop cancelled unexpectedly"
                    raise
                except Exception as exc:
                    health.error = f"{type(exc).__name__}: {exc}"

                with contextlib.suppress(Exception):
                    await self.adapter.stop()
                if self.log:
                    with contextlib.suppress(Exception):
                        self.log.record(
                            "runtime_health",
                            "background_loop_failed",
                            {"loop": name, "error": health.error},
                        )
                if self._closing:
                    return
                health.restart_count += 1
                await asyncio.sleep(0.1)
        finally:
            health.running = False

    def _mark_loop_success(self, name: str) -> None:
        now = time.time()
        health = self._loop_health[name]
        health.last_tick_at = now
        health.last_success_at = now
        health.error = None
        self._loop_ready[name].set()

    async def status(self) -> dict[str, object]:
        now = time.time()
        adapter_error: str | None = None
        adapter_state = None
        try:
            adapter_state = await asyncio.wait_for(
                self.adapter.state(),
                timeout=self.config.adapter_status_timeout_s,
            )
        except Exception as exc:
            adapter_error = f"{type(exc).__name__}: {exc}"

        loop_status: dict[str, dict[str, object]] = {}
        loops_ready = True
        loop_periods = {
            "safety": 1.0 / self.config.safety_hz,
            "state": 1.0 / self.config.state_hz,
        }
        for name, health in self._loop_health.items():
            stale_after_s = max(1.0, loop_periods[name] * 5.0)
            age_s = None if health.last_success_at is None else now - health.last_success_at
            healthy = (
                health.running
                and health.error is None
                and age_s is not None
                and age_s <= stale_after_s
            )
            loops_ready = loops_ready and healthy
            loop_status[name] = {
                "running": health.running,
                "healthy": healthy,
                "started_at": health.started_at,
                "last_tick_at": health.last_tick_at,
                "last_success_at": health.last_success_at,
                "last_success_age_s": age_s,
                "stale_after_s": stale_after_s,
                "error": health.error,
                "restart_count": health.restart_count,
            }

        log_health = (
            self.log.health()
            if self.log is not None
            else {"enabled": False, "healthy": True, "error": None}
        )
        adapter_ready = (
            adapter_error is None and adapter_state is not None and adapter_state.connected
        )
        ready = (
            self._started_at is not None
            and not self._closing
            and loops_ready
            and adapter_ready
            and bool(log_health["healthy"])
        )

        async with self._lock:
            clients = [
                {
                    "client_id": client_id,
                    "connected_at": connection.connected_at,
                    "last_seen_at": connection.last_seen_at,
                    "registered": connection.registration is not None,
                    **(
                        connection.registration.model_dump(
                            mode="json",
                            exclude={"v", "type"},
                        )
                        if connection.registration is not None
                        else {}
                    ),
                }
                for client_id, connection in self.clients.items()
            ]
            command_deadline_remaining_ms = (
                None
                if self.command_deadline is None
                else max(0.0, (self.command_deadline - time.monotonic()) * 1000.0)
            )
            owner_client_id = self.owner_client_id
            estop_latched = self.estop_latched
            owner_connection = (
                self.clients.get(owner_client_id) if owner_client_id is not None else None
            )
            owner_registration = (
                owner_connection.registration if owner_connection is not None else None
            )
            bridge_run_id = (
                owner_registration.session_id
                if owner_registration is not None
                and owner_registration.client_kind == "physicode_bridge"
                else None
            )
            active_run_id = self._motion_run_id or bridge_run_id
            active_effect_id = self._motion_effect_id
            last_motion = dict(self._last_motion) if self._last_motion is not None else None
            active_motion = (
                None
                if self._motion_task is None
                else {
                    "request_id": self._motion_request_id,
                    "kind": self._motion_kind,
                    "client_id": self._motion_client_id,
                    "run_id": self._motion_run_id,
                    "effect_id": self._motion_effect_id,
                }
            )

        recent_fault = adapter_error or log_health.get("error")
        if recent_fault is None:
            recent_fault = next(
                (health["error"] for health in loop_status.values() if health["error"]),
                None,
            )

        config_payload = asdict(self.config)
        config_hash = hashlib.sha256(
            json.dumps(config_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        return {
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "timestamp": now,
            "uptime_s": None if self._started_at is None else now - self._started_at,
            "server": asdict(self.metadata),
            "config": {
                "hash": config_hash,
                "effective_safety_limits": {
                    "max_vx_mps": self.config.max_vx,
                    "max_vy_mps": self.config.max_vy,
                    "max_wz_rad_s": self.config.max_wz,
                    "motion_ttl_ms": self.config.motion_ttl_ms,
                },
            },
            "front_obstacle": (await self.front_obstacle_snapshot()).model_dump(mode="json"),
            "adapter": {
                "type": self.metadata.adapter_type,
                "healthy": adapter_ready,
                "connected": bool(adapter_state and adapter_state.connected),
                "capabilities": (
                    adapter_state.capabilities.model_dump(mode="json")
                    if adapter_state is not None
                    else None
                ),
                "state": (
                    adapter_state.model_dump(mode="json") if adapter_state is not None else None
                ),
                "error": adapter_error,
            },
            "loops": loop_status,
            "log": log_health,
            "clients": clients,
            "control": {
                "owner_client_id": owner_client_id,
                "estop_latched": estop_latched,
                "command_deadline_remaining_ms": command_deadline_remaining_ms,
            },
            "recent_fault": recent_fault,
            "active_execution": {
                "mission_id": None,
                "mission_status_source": "not_available_browser_local",
                "run_status_source": (
                    "physicode_bridge" if bridge_run_id is not None else "not_available"
                ),
                "run_id": active_run_id,
                "effect_id": active_effect_id,
                "motion": active_motion,
                "last_motion": last_motion,
            },
        }

    async def _operator_stop(self, reason: str) -> bool:
        try:
            await self._stop_adapter(reason)
            return True
        except Exception as exc:
            async with self._lock:
                self.estop_latched = True
                self.command_deadline = None
                self.last_command_at = None
            if self.log:
                self.log.record("adapter_command", "stop_unconfirmed", {
                    "reason": reason, "error": type(exc).__name__, "detail": str(exc),
                })
            await self._broadcast_control()
            await self.broadcast(EventMessage(
                event="stop_unconfirmed",
                detail="Physical stop unconfirmed; emergency stop remains latched",
            ))
            return False

    async def _stop_adapter(self, reason: str) -> None:
        await self.adapter.stop()
        async with self._lock:
            self._commanded_vx = 0.0
        if self.log:
            self.log.record("adapter_command", "stop", {"reason": reason})

    async def prepare_simulator_scenario(self, reason: str) -> None:
        """Stop active control work before development-only Simulator input starts."""
        await self._cancel_motion(reason)
        await self._stop_adapter(reason)
        await self._clear_command_deadline()
        self.pose_fusion.reset()
        await self.broadcast(EventMessage(event="simulator_run_prepared", detail=reason))

    async def _send_control(self, client_id: str) -> None:
        await self._send(
            client_id,
            ControlMessage(
                owner_client_id=self.owner_client_id,
                is_owner=self.owner_client_id == client_id,
                estop_latched=self.estop_latched,
            ),
        )

    async def _broadcast_control(self) -> None:
        for client_id in list(self.clients):
            await self._send_control(client_id)

    async def _error(self, client_id: str, code: str, detail: str) -> None:
        await self._send(client_id, ErrorMessage(code=code, detail=detail))

    async def _send(self, client_id: str, message: BaseModel) -> None:
        connection = self.clients.get(client_id)
        if connection is None:
            return
        try:
            await connection.websocket.send_text(message.model_dump_json())
            unlogged_types = (
                StateMessage,
                EventMessage,
                ScenarioEventMessage,
                PerceptionEventMessage,
            )
            if self.log and not isinstance(message, unlogged_types):
                self.log.record(
                    "server_message",
                    str(getattr(message, "type", message.__class__.__name__)),
                    {"client_id": client_id, "message": message.model_dump(mode="json")},
                )
        except (RuntimeError, WebSocketDisconnect):
            pass

    async def broadcast(self, message: BaseModel) -> None:
        if self.log and isinstance(message, EventMessage):
            self.log.record("server_event", message.event, {"detail": message.detail})
        for client_id in list(self.clients):
            await self._send(client_id, message)
