"""PC-side iron-X transport; reuses the tested odometry-based motion controller."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import uuid

from websockets.asyncio.client import connect

from .ironx_adapter import IronXAdapter
from .models import Capabilities, Pose, PoseEstimateQuality, RoverState, Velocity

logger = logging.getLogger(__name__)


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

    async def _rpc(self, method, params=None, *, deadline_s=0.25):
        # A caller cancelled while waiting for the lock must not close another RPC.
        async with self._rpc_lock:
            socket = self._socket
            if socket is None:
                raise RuntimeError("iron-X network connection unavailable")
            try:
                async with asyncio.timeout(deadline_s):
                    request_id = uuid.uuid4().hex
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
                        raise RuntimeError(f"iron-X gateway rejected {method}: {reply['error']}")
                    return reply["result"]
            except BaseException as exc:
                self.last_transport_error = f"{method}:{type(exc).__name__}"
                logger.warning("iron-X transport lost (%s)", self.last_transport_error)
                self.requires_rearm |= self._owned or self._busy or self._estop
                self._epoch += 1
                self._failed = True
                self._owned = False
                self._socket = None
                self._retry_at = time.monotonic() + 1
                await socket.close()
                raise

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
        if self._command_lock.locked():
            if self._last_state is None:
                return self._unavailable(command_age_ms)
            state = self._last_state.model_copy(deep=True)
            state.pose_quality.age_ms = (state.pose_quality.age_ms or 0) + (
                time.monotonic() - self._received_at
            ) * 1000
            state.connected = state.connected and state.pose_quality.age_ms < 300
            state.command_age_ms = command_age_ms
            return state
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
        if self._pending_stops:
            raise RuntimeError("iron-X network adapter stopped; stop confirmation pending")
        started = time.monotonic()
        epoch = self._epoch
        async with self._command_lock:
            if epoch != self._epoch:
                raise RuntimeError("iron-X drive superseded by stop")
            await self._drive(vx, vy, wz, ttl_ms=ttl_ms, started=started)

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
            if self._owned:
                await self._rpc("release", deadline_s=3)
                self._owned = False
            raise ValueError("Invalid iron-X differential-drive command")
        epoch = self._epoch
        if not self._owned:
            await self._rpc("acquire", deadline_s=3)
            self._owned = True
        # Drain this read-only reply before propagating a motion cancellation.
        # No drive is sent after cancellation; the existing RPC deadline still applies.
        reading = asyncio.create_task(self._rpc("state"))
        try:
            result = await asyncio.shield(reading)
        except asyncio.CancelledError:
            await asyncio.gather(reading, return_exceptions=True)
            raise
        if epoch != self._epoch or self._stop_lock.locked():
            raise RuntimeError("iron-X drive superseded by stop")
        state = RoverState.model_validate(result["state"])
        self._last_state = state.model_copy(deep=True)
        self._received_at = time.monotonic()
        if not state.connected:
            await self._rpc("release", deadline_s=3)
            self._owned = False
            raise RuntimeError("iron-X telemetry unavailable")
        remaining_ms = min(ttl_ms, 200) - (time.monotonic() - started) * 1000
        if remaining_ms < 1:
            await self._rpc("release", deadline_s=3)
            self._owned = False
            raise RuntimeError("iron-X command expired during network preparation")
        await self._rpc(
            "drive",
            {
                "vx": vx,
                "vy": vy,
                "wz": wz,
                "ttl_ms": remaining_ms,
                "nonce": result["nonce"],
            },
        )

    async def stop(self):
        self._epoch += 1
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
            if self._owned:
                await self._rpc("release", deadline_s=3)
                self._owned = False

    async def emergency_stop(self, reason):
        self._epoch += 1
        self._estop = True
        self.requires_rearm = True
        async with self._stop_lock, self._command_lock:
            if self._socket is None:
                await self._recover()
            await self._rpc("emergency_stop", {"reason": reason}, deadline_s=3)
            self._owned = False

    async def clear_emergency_stop(self):
        self._epoch += 1
        async with self._stop_lock, self._command_lock:
            if self._socket is None:
                await self._recover()
            await self._rpc("clear_emergency_stop", deadline_s=3)
            self._estop = False
            self.requires_rearm = False
            self._owned = False

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
