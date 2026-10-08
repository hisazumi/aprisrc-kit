from __future__ import annotations

import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .models import PerceptionObservation, Pose, RoverState
from .odometry import normalize_angle


class PerceptionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonPayload(PerceptionPayload):
    person_id: str = Field(default="person", min_length=1, max_length=64)
    center_x: float | None = Field(default=None, ge=0.0, le=1.0)
    center_y: float | None = Field(default=None, ge=0.0, le=1.0)
    width: float | None = Field(default=None, gt=0.0, le=1.0)
    height: float | None = Field(default=None, gt=0.0, le=1.0)
    bearing_deg: float | None = Field(default=None, ge=-180.0, le=180.0)


class MarkerPayload(PerceptionPayload):
    marker_id: int = Field(ge=0, le=1_000_000)
    relative_x_m: float | None = Field(default=None, ge=-10.0, le=10.0)
    relative_y_m: float | None = Field(default=None, ge=-10.0, le=10.0)
    relative_yaw_rad: float | None = Field(default=None, ge=-math.pi, le=math.pi)

    @model_validator(mode="after")
    def relative_position_is_complete(self) -> MarkerPayload:
        if (self.relative_x_m is None) != (self.relative_y_m is None):
            raise ValueError("relative_x_m and relative_y_m must be provided together")
        return self


class CourseMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(ge=0)
    label: str
    x_m: float
    y_m: float
    yaw_rad: float


class MarkerCorrectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applied: bool
    reason: str = ""
    innovation_m: float | None = None
    marker_id: int | None = None


def load_course_markers(path: Path) -> dict[int, CourseMarker]:
    document = json.loads(path.read_text(encoding="utf-8"))
    markers = [CourseMarker.model_validate(item) for item in document["markers"]]
    if len({marker.id for marker in markers}) != len(markers):
        raise ValueError("course marker ids must be unique")
    return {marker.id: marker for marker in markers}


class PoseFusion:
    """Transforms local odometry into the course frame using trusted marker observations."""

    def __init__(self, markers: dict[int, CourseMarker]) -> None:
        self.markers = markers
        self.reset()

    def reset(self) -> None:
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._offset_yaw = 0.0
        self._last_marker_id: int | None = None
        self._last_marker_at: float | None = None
        self._marker_confidence = 0.0

    def _course_pose(self, odom_pose: Pose) -> Pose:
        cosine = math.cos(self._offset_yaw)
        sine = math.sin(self._offset_yaw)
        return Pose(
            x=self._offset_x + cosine * odom_pose.x - sine * odom_pose.y,
            y=self._offset_y + sine * odom_pose.x + cosine * odom_pose.y,
            yaw=normalize_angle(odom_pose.yaw + self._offset_yaw),
        )

    def set_course_origin(self, pose: Pose) -> None:
        """Set the course transform after a development Simulator odometry reset."""
        self.reset()
        self._offset_x = pose.x
        self._offset_y = pose.y
        self._offset_yaw = pose.yaw

    def apply(self, state: RoverState) -> RoverState:
        pose = self._course_pose(state.pose)
        quality = state.pose_quality.model_copy(deep=True)
        quality.frame_id = "course"
        if self._last_marker_at is not None:
            marker_age_ms = max(0.0, (time.monotonic() - self._last_marker_at) * 1000.0)
            if marker_age_ms <= 5000.0:
                quality.source = "marker_corrected"
                quality.confidence = max(
                    quality.confidence,
                    self._marker_confidence * (1.0 - marker_age_ms / 7000.0),
                )
            else:
                quality.anomalies = [*quality.anomalies, "marker_correction_stale"]
            quality.last_marker_id = self._last_marker_id
        return state.model_copy(update={"pose": pose, "pose_quality": quality})

    def correct(
        self,
        odom_pose: Pose,
        payload: MarkerPayload,
        confidence: float,
    ) -> MarkerCorrectionResult:
        marker = self.markers.get(payload.marker_id)
        if marker is None:
            return MarkerCorrectionResult(
                applied=False, reason="unknown_marker", marker_id=payload.marker_id
            )
        if payload.relative_x_m is None or payload.relative_y_m is None:
            return MarkerCorrectionResult(
                applied=False, reason="relative_pose_missing", marker_id=payload.marker_id
            )
        distance = math.hypot(payload.relative_x_m, payload.relative_y_m)
        if not 0.08 <= distance <= 5.0:
            return MarkerCorrectionResult(
                applied=False, reason="marker_range_invalid", marker_id=payload.marker_id
            )

        current = self._course_pose(odom_pose)
        candidate_yaw = current.yaw
        if payload.relative_yaw_rad is not None:
            candidate_yaw = normalize_angle(marker.yaw_rad - payload.relative_yaw_rad)
        cosine = math.cos(candidate_yaw)
        sine = math.sin(candidate_yaw)
        candidate_x = marker.x_m - (
            cosine * payload.relative_x_m - sine * payload.relative_y_m
        )
        candidate_y = marker.y_m - (
            sine * payload.relative_x_m + cosine * payload.relative_y_m
        )
        innovation = math.hypot(candidate_x - current.x, candidate_y - current.y)
        yaw_innovation = abs(normalize_angle(candidate_yaw - current.yaw))
        if innovation > 3.0 or yaw_innovation > math.radians(90.0):
            return MarkerCorrectionResult(
                applied=False,
                reason="marker_innovation_too_large",
                innovation_m=innovation,
                marker_id=payload.marker_id,
            )

        alpha = min(0.75, max(0.25, confidence * 0.70))
        corrected_x = current.x + alpha * (candidate_x - current.x)
        corrected_y = current.y + alpha * (candidate_y - current.y)
        corrected_yaw = normalize_angle(
            current.yaw + alpha * normalize_angle(candidate_yaw - current.yaw)
        )
        self._offset_yaw = normalize_angle(corrected_yaw - odom_pose.yaw)
        cosine = math.cos(self._offset_yaw)
        sine = math.sin(self._offset_yaw)
        self._offset_x = corrected_x - (cosine * odom_pose.x - sine * odom_pose.y)
        self._offset_y = corrected_y - (sine * odom_pose.x + cosine * odom_pose.y)
        self._last_marker_id = marker.id
        self._last_marker_at = time.monotonic()
        self._marker_confidence = confidence
        return MarkerCorrectionResult(
            applied=True, innovation_m=innovation, marker_id=marker.id
        )


class ObservationValidator:
    def __init__(self) -> None:
        self._seen: deque[str] = deque(maxlen=500)
        self._seen_set: set[str] = set()

    def validate_common(self, observation: PerceptionObservation) -> str | None:
        if observation.observation_id in self._seen_set:
            return "duplicate_observation"
        self._seen.append(observation.observation_id)
        self._seen_set = set(self._seen)
        age = time.time() - observation.captured_at
        if age > 2.5:
            return "observation_too_old"
        if age < -0.5:
            return "observation_from_future"
        minimum = 0.50 if observation.kind == "person" else 0.65
        if observation.status == "detected" and observation.confidence < minimum:
            return "confidence_too_low"
        return None

    @staticmethod
    def payload(observation: PerceptionObservation) -> PersonPayload | MarkerPayload:
        model = PersonPayload if observation.kind == "person" else MarkerPayload
        return model.model_validate(observation.payload)


def validation_reason(error: ValidationError) -> str:
    first = error.errors()[0]
    return f"invalid_payload:{'.'.join(str(part) for part in first['loc'])}"


def event_payload(
    payload: PerceptionPayload,
    correction: MarkerCorrectionResult | None,
) -> dict[str, Any]:
    data = payload.model_dump(mode="json", exclude_none=True)
    if correction is not None:
        data["pose_correction"] = correction.model_dump(mode="json", exclude_none=True)
    return data
