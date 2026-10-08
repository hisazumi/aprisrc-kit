from __future__ import annotations

import asyncio
import contextlib
import math
from dataclasses import dataclass

from .adapter import (
    BoundedMotionExecutionError,
    BoundedMotionGoal,
    BoundedMotionResult,
    DeviceBoundedMotionAdapter,
)
from .models import Capabilities, Pose, PoseEstimateQuality, RoverState, Velocity
from .rover_protocol import (
    CancelRoverMotion,
    RenewMotionLease,
    RoverClearEmergencyStop,
    RoverEmergencyStop,
    RoverStop,
    SetVelocity,
    StartMotion,
)
from .rover_registry import RoverCommandRejectedError, RoverRegistry, RoverUnavailableError


@dataclass(slots=True)
class WebSocketRoverAdapterConfig:
    command_ttl_ms: int = 500
    command_ack_timeout_s: float = 0.4
    desired_velocity_lease_ms: int = 1000
    desired_motion_lease_ms: int = 500
    telemetry_stale_after_s: float = 1.0


class WebSocketRoverAdapter(DeviceBoundedMotionAdapter):
    def __init__(
        self,
        registry: RoverRegistry,
        rover_id: str,
        config: WebSocketRoverAdapterConfig | None = None,
    ) -> None:
        self.registry = registry
        self.rover_id = rover_id
        self.config = config or WebSocketRoverAdapterConfig()
        self._pose_offset = Pose(x=0.0, y=0.0, yaw=0.0)
        self._velocity_lock = asyncio.Lock()
        self._pending_velocity: tuple[float, float, int, int] | None = None
        self._velocity_worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        await self._cancel_velocity_worker()

    async def drive(self, vx: float, vy: float, wz: float, *, ttl_ms: int = 500) -> None:
        if abs(vy) > 1e-9:
            raise ValueError("differential-drive adapter does not support lateral velocity")
        await self.registry.require_healthy(self.rover_id)
        snapshot = await self.registry.rover_snapshot(self.rover_id)
        limits = snapshot["firmware_safety_limits"]
        linear_limit = float(limits["max_linear_speed_mps"])
        angular_limit = float(limits["max_angular_speed_rad_s"])
        lease_ms = min(
            max(100, ttl_ms, self.config.desired_velocity_lease_ms),
            int(limits["max_lease_ms"]),
        )
        velocity = (
            max(-linear_limit, min(linear_limit, vx)),
            max(-angular_limit, min(angular_limit, wz)),
            min(ttl_ms, self.config.command_ttl_ms),
            lease_ms,
        )
        async with self._velocity_lock:
            self._pending_velocity = velocity
            if self._velocity_worker_task is None or self._velocity_worker_task.done():
                self._velocity_worker_task = asyncio.create_task(
                    self._velocity_worker(),
                    name=f"velocity-dispatch-{self.rover_id}",
                )
        await asyncio.sleep(0)

    async def stop(self) -> None:
        await self._cancel_velocity_worker()
        try:
            snapshot = await self.registry.rover_snapshot(self.rover_id)
        except RoverUnavailableError:
            return
        if not snapshot["connected"]:
            return
        await self.registry.dispatch(
            self.rover_id,
            RoverStop,
            ttl_ms=self.config.command_ttl_ms,
            ack_timeout_s=self.config.command_ack_timeout_s,
            require_healthy=False,
            reason="adapter_stop",
        )

    async def emergency_stop(self, reason: str) -> None:
        await self._cancel_velocity_worker()
        await self.registry.dispatch(
            self.rover_id,
            RoverEmergencyStop,
            ttl_ms=self.config.command_ttl_ms,
            ack_timeout_s=self.config.command_ack_timeout_s,
            require_healthy=False,
            reason=reason,
        )

    async def clear_emergency_stop(self) -> None:
        await self.registry.dispatch(
            self.rover_id,
            RoverClearEmergencyStop,
            ttl_ms=self.config.command_ttl_ms,
            ack_timeout_s=self.config.command_ack_timeout_s,
            require_healthy=True,
        )

    async def reset_pose(self) -> None:
        state = await self.state()
        self._pose_offset = state.pose

    async def state(self, command_age_ms: float | None = None) -> RoverState:
        try:
            snapshot = await self.registry.rover_snapshot(self.rover_id)
        except RoverUnavailableError:
            return self._unavailable_state(command_age_ms)
        telemetry = snapshot["telemetry"]
        telemetry_age_s = snapshot["telemetry_age_s"]
        connected = bool(
            snapshot["connected"]
            and snapshot["heartbeat_healthy"]
            and telemetry is not None
            and telemetry_age_s is not None
            and float(telemetry_age_s) <= self.config.telemetry_stale_after_s
        )
        capabilities = snapshot["capabilities"]
        if telemetry is None:
            return self._unavailable_state(command_age_ms, capabilities=capabilities)

        fault_codes = list(telemetry["fault_codes"])
        encoder_status = "fault" if any("encoder" in code for code in fault_codes) else "ok"
        imu_status = "fault" if any("imu" in code for code in fault_codes) else "ok"
        source = "encoder_imu" if encoder_status == "ok" and imu_status == "ok" else "unavailable"
        raw_yaw = float(telemetry["odometry_yaw_rad"])
        yaw = math.atan2(
            math.sin(raw_yaw - self._pose_offset.yaw),
            math.cos(raw_yaw - self._pose_offset.yaw),
        )
        return RoverState(
            timestamp=float(snapshot["last_seen_at"]),
            connected=connected,
            pose=Pose(
                x=float(telemetry["odometry_x_m"]) - self._pose_offset.x,
                y=float(telemetry["odometry_y_m"]) - self._pose_offset.y,
                yaw=yaw,
            ),
            velocity=Velocity(
                vx=float(telemetry["linear_velocity_mps"]),
                vy=0.0,
                wz=float(telemetry["angular_velocity_rad_s"]),
            ),
            battery_percent=telemetry["battery_percent"],
            capabilities=self._capabilities(capabilities),
            command_age_ms=command_age_ms,
            pose_quality=PoseEstimateQuality(
                source=source,
                confidence=1.0 if connected and not fault_codes else 0.0,
                age_ms=float(telemetry_age_s or 0.0) * 1000.0,
                encoder_status=encoder_status,
                imu_status=imu_status,
                anomalies=fault_codes,
            ),
        )

    async def execute_bounded_motion(self, goal: BoundedMotionGoal) -> BoundedMotionResult:
        await self._cancel_velocity_worker()
        snapshot = await self.registry.rover_snapshot(self.rover_id)
        limits = snapshot["firmware_safety_limits"]
        lease_ms = min(
            self.config.desired_motion_lease_ms,
            int(limits["max_lease_ms"]),
        )
        waiter = await self.registry.create_motion_waiter(self.rover_id, goal.motion_id)
        try:
            await self.registry.dispatch(
                self.rover_id,
                StartMotion,
                ttl_ms=self.config.command_ttl_ms,
                ack_timeout_s=self.config.command_ack_timeout_s,
                motion_id=goal.motion_id,
                kind=goal.kind,
                distance_m=goal.distance_m,
                angle_rad=goal.angle_rad,
                max_linear_speed_mps=min(
                    goal.max_linear_speed_mps,
                    float(limits["max_linear_speed_mps"]),
                ),
                max_angular_speed_rad_s=min(
                    goal.max_angular_speed_rad_s,
                    float(limits["max_angular_speed_rad_s"]),
                ),
                max_duration_ms=min(
                    goal.max_duration_ms,
                    int(limits["max_motion_duration_ms"]),
                ),
                lease_ms=lease_ms,
                run_id=goal.run_id,
                effect_id=goal.effect_id,
                request_id=goal.request_id,
            )
            terminal = await self._wait_with_lease(goal.motion_id, waiter, lease_ms)
            result = BoundedMotionResult(
                motion_id=terminal.motion_id,
                status=terminal.status,
                reason=terminal.reason,
            )
            if result.status != "completed":
                raise BoundedMotionExecutionError(result)
            return result
        except asyncio.CancelledError:
            await asyncio.shield(self._cancel_motion(goal.motion_id, "server_task_cancelled"))
            raise
        except Exception:
            await self._cancel_motion(goal.motion_id, "server_motion_failed")
            raise
        finally:
            await self.registry.release_motion_waiter(self.rover_id, goal.motion_id)

    async def _velocity_worker(self) -> None:
        try:
            while True:
                async with self._velocity_lock:
                    velocity = self._pending_velocity
                    self._pending_velocity = None
                    if velocity is None:
                        self._velocity_worker_task = None
                        return
                linear, angular, ttl_ms, lease_ms = velocity
                try:
                    await self.registry.dispatch(
                        self.rover_id,
                        SetVelocity,
                        ttl_ms=ttl_ms,
                        ack_timeout_s=self.config.command_ack_timeout_s,
                        linear_velocity_mps=linear,
                        angular_velocity_rad_s=angular,
                        lease_ms=lease_ms,
                    )
                except (RoverCommandRejectedError, RoverUnavailableError):
                    # The firmware lease remains the final fail-safe. A delayed ACK must
                    # not inject an immediate stop into an otherwise fresh velocity stream.
                    continue
        finally:
            async with self._velocity_lock:
                if self._velocity_worker_task is asyncio.current_task():
                    self._velocity_worker_task = None

    async def _cancel_velocity_worker(self) -> None:
        async with self._velocity_lock:
            self._pending_velocity = None
            task = self._velocity_worker_task
            self._velocity_worker_task = None
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _wait_with_lease(
        self,
        motion_id: str,
        waiter: asyncio.Future,
        lease_ms: int,
    ):
        refresh_s = max(0.05, lease_ms / 2000.0)
        while True:
            try:
                return await asyncio.wait_for(asyncio.shield(waiter), timeout=refresh_s)
            except TimeoutError:
                try:
                    await self.registry.dispatch(
                        self.rover_id,
                        RenewMotionLease,
                        ttl_ms=self.config.command_ttl_ms,
                        ack_timeout_s=self.config.command_ack_timeout_s,
                        motion_id=motion_id,
                        lease_ms=lease_ms,
                    )
                except RoverCommandRejectedError as exc:
                    if exc.code != "motion_already_terminal":
                        raise
                    return await asyncio.wait_for(
                        asyncio.shield(waiter),
                        timeout=self.config.command_ack_timeout_s,
                    )

    async def _cancel_motion(self, motion_id: str, reason: str) -> None:
        with contextlib.suppress(RoverUnavailableError):
            await self.registry.dispatch(
                self.rover_id,
                CancelRoverMotion,
                ttl_ms=self.config.command_ttl_ms,
                ack_timeout_s=self.config.command_ack_timeout_s,
                require_healthy=False,
                motion_id=motion_id,
                reason=reason,
            )

    @staticmethod
    def _capabilities(payload: dict[str, object]) -> Capabilities:
        return Capabilities(
            lateral_motion=False,
            pose=bool(payload.get("encoders")),
            imu=bool(payload.get("imu")),
            lidar=False,
            camera=False,
        )

    def _unavailable_state(
        self,
        command_age_ms: float | None,
        *,
        capabilities: dict[str, object] | None = None,
    ) -> RoverState:
        return RoverState(
            timestamp=0.0,
            connected=False,
            pose=Pose(x=0.0, y=0.0, yaw=0.0),
            velocity=Velocity(vx=0.0, vy=0.0, wz=0.0),
            capabilities=self._capabilities(capabilities or {}),
            command_age_ms=command_age_ms,
            pose_quality=PoseEstimateQuality(),
        )
