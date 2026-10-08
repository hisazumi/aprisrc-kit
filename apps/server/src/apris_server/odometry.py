from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Pose, PoseEstimateQuality


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass(frozen=True, slots=True)
class OdometryConfig:
    wheel_radius_m: float = 0.0475
    track_width_m: float = 0.225
    ticks_per_revolution: int = 1320
    imu_weight: float = 0.70


class WheelImuOdometry:
    """Differential-drive odometry from cumulative encoders and IMU yaw rate."""

    def __init__(self, config: OdometryConfig | None = None) -> None:
        self.config = config or OdometryConfig()
        self.reset()

    def reset(self) -> None:
        self._pose = Pose(x=0.0, y=0.0, yaw=0.0)
        self._left_ticks: int | None = None
        self._right_ticks: int | None = None
        self._timestamp: float | None = None
        self._encoder_status: str = "missing"
        self._imu_status: str = "missing"
        self._anomalies: list[str] = []

    def update(
        self,
        *,
        timestamp: float,
        left_ticks: int | None,
        right_ticks: int | None,
        imu_yaw_rate_rad_s: float | None,
        encoder_fault: bool = False,
        imu_fault: bool = False,
    ) -> None:
        anomalies: list[str] = []
        dt = 0.0 if self._timestamp is None else max(0.0, min(timestamp - self._timestamp, 0.25))

        encoder_valid = (
            not encoder_fault
            and left_ticks is not None
            and right_ticks is not None
            and self._left_ticks is not None
            and self._right_ticks is not None
        )
        imu_valid = not imu_fault and imu_yaw_rate_rad_s is not None and math.isfinite(
            imu_yaw_rate_rad_s
        )

        distance = 0.0
        encoder_yaw_delta: float | None = None
        if encoder_valid:
            metres_per_tick = (
                2.0 * math.pi * self.config.wheel_radius_m / self.config.ticks_per_revolution
            )
            left_delta = (left_ticks - self._left_ticks) * metres_per_tick
            right_delta = (right_ticks - self._right_ticks) * metres_per_tick
            distance = (left_delta + right_delta) * 0.5
            encoder_yaw_delta = (right_delta - left_delta) / self.config.track_width_m
            self._encoder_status = "ok"
        elif encoder_fault:
            self._encoder_status = "fault"
            anomalies.append("encoder_fault")
        else:
            self._encoder_status = "missing"
            anomalies.append("encoder_missing")

        imu_yaw_delta = imu_yaw_rate_rad_s * dt if imu_valid else None
        if imu_valid:
            self._imu_status = "ok"
        elif imu_fault:
            self._imu_status = "fault"
            anomalies.append("imu_fault")
        else:
            self._imu_status = "missing"
            anomalies.append("imu_missing")

        if encoder_yaw_delta is not None and imu_yaw_delta is not None:
            yaw_delta = (
                (1.0 - self.config.imu_weight) * encoder_yaw_delta
                + self.config.imu_weight * imu_yaw_delta
            )
        elif encoder_yaw_delta is not None:
            yaw_delta = encoder_yaw_delta
        elif imu_yaw_delta is not None:
            yaw_delta = imu_yaw_delta
        else:
            yaw_delta = 0.0

        if encoder_valid:
            yaw_midpoint = self._pose.yaw + yaw_delta * 0.5
            self._pose = Pose(
                x=self._pose.x + distance * math.cos(yaw_midpoint),
                y=self._pose.y + distance * math.sin(yaw_midpoint),
                yaw=normalize_angle(self._pose.yaw + yaw_delta),
            )
        elif imu_valid:
            self._pose = self._pose.model_copy(
                update={"yaw": normalize_angle(self._pose.yaw + yaw_delta)}
            )

        if left_ticks is not None and right_ticks is not None:
            self._left_ticks = left_ticks
            self._right_ticks = right_ticks
        self._timestamp = timestamp
        self._anomalies = anomalies

    @property
    def pose(self) -> Pose:
        return self._pose.model_copy()

    def quality(self, age_ms: float = 0.0) -> PoseEstimateQuality:
        both_ok = self._encoder_status == "ok" and self._imu_status == "ok"
        encoder_only = self._encoder_status == "ok"
        confidence = 0.96 if both_ok else 0.62 if encoder_only else 0.20
        confidence *= max(0.0, 1.0 - min(age_ms, 5000.0) / 6000.0)
        source = "encoder_imu" if both_ok else "encoder_only" if encoder_only else "unavailable"
        return PoseEstimateQuality(
            frame_id="odom",
            source=source,
            confidence=confidence,
            age_ms=age_ms,
            encoder_status=self._encoder_status,
            imu_status=self._imu_status,
            anomalies=list(self._anomalies),
        )
