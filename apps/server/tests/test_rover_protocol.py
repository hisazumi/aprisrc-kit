from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from apris_server.fake_rover import FakeEsp32Rover
from apris_server.rover_protocol import (
    RenewMotionLease,
    RoverCapabilities,
    RoverHello,
    RoverSafetyLimits,
    RoverWelcome,
    SetVelocity,
    StartMotion,
    rover_wire_message_adapter,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPOSITORY_ROOT / "packages" / "protocol" / "rover-v1.schema.json"
FIXTURE_ROOT = REPOSITORY_ROOT / "packages" / "protocol" / "rover-v1-fixtures"


def make_hello() -> RoverHello:
    return RoverHello(
        protocol_versions=[1],
        rover_id="fake-ugv02",
        boot_id="boot-1",
        firmware_version="0.1.0-test",
        build_id="test-build",
        hardware_revision="test-hardware",
        capabilities=RoverCapabilities(),
        safety_limits=RoverSafetyLimits(
            max_linear_speed_mps=0.08,
            max_angular_speed_rad_s=0.5,
            max_distance_m=1.0,
            max_angle_rad=3.2,
            max_motion_duration_ms=10_000,
            max_lease_ms=500,
        ),
    )


def make_fake() -> FakeEsp32Rover:
    fake = FakeEsp32Rover(make_hello())
    fake.connect(
        RoverWelcome(
            rover_id="fake-ugv02",
            boot_id="boot-1",
            connection_epoch="epoch-1",
            server_version="0.1.0",
            build_id="server-test",
            instance_id="instance-test",
            heartbeat_interval_ms=500,
            clock_uncertainty_limit_ms=100,
        )
    )
    return fake


def start_motion(*, seq: int = 0, command_id: str = "command-1") -> StartMotion:
    return StartMotion(
        connection_epoch="epoch-1",
        seq=seq,
        command_id=command_id,
        issued_at_ms=1_000,
        ttl_ms=500,
        motion_id="motion-1",
        kind="linear",
        distance_m=0.2,
        max_linear_speed_mps=0.08,
        max_angular_speed_rad_s=0.5,
        max_duration_ms=5_000,
        lease_ms=500,
    )


def test_committed_schema_matches_models_and_validates_fixtures() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    generated = rover_wire_message_adapter.json_schema()
    generated["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    generated["$id"] = "https://apris.example/schema/rover-protocol-v1.json"
    generated["title"] = "APRIS Rover WebSocket protocol v1"
    assert committed == generated

    validator = Draft202012Validator(committed)
    validator.check_schema(committed)
    for fixture_path in sorted(FIXTURE_ROOT.glob("*.json")):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        validator.validate(fixture)
        rover_wire_message_adapter.validate_python(fixture)


def test_motion_shape_and_terminal_motor_state_are_strict() -> None:
    with pytest.raises(ValidationError):
        StartMotion(
            **{
                **start_motion().model_dump(),
                "kind": "rotate",
            }
        )

    with pytest.raises(ValidationError):
        rover_wire_message_adapter.validate_python(
            {
                "v": 1,
                "type": "motion_status",
                "rover_id": "fake-ugv02",
                "boot_id": "boot-1",
                "connection_epoch": "epoch-1",
                "seq": 1,
                "motion_id": "motion-1",
                "status": "completed",
                "progress": 1.0,
                "reason": None,
                "motor_stopped": False,
            }
        )


def test_fake_rover_executes_once_and_reports_completion_after_stop() -> None:
    fake = make_fake()
    started = fake.apply(start_motion(), now_ms=1_000)
    assert [message.type for message in started] == ["command_ack", "motion_status"]
    assert started[0].status == "accepted"
    assert started[1].status == "running"
    assert fake.linear_velocity_mps == pytest.approx(0.08)

    completed = fake.complete_motion()
    assert completed.status == "completed"
    assert completed.motor_stopped is True
    assert fake.motor_stopped is True

    duplicate = fake.apply(start_motion(seq=1, command_id="command-duplicate"), now_ms=1_100)
    assert duplicate[0].status == "accepted"
    assert duplicate[1].status == "completed"
    assert fake.active_motion is None
    assert fake.motor_stopped is True

    conflicting = StartMotion(
        **{
            **start_motion(seq=2, command_id="command-conflict").model_dump(),
            "distance_m": 0.3,
        }
    )
    conflict = fake.apply(conflicting, now_ms=1_200)
    assert conflict[0].status == "rejected"
    assert conflict[0].code == "motion_id_conflict"


def test_fake_rover_lease_expiry_and_disconnect_stop_motion() -> None:
    fake = make_fake()
    fake.apply(start_motion(), now_ms=1_000)
    expired = fake.tick(now_ms=1_500)
    assert expired[0].status == "cancelled"
    assert expired[0].reason == "motion_lease_expired"
    assert fake.motor_stopped is True

    fake = make_fake()
    fake.apply(start_motion(), now_ms=1_000)
    disconnected = fake.disconnect()
    assert disconnected is not None
    assert disconnected.status == "cancelled"
    assert disconnected.reason == "connection_lost"
    assert fake.motor_stopped is True
    assert fake.connection_epoch is None


def test_expired_motion_cannot_be_revived_by_late_lease_renewal() -> None:
    fake = make_fake()
    fake.apply(start_motion(), now_ms=1_000)

    renewed = fake.apply(
        RenewMotionLease(
            connection_epoch="epoch-1",
            seq=1,
            command_id="late-renew",
            issued_at_ms=1_500,
            ttl_ms=500,
            motion_id="motion-1",
            lease_ms=500,
        ),
        now_ms=1_500,
    )
    assert renewed[0].type == "motion_status"
    assert renewed[0].reason == "motion_lease_expired"
    assert renewed[1].status == "rejected"
    assert renewed[1].code == "motion_already_terminal"
    assert fake.motor_stopped is True


def test_new_connection_epoch_never_resumes_unfinished_motion() -> None:
    fake = make_fake()
    fake.apply(start_motion(), now_ms=1_000)
    assert fake.active_motion is not None
    fake.connect(
        RoverWelcome(
            rover_id="fake-ugv02",
            boot_id="boot-1",
            connection_epoch="epoch-2",
            server_version="0.1.0",
            build_id="server-test",
            instance_id="instance-test",
            heartbeat_interval_ms=500,
            clock_uncertainty_limit_ms=100,
        )
    )
    assert fake.active_motion is None
    assert fake.motor_stopped is True
    assert fake.motion_history["motion-1"].status == "cancelled"
    assert fake.motion_history["motion-1"].reason == "connection_replaced"

    replay = StartMotion(
        **{
            **start_motion(command_id="reconnect-replay").model_dump(),
            "connection_epoch": "epoch-2",
        }
    )
    result = fake.apply(replay, now_ms=1_100)
    assert result[0].status == "accepted"
    assert result[1].status == "cancelled"
    assert fake.active_motion is None
    assert fake.motor_stopped is True


def test_fake_rover_rejects_expired_sequence_limits_and_mixed_control_modes() -> None:
    fake = make_fake()
    expired = fake.apply(start_motion(), now_ms=1_501)
    assert expired[0].status == "rejected"
    assert expired[0].code == "command_expired"

    replayed = fake.apply(start_motion(), now_ms=1_100)
    assert replayed[0].status == "rejected"
    assert replayed[0].code == "non_increasing_server_sequence"

    over_limit = StartMotion(
        **{
            **start_motion(seq=1, command_id="over-limit").model_dump(),
            "max_linear_speed_mps": 0.09,
        }
    )
    rejected = fake.apply(over_limit, now_ms=1_100)
    assert rejected[0].code == "firmware_limit_exceeded"

    fake = make_fake()
    fake.apply(start_motion(), now_ms=1_000)
    velocity = SetVelocity(
        connection_epoch="epoch-1",
        seq=1,
        command_id="velocity-while-moving",
        issued_at_ms=1_100,
        ttl_ms=500,
        linear_velocity_mps=0.02,
        angular_velocity_rad_s=0.0,
        lease_ms=500,
    )
    busy = fake.apply(velocity, now_ms=1_100)
    assert busy[0].code == "control_mode_busy"
