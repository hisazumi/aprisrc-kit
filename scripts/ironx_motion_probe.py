"""Supervised low-speed pulse test; default mode NEVER creates a publisher.

This is not a production controller. SIGKILL, OS failure, or a dead driver cannot
be handled here; the STM32 watchdog must be qualified separately.
"""

import argparse
import json
import math
import signal
import time

COMMAND_TOPIC = "/apris_readonly/no_commands"


def validate_plan(vx, wz, duration):
    if not all(math.isfinite(v) for v in (vx, wz, duration)):
        raise ValueError("Plan must be finite")
    if abs(vx) > 0.05 or abs(wz) > 0.20 or not 0 < duration <= 1.0:
        raise ValueError("Limits: 0.05 m/s, 0.20 rad/s, duration <= 1 second")
    if (vx == 0) == (wz == 0):
        raise ValueError("Choose exactly one nonzero linear or angular velocity")
    return {"vx": vx, "wz": wz, "duration_s": duration}


def valid_odometry(age, vx, vy, wz):
    return all(math.isfinite(v) for v in (age, vx, vy, wz)) and 0 <= age <= 0.3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vx", type=float, default=0.05)
    parser.add_argument("--wz", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument(
        "--execute", action="store_true", help="MOVE after operator approval"
    )
    args = parser.parse_args()
    plan = validate_plan(args.vx, args.wz, args.duration)

    # Keep plan validation/test imports independent from ROS and motor access.
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.qos import qos_profile_sensor_data

    rclpy.init()
    node = rclpy.create_node("apris_supervised_motion_probe")
    latest = None
    publisher = None
    started = time.monotonic()

    def record(event, **values):
        print(
            json.dumps(
                {"event": event, "elapsed_s": time.monotonic() - started, **values},
                allow_nan=False,
            ),
            flush=True,
        )

    def observe(msg):
        nonlocal latest
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        age = node.get_clock().now().nanoseconds / 1e9 - stamp
        v = msg.twist.twist
        if not valid_odometry(age, v.linear.x, v.linear.y, v.angular.z):
            return
        if msg.header.frame_id != "odom" or msg.child_frame_id != "base_footprint":
            return
        latest = {
            "received": time.monotonic(),
            "source_age": age,
            "vx": v.linear.x,
            "vy": v.linear.y,
            "wz": v.angular.z,
        }

    def fresh():
        return latest is not None and (
            time.monotonic() - latest["received"] + latest["source_age"] <= 0.3
        )

    def publish(vx, wz):
        msg = Twist()
        msg.linear.x, msg.angular.z = vx, wz
        publisher.publish(msg)
        record("command", vx=vx, wz=wz, observed=latest)

    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    node.create_subscription(Odometry, "/odom", observe, qos_profile_sensor_data)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        subs = node.get_subscriptions_info_by_topic(COMMAND_TOPIC)
        pubs = node.get_publishers_info_by_topic(COMMAND_TOPIC)
        if len(subs) != 1 or subs[0].node_name != "ironx_driver" or pubs:
            raise RuntimeError(
                "Expected exactly ironx_driver and no other command publishers"
            )
        if not fresh():
            raise RuntimeError("Fresh EKF odometry required")
        if max(abs(latest["vx"]), abs(latest["vy"])) > 0.01 or abs(latest["wz"]) > 0.03:
            raise RuntimeError("Rover must be stationary before the test")
        record("preflight_ok", plan=plan, execute=args.execute, observed=latest)
        if not args.execute:
            record(
                "check_only", message="No publisher created; no motion commands sent"
            )
            return
        publisher = node.create_publisher(Twist, COMMAND_TOPIC, 1)
        deadline = time.monotonic() + 1
        while publisher.get_subscription_count() == 0:
            if time.monotonic() >= deadline:
                raise RuntimeError("Driver subscription did not match")
            rclpy.spin_once(node, timeout_sec=0.05)
        end = time.monotonic() + args.duration
        next_tick = time.monotonic()
        while time.monotonic() < end:
            now = time.monotonic()
            if now - next_tick > 0.15 or not fresh():
                raise RuntimeError("Control loop delayed or odometry stale")
            if node.count_publishers(COMMAND_TOPIC) != 1:
                raise RuntimeError("Competing publisher detected")
            publish(args.vx, args.wz)
            next_tick = now + 0.05
            while time.monotonic() < min(next_tick, end):
                rclpy.spin_once(
                    node, timeout_sec=max(0, min(next_tick, end) - time.monotonic())
                )
    finally:
        if publisher is not None:
            # Repeat zero commands, including after ordinary exceptions and SIGINT/TERM.
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            end = time.monotonic() + 1
            while time.monotonic() < end:
                publish(0.0, 0.0)
                rclpy.spin_once(node, timeout_sec=0.05)
            stopped = (
                fresh()
                and max(abs(latest["vx"]), abs(latest["vy"])) < 0.01
                and abs(latest["wz"]) < 0.03
            )
            record(
                "stop_observation",
                stopped=stopped,
                note="Odometry only; verify physical stop independently",
            )
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
