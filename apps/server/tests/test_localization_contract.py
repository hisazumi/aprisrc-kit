import json

import pytest
from pydantic import ValidationError

from apris_server.localization_contract import LocalizationSnapshot, MarkerObservation


def scope():
    return {
        "robotId": "robot-1",
        "controlEpoch": "control-1",
        "odomEpoch": "odom-1",
        "localizationEpoch": "loc-1",
        "map": {"mapId": "room", "revision": "1", "contentDigest": "a" * 64},
        "robotProfile": "robot-v1",
        "calibration": "cam-v1",
        "qualityProfile": "q-v1",
    }


def pose():
    return {"xM": 0.0, "yM": 0.0, "yawRad": 0.0}


def snapshot():
    return {
        **scope(),
        "clockId": "host-monotonic",
        "clockEpoch": "boot-1",
        "sampleTime": 1.0,
        "receivedTime": 1.0,
        "sequence": 0,
        "odomPose": pose(),
        "mapPose": None,
        "mapFromOdom": None,
        "odomAgeS": 0.0,
        "sensorStatus": "ok",
        "provenance": "simulated",
        "estimatorVersion": "planar-v1",
        "quality": {
            "status": "unlocalized",
            "reasons": ["initialization-required"],
            "positionErrorM": None,
            "headingErrorRad": None,
            "errorModel": "unqualified-v1",
            "lastCorrection": None,
            "distanceSinceCorrectionM": None,
            "rotationSinceCorrectionRad": None,
        },
    }


def observation():
    return {
        **scope(),
        "clockId": "host-monotonic",
        "clockEpoch": "boot-1",
        "captureTime": 1.0,
        "receivedTime": 1.1,
        "clockUncertaintyS": 0.01,
        "sourceId": "camera",
        "sessionEpoch": "camera-1",
        "sequence": 1,
        "observationId": "obs-1",
        "family": "example-square",
        "markerId": 1,
        "frameId": "base",
        "poseAmbiguous": False,
        "relativePose": {**pose(), "zM": 1.0, "rollRad": 0.0, "pitchRad": 0.0},
        "confidence": 0.9,
        "provenance": "synthetic",
    }


def parse(model, value):
    return model.model_validate_json(json.dumps(value))


def test_unlocalized_is_explicit_and_roundtrips():
    value = parse(LocalizationSnapshot, snapshot())
    assert value.mapPose is None
    assert LocalizationSnapshot.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(mapPose=pose()),
        lambda d: d.update(receivedTime=0.9),
        lambda d: d.update(sequence=True),
        lambda d: d.update(odomAgeS=-1),
        lambda d: d.update(provenance="truth"),
        lambda d: d["quality"].update(status="tracking"),
        lambda d: d["quality"].update(positionErrorM=float("nan")),
        lambda d: d["quality"].update(positionErrorM=-1),
        lambda d: d["quality"].update(reasons=[]),
    ],
)
def test_invalid_snapshots(mutation):
    data = snapshot()
    mutation(data)
    with pytest.raises(ValidationError):
        parse(LocalizationSnapshot, data)


def test_tracking_requires_pose_transform_and_known_error():
    data = snapshot()
    data.update(mapPose=pose(), mapFromOdom=pose())
    data["quality"].update(status="tracking", reasons=[], positionErrorM=0.1, headingErrorRad=0.1)
    parse(LocalizationSnapshot, data)
    data["quality"]["headingErrorRad"] = None
    with pytest.raises(ValidationError):
        parse(LocalizationSnapshot, data)


def test_normalized_marker_observation_roundtrip():
    value = parse(MarkerObservation, observation())
    assert MarkerObservation.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(frameId="camera"),
        lambda d: d.update(calibration=""),
        lambda d: d.update(clockUncertaintyS=-0.1),
        lambda d: d.update(captureTime=2.0),
        lambda d: d.update(confidence=1.1),
        lambda d: d.update(markerId=True),
        lambda d: d.update(operation="drive"),
        lambda d: d["relativePose"].update(yawRad=4),
    ],
)
def test_invalid_marker_observations(mutation):
    data = observation()
    mutation(data)
    with pytest.raises(ValidationError):
        parse(MarkerObservation, data)


def corrected_snapshot():
    data = snapshot()
    data.update(mapPose=pose(), mapFromOdom=pose())
    data["quality"].update(
        status="tracking",
        reasons=[],
        positionErrorM=0.1,
        headingErrorRad=0.1,
        lastCorrection={
            "observationId": "o",
            "sourceId": "camera",
            "sessionEpoch": "camera-1",
            "family": "example-square",
            "markerId": 1,
            "captureTime": 0.5,
        },
        distanceSinceCorrectionM=0.2,
        rotationSinceCorrectionRad=0.1,
    )
    return data


def test_correction_metadata_and_sensor_health():
    data = corrected_snapshot()
    parse(LocalizationSnapshot, data)
    data["quality"]["lastCorrection"]["captureTime"] = 1.1
    with pytest.raises(ValidationError, match="correction-after-sample"):
        parse(LocalizationSnapshot, data)
    data = corrected_snapshot()
    data["quality"]["distanceSinceCorrectionM"] = None
    with pytest.raises(ValidationError, match="correction-progress-required"):
        parse(LocalizationSnapshot, data)
    data = corrected_snapshot()
    data["sensorStatus"] = "unavailable"
    with pytest.raises(ValidationError, match="tracking-odometry-unavailable"):
        parse(LocalizationSnapshot, data)


def test_lost_pose_can_be_unavailable_but_never_claims_tracking():
    data = snapshot()
    data["quality"].update(status="lost", reasons=["odometry-reset"])
    assert parse(LocalizationSnapshot, data).mapPose is None
