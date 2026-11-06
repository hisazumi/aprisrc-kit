"""Local JSON-lines experiment. Always constructs a fake; never loads a hardware adapter."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import sys
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from .adapter import BoundedMotionGoal, BoundedMotionResult, DeviceBoundedMotionAdapter
from .control_contract import parse_control_message
from .front_obstacle import FrontObstacleObservationInput
from .models import MoveCommand, TurnCommand
from .motion_contract import SCOPE_KEYS, parse_motion_message
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
        duration = (
            abs(goal.distance_m or 0) / goal.max_linear_speed_mps
            if goal.kind == "linear"
            else abs(goal.angle_rad or 0) / goal.max_angular_speed_rad_s
        )
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
    control_capacity = 256
    operator_lease_s = 0.4
    motion_capacity = 256
    lease_s = 0.4
    command_ttl_s = 0.25
    progress_s = 1.2
    stop_s = 0.2

    def __init__(
        self, emit: Callable[[dict[str, Any]], None], *, runtime: RoverRuntime | None = None
    ) -> None:
        self.emit = emit
        if runtime is not None and type(runtime.adapter) is not PortFakeAdapter:
            raise ValueError("runner-port-requires-fake-adapter")
        self._owns_runtime = runtime is None
        self.adapter = runtime.adapter if runtime is not None else PortFakeAdapter()
        self.runtime = runtime or RoverRuntime(self.adapter)
        self._guard_hold: str | None = None
        self._inhibit_hold: str | None = None
        self._guard: str | None = None
        self._inhibited = False
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
        self.io_tasks: set[asyncio.Task[None]] = set()
        self.operation_io: list[asyncio.Task[None]] = []
        self.motion_records: dict[str, dict[str, Any]] = {}
        self.motion_requests: dict[str, tuple[dict, dict]] = {}
        self.motion_run: str | None = None
        self.control_epoch = uuid.uuid4().hex
        self.control_mode = False
        self.control_records: dict[str, tuple[dict, dict | str]] = {}
        self.operator_id: str | None = None
        self.operator_deadline = 0.0
        self.operator_sequence = 0
        self.runner_sequence = 0
        self.guard_id: str | None = None
        self.used_runs: set[str] = set()

    @property
    def guard(self) -> str | None:
        return self._guard

    @guard.setter
    def guard(self, value: str | None) -> None:
        if value is not None and self._guard_hold is None:
            self.runtime.require_stationary_handover()
            self._guard_hold = self.runtime.motion_interlock.hold("runner-handover")
        elif value is None and self._guard_hold is not None:
            self.runtime.motion_interlock.release(self._guard_hold)
            self._guard_hold = None
        self._guard = value

    @property
    def inhibited(self) -> bool:
        return self._inhibited

    @inhibited.setter
    def inhibited(self, value: bool) -> None:
        if value and self._inhibit_hold is None:
            self._inhibit_hold = self.runtime.motion_interlock.hold("runner-inhibited")
        elif not value and self._inhibit_hold is not None:
            self.runtime.motion_interlock.release(self._inhibit_hold)
            self._inhibit_hold = None
        self._inhibited = value

    async def start(self) -> None:
        if self._owns_runtime:
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
            # Enforce expiry here too: a delayed renewal must not beat the watchdog.
            self._expire(time.monotonic())
            return await self._dispatch(message)

    async def _dispatch(self, message: dict[str, Any], *, internal: bool = False) -> Any:
        action = message["action"]
        if action == "control":
            return await self._control(message["message"])
        if (
            self.control_mode
            and not internal
            and action not in {"motion", "fixture", "snapshot", "revoke"}
        ):
            raise ValueError("control-mode-requires-typed-command")
        if action == "admit":
            if self.session or self.operation or self.guard or self.inhibited or self.io_tasks:
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
            self.motion_records.clear()
            self.motion_requests.clear()
            self.motion_run = None
            self.session = session
            self.lease = time.monotonic() + self.lease_s
            return session
        if action == "snapshot":
            return {
                "target": "fake-only",
                "controlEpoch": self.control_epoch,
                "session": self.session,
                "guard": self.guard,
                "inhibited": self.inhibited,
                "moving": self.adapter.actuating,
                "owner": self.runtime.owner_client_id,
                "operation": self.operation,
                "pendingIo": len(self.io_tasks),
            }
        if action == "revoke":
            self._revoke(message.get("reason", "operator-stop"))
            return None
        if action == "recover":
            if (
                message.get("confirmed") is not True
                or self.session
                or self.operation
                or self.adapter.actuating
                or self.io_tasks
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
        if action == "motion":
            return await self._motion(message["message"])
        if action == "heartbeat":
            if message.get("token"):
                self._token(message["token"])
                if not self.operation["finishing"]:
                    self.operation["ttl"] = time.monotonic() + self.command_ttl_s
            self.lease = time.monotonic() + self.lease_s
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
            # Validate the converted SI request before allocating an operation.
            generation = self.generation + 1
            command = MoveCommand(
                type="move",
                request_id=str(generation),
                run_id=self.session,
                effect_id=str(generation),
                distance_m=duration * 0.1,
                speed_mps=0.1,
            )
            self.generation = generation
            token = {"session": self.session, "generation": generation}
            now = time.monotonic()
            self.operation_io = []
            self.operation = {
                "token": token,
                "request": str(generation),
                "ttl": now + self.command_ttl_s,
                "deadline": now + self.progress_s,
                "finishing": False,
                "override": None,
            }
            await self._send(command.model_dump(mode="json"))
            return token  # Accepted by port; runtime may still reject with a terminal result.
        if action == "stop":
            self._token(message["token"])
            self.operation["override"] = "cancelled"
            # Capture the client now; revocation may clear self.client before I/O runs.
            job = self._start_io(
                self.runtime.handle_text(self.client, json.dumps({"type": "cancel_motion"}))
            )
            self.operation_io.append(job)
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

    def _control_reply(self, m: dict) -> dict:
        return parse_control_message(
            dict(
                protocolVersion=1,
                connectionEpoch=self.control_epoch,
                requestId=m["requestId"],
                robotId="fake-only",
                kind="controlReply",
                command=m["kind"],
                operatorId=self.operator_id,
                runId=(self.motion_run or "legacy-" + self.session) if self.session else None,
                runEpoch=self.session,
                guardId=self.guard_id,
                inhibited=self.inhibited,
                stopPending=bool(self.operation or self.io_tasks),
            )
        )

    def _operator(self, m: dict) -> None:
        if not self.operator_id or m["operatorId"] != self.operator_id:
            raise ValueError("revoked-operator")

    def _control_run(self, m: dict) -> None:
        if not self.session or m["runEpoch"] != self.session or m["runId"] != self.motion_run:
            raise ValueError("revoked-run")

    def _stationary_evidence(self) -> None:
        self.runtime.require_stationary_handover()
        if self.operation or self.io_tasks or self.adapter.actuating:
            raise ValueError("stop-pending")
        if not self.adapter.evidence.is_set() or self.adapter.evidence_at > time.monotonic():
            raise ValueError("stop-evidence-required")

    async def _control(self, value: Any) -> dict:
        # request() already checks expiry while holding the shared state lock.
        m = parse_control_message(value)
        kind = m["kind"]
        if kind == "controlReply":
            raise ValueError("wrong-direction")
        if m["connectionEpoch"] != self.control_epoch or m["robotId"] != "fake-only":
            raise ValueError("stale-control-epoch-or-robot")
        # Stop/read paths cannot be blocked by exhausted business-command storage.
        if kind == "globalStop":
            self.inhibited = True
            self._revoke("operator-global-stop")
            return self._control_reply(m)
        if kind == "snapshot":
            return self._control_reply(m)
        if kind == "operatorHeartbeat":
            self._operator(m)
            if m["sequence"] > self.operator_sequence:
                self.operator_sequence = m["sequence"]
                self.operator_deadline = time.monotonic() + self.operator_lease_s
            return self._control_reply(m)
        if kind == "runnerHeartbeat":
            self._control_run(m)
            if m["sequence"] > self.runner_sequence:
                self.runner_sequence = m["sequence"]
                self.lease = time.monotonic() + self.lease_s
            return self._control_reply(m)
        old = self.control_records.get(m["requestId"])
        if old:
            if old[0] != m:
                raise ValueError("id-conflict")
            if isinstance(old[1], str):
                raise ValueError(old[1])
            return old[1].copy()  # Historical acknowledgement, never re-execute it.
        if len(self.control_records) >= self.control_capacity:
            raise ValueError("control-capacity-exhausted")
        try:
            await self._apply_control(m)
        except ValueError as error:
            self.control_records[m["requestId"]] = (m, str(error))
            raise
        result = self._control_reply(m)
        self.control_records[m["requestId"]] = (m, result)
        return result.copy()

    async def _apply_control(self, m: dict) -> None:
        kind = m["kind"]
        if kind == "openOperator":
            if self.operator_id or self.session or self.operation or self.io_tasks:
                raise ValueError("operator-admission-busy")
            self.control_mode = True
            self.inhibited = True  # Fresh authority requires explicit recovery.
            self.operator_id = uuid.uuid4().hex
            self.operator_sequence = 0
            self.operator_deadline = time.monotonic() + self.operator_lease_s
            if self.guard and not self.guard_id:
                self.guard_id = uuid.uuid4().hex
        elif kind == "openRun":
            self._operator(m)
            if m["runId"] in self.used_runs:
                raise ValueError("run-id-reused")
            await self._dispatch({"action": "admit"}, internal=True)
            self.motion_run = m["runId"]
            self.used_runs.add(m["runId"])
            self.runner_sequence = 0
        elif kind == "closeRun":
            self._control_run(m)
            self._revoke("run-closed")
        elif kind == "acquireHandover":
            self._control_run(m)
            self._stationary_evidence()
            await self._dispatch({"action": "hold", "session": self.session}, internal=True)
            self.guard_id = uuid.uuid4().hex
        elif kind == "clearHandover":
            self._operator(m)
            if not self.guard or m["guardId"] != self.guard_id:
                raise ValueError("stale-guard")
            self._stationary_evidence()
            self.guard = None
            self.guard_id = None
        elif kind == "recover":
            self._operator(m)
            if m["guardId"] != self.guard_id:
                raise ValueError("stale-guard")
            self._stationary_evidence()
            await self._dispatch({"action": "recover", "confirmed": True}, internal=True)
            self.guard_id = None
        else:
            raise ValueError("unsupported-control")

    async def _motion(self, value: Any) -> dict:
        """Called under the port lock after expiry/session checks; fake-only bridge."""
        m = parse_motion_message(value)
        kind = m["kind"]
        if kind not in {"startMotion", "renewMotion", "cancelMotion"}:
            raise ValueError("wrong-direction")
        if m["connectionEpoch"] != self.session:
            raise ValueError("stale-epoch")
        if m["robotId"] != "fake-only" or (
            self.motion_run is not None and m["runId"] != self.motion_run
        ):
            raise ValueError("wrong-run-or-robot")
        old_request = self.motion_requests.get(m["requestId"])
        if old_request:
            if old_request[0] != m:
                raise ValueError("id-conflict")
            if kind == "startMotion":
                return self.motion_records[m["operationId"]]["result"].copy()
            return old_request[1].copy()  # A retry does not extend a TTL.
        if kind == "startMotion" and m["operationId"] in self.motion_records:
            raise ValueError("id-conflict")
        if len(self.motion_requests) >= self.motion_capacity:
            raise ValueError("capacity-exhausted")
        scope = {k: m[k] for k in SCOPE_KEYS}
        if kind != "startMotion":
            op = self.operation
            if op is None or "wire" not in op:
                raise ValueError("stale-motion")
            if any(m[k] != op["wire"][k] for k in SCOPE_KEYS if k != "requestId"):
                raise ValueError("stale-motion")
            if m["generation"] != op["token"]["generation"]:
                raise ValueError("stale-motion")
            if kind == "renewMotion":
                if not op["finishing"]:
                    op["ttl"] = time.monotonic() + self.command_ttl_s
                # A renewal can race with completion: acknowledge without prolonging stop.
            else:
                op["override"] = "cancelled"
                job = self._start_io(
                    self.runtime.handle_text(self.client, json.dumps({"type": "cancel_motion"}))
                )
                self.operation_io.append(job)
                self._finish("cancelled", "scoped-stop")
            ack = dict(scope, kind="commandAck", generation=m["generation"])
            self.motion_requests[m["requestId"]] = (m, ack)
            return ack.copy()
        # Rejected starts also get tombstones: a retry must not become a new movement.
        self.motion_run = m["runId"]
        if self.operation or self.guard or self.inhibited or self.io_tasks:
            rejected = dict(scope, kind="rejected", reason="motion-inhibited")
            self.motion_records[m["operationId"]] = {"result": rejected}
            self.motion_requests[m["requestId"]] = (m, rejected)
            return rejected.copy()
        generation = self.generation + 1
        common = dict(request_id=str(generation), run_id=m["runId"], effect_id=m["operationId"])
        g = m["goal"]
        if g["kind"] == "move":
            command = MoveCommand(
                type="move", distance_m=g["distanceM"], speed_mps=g["speedMps"], **common
            )
        else:
            command = TurnCommand(
                type="turn",
                angle_deg=g["angleRad"] * 180 / math.pi,
                speed_rad_s=g["speedRadS"],
                **common,
            )
        self.generation = generation
        now = time.monotonic()
        accepted = dict(scope, kind="accepted", generation=generation)
        self.motion_records[m["operationId"]] = {"result": accepted}
        self.motion_requests[m["requestId"]] = (m, accepted)
        self.operation_io = []
        self.operation = {
            "token": {"session": self.session, "generation": generation},
            "request": str(generation),
            "wire": scope,
            "ttl": now + self.command_ttl_s,
            "deadline": now + self.progress_s,
            "finishing": False,
            "override": None,
        }
        await self._send(command.model_dump(mode="json"))
        return accepted.copy()

    def _start_io(self, operation: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        hold = self.runtime.motion_interlock.hold("runner-stop-io")
        task = asyncio.create_task(operation)
        self.io_tasks.add(task)

        def done(job: asyncio.Task[None]) -> None:
            self.io_tasks.discard(job)
            # Consume exceptions; errors never silently reopen admission.
            if job.cancelled() or job.exception() is not None:
                self.inhibited = True
            self.runtime.motion_interlock.release(hold)

        task.add_done_callback(done)
        return task

    def _expire(self, now: float) -> None:
        if self.operator_id and now >= self.operator_deadline:
            self.operator_id = None
            self.inhibited = True
            self._revoke("operator-lease-expired")
        if self.session and now >= self.lease:
            self._revoke("lease-expired")
        elif self.operation and not self.operation["finishing"]:
            if now >= self.operation["ttl"]:
                self._revoke("command-ttl")
            elif now >= self.operation["deadline"]:
                self._revoke("progress-deadline")

    def _revoke(self, reason: str) -> None:
        session, self.session = self.session, None
        if self.operation:
            self.operation["override"] = "interrupted"
        if self.client:
            client, self.client = self.client, None
            job = self._start_io(self.runtime.remove_client(client))
            if self.operation:
                self.operation_io.append(job)
        self._finish("interrupted", reason)
        if session:
            self.emit({"kind": "revoked", "reason": reason})

    def _finish(self, status: str, reason: str) -> None:
        op = self.operation
        if op is None or op["finishing"]:
            return
        op["finishing"] = True
        # Start at the request, not after adapter.stop or disconnect returns.
        op["stopDeadline"] = time.monotonic() + self.stop_s
        self.finishing = asyncio.create_task(self._evidence(op, status, reason))

    async def _evidence(self, op: dict[str, Any], status: str, reason: str) -> None:
        deadline = op["stopDeadline"]
        jobs = self.operation_io
        confirmed = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            pending = [job for job in jobs if not job.done()]
            if pending:
                # wait() does not await cancellation of a non-cooperative I/O task.
                await asyncio.wait(pending, timeout=remaining)
            else:
                try:
                    await asyncio.wait_for(self.adapter.evidence.wait(), timeout=remaining)
                except TimeoutError:
                    break
            async with self.lock:
                if self.operation is not op:
                    return
                self._expire(time.monotonic())
                # Revocation can append another I/O task during the wait.
                if any(not job.done() for job in jobs):
                    continue
                failed = any(job.cancelled() or job.exception() is not None for job in jobs)
                if not failed and not self.adapter.evidence.is_set():
                    # I/O returned; the remaining deadline still belongs to evidence.
                    continue
                confirmed = (
                    not failed
                    and self.adapter.evidence.is_set()
                    and self.adapter.evidence_at <= deadline
                    and time.monotonic() <= deadline
                    and not self.adapter.actuating
                )
                # Check and publish atomically: no revoke may add I/O between them.
                self._complete_evidence(op, status, reason, confirmed)
                return
        async with self.lock:
            self._complete_evidence(op, status, reason, False)

    def _complete_evidence(
        self, op: dict[str, Any], status: str, reason: str, confirmed: bool
    ) -> None:
        if self.operation is not op:
            return
        status = op["override"] or status
        self.operation = None
        if not confirmed:
            status, reason = "stop-unconfirmed", "stop-evidence-timeout"
            self.inhibited = True
            self._revoke(reason)
        if "wire" in op:
            evidence = (
                {
                    "kind": "simulated",
                    "epoch": "fake-" + op["token"]["session"],
                    "observedAt": time.monotonic(),
                }
                if confirmed
                else {"kind": "unknown"}
            )
            result = parse_motion_message(
                dict(
                    op["wire"],
                    kind="terminal",
                    generation=op["token"]["generation"],
                    outcome=status,
                    reason=reason[:256],
                    evidence=evidence,
                )
            )
            self.motion_records[op["wire"]["operationId"]]["result"] = result
            self.emit(result)
            return
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
                    if "wire" in op:
                        self.emit(
                            dict(op["wire"], kind="running", generation=op["token"]["generation"])
                        )
                    else:
                        self.emit({"kind": "running", "token": op["token"]})
                elif status in {"completed", "failed", "cancelled"}:
                    self._finish(status, message.get("detail") or "runtime-" + status)

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(0.01)
            async with self.lock:
                self._expire(time.monotonic())

    async def close(self) -> None:
        async with self.lock:
            self._revoke("port-closed")
        if self.finishing:
            await self.finishing
        for task in self.tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        # Bound shutdown waits as well. The owner process remains responsible for
        # terminating a backend that cannot respond even to task cancellation.
        if self._owns_runtime:
            self._start_io(self.runtime.close())
        jobs = set(self.io_tasks)
        if not jobs:
            return
        _, pending = await asyncio.wait(jobs, timeout=self.stop_s)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=0.05)


async def main() -> None:
    def emit(value: dict[str, Any]) -> None:
        print(json.dumps(value, allow_nan=False), flush=True)

    port = RunnerPort(emit)
    await port.start()
    try:
        while line := await asyncio.to_thread(sys.stdin.readline, 65_537):
            if len(line.encode("utf-8")) > 65_536 or not line.endswith("\n"):
                emit({"kind": "reply", "id": None, "ok": False, "error": "invalid-frame-size"})
                break  # Never reinterpret the remainder of an oversized frame as a command.
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
