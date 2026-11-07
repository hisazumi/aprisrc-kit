import json
import math
from pathlib import Path

import pytest

from apris_server.course_map import PlanarPose, load_map
from apris_server.localization import (
    Localization,
    LocalizationProfile,
    OdometrySample,
    SourceSession,
)
from apris_server.localization_contract import LocalizationScope, MarkerObservation

ROOT = Path(__file__).parents[1]


class Clock:
    time = 0.0

    def __call__(self):
        return self.time


def pose(x=0.0, y=0.0, yaw=0.0):
    return PlanarPose(xM=float(x), yM=float(y), yawRad=float(yaw))


def setup(**overrides):
    clock = Clock()
    world = load_map((ROOT / "config/maps/demo-room.json").read_bytes())
    profile = LocalizationProfile.model_validate_json(
        (ROOT / "scenarios/localization/profile.json").read_text()
    )
    if overrides:
        profile = LocalizationProfile.model_validate({**profile.model_dump(), **overrides})
    scope = LocalizationScope(
        robotId="r",
        controlEpoch="c",
        odomEpoch="o",
        localizationEpoch="l",
        map=world.identity,
        robotProfile="robot-v1",
        calibration="cam-v1",
        qualityProfile=profile.id,
    )
    localizer = Localization(
        world,
        scope,
        profile,
        clock=clock,
        clock_id="host",
        clock_epoch="boot",
        provenance="synthetic",
        sources=(SourceSession(sourceId="camera", sessionEpoch="s"),),
    )
    return localizer, clock


def sample(loc, clock, t, p=None, *, seq=None, **overrides):
    clock.time = t
    data = dict(
        robotId=loc.scope.robotId,
        controlEpoch=loc.scope.controlEpoch,
        odomEpoch=loc.scope.odomEpoch,
        clockId="host",
        clockEpoch="boot",
        sampleTime=float(t),
        receivedTime=float(t),
        sequence=round(t * 100) if seq is None else seq,
        pose=p or pose(),
        sensorStatus="ok",
        provenance="synthetic",
    )
    return loc.add_odometry(OdometrySample(**(data | overrides)))


def observation(loc, capture=0.0, received=None, x=1.0, y=0.0, yaw=0.0, **overrides):
    # Known marker at (0,0,.8). At body pose (-1,0,0) it is one metre forward.
    data = dict(
        **loc.scope.model_dump(),
        clockId="host",
        clockEpoch="boot",
        captureTime=float(capture),
        receivedTime=float(capture if received is None else received),
        clockUncertaintyS=0.0,
        sourceId="camera",
        sessionEpoch="s",
        sequence=1,
        observationId="obs-1",
        family="example-square",
        markerId=1,
        frameId="base",
        relativePose=dict(xM=x, yM=y, zM=0.8, rollRad=0.0, pitchRad=0.0, yawRad=yaw),
        confidence=0.95,
        poseAmbiguous=False,
        provenance="synthetic",
    )
    data.update(overrides)
    return MarkerObservation.model_validate(data)


def test_unlocalized_and_manual_initialization_not_zero_assumption():
    loc, c = setup()
    sample(loc, c, 0, pose(8, -3, math.pi / 2))
    assert loc.snapshot().mapPose is None
    with pytest.raises(ValueError, match="stop-unconfirmed"):
        loc.initialize_placement("start-placement", stopped=False)
    loc.initialize_placement("start-placement", stopped=True)
    assert loc.snapshot().mapPose.xM == pytest.approx(0)
    sample(loc, c, 0.1, pose(8, -2.9, math.pi / 2))
    current = loc.snapshot()
    assert current.mapPose.xM == pytest.approx(0.1)
    assert current.mapPose.yM == pytest.approx(0, abs=1e-12)
    assert current.odomPose == pose(8, -2.9, math.pi / 2)


def test_delayed_marker_uses_capture_pose_not_current_pose():
    loc, c = setup()
    sample(loc, c, 0)
    sample(loc, c, 0.2, pose(0.2))
    result = loc.initialize_marker(observation(loc, capture=0.1, received=0.2), stopped=True)
    assert result.applied
    assert loc.snapshot().mapPose.xM == pytest.approx(-0.9)
    assert loc.snapshot().odomPose.xM == 0.2
    assert loc.snapshot().quality.distanceSinceCorrectionM == pytest.approx(0.1)


def test_heading_interpolation_crosses_pi_by_short_arc():
    loc, c = setup()
    sample(loc, c, 0, pose(0, 0, math.radians(179)))
    sample(loc, c, 0.2, pose(0, 0, math.radians(-179)))
    assert loc.initialize_marker(observation(loc, 0.1, 0.2, yaw=math.pi), stopped=True).applied
    assert loc.snapshot().mapPose.yawRad == pytest.approx(math.radians(-179))


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"markerId": 99}, "unknown-marker"),
        ({"calibration": "other"}, "scope-mismatch"),
        ({"odomEpoch": "old"}, "scope-mismatch"),
        ({"localizationEpoch": "old"}, "scope-mismatch"),
        ({"clockEpoch": "old"}, "clock-mismatch"),
        ({"sessionEpoch": "old"}, "source-session-mismatch"),
        ({"confidence": 0.1}, "confidence-too-low"),
        ({"clockUncertaintyS": 0.03}, "clock-uncertain"),
        ({"poseAmbiguous": True}, "ambiguous-pose"),
        ({"provenance": "real"}, "provenance-mismatch"),
    ],
)
def test_rejected_initialization(change, reason):
    loc, c = setup()
    sample(loc, c, 0)
    result = loc.initialize_marker(observation(loc, **change), stopped=True)
    assert not result.applied and result.reason == reason
    assert loc.snapshot().mapPose is None


def test_history_bounds_no_extrapolation_and_stale_input():
    loc, c = setup(historySamples=2, historySeconds=0.3, maxOdomAgeS=2.0)
    for t in [0, 0.1, 0.2]:
        sample(loc, c, t)
    assert loc.history_size == 2
    assert (
        loc.initialize_marker(observation(loc, 0, 0.2), stopped=True).reason
        == "history-unavailable"
    )
    c.time = 0.3
    assert (
        loc.initialize_marker(observation(loc, 0.25, 0.3), stopped=True).reason
        == "history-unavailable"
    )
    c.time = 2.0
    assert (
        loc.initialize_marker(observation(loc, 0.1, 0.2), stopped=True).reason
        == "observation-too-old"
    )


def test_innovation_rejection_does_not_renew_or_mutate_odometry():
    loc, c = setup()
    sample(loc, c, 0)
    loc.initialize_placement("start-placement", stopped=True)
    sample(loc, c, 0.1)
    before = loc.snapshot()
    result = loc.correct(observation(loc, 0.1, 0.1, x=4.0))
    assert result.reason == "innovation-too-large"
    after = loc.snapshot()
    assert after.quality == before.quality
    assert after.mapFromOdom == before.mapFromOdom
    assert after.odomPose == before.odomPose


def test_repeated_out_of_order_and_old_source_sequence():
    loc, c = setup()
    sample(loc, c, 0)
    obs = observation(loc)
    assert loc.initialize_marker(obs, stopped=True).applied
    assert loc.correct(obs).reason == "duplicate-observation"
    sample(loc, c, 0.2)
    assert loc.correct(observation(loc, 0.1, 0.2, observationId="b", sequence=2)).applied
    assert (
        loc.correct(observation(loc, 0.05, 0.2, observationId="c", sequence=3)).reason
        == "capture-order"
    )
    assert (
        loc.correct(observation(loc, 0.15, 0.2, observationId="d", sequence=1)).reason
        == "source-order"
    )


def test_marker_absence_degrades_then_latches_lost_and_requires_explicit_reinit():
    loc, c = setup(positionDriftPerM=0.4, positionDriftPerS=0.0, headingDriftPerS=0.0)
    sample(loc, c, 0)
    loc.initialize_placement("start-placement", stopped=True)
    sample(loc, c, 0.2, pose(0.5))
    assert loc.snapshot().quality.status == "degraded"
    sample(loc, c, 0.4, pose(1.5))
    assert loc.snapshot().quality.status == "lost"
    assert loc.correct(observation(loc, 0.4, 0.4)).reason == "reinitialization-required"
    assert loc.snapshot().quality.status == "lost"
    loc.initialize_placement("start-placement", stopped=True)
    assert loc.snapshot().quality.status == "tracking"


def test_freshness_boundary_and_sensor_loss():
    loc, c = setup()
    sample(loc, c, 0)
    loc.initialize_placement("start-placement", stopped=True)
    c.time = loc.profile.maxOdomAgeS
    assert loc.snapshot().quality.status == "tracking"
    c.time += 0.000001
    assert loc.snapshot().quality.status == "lost"
    sample(loc, c, 0.6)
    assert loc.snapshot().quality.status == "lost"
    loc.initialize_placement("start-placement", stopped=True)
    sample(loc, c, 0.7, sensorStatus="unavailable")
    assert loc.snapshot().quality.status == "lost"


def test_clock_regression_requires_reset():
    loc, c = setup()
    sample(loc, c, 1)
    loc.initialize_placement("start-placement", stopped=True)
    c.time = 0.9
    with pytest.raises(ValueError, match="clock-regressed"):
        loc.snapshot()
    c.time = 1.1
    assert loc.snapshot().quality.status == "lost"
    with pytest.raises(ValueError, match="reset-required"):
        loc.initialize_placement("start-placement", stopped=True)


def test_reset_fences_old_epoch_and_clears_history():
    loc, c = setup()
    sample(loc, c, 0)
    old = observation(loc)
    loc.initialize_marker(old, stopped=True)
    new_scope = LocalizationScope.model_validate(
        {**loc.scope.model_dump(), "odomEpoch": "o2", "localizationEpoch": "l2"}
    )
    loc.reset(new_scope, clock_epoch="boot", stopped=True)
    assert loc.history_size == 0
    sample(loc, c, 0.1)
    assert loc.snapshot().mapPose is None
    assert loc.initialize_marker(old, stopped=True).reason == "scope-mismatch"


def test_3d_marker_tilt_is_removed_before_planar_projection():
    loc, c = setup()
    doc = json.loads((ROOT / "config/maps/demo-room.json").read_text())
    doc["markers"][0]["pose"]["rollRad"] = math.pi / 2
    world = load_map(json.dumps(doc).encode())
    scope = LocalizationScope.model_validate({**loc.scope.model_dump(), "map": world.identity})
    loc = Localization(
        world,
        scope,
        loc.profile,
        clock=c,
        clock_id="host",
        clock_epoch="boot",
        provenance="synthetic",
        sources=(SourceSession(sourceId="camera", sessionEpoch="s"),),
    )
    sample(loc, c, 0)
    relative = dict(xM=1.0, yM=0.0, zM=0.8, rollRad=math.pi / 2, pitchRad=0.0, yawRad=0.0)
    assert loc.initialize_marker(observation(loc, relativePose=relative), stopped=True).applied
    assert loc.snapshot().mapPose.xM == pytest.approx(-1)
    relative["rollRad"] = 0.0
    sample(loc, c, 0.1)
    result = loc.correct(
        observation(loc, 0.1, 0.1, sequence=2, observationId="b", relativePose=relative)
    )
    assert result.reason == "nonplanar-pose"


@pytest.mark.parametrize("capture,expected", [(0.0, True), (0.000001, True)])
def test_observation_age_at_limit(capture, expected):
    loc, c = setup(maxOdomAgeS=2.0)
    sample(loc, c, 0)
    sample(loc, c, 0.5)
    c.time = 1.0
    assert loc.initialize_marker(observation(loc, capture, 1.0), stopped=True).applied == expected
    other, cc = setup(maxOdomAgeS=2.0)
    sample(other, cc, 0)
    cc.time = 1.000001
    assert (
        other.initialize_marker(observation(other, 0, 1.0), stopped=True).reason
        == "observation-too-old"
    )


@pytest.mark.parametrize(
    "uncertainty,reason",
    [(0.019999, "marker-corrected"), (0.02, "marker-corrected"), (0.020001, "clock-uncertain")],
)
def test_clock_uncertainty_boundary(uncertainty, reason):
    loc, c = setup()
    sample(loc, c, 0)
    sample(loc, c, 0.2)
    result = loc.initialize_marker(
        observation(loc, 0.1, 0.2, clockUncertaintyS=uncertainty), stopped=True
    )
    assert result.reason == reason


def test_clock_uncertainty_needs_history_on_both_sides():
    loc, c = setup()
    sample(loc, c, 0)
    assert (
        loc.initialize_marker(observation(loc, clockUncertaintyS=0.01), stopped=True).reason
        == "history-unavailable"
    )


@pytest.mark.parametrize("delta,expected", [(0.499999, True), (0.5, True), (0.500001, False)])
def test_position_innovation_boundary(delta, expected):
    loc, c = setup()
    sample(loc, c, 0)
    assert loc.initialize_marker(observation(loc), stopped=True).applied
    sample(loc, c, 0.1)
    r = loc.correct(observation(loc, 0.1, 0.1, x=1 + delta, sequence=2, observationId="b"))
    assert r.applied == expected


@pytest.mark.parametrize("yaw,expected", [(0.499999, True), (0.5, True), (0.500001, False)])
def test_heading_innovation_boundary(yaw, expected):
    loc, c = setup(maxInnovationM=2.0)
    sample(loc, c, 0)
    loc.initialize_marker(observation(loc), stopped=True)
    sample(loc, c, 0.1)
    assert (
        loc.correct(observation(loc, 0.1, 0.1, yaw=yaw, sequence=2, observationId="b")).applied
        == expected
    )


def test_good_marker_correction_reduces_drift_without_touching_local_progress():
    loc, c = setup(positionDriftPerM=0.4)
    sample(loc, c, 0)
    loc.initialize_marker(observation(loc), stopped=True)
    sample(loc, c, 0.2, pose(0.5))
    assert loc.snapshot().quality.status == "degraded"
    assert loc.correct(observation(loc, 0.2, 0.2, x=0.6, sequence=2, observationId="b")).applied
    s = loc.snapshot()
    assert s.mapPose.xM == pytest.approx(-0.6)
    assert s.odomPose.xM == 0.5
    assert s.quality.status == "tracking"
    assert s.quality.positionErrorM == loc.profile.markerPositionErrorM


def test_update_cannot_hide_a_missed_freshness_deadline():
    loc, c = setup()
    sample(loc, c, 0)
    loc.initialize_placement("start-placement", stopped=True)
    sample(loc, c, 0.6)
    assert loc.snapshot().quality.status == "lost"


def test_capacity_fails_closed_and_does_not_renew_correction():
    loc, c = setup(maxAcceptedObservations=1)
    sample(loc, c, 0)
    loc.initialize_marker(observation(loc), stopped=True)
    sample(loc, c, 0.1)
    before = loc.snapshot()
    assert (
        loc.correct(observation(loc, 0.1, 0.1, sequence=2, observationId="b")).reason
        == "observation-capacity"
    )
    assert loc.snapshot().quality.lastCorrection == before.quality.lastCorrection


def test_unhealthy_history_and_large_gap_are_not_interpolated():
    loc, c = setup(maxOdomAgeS=2.0, maxObservationAgeS=2.0)
    sample(loc, c, 0)
    sample(loc, c, 1.1)
    assert loc.initialize_marker(observation(loc, 0.5, 1.1), stopped=True).reason == "history-gap"
    loc, c = setup()
    sample(loc, c, 0, sensorStatus="degraded")
    sample(loc, c, 0.2)
    assert (
        loc.initialize_marker(observation(loc, 0.1, 0.2), stopped=True).reason
        == "history-unhealthy"
    )


def test_odometry_jump_needs_reset_and_does_not_replace_last_pose():
    loc, c = setup()
    sample(loc, c, 0)
    loc.initialize_placement("start-placement", stopped=True)
    with pytest.raises(ValueError, match="odometry-jump"):
        sample(loc, c, 0.1, pose(100))
    assert loc.snapshot().odomPose == pose()
    assert loc.snapshot().quality.status == "lost"
    with pytest.raises(ValueError, match="reset-required"):
        loc.initialize_placement("start-placement", stopped=True)


@pytest.mark.parametrize(
    "extra,reason",
    [
        ({"odomEpoch": "old"}, "scope-mismatch"),
        ({"clockEpoch": "old"}, "clock-mismatch"),
        ({"sequence": 0}, "odometry-order"),
        ({"receivedTime": 2.0}, "reception-in-future"),
    ],
)
def test_rejected_odometry_does_not_replace_history(extra, reason):
    loc, c = setup()
    sample(loc, c, 0)
    with pytest.raises(ValueError, match=reason):
        sample(loc, c, 0.1, **extra)
    assert loc.history_size == 1


def test_extreme_finite_relative_pose_is_rejected_without_overflow():
    loc, c = setup()
    sample(loc, c, 0)
    assert loc.initialize_marker(observation(loc, x=1e308), stopped=True).reason == "marker-range"


def test_reset_requires_new_odom_and_clock_epochs_when_appropriate():
    loc, c = setup()
    sample(loc, c, 1)
    new = LocalizationScope.model_validate({**loc.scope.model_dump(), "localizationEpoch": "l2"})
    with pytest.raises(ValueError, match="new-odometry-epoch-required"):
        loc.reset(new, clock_epoch="boot", stopped=True)
    c.time = 0.9
    with pytest.raises(ValueError, match="clock-regressed"):
        loc.snapshot()
    new = LocalizationScope.model_validate({**new.model_dump(), "odomEpoch": "o2"})
    with pytest.raises(ValueError, match="new-clock-epoch-required"):
        loc.reset(new, clock_epoch="boot", stopped=True)
    loc.reset(new, clock_epoch="boot2", stopped=True)
    sample(loc, c, 0.1, clockEpoch="boot2")
    assert loc.snapshot().mapPose is None


def test_existing_encoder_imu_estimate_can_feed_localization():
    from apris_server.odometry import OdometryConfig, WheelImuOdometry

    config = OdometryConfig()
    odom = WheelImuOdometry(config)
    loc, c = setup()
    ticks_per_m = config.ticks_per_revolution / (2 * math.pi * config.wheel_radius_m)
    for step in range(11):
        odom.update(
            timestamp=step * 0.1,
            left_ticks=round(step * 0.01 * ticks_per_m),
            right_ticks=round(step * 0.01 * ticks_per_m),
            imu_yaw_rate_rad_s=0.0,
        )
        p = odom.pose
        sample(loc, c, step * 0.1, pose(p.x, p.y, p.yaw))
        if step == 0:
            loc.initialize_placement("start-placement", stopped=True)
    assert loc.snapshot().mapPose.xM == pytest.approx(0.1, abs=0.001)
    assert loc.snapshot().odomPose.xM == odom.pose.x


def test_pre_loss_capture_cannot_reinitialize_even_after_fresh_odometry():
    loc, c = setup()
    sample(loc, c, 0)
    loc.initialize_marker(observation(loc), stopped=True)
    sample(loc, c, 0.2)
    c.time = 0.71
    assert loc.snapshot().quality.status == "lost"
    sample(loc, c, 0.8)
    assert (
        loc.initialize_marker(
            observation(loc, 0.1, 0.8, sequence=2, observationId="b"), stopped=True
        ).reason
        == "pre-loss-observation"
    )
    assert loc.initialize_marker(
        observation(loc, 0.8, 0.8, sequence=3, observationId="c"), stopped=True
    ).applied


def test_tracking_never_initializes_without_explicit_action():
    loc, c = setup()
    sample(loc, c, 0)
    assert loc.correct(observation(loc)).reason == "initialization-required"
    assert loc.snapshot().mapPose is None


@pytest.mark.parametrize(
    "changes",
    [
        {"degradedPositionM": 0.5},
        {"minMarkerRangeM": 5.0},
        {"maxYawRateRadS": 4.0},
        {"historySamples": 1},
        {"positionDriftPerM": -1.0},
        {"maxOdomAgeS": float("nan")},
    ],
)
def test_invalid_profiles(changes):
    with pytest.raises(ValueError):
        setup(**changes)


@pytest.mark.parametrize("heading", [-math.pi, -1.2, 0.0, 0.7, math.pi])
def test_3d_geometry_with_translation_heading_and_marker_tilt(heading):
    from apris_server.course_map import MarkerPose
    from apris_server.localization_geometry import angle, marker_base_pose

    # Independent fixture construction: base=(2,-3,heading), world marker=(4,1,.8).
    co, si = math.cos(heading), math.sin(heading)
    world = MarkerPose(xM=4.0, yM=1.0, zM=0.8, rollRad=0.6, pitchRad=-0.3, yawRad=0.8)
    rel = MarkerPose(
        xM=co * 2 + si * 4,
        yM=-si * 2 + co * 4,
        zM=0.8,
        rollRad=0.6,
        pitchRad=-0.3,
        yawRad=angle(0.8 - heading),
    )
    result = marker_base_pose(world, rel, max_tilt=0.01, max_height=0.01)
    assert result.xM == pytest.approx(2.0)
    assert result.yM == pytest.approx(-3.0)
    assert angle(result.yawRad - heading) == pytest.approx(0.0, abs=1e-12)
