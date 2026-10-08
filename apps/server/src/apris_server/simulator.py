from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from .adapter import RoverAdapter
from .models import Capabilities, Pose, PoseEstimateQuality, RoverState, Velocity
from .odometry import OdometryConfig, WheelImuOdometry


@dataclass(slots=True)
class SimulatorConfig:
    update_hz: float = 50.0
    battery_drain_percent_per_hour: float = 4.0


class SimulatorFaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_latency_ms: int = Field(default=0, ge=0, le=2000)
    state_latency_ms: int = Field(default=0, ge=0, le=2000)
    drop_next_commands: int = Field(default=0, ge=0, le=100)
    pose_noise_m: float = Field(default=0.0, ge=0.0, le=1.0)
    yaw_noise_deg: float = Field(default=0.0, ge=0.0, le=45.0)
    stale_state_ms: int = Field(default=0, ge=0, le=10_000)
    battery_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    encoder_fault: bool = False
    imu_fault: bool = False
    seed: int = Field(default=1, ge=0, le=1_000_000)


class SimulatorMarkerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    id: int = Field(ge=0)
    x_m: float = Field(ge=-10.0, le=10.0)
    y_m: float = Field(ge=-10.0, le=10.0)


class SimulatorPoseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    x: float = Field(ge=-10.0, le=10.0)
    y: float = Field(ge=-10.0, le=10.0)
    yaw: float = Field(ge=-math.pi, le=math.pi)
    markers: list[SimulatorMarkerInput] = Field(default_factory=list, max_length=10)


@dataclass(slots=True)
class TruthSample:
    monotonic_time: float
    x: float
    y: float
    yaw: float
    vx: float
    wz: float
    battery: float
    odom_x: float
    odom_y: float
    odom_yaw: float
    pose_quality: PoseEstimateQuality


class DifferentialDriveSimulator(RoverAdapter):
    """Small deterministic planar simulator with no physics-engine dependency."""

    def __init__(self, config: SimulatorConfig | None = None) -> None:
        self.config = config or SimulatorConfig()
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._vx = 0.0
        self._wz = 0.0
        self._battery = 100.0
        self._left_distance = 0.0
        self._right_distance = 0.0
        self._odometry = WheelImuOdometry(OdometryConfig())
        self._last_update = time.monotonic()
        self._odometry.update(
            timestamp=self._last_update,
            left_ticks=0,
            right_ticks=0,
            imu_yaw_rate_rad_s=0.0,
        )
        self._history: deque[TruthSample] = deque(maxlen=2048)
        self._history.append(self._truth_sample(self._last_update))
        self._faults = SimulatorFaults()
        self._fault_epoch = self._last_update
        self._lock = asyncio.Lock()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._last_update = time.monotonic()
        self._task = asyncio.create_task(self._run(), name="differential-drive-simulator")

    async def close(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        period = 1.0 / self.config.update_hz
        while self._running:
            await asyncio.sleep(period)
            async with self._lock:
                self._advance(time.monotonic())

    def _advance(self, now: float) -> None:
        dt = max(0.0, min(now - self._last_update, 0.25))
        if dt == 0.0:
            return

        yaw_midpoint = self._yaw + self._wz * dt * 0.5
        linear_distance = self._vx * dt
        angular_distance = self._wz * dt
        self._x += self._vx * math.cos(yaw_midpoint) * dt
        self._y += self._vx * math.sin(yaw_midpoint) * dt
        self._yaw = math.atan2(
            math.sin(self._yaw + self._wz * dt),
            math.cos(self._yaw + self._wz * dt),
        )

        drain = self.config.battery_drain_percent_per_hour * dt / 3600.0
        self._battery = max(0.0, self._battery - drain)
        track_width = self._odometry.config.track_width_m
        self._left_distance += linear_distance - angular_distance * track_width * 0.5
        self._right_distance += linear_distance + angular_distance * track_width * 0.5
        metres_per_tick = (
            2.0
            * math.pi
            * self._odometry.config.wheel_radius_m
            / self._odometry.config.ticks_per_revolution
        )
        self._odometry.update(
            timestamp=now,
            left_ticks=round(self._left_distance / metres_per_tick),
            right_ticks=round(self._right_distance / metres_per_tick),
            imu_yaw_rate_rad_s=self._wz,
            encoder_fault=self._faults.encoder_fault,
            imu_fault=self._faults.imu_fault,
        )
        self._last_update = now
        self._history.append(self._truth_sample(now))

    def _truth_sample(self, now: float) -> TruthSample:
        odom_pose = self._odometry.pose
        return TruthSample(
            monotonic_time=now,
            x=self._x,
            y=self._y,
            yaw=self._yaw,
            vx=self._vx,
            wz=self._wz,
            battery=self._battery,
            odom_x=odom_pose.x,
            odom_y=odom_pose.y,
            odom_yaw=odom_pose.yaw,
            pose_quality=self._odometry.quality(),
        )

    def _sample_at(self, target_time: float) -> TruthSample:
        for sample in reversed(self._history):
            if sample.monotonic_time <= target_time:
                return sample
        return self._history[0]

    async def drive(self, vx: float, vy: float, wz: float, *, ttl_ms: int = 500) -> None:
        del ttl_ms
        if abs(vy) > 1e-9:
            raise ValueError("differential-drive adapter does not support lateral velocity")
        latency_ms = self._faults.command_latency_ms
        if latency_ms:
            await asyncio.sleep(latency_ms / 1000.0)
        async with self._lock:
            self._advance(time.monotonic())
            if self._faults.drop_next_commands > 0:
                self._faults.drop_next_commands -= 1
                return
            self._vx = vx
            self._wz = wz

    async def stop(self) -> None:
        async with self._lock:
            self._advance(time.monotonic())
            self._vx = 0.0
            self._wz = 0.0

    async def reset_pose(self) -> None:
        async with self._lock:
            self._advance(time.monotonic())
            self._x = 0.0
            self._y = 0.0
            self._yaw = 0.0
            self._left_distance = 0.0
            self._right_distance = 0.0
            self._odometry.reset()
            now = time.monotonic()
            self._odometry.update(
                timestamp=now,
                left_ticks=0,
                right_ticks=0,
                imu_yaw_rate_rad_s=0.0,
            )
            self._history.clear()
            self._history.append(self._truth_sample(now))

    async def set_faults(self, faults: SimulatorFaults) -> None:
        async with self._lock:
            self._advance(time.monotonic())
            self._faults = faults.model_copy(deep=True)
            self._fault_epoch = time.monotonic()

    async def clear_faults(self) -> None:
        await self.set_faults(SimulatorFaults())

    async def faults(self) -> SimulatorFaults:
        async with self._lock:
            return self._faults.model_copy(deep=True)

    async def state(self, command_age_ms: float | None = None) -> RoverState:
        latency_ms = self._faults.state_latency_ms
        if latency_ms:
            await asyncio.sleep(latency_ms / 1000.0)
        async with self._lock:
            now = time.monotonic()
            self._advance(now)
            faults = self._faults
            sample = self._sample_at(now - faults.stale_state_ms / 1000.0)
            phase = faults.seed + (sample.monotonic_time - self._fault_epoch)
            x = sample.odom_x + faults.pose_noise_m * math.sin(phase * 1.37)
            y = sample.odom_y + faults.pose_noise_m * math.cos(phase * 1.91)
            yaw_noise = math.radians(faults.yaw_noise_deg) * math.sin(phase * 1.13)
            yaw = math.atan2(
                math.sin(sample.odom_yaw + yaw_noise),
                math.cos(sample.odom_yaw + yaw_noise),
            )
            sample_age = max(0.0, now - sample.monotonic_time)
            quality = sample.pose_quality.model_copy(deep=True)
            quality.age_ms = sample_age * 1000.0
            quality.confidence *= max(0.0, 1.0 - min(quality.age_ms, 5000.0) / 6000.0)
            if faults.stale_state_ms:
                quality.anomalies = [*quality.anomalies, "state_stale"]
            return RoverState(
                timestamp=time.time() - sample_age,
                connected=self._running,
                pose=Pose(x=x, y=y, yaw=yaw),
                velocity=Velocity(vx=sample.vx, vy=0.0, wz=sample.wz),
                battery_percent=(
                    faults.battery_percent
                    if faults.battery_percent is not None
                    else sample.battery
                ),
                capabilities=Capabilities(),
                command_age_ms=command_age_ms,
                pose_quality=quality,
            )
