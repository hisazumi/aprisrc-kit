"""Same-host iron-X adapter; no ROS dependency in the Kit Python environment."""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
import uuid
from pathlib import Path

from .adapter import BoundedMotionExecutionError, BoundedMotionGoal, BoundedMotionResult
from .ironx_profile import load_profile
from .ros2_readonly_adapter import Ros2ReadOnlyAdapter


class IronXAdapter(Ros2ReadOnlyAdapter):
    def __init__(self, state_file: Path, command_file: Path, bridge_state_file: Path):
        super().__init__(state_file)
        self.profile = load_profile()
        self.command_file = command_file
        self.bridge_state_file = bridge_state_file
        self._epoch = 0
        self._busy = False
        self._estop = False
        self._lock = None
        self._stop_lock = asyncio.Lock()

    async def start(self):
        # ROS runs on Linux; keep importing the general Kit app portable.
        import fcntl

        lock = self.command_file.with_suffix(".lock").open("a")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise RuntimeError("Another iron-X Adapter owns this command mailbox") from None
        self._lock = lock
        await super().start()

    def _bridge(self):
        try:
            data = json.loads(self.bridge_state_file.read_text())
            age = time.monotonic() - data["monotonic"]
            if not 0 <= age < 0.3 or data["fault"]:
                raise ValueError("stale or faulted bridge")
            if data.get("profile", "standard") != self.profile.name:
                raise ValueError("bridge profile mismatch")
            return data
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("iron-X command bridge unavailable") from exc

    def _write(self, vx, wz, ttl_ms):
        command_id = uuid.uuid4().hex
        data = dict(id=command_id, monotonic=time.monotonic(), vx=vx, wz=wz, ttl_ms=ttl_ms)
        temporary = self.command_file.with_name(self.command_file.name + "." + command_id)
        try:
            temporary.write_text(json.dumps(data, allow_nan=False))
            os.replace(temporary, self.command_file)
        finally:
            temporary.unlink(missing_ok=True)
        return command_id

    async def state(self, command_age_ms=None):
        state = await super().state(command_age_ms)
        state.pose_quality.anomalies = [
            a for a in state.pose_quality.anomalies if a != "ros2_readonly"
        ]
        try:
            self._bridge()
        except RuntimeError:
            state.connected = False
            state.pose_quality.anomalies.append("command_bridge_unavailable")
        if state.pose_quality.age_ms is None or state.pose_quality.age_ms >= 300:
            state.connected = False
        return state

    async def drive(self, vx, vy, wz, *, ttl_ms=500):
        started = time.monotonic()
        epoch = self._epoch
        if self._stop_lock.locked():
            raise RuntimeError("iron-X stop confirmation in progress")
        if not all(math.isfinite(v) for v in (vx, vy, wz, ttl_ms)) or vy != 0 or ttl_ms <= 0:
            self._write(0, 0, 300)
            raise ValueError("Invalid differential-drive command")
        if abs(vx) > 0.15 or abs(wz) > 0.2:
            self._write(0, 0, 300)
            raise ValueError("iron-X limits: 0.15 m/s and 0.2 rad/s")
        state = await self.state()
        if self._stop_lock.locked() or epoch != self._epoch:
            raise RuntimeError("iron-X drive superseded by stop")
        if self._estop or not state.connected:
            self._write(0, 0, 300)
            raise RuntimeError("iron-X stopped or telemetry unavailable")
        elapsed_ms = (time.monotonic() - started) * 1000
        remaining_ms = min(ttl_ms, self.profile.local_command_ms) - elapsed_ms
        if remaining_ms < 1:
            self._write(0, 0, 300)
            raise RuntimeError("iron-X command expired during telemetry validation")
        self._write(vx, wz, remaining_ms)

    async def stop(self):
        self._epoch += 1
        async with self._stop_lock:
            await self._confirm_stop()

    async def _confirm_stop(self):
        command_id = self._write(0, 0, 300)
        started = time.monotonic()
        stable = None
        stamps = set()
        while time.monotonic() - started < 2:
            bridge = self._bridge()
            state = await self.state()
            zero = (
                state.connected
                and bridge.get("command_id") == command_id
                and bridge.get("vx") == 0
                and bridge.get("wz") == 0
                and abs(state.velocity.vx) < 0.01
                and abs(state.velocity.vy) < 0.01
                and abs(state.velocity.wz) < 0.03
            )
            if zero:
                stable = stable if stable is not None else time.monotonic()
                stamps.add(state.timestamp)
                if time.monotonic() - stable >= 0.2 and len(stamps) >= 3:
                    return
            else:
                stable = None
                stamps.clear()
            await asyncio.sleep(0.05)
        raise TimeoutError("iron-X physical stop not confirmed by telemetry")

    async def emergency_stop(self, reason):
        self._estop = True
        await self.stop()

    async def clear_emergency_stop(self):
        await self.stop()
        self._estop = False

    async def close(self):
        try:
            await self.stop()
        finally:
            await super().close()
            if self._lock is not None:
                self._lock.close()
                self._lock = None

    async def execute_bounded_motion(self, goal: BoundedMotionGoal):
        if self._busy:
            raise RuntimeError("iron-X motion already active")
        self._busy = True
        epoch = self._epoch
        try:
            linear = goal.kind == "linear"
            target = goal.distance_m if linear else goal.angle_rad
            speed = goal.max_linear_speed_mps if linear else goal.max_angular_speed_rad_s
            if (
                goal.kind not in ("linear", "rotate")
                or target is None
                or not all(math.isfinite(v) for v in (target, speed, goal.max_duration_ms))
                or speed <= 0
                or not 0 < goal.max_duration_ms <= 120000
                or abs(target) > (1 if linear else math.pi)
            ):
                raise ValueError("Invalid bounded motion goal")
            speed = min(speed, 0.15 if linear else 0.2)
            tolerance = 0.015 if linear else 0.04
            initial = await self.state()
            if not initial.connected:
                raise RuntimeError("Fresh odometry and bridge required")
            previous_yaw = initial.pose.yaw
            accumulated = 0.0
            end = time.monotonic() + goal.max_duration_ms / 1000
            while True:
                if epoch != self._epoch:
                    raise asyncio.CancelledError()
                state = await self.state()
                if epoch != self._epoch:
                    raise asyncio.CancelledError()
                if not state.connected:
                    raise RuntimeError("Odometry lost during motion")
                dx, dy = state.pose.x - initial.pose.x, state.pose.y - initial.pose.y
                if linear:
                    progress = dx * math.cos(initial.pose.yaw) + dy * math.sin(initial.pose.yaw)
                    cross = -dx * math.sin(initial.pose.yaw) + dy * math.cos(initial.pose.yaw)
                    if abs(cross) > 0.05:
                        raise RuntimeError("Excessive lateral drift")
                else:
                    accumulated += math.atan2(
                        math.sin(state.pose.yaw - previous_yaw),
                        math.cos(state.pose.yaw - previous_yaw),
                    )
                    previous_yaw = state.pose.yaw
                    progress = accumulated
                remaining = target - progress
                if abs(remaining) <= tolerance:
                    break
                if remaining * target < 0 or time.monotonic() >= end:
                    raise TimeoutError("Target overshot or motion deadline exceeded")
                velocity = math.copysign(
                    min(speed, max(0.01 if linear else 0.04, abs(remaining))), remaining
                )
                await self.drive(
                    velocity if linear else 0, 0, 0 if linear else velocity, ttl_ms=200
                )
                await asyncio.sleep(0.05)
            await self.stop()
            final = await self.state()
            if linear:
                achieved = (final.pose.x - initial.pose.x) * math.cos(initial.pose.yaw) + (
                    final.pose.y - initial.pose.y
                ) * math.sin(initial.pose.yaw)
            else:
                achieved = accumulated + math.atan2(
                    math.sin(final.pose.yaw - previous_yaw), math.cos(final.pose.yaw - previous_yaw)
                )
            if not final.connected or abs(target - achieved) > (0.03 if linear else 0.08):
                raise RuntimeError("Stopped outside target tolerance")
            return BoundedMotionResult(goal.motion_id, "completed", None)
        except asyncio.CancelledError:
            await self.stop()
            raise
        except Exception as exc:
            try:
                await self.stop()
            except Exception as stop_exc:
                raise BoundedMotionExecutionError(
                    BoundedMotionResult(
                        goal.motion_id, "failed", f"{exc}; stop unconfirmed: {stop_exc}"
                    )
                ) from exc
            raise BoundedMotionExecutionError(
                BoundedMotionResult(goal.motion_id, "failed", str(exc))
            ) from exc
        finally:
            self._busy = False
