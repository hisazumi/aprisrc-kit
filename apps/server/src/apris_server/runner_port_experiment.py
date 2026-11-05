"""Local JSON-lines experiment. Always constructs a fake; never loads a hardware adapter."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any

from .adapter import BoundedMotionGoal, BoundedMotionResult, DeviceBoundedMotionAdapter
from .front_obstacle import FrontObstacleObservationInput
from .runtime import RoverRuntime
from .simulator import DifferentialDriveSimulator


class PortFakeAdapter(DifferentialDriveSimulator, DeviceBoundedMotionAdapter):
    """Synthetic bounded operation and independently delayed stop evidence; no odometry claim."""

    def __init__(self) -> None:
        super().__init__()
        self.evidence_delay = 0.0
        self.evidence_at = 0.0
        self.evidence = asyncio.Event()
        self.evidence.set()
        self.evidence_timer: asyncio.TimerHandle | None = None
        self.actuating = False
        self.goals: list[BoundedMotionGoal] = []

    async def execute_bounded_motion(self, goal: BoundedMotionGoal) -> BoundedMotionResult:
        self.goals.append(goal)
        self.actuating = True
        self.evidence_at = math.inf
        self.evidence.clear()
        # Fake time is derived from the SI bounded goal, not a hardware timing model.
        duration = abs(goal.distance_m or 0) / goal.max_linear_speed_mps
        try:
            await asyncio.sleep(duration)
            await self.stop()
            return BoundedMotionResult(goal.motion_id, "completed", None)
        finally:
            self.actuating = False

    async def stop(self) -> None:
        await super().stop()
        self.actuating = False
        self.evidence_at = time.monotonic() + self.evidence_delay
        self.evidence.clear()
        if self.evidence_timer:
            self.evidence_timer.cancel()
        if math.isfinite(self.evidence_delay):
            self.evidence_timer = asyncio.get_running_loop().call_later(
                self.evidence_delay, self.evidence.set
            )

    async def close(self) -> None:
        if self.evidence_timer:
            self.evidence_timer.cancel()
        await super().close()


class Inbox:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def send_text(self, text: str) -> None:
        message = json.loads(text)
        if message["type"] in {"motion", "error"}:
            self.messages.put_nowait(message)


class RunnerPort:
    lease_s = 0.4
    command_ttl_s = 0.25
    progress_s = 1.2
    stop_s = 0.2

    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self.emit = emit
        self.adapter = PortFakeAdapter()
        self.runtime = RoverRuntime(self.adapter)
        self.inbox = Inbox()
        self.session: str | None = None
        self.client: str | None = None
        self.generation = 0
        self.lease = 0.0
        self.operation: dict[str, Any] | None = None
        self.guard: str | None = None
        self.inhibited = False
        self.lock = asyncio.Lock()
        self.tasks: list[asyncio.Task[None]] = []
        self.finishing: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.runtime.start()
        self.tasks = [asyncio.create_task(self._watch()), asyncio.create_task(self._events())]

    async def _send(self, message: dict[str, Any]) -> None:
        if self.client is None:
            raise ValueError("no-client")
        await self.runtime.handle_text(self.client, json.dumps(message))

    def _valid(self, session: str | None) -> None:
        if session is None or session != self.session or time.monotonic() >= self.lease:
            raise ValueError("revoked-session")

    def _token(self, token: dict[str, Any]) -> None:
        self._valid(token.get("session"))
        if self.operation is None or token != self.operation["token"]:
            raise ValueError("stale-motion")

    async def request(self, message: dict[str, Any]) -> Any:
        async with self.lock:
            action = message["action"]
            if action == "admit":
                if self.session or self.operation or self.guard or self.inhibited:
                    raise ValueError("admission-inhibited")
                self.client = await self.runtime.add_client(self.inbox)  # type: ignore[arg-type]
                session = uuid.uuid4().hex
                await self._send(
                    {
                        "type": "client_hello",
                        "client_kind": "service_app",
                        "device_id": "fake-runner",
                        "session_id": session,
                        "app_version": "experiment",
                        "build_id": "fake-only",
                    }
                )
                await self._send({"type": "acquire_control"})
                if self.runtime.owner_client_id != self.client:
                    await self.runtime.remove_client(self.client)
                    self.client = None
                    raise ValueError("control-busy")
                self.session = session
                self.lease = time.monotonic() + self.lease_s
                return session
            if action == "snapshot":
                return {
                    "target": "fake-only",
                    "session": self.session,
                    "guard": self.guard,
                    "inhibited": self.inhibited,
                    "moving": self.adapter.actuating,
                    "owner": self.runtime.owner_client_id,
                    "operation": self.operation,
                }
            if action == "revoke":
                await self._revoke(message.get("reason", "operator-stop"))
                return None
            if action == "recover":
                if (
                    message.get("confirmed") is not True
                    or self.session
                    or self.operation
                    or self.adapter.actuating
                ):
                    raise ValueError("recovery-not-ready")
                self.guard = None
                self.inhibited = False
                return None
            if action == "fixture":
                # Explicit trusted test input; not a capability available to service code.
                if "evidenceDelay" in message:
                    delay = message["evidenceDelay"]
                    if delay == "missing":
                        self.adapter.evidence_delay = math.inf
                    elif isinstance(delay, (int, float)) and math.isfinite(delay) and delay >= 0:
                        self.adapter.evidence_delay = delay
                    else:
                        raise ValueError("invalid-evidence-delay")
                if "front" in message:
                    await self.runtime.ingest_front_obstacle(
                        FrontObstacleObservationInput(
                            state=message["front"],
                            perception_health="healthy",
                            source="manual",
                            confidence=1.0,
                        )
                    )
                return None
            self._valid(message.get("session"))
            if action == "heartbeat":
                self.lease = time.monotonic() + self.lease_s
                if message.get("token"):
                    self._token(message["token"])
                    if not self.operation["finishing"]:
                        self.operation["ttl"] = time.monotonic() + self.command_ttl_s
                return None
            if action == "move":
                if self.operation or self.guard or self.inhibited:
                    raise ValueError("motion-inhibited")
                duration = message["duration"]
                if (
                    type(duration) not in (int, float)
                    or not math.isfinite(duration)
                    or not 0 < duration <= 1
                ):
                    raise ValueError("invalid-duration")
                self.generation += 1
                token = {"session": self.session, "generation": self.generation}
                now = time.monotonic()
                self.operation = {
                    "token": token,
                    "request": str(self.generation),
                    "ttl": now + self.command_ttl_s,
                    "deadline": now + self.progress_s,
                    "finishing": False,
                    "override": None,
                }
                await self._send(
                    {
                        "type": "move",
                        "request_id": str(self.generation),
                        "run_id": self.session,
                        "effect_id": str(self.generation),
                        "distance_m": duration * 0.1,
                        "speed_mps": 0.1,
                    }
                )
                return token  # Accepted by port; runtime may still reject with a terminal result.
            if action == "stop":
                self._token(message["token"])
                self.operation["override"] = "cancelled"
                await self._send({"type": "cancel_motion"})
                self._finish("cancelled", "scoped-stop")
                return None
            if action == "hold":
                if self.operation or self.guard or self.inhibited:
                    raise ValueError("not-stationary")
                self.guard = self.session
                return None
            if action == "clear":
                if self.guard != self.session or message.get("confirmed") is not True:
                    raise ValueError("clearance-required")
                self.guard = None
                return None
            raise ValueError("unsupported-action")

    async def _revoke(self, reason: str) -> None:
        session, self.session = self.session, None  # Fence before awaiting runtime stop.
        if self.operation:
            self.operation["override"] = "interrupted"
        if self.client:
            client, self.client = self.client, None
            await self.runtime.remove_client(client)
        self._finish("interrupted", reason)
        if session:
            self.emit({"kind": "revoked", "reason": reason})

    def _finish(self, status: str, reason: str) -> None:
        op = self.operation
        if op is None or op["finishing"]:
            return
        op["finishing"] = True
        self.finishing = asyncio.create_task(self._evidence(op, status, reason))

    async def _evidence(self, op: dict[str, Any], status: str, reason: str) -> None:
        deadline = time.monotonic() + self.stop_s
        try:
            await asyncio.wait_for(self.adapter.evidence.wait(), timeout=self.stop_s)
        except TimeoutError:
            pass
        async with self.lock:
            if self.operation is not op:
                return
            confirmed = self.adapter.evidence_at <= deadline and not self.adapter.actuating
            status = op["override"] or status
            self.operation = None
            if not confirmed:
                status, reason = "stop-unconfirmed", "stop-evidence-timeout"
                self.inhibited = True
                await self._revoke(reason)
            self.emit(
                {
                    "kind": "terminal",
                    "event": {
                        "token": op["token"],
                        "status": status,
                        "reason": reason,
                        "evidence": "fake-stop" if confirmed else None,
                    },
                }
            )

    async def _events(self) -> None:
        while True:
            message = await self.inbox.messages.get()
            async with self.lock:
                op = self.operation
                if not op or message.get("request_id") != op["request"]:
                    continue
                status = message.get("status")
                if status == "started":
                    self.emit({"kind": "running", "token": op["token"]})
                elif status in {"completed", "failed", "cancelled"}:
                    self._finish(status, message.get("detail") or "runtime-" + status)

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(0.01)
            async with self.lock:
                now = time.monotonic()
                if self.session and now >= self.lease:
                    await self._revoke("lease-expired")
                elif self.operation and not self.operation["finishing"]:
                    if now >= self.operation["ttl"]:
                        await self._revoke("command-ttl")
                    elif now >= self.operation["deadline"]:
                        await self._revoke("progress-deadline")

    async def close(self) -> None:
        async with self.lock:
            await self._revoke("port-closed")
        if self.finishing:
            await self.finishing
        for task in self.tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self.runtime.close()


async def main() -> None:
    def emit(value: dict[str, Any]) -> None:
        print(json.dumps(value, allow_nan=False), flush=True)

    port = RunnerPort(emit)
    await port.start()
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            request: dict[str, Any] = {}
            try:
                request = json.loads(line)
                value = await port.request(request)
                emit(
                    {
                        "kind": "reply",
                        "id": request.get("id"),
                        "channel": request.get("channel"),
                        "ok": True,
                        "value": value,
                    }
                )
            except (ValueError, KeyError, TypeError) as error:
                emit(
                    {
                        "kind": "reply",
                        "id": request.get("id"),
                        "channel": request.get("channel"),
                        "ok": False,
                        "error": str(error),
                    }
                )
    finally:
        await port.close()


if __name__ == "__main__":
    asyncio.run(main())
