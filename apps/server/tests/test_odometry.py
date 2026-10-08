import math

import pytest

from apris_server.odometry import OdometryConfig, WheelImuOdometry


def ticks_for_distance(config: OdometryConfig, distance_m: float) -> int:
    metres_per_tick = 2 * math.pi * config.wheel_radius_m / config.ticks_per_revolution
    return round(distance_m / metres_per_tick)


def test_encoder_and_imu_odometry_estimates_translation_and_heading() -> None:
    config = OdometryConfig(imu_weight=0.5)
    odometry = WheelImuOdometry(config)
    odometry.update(
        timestamp=1.0,
        left_ticks=0,
        right_ticks=0,
        imu_yaw_rate_rad_s=0.0,
    )
    odometry.update(
        timestamp=2.0,
        left_ticks=ticks_for_distance(config, 0.10),
        right_ticks=ticks_for_distance(config, 0.10),
        imu_yaw_rate_rad_s=0.0,
    )

    assert odometry.pose.x == pytest.approx(0.10, abs=0.001)
    assert odometry.pose.y == pytest.approx(0.0, abs=0.001)
    quality = odometry.quality()
    assert quality.source == "encoder_imu"
    assert quality.confidence > 0.9


def test_odometry_reports_sensor_faults_without_integrating_bad_encoder_data() -> None:
    odometry = WheelImuOdometry()
    odometry.update(
        timestamp=1.0,
        left_ticks=0,
        right_ticks=0,
        imu_yaw_rate_rad_s=0.0,
    )
    odometry.update(
        timestamp=1.1,
        left_ticks=100,
        right_ticks=100,
        imu_yaw_rate_rad_s=None,
        encoder_fault=True,
        imu_fault=True,
    )

    assert odometry.pose.x == 0.0
    quality = odometry.quality()
    assert quality.source == "unavailable"
    assert quality.anomalies == ["encoder_fault", "imu_fault"]
