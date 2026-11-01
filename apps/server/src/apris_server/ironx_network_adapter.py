"""PC-side iron-X transport; reuses the tested odometry-based motion controller."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import uuid
from contextvars import ContextVar

from websockets.asyncio.client import connect

from .ironx_adapter import IronXAdapter
from .models import Capabilities, Pose, PoseEstimateQuality, RoverState, Velocity

logger = logging.getLogger(__name__)
_drive_trace = ContextVar("ironx_drive_trace", default=None)


class OwnershipExpired(RuntimeError):
    """The gateway replied; control is unavailable but transport is intact."""


class GatewayStopping(RuntimeError):
    """An owned drive was rejected while the gateway was confirming a stop."""


class NonceRejected(RuntimeError):
    """A drive challenge was rejected; transport is intact but stop must be confirmed."""


class DriveNotSent(RuntimeError):
    """A queued drive became obsolete before any bytes were sent."""


class IronXNetworkAdapter(IronXAdapter):
    """Only bounded-motion logic is inherited; no local file or ROS access is used."""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self._socket = None
        self._rpc_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._pending_stops = 0
        self._epoch = 0
        self._busy = False
        self._estop = False
        self._owned = False
        self._failed = False
        self._last_state = None
        self._received_at = 0.0
        self._poll_task = None
        self._closing = False
        self._retry_at = 0.0
        self.requires_rearm = False
        self.last_transport_error = None
        self._next_drive = None
        self._stop_unconfirmed = False
        self.last_drive_diagnostics = None

    async def start(self):
        self._closing = False
        await self._connect()

    async def _connect(self):
        self._socket = await connect(
            self.url,
            additional_headers={"Authorization": f"Bearer {self.token}"},
            open_timeout=3,
            close_timeout=1,
            max_size=65536,
            proxy=None,
        )
        self._failed = False

    async def _recover(self):
        async with self._rpc_lock:
            if self._socket is not None or self._closing:
                return
            if time.monotonic() < self._retry_at:
                return
            self._retry_at = time.monotonic() + 1
            try:
                await self._connect()
                logger.info("iron-X state connection restored; no commands replayed")
            except Exception as exc:
                self.last_transport_error = f"connect:{type(exc).__name__}"

    async def _rpc(self, method, params=None, *, deadline_s=0.25, prepare_params=None):
        # A caller cancelled while waiting for the lock must not close another RPC.
        queued_at = time.monotonic()
        async with self._rpc_lock:
            socket = self._socket
            if socket is None:
                raise RuntimeError("iron-X network connection unavailable")
            started = time.monotonic()
            diagnostic = {"method": method, "request_id": None,
                          "rpc_wait_ms": (started - queued_at) * 1000,
                          "deadline_ms": deadline_s * 1000, "outcome": "pending"}
            try:
                if prepare_params is not None:
                    params = prepare_params()
                async with asyncio.timeout(deadline_s):
                    request_id = uuid.uuid4().hex
                    diagnostic["request_id"] = request_id
                    await socket.send(
                        json.dumps(
                            {"id": request_id, "method": method, "params": params or {}},
                            allow_nan=False,
                        )
                    )
                    reply = json.loads(await socket.recv())
                    if reply.get("id") != request_id:
                        raise ValueError("iron-X response ID mismatch")
                    if "error" in reply:
                        error = reply["error"]
                        diagnostic["gateway_error"] = (
                            {"code": str(error.get("code", ""))[:100],
                             "message": str(error.get("message", ""))[:500]}
                            if isinstance(error, dict) else {"message": str(error)[:500]}
                        )
                        if self._owned and isinstance(error, dict) and error.get("code") in (
                            "not_owner", "lease_expired"
                        ):
                            raise OwnershipExpired(
                                f"iron-X gateway rejected {method}: {error}"
                            )
                        if (self._owned and method == "drive" and isinstance(error, dict)
                                and error.get("code") in ("expired_nonce", "invalid_nonce")):
                            raise NonceRejected(f"iron-X gateway rejected {method}: {error}")
                        if (self._owned and method == "drive" and isinstance(error, dict)
                                and error.get("code") == "stopping"):
                            raise GatewayStopping(
                                f"iron-X gateway rejected {method}: {error}"
                            )
                        raise RuntimeError(f"iron-X gateway rejected {method}: {reply['error']}")
                    diagnostic["outcome"] = "ok"
                    return reply["result"]
            except DriveNotSent:
                diagnostic["outcome"] = "not_sent"
                raise
            except (OwnershipExpired, GatewayStopping, NonceRejected) as exc:
                diagnostic["outcome"] = {
                    OwnershipExpired: "ownership_expired",
                    GatewayStopping: "gateway_stopping",
                    NonceRejected: "nonce_rejected",
                }[type(exc)]
                self._next_drive = None
                self._epoch += 1
                self._owned = False
                self._estop = self.requires_rearm = True
                self._stop_unconfirmed = True
                raise
            except BaseException as exc:
                diagnostic["outcome"] = type(exc).__name__
                diagnostic["elapsed_ms"] = (time.monotonic() - started) * 1000
                self.last_transport_error = f"{method}:{type(exc).__name__}"
                logger.warning("iron-X transport lost (%s, elapsed=%.1f ms, deadline=%.1f ms)",
                               self.last_transport_error, (time.monotonic() - started) * 1000,
                               deadline_s * 1000)
                self.requires_rearm |= self._owned or self._busy or self._estop
                self._stop_unconfirmed |= self._owned or self._busy or self._estop
                self._next_drive = None
                self._epoch += 1
                self._failed = True
                self._owned = False
                self._socket = None
                self._retry_at = time.monotonic() + 1
                await socket.close()
                raise
            finally:
                diagnostic.setdefault("elapsed_ms", (time.monotonic() - started) * 1000)
                trace = _drive_trace.get()
                if trace is not None:
                    trace["rpcs"].append(diagnostic)
                if (diagnostic["outcome"] != "ok" or diagnostic["elapsed_ms"] >= 100
                        or diagnostic["rpc_wait_ms"] >= 100):
                    logger.warning("iron-X RPC diagnostic %s", json.dumps(diagnostic))

    def _unavailable(self, command_age_ms):
        return RoverState(
            timestamp=time.time(),
            connected=False,
            pose=Pose(x=0, y=0, yaw=0),
            velocity=Velocity(vx=0, vy=0, wz=0),
            capabilities=Capabilities(pose=False, imu=False),
            pose_quality=PoseEstimateQuality(anomalies=["ironx_network_unavailable"]),
            command_age_ms=command_age_ms,
        )

    async def state(self, command_age_ms=None):
        if self._closing:
            return self._unavailable(command_age_ms)
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_state())
        state = (await asyncio.shield(self._poll_task)).model_copy(deep=True)
        state.command_age_ms = command_age_ms
        if self.requires_rearm:
            state.pose_quality.anomalies.append("ironx_rearm_required")
        return state

    async def _poll_state(self):
        command_age_ms = None
        if self._socket is None:
            await self._recover()
        if self._failed or self._socket is None or self._stop_lock.locked():
            return self._unavailable(command_age_ms)
        cached_state = None
        if self._last_state is not None:
            cached_state = self._last_state.model_copy(deep=True)
            cached_state.pose_quality.age_ms = (cached_state.pose_quality.age_ms or 0) + (
                time.monotonic() - self._received_at
            ) * 1000
            cached_state.connected = (
                cached_state.connected and cached_state.pose_quality.age_ms < 300
            )
            cached_state.command_age_ms = command_age_ms
        if self._command_lock.locked():
            return cached_state or self._unavailable(command_age_ms)
        # Display polling must not queue a redundant RPC ahead of a fresh drive.
        # Reading this snapshot neither renews ownership nor refreshes its age.
        if (self._owned and not self.requires_rearm and cached_state is not None
                and cached_state.connected and cached_state.pose_quality.age_ms < 100):
            return cached_state
        try:
            started = time.monotonic()
            result = await self._rpc("state", deadline_s=1)
            state = RoverState.model_validate(result["state"])
            if "gateway_emergency_stop" in state.pose_quality.anomalies:
                self.requires_rearm = self._estop = True
            age = (state.pose_quality.age_ms or 0) + (time.monotonic() - started) * 1000
            state.pose_quality.age_ms = age
            state.connected = state.connected and age < 300
            state.command_age_ms = command_age_ms
            self._last_state = state.model_copy(deep=True)
            self._received_at = time.monotonic()
            return state
        except Exception:
            return self._unavailable(command_age_ms)

    async def drive(self, vx, vy, wz, *, ttl_ms=500):
        started = time.monotonic()
        trace = {"rpcs": [], "command_wait_ms": 0.0, "outcome": "pending"}
        token = _drive_trace.set(trace)
        epoch = self._epoch
        try:
            if self._pending_stops:
                raise RuntimeError("iron-X network adapter stopped; stop confirmation pending")
            async with self._command_lock:
                trace["command_wait_ms"] = (time.monotonic() - started) * 1000
                if epoch != self._epoch:
                    raise RuntimeError("iron-X drive superseded by stop")
                await self._drive(vx, vy, wz, ttl_ms=ttl_ms, started=started)
                trace["outcome"] = "ok"
        except BaseException as exc:
            trace["outcome"] = type(exc).__name__
            trace["detail"] = str(exc)[:500]
            raise
        finally:
            trace["total_ms"] = (time.monotonic() - started) * 1000
            self.last_drive_diagnostics = trace
            _drive_trace.reset(token)

    async def _drive(self, vx, vy, wz, *, ttl_ms, started):
        if (
            self._failed
            or self._estop
            or self.requires_rearm
            or self._pending_stops
            or self._stop_lock.locked()
        ):
            raise RuntimeError(
                "iron-X network adapter stopped; reconnect and explicitly clear stop"
            )
        if (
            not all(math.isfinite(v) for v in (vx, vy, wz, ttl_ms))
            or vy != 0
            or ttl_ms <= 0
            or abs(vx) > 0.15
            or abs(wz) > 0.2
        ):
            self._next_drive = None
            if self._owned:
                await self._rpc("release", deadline_s=3)
                self._owned = False
            raise ValueError("Invalid iron-X differential-drive command")
        epoch = self._epoch
        if not self._owned:
            await self._rpc("acquire", deadline_s=3)
            self._owned = True
        cached, self._next_drive = self._next_drive, None
        trace = _drive_trace.get()
        if trace is not None:
            trace["cached_reply_age_ms"] = (
                (time.monotonic() - cached[1]) * 1000 if cached else None
            )
        if cached is not None and time.monotonic() - cached[1] < 0.1:
            result, observed_at = cached
            if trace is not None:
                trace["used_cached_reply"] = True
        else:
            if trace is not None:
                trace["used_cached_reply"] = False
            # Drain read-only replies on cancellation; never send the next drive.
            observed_at = time.monotonic()
            reading = asyncio.create_task(self._rpc("state"))
            try:
                result = await asyncio.shield(reading)
            except asyncio.CancelledError:
                await asyncio.gather(reading, return_exceptions=True)
                raise
        if epoch != self._epoch or self._stop_lock.locked():
            raise RuntimeError("iron-X drive superseded by stop")
        state = RoverState.model_validate(result["state"])
        state.pose_quality.age_ms = (state.pose_quality.age_ms or 0) + (
            time.monotonic() - observed_at
        ) * 1000
        state.connected = state.connected and state.pose_quality.age_ms < 300
        self._last_state = state.model_copy(deep=True)
        self._received_at = time.monotonic()
        validated_at = self._received_at
        if not state.connected:
            await self._rpc("release", deadline_s=3)
            self._owned = False
            raise RuntimeError("iron-X telemetry unavailable")
        remaining_ms = min(ttl_ms, 200) - (time.monotonic() - started) * 1000
        if trace is not None:
            trace["prepared_at_ms"] = (time.monotonic() - started) * 1000
            trace["remaining_ttl_ms"] = remaining_ms
        if remaining_ms < 1:
            await self._rpc("release", deadline_s=3)
            self._owned = False
            raise RuntimeError("iron-X command expired during network preparation")
        sent_at = time.monotonic()

        def prepare_drive():
            # Recheck after acquiring the RPC lock, not before a potentially long wait.
            nonlocal sent_at
            sent_at = time.monotonic()
            remaining = min(ttl_ms, 200) - (sent_at - started) * 1000
            nonce_age = (sent_at - observed_at) * 1000
            if trace is not None:
                trace["send_remaining_ttl_ms"] = remaining
                trace["send_challenge_age_ms"] = nonce_age
            if epoch != self._epoch or self._pending_stops or self._stop_lock.locked():
                raise DriveNotSent("iron-X queued drive superseded by stop")
            telemetry_age = state.pose_quality.age_ms + (sent_at - validated_at) * 1000
            if remaining < 1 or nonce_age >= 300 or telemetry_age >= 300:
                raise DriveNotSent("iron-X queued drive expired before send")
            return {
                "vx": vx,
                "vy": vy,
                "wz": wz,
                "ttl_ms": remaining,
                "nonce": result["nonce"],
            }

        try:
            # Reply latency never extends command validity.
            reply = await self._rpc("drive", deadline_s=1, prepare_params=prepare_drive)
        except DriveNotSent:
            # Confirm stopping on the existing connection; never replay an obsolete drive.
            if self._owned:
                await self._rpc("release", deadline_s=3)
                self._owned = False
            raise
        # A fresh single-use challenge replaces the next telemetry round trip.
        # Old gateways return null; keep their original state/drive sequence.
        if isinstance(reply, dict) and "state" in reply and "nonce" in reply:
            if epoch == self._epoch and not self._pending_stops:
                self._next_drive = (reply, sent_at)

    async def stop(self):
        self._epoch += 1
        self._next_drive = None
        self._pending_stops += 1
        stopping = asyncio.create_task(self._confirm_stop())
        cancelled = False
        try:
            # Cancellation belongs to the motion, not to its stop acknowledgement.
            # Repeated cancellations must also leave the bounded RPC running.
            while not stopping.done():
                try:
                    await asyncio.shield(stopping)
                except asyncio.CancelledError:
                    cancelled = True
            stopping.result()
            if cancelled:
                raise asyncio.CancelledError()
        finally:
            self._pending_stops -= 1

    async def _confirm_stop(self):
        async with self._stop_lock, self._command_lock:
            if self._failed:
                raise RuntimeError("iron-X connection lost; physical stop not confirmed")
            if self._stop_unconfirmed:
                self._estop = self.requires_rearm = True
                await self._rpc("emergency_stop", {"reason": "confirm stop after transport loss"},
                                deadline_s=3)
                self._stop_unconfirmed = False
                self._owned = False
            elif self._owned:
                try:
                    await self._rpc("release", deadline_s=3)
                except OwnershipExpired:
                    await self._rpc("emergency_stop", {
                        "reason": "confirm stop after ownership expiry"
                    }, deadline_s=3)
                    self._stop_unconfirmed = False
                self._owned = False

    async def emergency_stop(self, reason):
        self._epoch += 1
        self._next_drive = None
        self._stop_unconfirmed = True
        self._estop = True
        self.requires_rearm = True
        async with self._stop_lock, self._command_lock:
            if self._socket is None:
                await self._recover()
            await self._rpc("emergency_stop", {"reason": reason}, deadline_s=3)
            self._owned = False
            self._stop_unconfirmed = False

    async def clear_emergency_stop(self):
        self._epoch += 1
        self._next_drive = None
        async with self._stop_lock, self._command_lock:
            if self._socket is None:
                await self._recover()
            await self._rpc("clear_emergency_stop", deadline_s=3)
            self._estop = False
            self.requires_rearm = False
            self._owned = False
            self._stop_unconfirmed = False

    async def reset_pose(self):
        raise RuntimeError("iron-X shared odometry cannot be reset by a student client")

    async def close(self):
        self._closing = True
        if self._poll_task is not None and not self._poll_task.done():
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
        try:
            if self._socket is not None and not self._failed:
                await self.stop()
        finally:
            if self._socket is not None:
                await self._socket.close()
                self._socket = None
