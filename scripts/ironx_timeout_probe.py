"""Supervised command-silence test. Default: subscriptions only, no commands."""

import argparse
import json
import multiprocessing
import os
import signal
import time

from ironx_motion_probe import COMMAND_TOPIC, valid_odometry

PULSE_S = 0.4
SILENCE_S = 0.6
SPEED = 0.05


def classify(samples, pulse_start, last_command, rescue_at):
    """Use raw wheel samples only; never credit rescue-induced stopping."""
    samples = [
        s
        for s in samples
        if s["topic"] == "wheel" and pulse_start <= s["t"] < rescue_at
    ]
    if not any(abs(s["vx"]) >= 0.015 for s in samples):
        return {"result": "inconclusive_no_measured_motion"}
    tail = []
    for s in samples:
        # Exclude samples whose capture could precede the last command.
        if s["t"] - s["age"] <= last_command + 0.05:
            continue
        if abs(s["vx"]) < 0.01 and abs(s["vy"]) < 0.01 and abs(s["wz"]) < 0.03:
            tail.append(s)
        else:
            tail = []
    if len(tail) >= 3 and tail[-1]["t"] - tail[0]["t"] >= 0.15:
        return {
            "result": "stop_observed_before_rescue",
            "first_low_speed_after_last_command_s": tail[0]["t"] - last_command,
        }
    return {"result": "no_confirmed_stop_within_test_window"}


def rescue_worker(ready, armed, urgent, deadline, first_zero, delayed_publisher=False):
    # Separate session/process: parent interruption must not remove fallback stopping.
    os.setsid()
    import rclpy
    from geometry_msgs.msg import Twist

    rclpy.init()
    node = rclpy.create_node("apris_timeout_rescue")
    pub = None if delayed_publisher else node.create_publisher(Twist, COMMAND_TOPIC, 1)
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    try:
        end = time.monotonic() + 4
        while (
            pub is not None
            and pub.get_subscription_count() == 0
            and time.monotonic() < end
        ):
            rclpy.spin_once(node, timeout_sec=0.05)
        if pub is not None and pub.get_subscription_count() != 1:
            return
        ready.set()
        if not armed.wait(10):
            return
        while time.monotonic() < deadline.value and not urgent.is_set():
            time.sleep(0.005)
        first_zero.value = time.monotonic()
        # Do not trip the bridge's competing-publisher guard before the deadline.
        # Mark the observation cutoff BEFORE creating the fallback publisher.
        if pub is None:
            pub = node.create_publisher(Twist, COMMAND_TOPIC, 1)
        end = time.monotonic() + 1
        while time.monotonic() < end:
            pub.publish(Twist())
            time.sleep(0.05)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.qos import qos_profile_sensor_data

    rclpy.init()
    node = rclpy.create_node("apris_timeout_probe")
    samples, latest = [], {}
    worker = publisher = None
    pulse_start = last_command = None
    ctx = multiprocessing.get_context("spawn")
    ready, armed, urgent = ctx.Event(), ctx.Event(), ctx.Event()
    deadline, first_zero = ctx.Value("d", 0, lock=False), ctx.Value("d", 0, lock=False)

    def record(event, **values):
        print(
            json.dumps(
                {"event": event, "monotonic": time.monotonic(), **values},
                allow_nan=False,
            ),
            flush=True,
        )

    def observe(topic, msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        age = node.get_clock().now().nanoseconds / 1e9 - stamp
        v = msg.twist.twist
        if not valid_odometry(age, v.linear.x, v.linear.y, v.angular.z):
            return
        if msg.header.frame_id != "odom" or msg.child_frame_id != "base_footprint":
            return
        if topic in latest and stamp <= latest[topic]["stamp"]:
            return
        s = {
            "topic": topic,
            "stamp": stamp,
            "t": time.monotonic(),
            "age": age,
            "vx": v.linear.x,
            "vy": v.linear.y,
            "wz": v.angular.z,
        }
        latest[topic] = s
        samples.append(s)
        record("observation", **s)

    def fresh():
        return all(
            k in latest and time.monotonic() - latest[k]["t"] + latest[k]["age"] <= 0.3
            for k in ("wheel", "ekf")
        )

    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    for key, topic in (("wheel", "/wheel/odometry"), ("ekf", "/odom")):
        node.create_subscription(
            Odometry, topic, lambda msg, k=key: observe(k, msg), qos_profile_sensor_data
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
            raise RuntimeError("Expected one driver and no command publishers")
        if not fresh() or any(
            abs(latest[k][v]) > limit
            for k in latest
            for v, limit in (("vx", 0.01), ("vy", 0.01), ("wz", 0.03))
        ):
            raise RuntimeError("Fresh, stationary wheel and EKF telemetry required")
        record(
            "preflight_ok",
            execute=args.execute,
            vx=SPEED,
            pulse_s=PULSE_S,
            silence_s=SILENCE_S,
            rescue_after_start_s=PULSE_S + SILENCE_S,
        )
        if not args.execute:
            record(
                "check_only", message="No command publisher or rescue process created"
            )
            return
        worker = ctx.Process(
            target=rescue_worker, args=(ready, armed, urgent, deadline, first_zero)
        )
        worker.start()
        end = time.monotonic() + 6
        while not ready.is_set():
            if not worker.is_alive() or time.monotonic() > end:
                raise RuntimeError("Rescue process not ready")
            rclpy.spin_once(node, timeout_sec=0.05)
        publisher = node.create_publisher(Twist, COMMAND_TOPIC, 1)
        end = time.monotonic() + 3
        while (
            publisher.get_subscription_count() != 1
            or node.count_publishers(COMMAND_TOPIC) != 2
        ):
            if time.monotonic() > end:
                raise RuntimeError("Unexpected command graph")
            rclpy.spin_once(node, timeout_sec=0.05)
        pulse_start = time.monotonic()
        deadline.value = pulse_start + PULSE_S + SILENCE_S
        armed.set()
        record("armed", rescue_deadline=deadline.value)
        tick = pulse_start
        while time.monotonic() < pulse_start + PULSE_S:
            now = time.monotonic()
            if (
                now - tick > 0.15
                or not fresh()
                or not worker.is_alive()
                or first_zero.value
            ):
                raise RuntimeError("Timing, telemetry, or rescue health changed")
            if node.count_publishers(COMMAND_TOPIC) != 2:
                raise RuntimeError("Competing publisher")
            msg = Twist()
            msg.linear.x = SPEED
            publisher.publish(msg)
            last_command = time.monotonic()
            record("drive", vx=SPEED)
            tick = now + 0.05
            while time.monotonic() < min(tick, pulse_start + PULSE_S):
                rclpy.spin_once(
                    node,
                    timeout_sec=max(
                        0, min(tick, pulse_start + PULSE_S) - time.monotonic()
                    ),
                )
        record("silence_started", last_command=last_command)
        while not first_zero.value:
            if (
                not fresh()
                or not worker.is_alive()
                or time.monotonic() > deadline.value + 0.2
            ):
                raise RuntimeError("Telemetry or rescue deadline failed")
            rclpy.spin_once(node, timeout_sec=0.02)
        record("rescue_started", first_zero=first_zero.value)
        record(
            "assessment",
            **classify(samples, pulse_start, last_command, first_zero.value),
        )
    finally:
        if worker is not None:
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, signal.SIG_IGN)
            urgent.set()
            # Even errors before arming produce only fallback zero commands.
            armed.set()
            end = time.monotonic() + 1.5
            while time.monotonic() < end:
                if publisher is not None:
                    publisher.publish(Twist())
                rclpy.spin_once(node, timeout_sec=0.05)
            worker.join(timeout=2)
            record(
                "final_observation",
                fresh=fresh(),
                observed=latest,
                rescue_exited=not worker.is_alive(),
            )
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
