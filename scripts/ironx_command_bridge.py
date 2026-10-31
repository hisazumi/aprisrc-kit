"""Bounded ROS command bridge. Default is a publisher-free preflight."""

import argparse
import json
import math
import signal
import time

from ironx_motion_probe import COMMAND_TOPIC, valid_odometry

INPUT_TOPIC = "/apris/command_velocity"
TIMEOUT = 0.3


class CommandLease:
    def __init__(self):
        self.deadline = float("-inf")
        self.stamp = float("-inf")
        self.velocity = (0.0, 0.0)
        self.reason = "waiting_for_command"
        self.fault = None

    def stop(self, reason):
        self.deadline = float("-inf")
        self.velocity = (0.0, 0.0)
        self.reason = reason

    def latch(self, reason):
        self.fault = reason
        self.stop(reason)

    def accept(self, stamp, source_now, now, vx, vy, vz, wx, wy, wz):
        values = (stamp, source_now, now, vx, vy, vz, wx, wy, wz)
        if self.fault:
            return False
        if not all(math.isfinite(v) for v in values):
            self.stop("invalid_command")
            return False
        age = source_now - stamp
        if not 0 <= age < TIMEOUT or stamp <= self.stamp:
            self.stop("stale_or_replayed_command")
            return False
        if abs(vx) > 0.05 or abs(wz) > 0.2 or any(v != 0 for v in (vy, vz, wx, wy)):
            self.stop("unsupported_velocity")
            return False
        self.stamp = stamp
        self.deadline = now + TIMEOUT - age
        self.velocity = (vx, wz)
        self.reason = "command_active"
        return True

    def output(self, now, telemetry_fresh):
        if self.fault:
            return (0.0, 0.0)
        if not telemetry_fresh:
            self.stop("telemetry_stale")
        elif now >= self.deadline:
            self.stop("command_timeout")
        return self.velocity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="Enable motor publishing")
    args = parser.parse_args()
    import rclpy
    from geometry_msgs.msg import Twist, TwistStamped
    from nav_msgs.msg import Odometry
    from rclpy.qos import qos_profile_sensor_data

    rclpy.init()
    node = rclpy.create_node("apris_command_bridge")
    lease = CommandLease()
    latest = None
    publisher = None

    def record(event, **values):
        print(
            json.dumps({"event": event, "monotonic": time.monotonic(), **values}),
            flush=True,
        )

    def observe(msg):
        nonlocal latest
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        age = node.get_clock().now().nanoseconds / 1e9 - stamp
        v = msg.twist.twist
        if (
            valid_odometry(age, v.linear.x, v.linear.y, v.angular.z)
            and msg.header.frame_id == "odom"
            and msg.child_frame_id == "base_footprint"
        ):
            latest = (time.monotonic() - age, v.linear.x, v.linear.y, v.angular.z)

    def fresh():
        return latest is not None and 0 <= time.monotonic() - latest[0] < TIMEOUT

    def command(msg):
        if msg.header.frame_id != "base_footprint" or not fresh():
            lease.stop("command_frame_or_telemetry_invalid")
            return
        v = msg.twist
        accepted = lease.accept(
            msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9,
            node.get_clock().now().nanoseconds / 1e9,
            time.monotonic(),
            v.linear.x,
            v.linear.y,
            v.linear.z,
            v.angular.x,
            v.angular.y,
            v.angular.z,
        )
        record("input", accepted=accepted, reason=lease.reason)

    def publish(vx, wz):
        msg = Twist()
        msg.linear.x, msg.angular.z = vx, wz
        publisher.publish(msg)
        record("output", vx=vx, wz=wz, reason=lease.reason)

    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    node.create_subscription(
        Odometry, "/wheel/odometry", observe, qos_profile_sensor_data
    )
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        end = time.monotonic() + 4
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
        subs = node.get_subscriptions_info_by_topic(COMMAND_TOPIC)
        if (
            len(subs) != 1
            or subs[0].node_name != "ironx_driver"
            or node.count_publishers(COMMAND_TOPIC)
        ):
            raise RuntimeError("Expected isolated driver with no command publishers")
        if (
            not fresh()
            or abs(latest[1]) >= 0.01
            or abs(latest[2]) >= 0.01
            or abs(latest[3]) >= 0.03
        ):
            raise RuntimeError("Fresh stationary wheel telemetry required")
        if node.count_publishers(INPUT_TOPIC):
            raise RuntimeError("Stop command senders before starting bridge")
        record("preflight_ok", enabled=args.enable)
        if not args.enable:
            return
        publisher = node.create_publisher(Twist, COMMAND_TOPIC, 1)
        end = time.monotonic() + 3
        while (
            publisher.get_subscription_count() != 1
            or node.count_publishers(COMMAND_TOPIC) != 1
        ):
            if time.monotonic() >= end:
                raise RuntimeError("Driver publisher discovery failed")
            publish(0.0, 0.0)
            rclpy.spin_once(node, timeout_sec=0.02)
        node.create_subscription(TwistStamped, INPUT_TOPIC, command, 1)
        previous = time.monotonic()
        while rclpy.ok():
            now = time.monotonic()
            if now - previous > 0.15:
                lease.latch("control_loop_delayed_restart_required")
            previous = now
            if (
                node.count_publishers(COMMAND_TOPIC) != 1
                or node.count_publishers(INPUT_TOPIC) > 1
            ):
                lease.latch("competing_publisher_restart_required")
            if publisher.get_subscription_count() != 1:
                lease.latch("driver_connection_changed_restart_required")
            publish(*lease.output(now, fresh()))
            end = now + 0.02
            while time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=max(0, end - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        if publisher is not None:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            lease.stop("shutdown")
            end = time.monotonic() + 1
            while time.monotonic() < end:
                publish(0.0, 0.0)
                time.sleep(0.05)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
