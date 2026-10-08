import time

import pytest
from pydantic import ValidationError

from apris_server.models import (
    ClientHello,
    DriveCommand,
    MoveCommand,
    PathClearance,
    PerceptionObservation,
    TurnCommand,
    client_message_adapter,
)


def test_client_hello_is_parsed() -> None:
    message = client_message_adapter.validate_python(
        {
            "v": 1,
            "type": "client_hello",
            "client_kind": "operator_console",
            "device_id": "device-1",
            "session_id": "session-1",
            "app_version": "0.1.0",
            "build_id": "test",
        }
    )
    assert isinstance(message, ClientHello)
    assert message.client_kind == "operator_console"


def test_drive_message_is_parsed() -> None:
    message = client_message_adapter.validate_json(
        '{"v":1,"type":"drive","vx":0.2,"vy":0,"wz":0.3,"ttl_ms":500,"seq":1}'
    )
    assert isinstance(message, DriveCommand)
    assert message.vx == pytest.approx(0.2)


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_velocity_is_rejected(invalid: str) -> None:
    with pytest.raises(ValidationError):
        client_message_adapter.validate_json(
            f'{{"v":1,"type":"drive","vx":{invalid},"vy":0,"wz":0,"ttl_ms":500,"seq":1}}'
        )


def test_high_level_motion_messages_are_parsed() -> None:
    move = client_message_adapter.validate_json(
        '{"v":1,"type":"move","request_id":"m1","run_id":"r1",'
        '"effect_id":"e1","distance_m":0.4,"speed_mps":0.18}'
    )
    turn = client_message_adapter.validate_json(
        '{"v":1,"type":"turn","request_id":"t1","angle_deg":90,"speed_rad_s":0.7}'
    )

    assert isinstance(move, MoveCommand)
    assert move.run_id == "r1"
    assert move.effect_id == "e1"
    assert isinstance(turn, TurnCommand)


def test_path_clearance_is_a_narrow_boolean_message() -> None:
    message = client_message_adapter.validate_json(
        '{"v":1,"type":"path_clearance","confirmed":true}'
    )
    assert isinstance(message, PathClearance)
    assert message.confirmed is True

    with pytest.raises(ValidationError):
        client_message_adapter.validate_json(
            '{"v":1,"type":"path_clearance","confirmed":true,"state":"CLEAR"}'
        )


@pytest.mark.parametrize(
    "raw",
    [
        '{"v":1,"type":"move","request_id":"m1","distance_m":0,"speed_mps":0.18}',
        '{"v":1,"type":"turn","request_id":"t1","angle_deg":0,"speed_rad_s":0.7}',
    ],
)
def test_zero_length_motion_is_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        client_message_adapter.validate_json(raw)


def test_perception_observation_is_parsed_and_lost_confidence_is_strict() -> None:
    message = client_message_adapter.validate_python(
        {
            "v": 1,
            "type": "perception_observation",
            "observation_id": "person-1",
            "kind": "person",
            "status": "detected",
            "confidence": 0.9,
            "captured_at": time.time(),
            "source": "camera",
            "payload": {"person_id": "p1"},
        }
    )
    assert isinstance(message, PerceptionObservation)

    with pytest.raises(ValidationError):
        client_message_adapter.validate_python(
            {
                **message.model_dump(),
                "status": "lost",
                "confidence": 0.1,
            }
        )
