from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientHello(StrictModel):
    v: Literal[1] = 1
    type: Literal["client_hello"]
    client_kind: Literal[
        "service_app",
        "operator_console",
        "development_lab",
        "vehicle_perception",
        "physicode_bridge",
    ]
    device_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    app_version: str = Field(min_length=1, max_length=64)
    build_id: str = Field(min_length=1, max_length=128)


class AcquireControl(StrictModel):
    v: Literal[1] = 1
    type: Literal["acquire_control"]


class ReleaseControl(StrictModel):
    v: Literal[1] = 1
    type: Literal["release_control"]


class DriveCommand(StrictModel):
    v: Literal[1] = 1
    type: Literal["drive"]
    vx: float
    vy: float = 0.0
    wz: float
    ttl_ms: int = Field(default=500, ge=100, le=2000)
    seq: int = Field(default=0, ge=0)

    @field_validator("vx", "vy", "wz")
    @classmethod
    def finite_velocity(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("velocity must be finite")
        return value


class StopCommand(StrictModel):
    v: Literal[1] = 1
    type: Literal["stop"]
    reason: str = Field(default="operator", max_length=120)


class MoveCommand(StrictModel):
    v: Literal[1] = 1
    type: Literal["move"]
    request_id: str = Field(min_length=1, max_length=64)
    run_id: str | None = Field(default=None, min_length=1, max_length=64)
    effect_id: str | None = Field(default=None, min_length=1, max_length=64)
    distance_m: float = Field(ge=-5.0, le=5.0)
    speed_mps: float = Field(default=0.18, ge=0.05, le=0.30)

    @field_validator("distance_m", "speed_mps")
    @classmethod
    def finite_motion_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("motion value must be finite")
        return value

    @field_validator("distance_m")
    @classmethod
    def nonzero_distance(cls, value: float) -> float:
        if abs(value) < 1e-9:
            raise ValueError("distance must not be zero")
        return value


class TurnCommand(StrictModel):
    v: Literal[1] = 1
    type: Literal["turn"]
    request_id: str = Field(min_length=1, max_length=64)
    run_id: str | None = Field(default=None, min_length=1, max_length=64)
    effect_id: str | None = Field(default=None, min_length=1, max_length=64)
    angle_deg: float = Field(ge=-720.0, le=720.0)
    speed_rad_s: float = Field(default=0.70, ge=0.10, le=1.20)

    @field_validator("angle_deg", "speed_rad_s")
    @classmethod
    def finite_motion_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("motion value must be finite")
        return value

    @field_validator("angle_deg")
    @classmethod
    def nonzero_angle(cls, value: float) -> float:
        if abs(value) < 1e-9:
            raise ValueError("angle must not be zero")
        return value


class CancelMotion(StrictModel):
    v: Literal[1] = 1
    type: Literal["cancel_motion"]


class EmergencyStop(StrictModel):
    v: Literal[1] = 1
    type: Literal["estop"]
    reason: str = Field(default="operator", max_length=120)


class ClearEmergencyStop(StrictModel):
    v: Literal[1] = 1
    type: Literal["clear_estop"]


class ResetPose(StrictModel):
    v: Literal[1] = 1
    type: Literal["reset_pose"]


class ReadFrontObstacle(StrictModel):
    v: Literal[1] = 1
    type: Literal["read_front_obstacle"]
    request_id: str = Field(min_length=1, max_length=64)
    run_id: str | None = Field(default=None, min_length=1, max_length=64)
    effect_id: str | None = Field(default=None, min_length=1, max_length=64)


class PathClearance(StrictModel):
    v: Literal[1] = 1
    type: Literal["path_clearance"]
    confirmed: bool


class PerceptionObservation(StrictModel):
    v: Literal[1] = 1
    type: Literal["perception_observation"] = "perception_observation"
    observation_id: str = Field(min_length=1, max_length=64)
    kind: Literal["person", "marker"]
    status: Literal["detected", "lost"] = "detected"
    confidence: float = Field(ge=0.0, le=1.0)
    captured_at: float = Field(gt=0.0)
    source: Literal["camera", "recorded", "manual", "scenario", "replay"]
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def lost_observation_has_zero_confidence(self) -> PerceptionObservation:
        if self.status == "lost" and self.confidence != 0.0:
            raise ValueError("lost observations must have zero confidence")
        return self


ClientMessage = Annotated[
    ClientHello
    | AcquireControl
    | ReleaseControl
    | DriveCommand
    | StopCommand
    | MoveCommand
    | TurnCommand
    | CancelMotion
    | EmergencyStop
    | ClearEmergencyStop
    | ResetPose
    | ReadFrontObstacle
    | PathClearance
    | PerceptionObservation,
    Field(discriminator="type"),
]
client_message_adapter = TypeAdapter(ClientMessage)


class Pose(StrictModel):
    x: float
    y: float
    yaw: float


class Velocity(StrictModel):
    vx: float
    vy: float
    wz: float


class Capabilities(StrictModel):
    lateral_motion: bool = False
    pose: bool = True
    imu: bool = True
    lidar: bool = False
    camera: bool = False


class PoseEstimateQuality(StrictModel):
    frame_id: Literal["odom", "course"] = "odom"
    source: Literal["encoder_imu", "encoder_only", "marker_corrected", "unavailable"] = (
        "unavailable"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    age_ms: float = Field(default=0.0, ge=0.0)
    encoder_status: Literal["ok", "missing", "fault"] = "missing"
    imu_status: Literal["ok", "missing", "fault"] = "missing"
    anomalies: list[str] = Field(default_factory=list)
    last_marker_id: int | None = None


class RoverState(StrictModel):
    timestamp: float
    connected: bool
    pose: Pose
    velocity: Velocity
    battery_percent: float | None = None
    capabilities: Capabilities
    command_age_ms: float | None = None
    pose_quality: PoseEstimateQuality = Field(default_factory=PoseEstimateQuality)


class HelloMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["hello"] = "hello"
    client_id: str
    server_name: str = "APRIS Rover Local Server"
    server_version: str = "0.1.0"
    build_id: str = "unknown"
    instance_id: str = "unknown"
    supported_protocol_versions: list[Literal[1]] = Field(default_factory=lambda: [1])
    capabilities: Capabilities


class ControlMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["control"] = "control"
    owner_client_id: str | None
    is_owner: bool
    estop_latched: bool


class StateMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["state"] = "state"
    state: RoverState


class EventMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["event"] = "event"
    event: str
    detail: str = ""


class ScenarioEventMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["scenario_event"] = "scenario_event"
    event_id: str
    kind: Literal["person", "marker", "voice_intent"]
    payload: dict[str, Any]
    source: Literal["manual", "scenario", "replay"]
    scenario_id: str | None = None


class PerceptionEventMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["perception_event"] = "perception_event"
    event_id: str
    kind: Literal["person", "marker"]
    status: Literal["detected", "lost", "rejected"]
    confidence: float = Field(ge=0.0, le=1.0)
    captured_at: float
    source: Literal["camera", "recorded", "manual", "scenario", "replay"]
    payload: dict[str, Any]
    accepted: bool
    reason: str = ""


class MotionMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["motion"] = "motion"
    request_id: str
    run_id: str | None = None
    effect_id: str | None = None
    motion: Literal["move", "turn"]
    status: Literal["started", "completed", "cancelled", "failed"]
    detail: str = ""


class FrontObstacleSnapshot(StrictModel):
    state: Literal["CLEAR", "BLOCKED", "UNKNOWN"]
    observed_state: Literal["CLEAR", "BLOCKED", "UNKNOWN"]
    perception_health: Literal["healthy", "degraded", "unavailable"]
    source: Literal["manual", "scenario", "camera", "sensor", "replay"] | None
    observed_at: float | None
    heartbeat_at: float | None
    observation_age_ms: float | None
    heartbeat_age_ms: float | None
    stale_after_ms: float
    stale: bool
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    distance_m: float | None = Field(default=None, ge=0.0)
    lateral_m: float | None = None
    latched: bool
    latched_at: float | None
    cleared_at: float | None
    clear_reason: str | None


class FrontObstacleMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["front_obstacle"] = "front_obstacle"
    request_id: str | None = None
    run_id: str | None = None
    effect_id: str | None = None
    obstacle: FrontObstacleSnapshot


class ErrorMessage(StrictModel):
    v: Literal[1] = 1
    type: Literal["error"] = "error"
    code: str
    detail: str
