"""Supervised bridge command-loss test; default never starts motion publishers."""

import argparse
import json
import multiprocessing
import signal
import subprocess
import sys
import time
from pathlib import Path

from ironx_command_bridge import INPUT_TOPIC
from ironx_motion_probe import COMMAND_TOPIC, valid_odometry
from ironx_timeout_probe import classify, rescue_worker

PULSE_S = 0.4
RESCUE_S = 1.3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    import rclpy
    from geometry_msgs.msg import TwistStamped
    from nav_msgs.msg import Odometry
    from rclpy.qos import qos_profile_sensor_data

    rclpy.init()
    node = rclpy.create_node("apris_bridge_stop_probe")
    bridge = worker = publisher = bridge_log = None
    samples = []
    ctx = multiprocessing.get_context("spawn")
    ready, armed, urgent = ctx.Event(), ctx.Event(), ctx.Event()
    deadline, cutoff = ctx.Value("d", 0, lock=False), ctx.Value("d", 0, lock=False)

    def record(event, **values):
        print(
            json.dumps(
                {"event": event, "monotonic": time.monotonic(), **values},
                allow_nan=False,
            ),
            flush=True,
        )

    def wheel(msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        age = node.get_clock().now().nanoseconds / 1e9 - stamp
        v = msg.twist.twist
        if not valid_odometry(age, v.linear.x, v.linear.y, v.angular.z):
            return
        if msg.header.frame_id != "odom" or msg.child_frame_id != "base_footprint":
            return
        if samples and stamp <= samples[-1]["stamp"]:
            return
        s = {
            "topic": "wheel",
            "t": time.monotonic(),
            "stamp": stamp,
            "age": age,
            "vx": v.linear.x,
            "vy": v.linear.y,
            "wz": v.angular.z,
        }
        samples.append(s)
        record("wheel", **s)

    def fresh():
        return (
            bool(samples)
            and time.monotonic() - samples[-1]["t"] + samples[-1]["age"] < 0.3
        )

    def stationary():
        return fresh() and all(
            abs(samples[-1][k]) < limit
            for k, limit in (("vx", 0.01), ("vy", 0.01), ("wz", 0.03))
        )

    def spin(duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=min(0.02, max(0, end - time.monotonic())))

    def send(vx):
        msg = TwistStamped()
        msg.header.frame_id = "base_footprint"
        msg.header.stamp = node.get_clock().now().to_msg()
        msg.twist.linear.x = vx
        publisher.publish(msg)
        record("input_command", vx=vx)

    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    node.create_subscription(
        Odometry, "/wheel/odometry", wheel, qos_profile_sensor_data
    )
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        spin(4)
        subs = node.get_subscriptions_info_by_topic(COMMAND_TOPIC)
        drivers = [s for s in subs if s.node_name == "ironx_driver"]
        if len(drivers) != 1 or len(subs) != 1:
            raise RuntimeError("Unexpected driver subscribers")
        if (
            node.count_publishers(COMMAND_TOPIC)
            or node.count_publishers(INPUT_TOPIC)
            or not stationary()
        ):
            raise RuntimeError("Require stationary telemetry and no command publishers")
        record("preflight_ok", execute=args.execute, pulse_s=PULSE_S, rescue_s=RESCUE_S)
        if not args.execute:
            record(
                "check_only", message="No publishers, bridge, or rescue process started"
            )
            return
        # Controller JSONL records output without adding a driver-topic subscriber.
        path = Path(__file__).with_name("ironx_command_bridge.py")
        log_path = Path(".runtime/ironx") / (
            f"bridge-stop-controller-{time.time_ns()}.jsonl"
        )
        bridge_log = log_path.open("x")
        bridge = subprocess.Popen(
            [sys.executable, "-B", str(path), "--enable"],
            stdout=bridge_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        record("bridge_started", log=str(log_path))
        end = time.monotonic() + 10
        while not node.get_subscriptions_info_by_topic(INPUT_TOPIC):
            if bridge.poll() is not None or time.monotonic() >= end:
                raise RuntimeError("Bridge startup failed")
            spin(0.02)
        worker = ctx.Process(
            target=rescue_worker, args=(ready, armed, urgent, deadline, cutoff, True)
        )
        worker.start()
        end = time.monotonic() + 6
        while not ready.is_set():
            if not worker.is_alive() or time.monotonic() >= end:
                raise RuntimeError("Fallback process startup failed")
            spin(0.02)
        publisher = node.create_publisher(TwistStamped, INPUT_TOPIC, 1)
        end = time.monotonic() + 3
        while publisher.get_subscription_count() != 1:
            if time.monotonic() >= end:
                raise RuntimeError("Bridge input not matched")
            spin(0.02)
        if not stationary() or bridge.poll() is not None:
            raise RuntimeError("Require live bridge and stationary wheels")
        start = time.monotonic()
        deadline.value = start + RESCUE_S
        armed.set()
        record("armed", rescue_deadline=deadline.value)
        last = None
        while time.monotonic() < start + PULSE_S:
            if (
                (last is not None and time.monotonic() - last > 0.15)
                or not fresh()
                or bridge.poll() is not None
                or not worker.is_alive()
                or cutoff.value
                or node.count_publishers(COMMAND_TOPIC) != 1
                or node.count_publishers(INPUT_TOPIC) != 1
            ):
                raise RuntimeError("Control health changed")
            send(0.05)
            last = time.monotonic()
            spin(0.05)
        record("silence_started", last_command=last)
        while not cutoff.value:
            if (
                not fresh()
                or bridge.poll() is not None
                or not worker.is_alive()
                or time.monotonic() > deadline.value + 0.2
            ):
                raise RuntimeError("Observation or fallback health changed")
            spin(0.02)
        record("fallback_cutoff", t=cutoff.value)
        record("assessment", **classify(samples, start, last, cutoff.value))
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, signal.SIG_IGN)
        if worker is not None:
            urgent.set()
            armed.set()
        if bridge is not None:
            end = time.monotonic() + 1.5
            while time.monotonic() < end:
                if publisher is not None:
                    send(0.0)
                spin(0.05)
            bridge.terminate()
            try:
                bridge.wait(timeout=3)
            except subprocess.TimeoutExpired:
                bridge.kill()
                bridge.wait(timeout=2)
            spin(0.3)
            record(
                "final_observation",
                stationary=stationary(),
                observed=samples[-1] if samples else None,
            )
        if worker is not None:
            worker.join(timeout=3)
            record("fallback_finished", exited=not worker.is_alive())
        if bridge_log is not None:
            bridge_log.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
