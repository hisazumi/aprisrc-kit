"""ROS Humble/Python 3.10: subscribe only, atomically export local telemetry."""

import argparse
import json
import math
import os
import time
from pathlib import Path

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState


class StatusBridge(Node):
    def __init__(self, output, battery_scale):
        super().__init__("apris_status_bridge")
        self.output = output
        self.battery_scale = battery_scale
        self.odom = None
        self.battery = None
        self.create_subscription(
            Odometry, "/odom", self.on_odom, qos_profile_sensor_data
        )
        self.create_subscription(
            BatteryState, "/battery_state", self.on_battery, qos_profile_sensor_data
        )
        self.create_timer(0.1, self.save)

    def on_odom(self, msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        age = self.get_clock().now().nanoseconds / 1e9 - stamp
        q = msg.pose.pose.orientation
        norm = math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w)
        if not math.isfinite(norm) or not 0.9 <= norm <= 1.1 or not 0 <= age <= 1.5:
            return
        x, y, z, w = q.x / norm, q.y / norm, q.z / norm, q.w / norm
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        self.odom = {
            "received_monotonic": time.monotonic(),
            "received_at": time.time(),
            "source_age_s": age,
            "frame_id": msg.header.frame_id,
            "child_frame_id": msg.child_frame_id,
            "pose": {
                "x": msg.pose.pose.position.x,
                "y": msg.pose.pose.position.y,
                "yaw": yaw,
            },
            "velocity": {
                "vx": msg.twist.twist.linear.x,
                "vy": msg.twist.twist.linear.y,
                "wz": msg.twist.twist.angular.z,
            },
        }

    def on_battery(self, msg):
        percent = msg.percentage * self.battery_scale
        if math.isfinite(percent) and 0 <= percent <= 100:
            self.battery = {"received_monotonic": time.monotonic(), "percent": percent}

    def save(self):
        data = {
            "version": 1,
            "monotonic": time.monotonic(),
            "odom": self.odom,
            "battery": self.battery,
        }
        try:
            content = json.dumps(data, allow_nan=False)
        except ValueError:
            return
        temporary = self.output.with_suffix(".tmp")
        temporary.write_text(content)
        os.replace(temporary, self.output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--battery-scale",
        type=float,
        choices=[1.0, 100.0],
        default=100.0,
        help="Use 1 for iron-X driver v1.0 which already reports 0..100",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = StatusBridge(args.output, args.battery_scale)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
