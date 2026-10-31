"""Bounded ROS command bridge. Default is a publisher-free preflight."""

import argparse
import json
import math
import os
import signal
import time
from pathlib import Path

from ironx_motion_probe import COMMAND_TOPIC, valid_odometry

INPUT_TOPIC = "/apris/command_velocity"
TIMEOUT = 0.3


class FileCommands:
    """Same-host mailbox; reading an unchanged file never renews a command."""

    def __init__(self, path, lease):
        self.path = path
        self.lease = lease
        self.started = time.monotonic()
        self.seen = None
        self.accepted_id = None

    def poll(self, now):
        try:
            raw = self.path.read_text()
            if len(raw) > 2048:
                raise ValueError("oversized command")
            if raw == self.seen:
                return
            self.seen = raw
            data = json.loads(raw)
            sent, ttl = data["monotonic"], data["ttl_ms"] / 1000
            if (
                not isinstance(data["id"], str)
                or not data["id"]
                or not all(math.isfinite(v) for v in (sent, ttl))
                or sent <= self.started
                or not 0 < ttl <= TIMEOUT
                or not 0 <= now - sent < ttl
            ):
                raise ValueError("expired or invalid command")
            if self.lease.accept(sent, now, now, data["vx"], 0, 0, 0, 0, data["wz"]):
                self.lease.deadline = min(self.lease.deadline, sent + ttl)
                self.accepted_id = data["id"]
        except (OSError, ValueError, TypeError, KeyError):
            self.lease.stop("file_command_unavailable_or_invalid")


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
        self.velocity = (float(vx), float(wz))
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
    parser.add_argument("--command-file", type=Path)
    parser.add_argument("--status-file", type=Path)
    args = parser.parse_args()
    if bool(args.command_file) != bool(args.status_file):
        parser.error("--command-file and --status-file must be supplied together")
    import rclpy
    from geometry_msgs.msg import Twist, TwistStamped
    from nav_msgs.msg import Odometry
    from rclpy.qos import qos_profile_sensor_data

    rclpy.init()
    node = rclpy.create_node("apris_command_bridge")
    lease = CommandLease()
    mailbox = FileCommands(args.command_file, lease) if args.command_file else None
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
        msg.linear.x, msg.angular.z = float(vx), float(wz)
        publisher.publish(msg)
        record("output", vx=vx, wz=wz, reason=lease.reason)
        if args.status_file:
            data = {
                "monotonic": time.monotonic(),
                "command_id": mailbox.accepted_id,
                "vx": vx,
                "wz": wz,
                "fault": lease.fault,
                "reason": lease.reason,
            }
            temporary = args.status_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, allow_nan=False))
            os.replace(temporary, args.status_file)

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
        if mailbox is None:
            node.create_subscription(TwistStamped, INPUT_TOPIC, command, 1)
        previous = time.monotonic()
        while rclpy.ok():
            now = time.monotonic()
            if now - previous > 0.15:
                lease.latch("control_loop_delayed_restart_required")
            previous = now
            if node.count_publishers(COMMAND_TOPIC) != 1 or node.count_publishers(
                INPUT_TOPIC
            ) > (0 if mailbox else 1):
                lease.latch("competing_publisher_restart_required")
            if publisher.get_subscription_count() != 1:
                lease.latch("driver_connection_changed_restart_required")
            if mailbox:
                mailbox.poll(now)
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
