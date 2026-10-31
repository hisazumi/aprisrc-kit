"""Local ROS telemetry only. No ROS import, publisher, or motor transport."""

from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path

from .adapter import (
    BoundedMotionExecutionError,
    BoundedMotionGoal,
    BoundedMotionResult,
    DeviceBoundedMotionAdapter,
)
from .models import Capabilities, Pose, PoseEstimateQuality, RoverState, Velocity


class Ros2ReadOnlyAdapter(DeviceBoundedMotionAdapter):
    def __init__(self, path: Path | None):
        if path is None:
            raise ValueError("ROS state file is required")
        self.path = path
        self.running = False

    async def start(self) -> None:
        self.running = True

    async def close(self) -> None:
        self.running = False

    async def drive(self, vx: float, vy: float, wz: float, *, ttl_ms: int = 500) -> None:
        raise RuntimeError("ros2_readonly: motion is disabled")

    async def execute_bounded_motion(self, goal: BoundedMotionGoal) -> BoundedMotionResult:
        raise BoundedMotionExecutionError(
            BoundedMotionResult(goal.motion_id, "failed", "ros2_readonly: motion is disabled")
        )

    async def stop(self) -> None:
        # There is no command output to stop. This is not a physical E-stop interface.
        pass

    async def reset_pose(self) -> None:
        raise RuntimeError("ros2_readonly: pose reset is disabled")

    async def state(self, command_age_ms: float | None = None) -> RoverState:
        state = RoverState(
            timestamp=time.time(),
            connected=False,
            pose=Pose(x=0, y=0, yaw=0),
            velocity=Velocity(vx=0, vy=0, wz=0),
            capabilities=Capabilities(pose=False, imu=False),
            pose_quality=PoseEstimateQuality(anomalies=["ros2_readonly", "telemetry_unavailable"]),
            command_age_ms=command_age_ms,
        )
        try:
            raw = await asyncio.to_thread(self.path.read_text)
            if len(raw) > 16384:
                raise ValueError("oversized snapshot")
            data = json.loads(raw)
            if data["version"] != 1:
                raise ValueError("snapshot version")
            now = time.monotonic()
            snapshot_age = now - float(data["monotonic"])
            odom = data["odom"]
            age = now - float(odom["received_monotonic"]) + float(odom["source_age_s"])
            pose = Pose.model_validate(odom["pose"])
            velocity = Velocity.model_validate(odom["velocity"])
            numbers = [
                snapshot_age,
                age,
                *pose.model_dump().values(),
                *velocity.model_dump().values(),
            ]
            if not all(math.isfinite(v) for v in numbers):
                raise ValueError("non-finite telemetry")
            fresh = self.running and 0 <= snapshot_age <= 1.5 and 0 <= age <= 1.5
            if odom["frame_id"] != "odom" or odom["child_frame_id"] != "base_footprint":
                raise ValueError("unexpected odometry frames")
            state.pose, state.velocity = pose, velocity
            state.connected = fresh
            state.capabilities.pose = fresh
            state.timestamp = float(odom["received_at"])
            if not math.isfinite(state.timestamp):
                raise ValueError("invalid timestamp")
            state.pose_quality = PoseEstimateQuality(
                source="unavailable",
                confidence=0,
                age_ms=max(0, age * 1000),
                anomalies=["ros2_readonly", "ros2_ekf_unqualified"]
                + ([] if fresh else ["telemetry_stale"]),
            )
            battery = data.get("battery")
            if battery and 0 <= now - battery["received_monotonic"] <= 3:
                percent = float(battery["percent"])
                if math.isfinite(percent) and 0 <= percent <= 100:
                    state.battery_percent = percent
            return state
        except (OSError, ValueError, KeyError, TypeError):
            return state.model_copy(update={"connected": False, "battery_percent": None})
