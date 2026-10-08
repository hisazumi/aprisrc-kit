from __future__ import annotations

import asyncio
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .rover_protocol import (
    RoverCommandAck,
    RoverCommandEnvelope,
    RoverEvent,
    RoverHeartbeat,
    RoverHello,
    RoverMotionStatus,
    RoverSessionInbound,
    RoverTelemetry,
    RoverWelcome,
    ServerRoverCommand,
)
from .structured_log import StructuredLog


class RoverProtocolError(Exception):
    def __init__(self, code: str, detail: str, close_code: int = 4400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.close_code = close_code


class RoverUnavailableError(RuntimeError):
    pass


class RoverCommandRejectedError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(slots=True)
class RoverSession:
    rover_id: str
    boot_id: str
    connection_epoch: str
    websocket: WebSocket | None
    hello: RoverHello
    connected_at: float
    last_seen_at: float
    last_rover_seq: int = -1
    last_server_seq: int = -1
    latest_heartbeat: RoverHeartbeat | None = None
    latest_heartbeat_at: float | None = None
    latest_telemetry: RoverTelemetry | None = None
    latest_telemetry_at: float | None = None
    latest_command_ack: RoverCommandAck | None = None
    latest_motion_status: RoverMotionStatus | None = None
    latest_event: RoverEvent | None = None
    pending_commands: dict[str, asyncio.Future[RoverCommandAck]] = field(default_factory=dict)
    motion_waiters: dict[str, asyncio.Future[RoverMotionStatus]] = field(default_factory=dict)

    @property
    def connected(self) -> bool:
        return self.websocket is not None


class RoverRegistry:
    def __init__(
        self,
        auth_token: str | None,
        *,
        structured_log: StructuredLog | None = None,
        heartbeat_interval_ms: int = 500,
        clock_uncertainty_limit_ms: int = 100,
    ) -> None:
        self._auth_token = auth_token
        self._log = structured_log
        self._heartbeat_interval_ms = heartbeat_interval_ms
        self._clock_uncertainty_limit_ms = clock_uncertainty_limit_ms
        self._heartbeat_stale_after_s = heartbeat_interval_ms * 3.0 / 1000.0
        self._sessions: dict[str, RoverSession] = {}
        self._lock = asyncio.Lock()

    @property
    def credential_configured(self) -> bool:
        return bool(self._auth_token)

    def authorize(self, authorization_header: str | None) -> bool:
        if not self._auth_token or authorization_header is None:
            return False
        scheme, separator, candidate = authorization_header.partition(" ")
        return (
            bool(separator)
            and scheme.lower() == "bearer"
            and hmac.compare_digest(candidate, self._auth_token)
        )

    async def connect(
        self,
        websocket: WebSocket,
        hello: RoverHello,
        *,
        server_version: str,
        build_id: str,
        instance_id: str,
    ) -> RoverWelcome:
        if 1 not in hello.protocol_versions:
            raise RoverProtocolError(
                "unsupported_protocol_version",
                "Rover and server have no supported protocol version in common",
                4406,
            )
        now = time.time()
        async with self._lock:
            existing = self._sessions.get(hello.rover_id)
            if existing is not None and existing.connected:
                raise RoverProtocolError(
                    "duplicate_rover_id",
                    "Another connection is already registered for this rover_id",
                    4409,
                )
            epoch = uuid.uuid4().hex
            session = RoverSession(
                rover_id=hello.rover_id,
                boot_id=hello.boot_id,
                connection_epoch=epoch,
                websocket=websocket,
                hello=hello,
                connected_at=now,
                last_seen_at=now,
            )
            self._sessions[hello.rover_id] = session
        self._record(
            "rover_connected",
            {
                "rover_id": hello.rover_id,
                "boot_id": hello.boot_id,
                "connection_epoch": epoch,
                "firmware_version": hello.firmware_version,
                "build_id": hello.build_id,
            },
        )
        return RoverWelcome(
            rover_id=hello.rover_id,
            boot_id=hello.boot_id,
            connection_epoch=epoch,
            server_version=server_version,
            build_id=build_id,
            instance_id=instance_id,
            heartbeat_interval_ms=self._heartbeat_interval_ms,
            clock_uncertainty_limit_ms=self._clock_uncertainty_limit_ms,
        )

    async def handle(
        self,
        rover_id: str,
        connection_epoch: str,
        message: RoverSessionInbound,
    ) -> None:
        async with self._lock:
            session = self._sessions.get(rover_id)
            if session is None or not session.connected:
                raise RoverProtocolError("rover_not_registered", "Rover session is not active")
            if session.connection_epoch != connection_epoch:
                raise RoverProtocolError("stale_connection_epoch", "Connection epoch is stale")
            if message.rover_id != rover_id or message.connection_epoch != connection_epoch:
                raise RoverProtocolError(
                    "session_identity_mismatch",
                    "Message identity does not match the registered rover session",
                )
            if message.boot_id != session.boot_id:
                raise RoverProtocolError(
                    "boot_id_mismatch",
                    "Message boot_id does not match the registered rover session",
                )
            if message.seq <= session.last_rover_seq:
                raise RoverProtocolError(
                    "non_increasing_rover_sequence",
                    "Rover message sequence must increase within a connection epoch",
                )
            session.last_rover_seq = message.seq
            session.last_seen_at = time.time()
            if isinstance(message, RoverHeartbeat):
                session.latest_heartbeat = message
                session.latest_heartbeat_at = session.last_seen_at
            elif isinstance(message, RoverTelemetry):
                session.latest_telemetry = message
                session.latest_telemetry_at = session.last_seen_at
            elif isinstance(message, RoverCommandAck):
                session.latest_command_ack = message
                pending = session.pending_commands.get(message.command_id)
                if pending is not None and not pending.done():
                    pending.set_result(message)
            elif isinstance(message, RoverMotionStatus):
                session.latest_motion_status = message
                if message.status in {"completed", "cancelled", "failed"}:
                    waiter = session.motion_waiters.get(message.motion_id)
                    if waiter is not None and not waiter.done():
                        waiter.set_result(message)
            elif isinstance(message, RoverEvent):
                session.latest_event = message
        payload: dict[str, object] = {
            "rover_id": rover_id,
            "connection_epoch": connection_epoch,
            "seq": message.seq,
            "type": message.type,
        }
        if isinstance(message, RoverTelemetry):
            payload.update(
                {
                    "linear_velocity_mps": message.linear_velocity_mps,
                    "angular_velocity_rad_s": message.angular_velocity_rad_s,
                    "motor_state": message.motor_state,
                }
            )
        elif isinstance(message, RoverCommandAck):
            payload.update(
                {
                    "command_id": message.command_id,
                    "status": message.status,
                    "code": message.code,
                }
            )
        elif isinstance(message, RoverEvent):
            payload.update({"event": message.event, "detail": message.detail})
        self._record("rover_message", payload)

    async def disconnect(self, rover_id: str, connection_epoch: str) -> None:
        disconnected = False
        async with self._lock:
            session = self._sessions.get(rover_id)
            if (
                session is not None
                and session.connected
                and session.connection_epoch == connection_epoch
            ):
                session.websocket = None
                session.last_seen_at = time.time()
                error = RoverUnavailableError("rover connection closed")
                for future in [
                    *session.pending_commands.values(),
                    *session.motion_waiters.values(),
                ]:
                    if not future.done():
                        future.set_exception(error)
                disconnected = True
        if disconnected:
            self._record(
                "rover_disconnected",
                {"rover_id": rover_id, "connection_epoch": connection_epoch},
            )

    async def status(self) -> dict[str, object]:
        now = time.time()
        async with self._lock:
            rovers = [self._session_status(session, now) for session in self._sessions.values()]
        return {
            "credential_configured": self.credential_configured,
            "connected_count": sum(bool(rover["connected"]) for rover in rovers),
            "items": sorted(rovers, key=lambda rover: str(rover["rover_id"])),
        }

    async def dispatch(
        self,
        rover_id: str,
        command_type: type[RoverCommandEnvelope],
        *,
        ttl_ms: int = 500,
        ack_timeout_s: float = 0.4,
        require_healthy: bool = True,
        **payload: object,
    ) -> tuple[ServerRoverCommand, RoverCommandAck]:
        loop = asyncio.get_running_loop()
        command_id = uuid.uuid4().hex
        async with self._lock:
            session = self._require_connected_session(rover_id)
            if require_healthy:
                self._require_fresh_heartbeat(session, time.time())
            session.last_server_seq += 1
            command = command_type(
                connection_epoch=session.connection_epoch,
                seq=session.last_server_seq,
                command_id=command_id,
                issued_at_ms=int(time.time() * 1000.0),
                ttl_ms=ttl_ms,
                **payload,
            )
            future: asyncio.Future[RoverCommandAck] = loop.create_future()
            session.pending_commands[command_id] = future
            websocket = session.websocket
            epoch = session.connection_epoch
        if websocket is None:
            raise RoverUnavailableError("rover disconnected before command send")
        command_log = {
            "rover_id": rover_id,
            "connection_epoch": epoch,
            "command_id": command_id,
            "command_type": command.type,
            "seq": command.seq,
            "ttl_ms": command.ttl_ms,
        }
        started_at = time.monotonic()
        try:
            await websocket.send_json(command.model_dump(mode="json"))
            self._record("command_sent", command_log)
            acknowledgement = await asyncio.wait_for(future, timeout=ack_timeout_s)
            self._record(
                "command_acknowledged",
                {
                    **command_log,
                    "latency_ms": round((time.monotonic() - started_at) * 1000.0, 3),
                    "status": acknowledgement.status,
                    "code": acknowledgement.code,
                },
            )
        except asyncio.CancelledError:
            self._record(
                "command_cancelled",
                {
                    **command_log,
                    "latency_ms": round((time.monotonic() - started_at) * 1000.0, 3),
                },
            )
            raise
        except TimeoutError as exc:
            self._record(
                "command_ack_timeout",
                {
                    **command_log,
                    "latency_ms": round((time.monotonic() - started_at) * 1000.0, 3),
                },
            )
            raise RoverUnavailableError(
                f"command acknowledgement timed out: {command.type}"
            ) from exc
        except Exception as exc:
            if isinstance(exc, RoverUnavailableError):
                raise
            self._record(
                "command_send_failed",
                {
                    **command_log,
                    "latency_ms": round((time.monotonic() - started_at) * 1000.0, 3),
                    "error": type(exc).__name__,
                },
            )
            raise RoverUnavailableError(f"command send failed: {command.type}") from exc
        finally:
            async with self._lock:
                current = self._sessions.get(rover_id)
                if current is not None and current.connection_epoch == epoch:
                    current.pending_commands.pop(command_id, None)
        if acknowledgement.status == "rejected":
            raise RoverCommandRejectedError(
                acknowledgement.code or "command_rejected",
                acknowledgement.detail,
            )
        return command, acknowledgement

    async def require_healthy(self, rover_id: str) -> None:
        async with self._lock:
            session = self._require_connected_session(rover_id)
            self._require_fresh_heartbeat(session, time.time())

    async def create_motion_waiter(
        self,
        rover_id: str,
        motion_id: str,
    ) -> asyncio.Future[RoverMotionStatus]:
        loop = asyncio.get_running_loop()
        async with self._lock:
            session = self._require_connected_session(rover_id)
            existing = session.motion_waiters.get(motion_id)
            if existing is not None and not existing.done():
                raise RuntimeError(f"motion waiter already exists: {motion_id}")
            waiter: asyncio.Future[RoverMotionStatus] = loop.create_future()
            session.motion_waiters[motion_id] = waiter
            return waiter

    async def release_motion_waiter(self, rover_id: str, motion_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(rover_id)
            if session is not None:
                session.motion_waiters.pop(motion_id, None)

    async def rover_snapshot(self, rover_id: str) -> dict[str, Any]:
        now = time.time()
        async with self._lock:
            session = self._sessions.get(rover_id)
            if session is None:
                raise RoverUnavailableError(f"unknown rover_id: {rover_id}")
            return self._session_status(session, now)

    async def close(self) -> None:
        async with self._lock:
            sockets = [
                session.websocket for session in self._sessions.values() if session.connected
            ]
            for session in self._sessions.values():
                session.websocket = None
                error = RoverUnavailableError("rover registry closed")
                for future in [
                    *session.pending_commands.values(),
                    *session.motion_waiters.values(),
                ]:
                    if not future.done():
                        future.set_exception(error)
        for websocket in sockets:
            if websocket is not None:
                try:
                    await websocket.close(code=1001, reason="server shutdown")
                except Exception:
                    pass

    def _session_status(self, session: RoverSession, now: float) -> dict[str, Any]:
        heartbeat_age_s = (
            None
            if session.latest_heartbeat_at is None
            else max(0.0, now - session.latest_heartbeat_at)
        )
        clock_healthy = bool(
            session.latest_heartbeat is not None
            and session.latest_heartbeat.clock_uncertainty_ms
            <= self._clock_uncertainty_limit_ms
        )
        heartbeat_healthy = bool(
            session.connected
            and heartbeat_age_s is not None
            and heartbeat_age_s <= self._heartbeat_stale_after_s
            and clock_healthy
        )
        telemetry_age_s = (
            None
            if session.latest_telemetry_at is None
            else max(0.0, now - session.latest_telemetry_at)
        )
        return {
            "rover_id": session.rover_id,
            "boot_id": session.boot_id,
            "connection_epoch": session.connection_epoch,
            "connected": session.connected,
            "connected_at": session.connected_at,
            "last_seen_at": session.last_seen_at,
            "last_rover_seq": session.last_rover_seq,
            "last_server_seq": session.last_server_seq,
            "heartbeat_age_s": heartbeat_age_s,
            "heartbeat_stale_after_s": self._heartbeat_stale_after_s,
            "heartbeat_healthy": heartbeat_healthy,
            "clock_healthy": clock_healthy,
            "telemetry_age_s": telemetry_age_s,
            "firmware_version": session.hello.firmware_version,
            "build_id": session.hello.build_id,
            "hardware_revision": session.hello.hardware_revision,
            "capabilities": session.hello.capabilities.model_dump(mode="json"),
            "firmware_safety_limits": session.hello.safety_limits.model_dump(mode="json"),
            "heartbeat": (
                session.latest_heartbeat.model_dump(mode="json")
                if session.latest_heartbeat is not None
                else None
            ),
            "telemetry": (
                session.latest_telemetry.model_dump(mode="json")
                if session.latest_telemetry is not None
                else None
            ),
            "latest_command_ack": (
                session.latest_command_ack.model_dump(mode="json")
                if session.latest_command_ack is not None
                else None
            ),
            "latest_motion_status": (
                session.latest_motion_status.model_dump(mode="json")
                if session.latest_motion_status is not None
                else None
            ),
            "latest_event": (
                session.latest_event.model_dump(mode="json")
                if session.latest_event is not None
                else None
            ),
        }

    def _require_connected_session(self, rover_id: str) -> RoverSession:
        session = self._sessions.get(rover_id)
        if session is None or not session.connected:
            raise RoverUnavailableError(f"rover is not connected: {rover_id}")
        return session

    def _require_fresh_heartbeat(self, session: RoverSession, now: float) -> None:
        if session.latest_heartbeat_at is None or session.latest_heartbeat is None:
            raise RoverUnavailableError("rover heartbeat has not been received")
        if now - session.latest_heartbeat_at > self._heartbeat_stale_after_s:
            raise RoverUnavailableError("rover heartbeat is stale")
        if (
            session.latest_heartbeat.clock_uncertainty_ms
            > self._clock_uncertainty_limit_ms
        ):
            raise RoverUnavailableError("rover clock uncertainty exceeds safety limit")

    def _record(self, event: str, payload: dict[str, object]) -> None:
        if self._log is not None:
            self._log.record("rover_connection", event, payload)
