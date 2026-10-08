from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class StrictRoverModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoverCapabilities(StrictRoverModel):
    bounded_motion: bool = True
    velocity_control: bool = True
    encoders: bool = True
    imu: bool = True
    battery: bool = True


class RoverSafetyLimits(StrictRoverModel):
    max_linear_speed_mps: float = Field(gt=0.0, le=2.0)
    max_angular_speed_rad_s: float = Field(gt=0.0, le=10.0)
    max_distance_m: float = Field(gt=0.0, le=100.0)
    max_angle_rad: float = Field(gt=0.0, le=100.0)
    max_motion_duration_ms: int = Field(ge=100, le=300_000)
    max_lease_ms: int = Field(ge=100, le=10_000)

    @field_validator(
        "max_linear_speed_mps",
        "max_angular_speed_rad_s",
        "max_distance_m",
        "max_angle_rad",
    )
    @classmethod
    def finite_limit(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("safety limit must be finite")
        return value


class RoverHello(StrictRoverModel):
    v: Literal[1] = 1
    type: Literal["rover_hello"] = "rover_hello"
    protocol_versions: list[int] = Field(min_length=1, max_length=8)
    rover_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    boot_id: str = Field(min_length=1, max_length=128)
    firmware_version: str = Field(min_length=1, max_length=64)
    build_id: str = Field(min_length=1, max_length=128)
    hardware_revision: str = Field(min_length=1, max_length=128)
    capabilities: RoverCapabilities
    safety_limits: RoverSafetyLimits

    @field_validator("protocol_versions")
    @classmethod
    def valid_protocol_versions(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(version <= 0 for version in value):
            raise ValueError("protocol versions must be unique positive integers")
        return value


class RoverSessionMessage(StrictRoverModel):
    v: Literal[1] = 1
    rover_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    boot_id: str = Field(min_length=1, max_length=128)
    connection_epoch: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=0)


class RoverHeartbeat(RoverSessionMessage):
    type: Literal["heartbeat"] = "heartbeat"
    sent_at_ms: int = Field(ge=0)
    clock_offset_ms: float
    clock_uncertainty_ms: float = Field(ge=0.0)
    motor_state: Literal["stopped", "moving", "fault"]
    estop_latched: bool
    active_motion_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("clock_offset_ms", "clock_uncertainty_ms")
    @classmethod
    def finite_clock_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("clock estimate must be finite")
        return value


class RoverTelemetry(RoverSessionMessage):
    type: Literal["telemetry"] = "telemetry"
    measured_at_ms: int = Field(ge=0)
    linear_velocity_mps: float
    angular_velocity_rad_s: float
    odometry_x_m: float
    odometry_y_m: float
    odometry_yaw_rad: float
    battery_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    motor_state: Literal["stopped", "moving", "fault"]
    fault_codes: list[str] = Field(default_factory=list, max_length=32)

    @field_validator(
        "linear_velocity_mps",
        "angular_velocity_rad_s",
        "odometry_x_m",
        "odometry_y_m",
        "odometry_yaw_rad",
    )
    @classmethod
    def finite_telemetry(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("telemetry value must be finite")
        return value


class RoverCommandAck(RoverSessionMessage):
    type: Literal["command_ack"] = "command_ack"
    command_id: str = Field(min_length=1, max_length=128)
    status: Literal["accepted", "rejected"]
    code: str | None = Field(default=None, min_length=1, max_length=64)
    detail: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def rejection_has_code(self) -> RoverCommandAck:
        if self.status == "rejected" and self.code is None:
            raise ValueError("rejected command acknowledgement requires code")
        if self.status == "accepted" and self.code is not None:
            raise ValueError("accepted command acknowledgement must not carry code")
        return self


class RoverMotionStatus(RoverSessionMessage):
    type: Literal["motion_status"] = "motion_status"
    motion_id: str = Field(min_length=1, max_length=128)
    status: Literal["accepted", "running", "completed", "cancelled", "failed"]
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = Field(default=None, min_length=1, max_length=120)
    motor_stopped: bool

    @model_validator(mode="after")
    def terminal_status_is_stopped(self) -> RoverMotionStatus:
        if self.status in {"completed", "cancelled", "failed"} and not self.motor_stopped:
            raise ValueError("terminal motion status requires stopped motor")
        return self


class RoverEvent(RoverSessionMessage):
    type: Literal["rover_event"] = "rover_event"
    event: str = Field(min_length=1, max_length=64)
    detail: str = Field(default="", max_length=240)


RoverSessionInbound = Annotated[
    RoverHeartbeat | RoverTelemetry | RoverCommandAck | RoverMotionStatus | RoverEvent,
    Field(discriminator="type"),
]
rover_session_message_adapter = TypeAdapter(RoverSessionInbound)


class RoverWelcome(StrictRoverModel):
    v: Literal[1] = 1
    type: Literal["rover_welcome"] = "rover_welcome"
    protocol_version: Literal[1] = 1
    rover_id: str
    boot_id: str
    connection_epoch: str
    server_version: str
    build_id: str
    instance_id: str
    heartbeat_interval_ms: int = Field(ge=100, le=10_000)
    clock_uncertainty_limit_ms: int = Field(ge=0, le=10_000)


class RoverError(StrictRoverModel):
    v: Literal[1] = 1
    type: Literal["rover_error"] = "rover_error"
    code: str = Field(min_length=1, max_length=64)
    detail: str = Field(max_length=240)
    command_id: str | None = Field(default=None, min_length=1, max_length=128)


class RoverCommandEnvelope(StrictRoverModel):
    v: Literal[1] = 1
    connection_epoch: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=0)
    command_id: str = Field(min_length=1, max_length=128)
    issued_at_ms: int = Field(ge=0)
    ttl_ms: int = Field(ge=50, le=2_000)
    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    effect_id: str | None = Field(default=None, min_length=1, max_length=128)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class StartMotion(RoverCommandEnvelope):
    type: Literal["start_motion"] = "start_motion"
    motion_id: str = Field(min_length=1, max_length=128)
    kind: Literal["linear", "rotate"]
    distance_m: float | None = None
    angle_rad: float | None = None
    max_linear_speed_mps: float = Field(gt=0.0, le=2.0)
    max_angular_speed_rad_s: float = Field(gt=0.0, le=10.0)
    max_duration_ms: int = Field(ge=100, le=300_000)
    lease_ms: int = Field(ge=100, le=10_000)

    @field_validator(
        "distance_m",
        "angle_rad",
        "max_linear_speed_mps",
        "max_angular_speed_rad_s",
    )
    @classmethod
    def finite_motion_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("motion value must be finite")
        return value

    @model_validator(mode="after")
    def target_matches_kind(self) -> StartMotion:
        if self.kind == "linear":
            if self.distance_m is None or abs(self.distance_m) < 1e-9:
                raise ValueError("linear motion requires non-zero distance_m")
            if self.angle_rad is not None:
                raise ValueError("linear motion must not include angle_rad")
        else:
            if self.angle_rad is None or abs(self.angle_rad) < 1e-9:
                raise ValueError("rotate motion requires non-zero angle_rad")
            if self.distance_m is not None:
                raise ValueError("rotate motion must not include distance_m")
        return self


class RenewMotionLease(RoverCommandEnvelope):
    type: Literal["renew_motion_lease"] = "renew_motion_lease"
    motion_id: str = Field(min_length=1, max_length=128)
    lease_ms: int = Field(ge=100, le=10_000)


class CancelRoverMotion(RoverCommandEnvelope):
    type: Literal["cancel_motion"] = "cancel_motion"
    motion_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="server_cancelled", min_length=1, max_length=120)


class SetVelocity(RoverCommandEnvelope):
    type: Literal["set_velocity"] = "set_velocity"
    linear_velocity_mps: float
    angular_velocity_rad_s: float
    lease_ms: int = Field(ge=100, le=10_000)

    @field_validator("linear_velocity_mps", "angular_velocity_rad_s")
    @classmethod
    def finite_velocity(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("velocity must be finite")
        return value


class RoverStop(RoverCommandEnvelope):
    type: Literal["stop"] = "stop"
    reason: str = Field(default="server_stop", min_length=1, max_length=120)


class RoverEmergencyStop(RoverCommandEnvelope):
    type: Literal["estop"] = "estop"
    reason: str = Field(default="server_estop", min_length=1, max_length=120)


class RoverClearEmergencyStop(RoverCommandEnvelope):
    type: Literal["clear_estop"] = "clear_estop"


ServerRoverCommand = Annotated[
    StartMotion
    | RenewMotionLease
    | CancelRoverMotion
    | SetVelocity
    | RoverStop
    | RoverEmergencyStop
    | RoverClearEmergencyStop,
    Field(discriminator="type"),
]
server_rover_command_adapter = TypeAdapter(ServerRoverCommand)


RoverWireMessage = Annotated[
    RoverHello
    | RoverHeartbeat
    | RoverTelemetry
    | RoverCommandAck
    | RoverMotionStatus
    | RoverEvent
    | RoverWelcome
    | RoverError
    | StartMotion
    | RenewMotionLease
    | CancelRoverMotion
    | SetVelocity
    | RoverStop
    | RoverEmergencyStop
    | RoverClearEmergencyStop,
    Field(discriminator="type"),
]
rover_wire_message_adapter = TypeAdapter(RoverWireMessage)
