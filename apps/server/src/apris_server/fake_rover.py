from __future__ import annotations

from dataclasses import dataclass

from .rover_protocol import (
    CancelRoverMotion,
    RenewMotionLease,
    RoverClearEmergencyStop,
    RoverCommandAck,
    RoverEmergencyStop,
    RoverEvent,
    RoverHeartbeat,
    RoverHello,
    RoverMotionStatus,
    RoverStop,
    RoverTelemetry,
    RoverWelcome,
    ServerRoverCommand,
    SetVelocity,
    StartMotion,
)


@dataclass(slots=True)
class FakeMotion:
    motion_id: str
    command_id: str
    started_at_ms: int
    lease_deadline_ms: int
    duration_deadline_ms: int
    command_signature: tuple[object, ...]
    status: str = "running"
    progress: float = 0.0
    reason: str | None = None


class FakeEsp32Rover:
    """Motor-free Rover protocol state machine used before firmware exists."""

    def __init__(self, hello: RoverHello) -> None:
        self.hello = hello
        self.connection_epoch: str | None = None
        self.last_server_seq = -1
        self._rover_seq = -1
        self.active_motion: FakeMotion | None = None
        self.motion_history: dict[str, FakeMotion] = {}
        self.linear_velocity_mps = 0.0
        self.angular_velocity_rad_s = 0.0
        self.velocity_lease_deadline_ms: int | None = None
        self.estop_latched = False

    @property
    def motor_stopped(self) -> bool:
        return self.linear_velocity_mps == 0.0 and self.angular_velocity_rad_s == 0.0

    def connect(self, welcome: RoverWelcome) -> None:
        if welcome.rover_id != self.hello.rover_id or welcome.boot_id != self.hello.boot_id:
            raise ValueError("welcome identity does not match fake rover")
        if self.active_motion is not None:
            self.active_motion.status = "cancelled"
            self.active_motion.reason = "connection_replaced"
        self.connection_epoch = welcome.connection_epoch
        self.last_server_seq = -1
        self._rover_seq = -1
        self._stop_motor()
        self.active_motion = None

    def apply(
        self,
        command: ServerRoverCommand,
        *,
        now_ms: int,
    ) -> list[RoverCommandAck | RoverMotionStatus | RoverEvent]:
        prelude = self.tick(now_ms=now_ms)
        invalid = self._validate_envelope(command, now_ms)
        if invalid is not None:
            return [*prelude, self._ack(command.command_id, "rejected", invalid)]

        if isinstance(command, StartMotion):
            return [*prelude, *self._start_motion(command, now_ms)]
        if isinstance(command, RenewMotionLease):
            return [*prelude, *self._renew_motion_lease(command, now_ms)]
        if isinstance(command, CancelRoverMotion):
            return [
                *prelude,
                *self._cancel_motion(command.motion_id, command.reason, command.command_id),
            ]
        if isinstance(command, SetVelocity):
            return [*prelude, *self._set_velocity(command, now_ms)]
        if isinstance(command, RoverStop):
            messages = [self._ack(command.command_id, "accepted")]
            terminal = self._terminate_active("cancelled", command.reason)
            self._stop_motor()
            if terminal is not None:
                messages.append(terminal)
            return [*prelude, *messages]
        if isinstance(command, RoverEmergencyStop):
            self.estop_latched = True
            messages = [self._ack(command.command_id, "accepted")]
            terminal = self._terminate_active("cancelled", "estop")
            self._stop_motor()
            if terminal is not None:
                messages.append(terminal)
            messages.append(self._event("estop_latched", command.reason))
            return [*prelude, *messages]
        if isinstance(command, RoverClearEmergencyStop):
            self.estop_latched = False
            self._stop_motor()
            return [
                *prelude,
                self._ack(command.command_id, "accepted"),
                self._event("estop_cleared", "motion remains stopped"),
            ]
        raise AssertionError(f"Unhandled command type: {type(command).__name__}")

    def tick(self, *, now_ms: int) -> list[RoverMotionStatus | RoverEvent]:
        messages: list[RoverMotionStatus | RoverEvent] = []
        active = self.active_motion
        if active is not None and now_ms >= active.duration_deadline_ms:
            terminal = self._terminate_active("failed", "max_duration_expired")
            if terminal is not None:
                messages.append(terminal)
        elif active is not None and now_ms >= active.lease_deadline_ms:
            terminal = self._terminate_active("cancelled", "motion_lease_expired")
            if terminal is not None:
                messages.append(terminal)

        if (
            self.velocity_lease_deadline_ms is not None
            and now_ms >= self.velocity_lease_deadline_ms
        ):
            self._stop_motor()
            messages.append(self._event("velocity_lease_expired", "motor stopped"))
        return messages

    def complete_motion(self, *, progress: float = 1.0) -> RoverMotionStatus:
        if self.active_motion is None:
            raise RuntimeError("no active motion")
        self.active_motion.progress = progress
        terminal = self._terminate_active("completed", None)
        if terminal is None:
            raise AssertionError("active motion did not produce terminal status")
        return terminal

    def disconnect(self) -> RoverMotionStatus | None:
        terminal = self._terminate_active("cancelled", "connection_lost")
        self._stop_motor()
        self.connection_epoch = None
        self.last_server_seq = -1
        return terminal

    def heartbeat(
        self,
        *,
        now_ms: int,
        clock_offset_ms: float = 0.0,
        clock_uncertainty_ms: float = 0.0,
    ) -> RoverHeartbeat:
        return RoverHeartbeat(
            rover_id=self.hello.rover_id,
            boot_id=self.hello.boot_id,
            connection_epoch=self._required_epoch(),
            seq=self._next_rover_seq(),
            sent_at_ms=now_ms,
            clock_offset_ms=clock_offset_ms,
            clock_uncertainty_ms=clock_uncertainty_ms,
            motor_state="stopped" if self.motor_stopped else "moving",
            estop_latched=self.estop_latched,
            active_motion_id=(
                self.active_motion.motion_id if self.active_motion is not None else None
            ),
        )

    def telemetry(
        self,
        *,
        now_ms: int,
        x_m: float = 0.0,
        y_m: float = 0.0,
        yaw_rad: float = 0.0,
        battery_percent: float = 100.0,
        fault_codes: list[str] | None = None,
    ) -> RoverTelemetry:
        return RoverTelemetry(
            rover_id=self.hello.rover_id,
            boot_id=self.hello.boot_id,
            connection_epoch=self._required_epoch(),
            seq=self._next_rover_seq(),
            measured_at_ms=now_ms,
            linear_velocity_mps=self.linear_velocity_mps,
            angular_velocity_rad_s=self.angular_velocity_rad_s,
            odometry_x_m=x_m,
            odometry_y_m=y_m,
            odometry_yaw_rad=yaw_rad,
            battery_percent=battery_percent,
            motor_state="stopped" if self.motor_stopped else "moving",
            fault_codes=fault_codes or [],
        )

    def _validate_envelope(self, command: ServerRoverCommand, now_ms: int) -> str | None:
        if self.connection_epoch is None or command.connection_epoch != self.connection_epoch:
            return "stale_connection_epoch"
        if command.seq <= self.last_server_seq:
            return "non_increasing_server_sequence"
        self.last_server_seq = command.seq
        if now_ms > command.issued_at_ms + command.ttl_ms:
            return "command_expired"
        return None

    def _start_motion(
        self,
        command: StartMotion,
        now_ms: int,
    ) -> list[RoverCommandAck | RoverMotionStatus]:
        known = self.motion_history.get(command.motion_id)
        if known is not None:
            if known.command_signature != self._motion_signature(command):
                return [self._ack(command.command_id, "rejected", "motion_id_conflict")]
            return [
                self._ack(command.command_id, "accepted"),
                self._motion_status(known),
            ]
        if self.estop_latched:
            return [self._ack(command.command_id, "rejected", "estop_latched")]
        if self.active_motion is not None or self.velocity_lease_deadline_ms is not None:
            return [self._ack(command.command_id, "rejected", "control_mode_busy")]

        limits = self.hello.safety_limits
        target = abs(command.distance_m if command.kind == "linear" else command.angle_rad or 0.0)
        target_limit = limits.max_distance_m if command.kind == "linear" else limits.max_angle_rad
        if target > target_limit:
            return [self._ack(command.command_id, "rejected", "firmware_limit_exceeded")]
        if (
            command.max_linear_speed_mps > limits.max_linear_speed_mps
            or command.max_angular_speed_rad_s > limits.max_angular_speed_rad_s
            or command.max_duration_ms > limits.max_motion_duration_ms
            or command.lease_ms > limits.max_lease_ms
        ):
            return [self._ack(command.command_id, "rejected", "firmware_limit_exceeded")]

        motion = FakeMotion(
            motion_id=command.motion_id,
            command_id=command.command_id,
            started_at_ms=now_ms,
            lease_deadline_ms=now_ms + command.lease_ms,
            duration_deadline_ms=now_ms + command.max_duration_ms,
            command_signature=self._motion_signature(command),
        )
        self.motion_history[motion.motion_id] = motion
        self.active_motion = motion
        if command.kind == "linear":
            direction = 1.0 if (command.distance_m or 0.0) > 0 else -1.0
            self.linear_velocity_mps = direction * command.max_linear_speed_mps
        else:
            direction = 1.0 if (command.angle_rad or 0.0) > 0 else -1.0
            self.angular_velocity_rad_s = direction * command.max_angular_speed_rad_s
        return [
            self._ack(command.command_id, "accepted"),
            self._motion_status(motion),
        ]

    def _renew_motion_lease(
        self,
        command: RenewMotionLease,
        now_ms: int,
    ) -> list[RoverCommandAck | RoverMotionStatus]:
        if self.active_motion is None or self.active_motion.motion_id != command.motion_id:
            known = self.motion_history.get(command.motion_id)
            if known is None:
                return [self._ack(command.command_id, "rejected", "unknown_motion_id")]
            return [
                self._ack(command.command_id, "rejected", "motion_already_terminal"),
                self._motion_status(known),
            ]
        if command.lease_ms > self.hello.safety_limits.max_lease_ms:
            return [self._ack(command.command_id, "rejected", "firmware_limit_exceeded")]
        self.active_motion.lease_deadline_ms = now_ms + command.lease_ms
        return [self._ack(command.command_id, "accepted")]

    def _cancel_motion(
        self,
        motion_id: str,
        reason: str,
        command_id: str,
    ) -> list[RoverCommandAck | RoverMotionStatus]:
        if self.active_motion is not None and self.active_motion.motion_id == motion_id:
            acknowledgement = self._ack(command_id, "accepted")
            terminal = self._terminate_active("cancelled", reason)
            if terminal is None:
                raise AssertionError("active motion did not produce terminal status")
            return [acknowledgement, terminal]
        known = self.motion_history.get(motion_id)
        if known is not None:
            return [self._ack(command_id, "accepted"), self._motion_status(known)]
        return [self._ack(command_id, "rejected", "unknown_motion_id")]

    def _set_velocity(
        self,
        command: SetVelocity,
        now_ms: int,
    ) -> list[RoverCommandAck]:
        if self.estop_latched:
            return [self._ack(command.command_id, "rejected", "estop_latched")]
        if self.active_motion is not None:
            return [self._ack(command.command_id, "rejected", "control_mode_busy")]
        limits = self.hello.safety_limits
        if (
            abs(command.linear_velocity_mps) > limits.max_linear_speed_mps
            or abs(command.angular_velocity_rad_s) > limits.max_angular_speed_rad_s
            or command.lease_ms > limits.max_lease_ms
        ):
            return [self._ack(command.command_id, "rejected", "firmware_limit_exceeded")]
        self.linear_velocity_mps = command.linear_velocity_mps
        self.angular_velocity_rad_s = command.angular_velocity_rad_s
        self.velocity_lease_deadline_ms = now_ms + command.lease_ms
        return [self._ack(command.command_id, "accepted")]

    def _terminate_active(self, status: str, reason: str | None) -> RoverMotionStatus | None:
        motion = self.active_motion
        if motion is None:
            return None
        self._stop_motor()
        motion.status = status
        motion.reason = reason
        self.active_motion = None
        return self._motion_status(motion)

    @staticmethod
    def _motion_signature(command: StartMotion) -> tuple[object, ...]:
        return (
            command.kind,
            command.distance_m,
            command.angle_rad,
            command.max_linear_speed_mps,
            command.max_angular_speed_rad_s,
            command.max_duration_ms,
            command.lease_ms,
            command.run_id,
            command.effect_id,
            command.request_id,
        )

    def _stop_motor(self) -> None:
        self.linear_velocity_mps = 0.0
        self.angular_velocity_rad_s = 0.0
        self.velocity_lease_deadline_ms = None

    def _ack(self, command_id: str, status: str, code: str | None = None) -> RoverCommandAck:
        return RoverCommandAck(
            rover_id=self.hello.rover_id,
            boot_id=self.hello.boot_id,
            connection_epoch=self._required_epoch(),
            seq=self._next_rover_seq(),
            command_id=command_id,
            status=status,
            code=code,
        )

    def _motion_status(self, motion: FakeMotion) -> RoverMotionStatus:
        return RoverMotionStatus(
            rover_id=self.hello.rover_id,
            boot_id=self.hello.boot_id,
            connection_epoch=self._required_epoch(),
            seq=self._next_rover_seq(),
            motion_id=motion.motion_id,
            status=motion.status,
            progress=motion.progress,
            reason=motion.reason,
            motor_stopped=motion.status in {"completed", "cancelled", "failed"},
        )

    def _event(self, event: str, detail: str) -> RoverEvent:
        return RoverEvent(
            rover_id=self.hello.rover_id,
            boot_id=self.hello.boot_id,
            connection_epoch=self._required_epoch(),
            seq=self._next_rover_seq(),
            event=event,
            detail=detail,
        )

    def _required_epoch(self) -> str:
        if self.connection_epoch is None:
            raise RuntimeError("fake rover is not connected")
        return self.connection_epoch

    def _next_rover_seq(self) -> int:
        self._rover_seq += 1
        return self._rover_seq
