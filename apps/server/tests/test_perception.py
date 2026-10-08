import math

from apris_server.models import Capabilities, Pose, PoseEstimateQuality, RoverState, Velocity
from apris_server.perception import CourseMarker, MarkerPayload, PoseFusion


def rover_state(pose: Pose) -> RoverState:
    return RoverState(
        timestamp=1.0,
        connected=True,
        pose=pose,
        velocity=Velocity(vx=0.0, vy=0.0, wz=0.0),
        capabilities=Capabilities(),
        pose_quality=PoseEstimateQuality(
            source="encoder_imu",
            confidence=0.9,
            encoder_status="ok",
            imu_status="ok",
        ),
    )


def test_known_marker_corrects_course_pose_and_quality() -> None:
    fusion = PoseFusion(
        {1: CourseMarker(id=1, label="origin", x_m=0.0, y_m=0.0, yaw_rad=0.0)}
    )
    odom_pose = Pose(x=0.0, y=0.0, yaw=0.0)
    result = fusion.correct(
        odom_pose,
        MarkerPayload(
            marker_id=1,
            relative_x_m=0.5,
            relative_y_m=0.0,
            relative_yaw_rad=0.0,
        ),
        confidence=0.9,
    )
    fused = fusion.apply(rover_state(odom_pose))

    assert result.applied is True
    assert fused.pose.x < -0.25
    assert fused.pose_quality.frame_id == "course"
    assert fused.pose_quality.source == "marker_corrected"
    assert fused.pose_quality.last_marker_id == 1


def test_unknown_or_implausible_marker_observation_is_rejected() -> None:
    fusion = PoseFusion(
        {1: CourseMarker(id=1, label="origin", x_m=0.0, y_m=0.0, yaw_rad=0.0)}
    )
    unknown = fusion.correct(
        Pose(x=0.0, y=0.0, yaw=0.0),
        MarkerPayload(marker_id=99, relative_x_m=0.5, relative_y_m=0.0),
        confidence=0.9,
    )
    implausible = fusion.correct(
        Pose(x=0.0, y=0.0, yaw=0.0),
        MarkerPayload(
            marker_id=1,
            relative_x_m=0.5,
            relative_y_m=0.0,
            relative_yaw_rad=math.pi,
        ),
        confidence=0.9,
    )

    assert unknown.reason == "unknown_marker"
    assert implausible.reason == "marker_innovation_too_large"
