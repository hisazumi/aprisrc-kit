"""Supervised Adapter probes; --floor-move requires a clear floor area."""

import argparse
import asyncio
import json
import math
import multiprocessing
import signal
import subprocess
import sys
import time
from pathlib import Path


async def cancellation_trial(adapter):
    from apris_server.adapter import BoundedMotionGoal

    goal = BoundedMotionGoal("cancel-probe", "linear", 0.10, None, 0.04, 0.2, 5000)
    task = asyncio.create_task(adapter.execute_bounded_motion(goal))
    try:
        await asyncio.sleep(0.4)
        if task.done():
            await task
            raise RuntimeError("Motion ended before cancellation; test inconclusive")
        started = time.monotonic()
        print(json.dumps({"event": "cancel_requested", "t": started}), flush=True)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            state = await adapter.state()
            print(
                json.dumps(
                    {
                        "event": "cancel_confirmed",
                        "t": time.monotonic(),
                        "latency_s": time.monotonic() - started,
                        "velocity": state.velocity.model_dump(),
                    }
                ),
                flush=True,
            )
        else:
            raise RuntimeError("Expected cancellation, not normal completion")
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def floor_move_trial(adapter, turn=False):
    from apris_server.adapter import BoundedMotionGoal

    initial = await adapter.state()
    goal = (
        BoundedMotionGoal(
            "floor-left-15deg", "rotate", None, math.radians(15), 0.04, 0.15, 4500
        )
        if turn
        else BoundedMotionGoal("floor-10cm", "linear", 0.10, None, 0.04, 0.2, 4500)
    )
    task = asyncio.create_task(adapter.execute_bounded_motion(goal))
    print(
        json.dumps(
            {
                "event": "floor_turn_started" if turn else "floor_move_started",
                "t": time.monotonic(),
                "target_m": goal.distance_m,
                "target_deg": 15 if turn else None,
                "max_speed_mps": 0 if turn else 0.04,
                "max_speed_rad_s": 0.15 if turn else 0,
                "initial_pose": initial.pose.model_dump(),
            }
        ),
        flush=True,
    )
    try:
        while not task.done():
            state = await adapter.state()
            print(
                json.dumps(
                    {
                        "event": "floor_observation",
                        "t": time.monotonic(),
                        "connected": state.connected,
                        "pose": state.pose.model_dump(),
                        "velocity": state.velocity.model_dump(),
                    }
                ),
                flush=True,
            )
            await asyncio.sleep(0.1)
        result = await task
        final = await adapter.state()
        dx, dy = final.pose.x - initial.pose.x, final.pose.y - initial.pose.y
        print(
            json.dumps(
                {
                    "event": "floor_turn_result" if turn else "floor_move_result",
                    "t": time.monotonic(),
                    "status": result.status,
                    "odometry_yaw_deg": math.degrees(
                        math.atan2(
                            math.sin(final.pose.yaw - initial.pose.yaw),
                            math.cos(final.pose.yaw - initial.pose.yaw),
                        )
                    ),
                    "odometry_forward_m": dx * math.cos(initial.pose.yaw)
                    + dy * math.sin(initial.pose.yaw),
                    "odometry_lateral_m": -dx * math.sin(initial.pose.yaw)
                    + dy * math.cos(initial.pose.yaw),
                    "velocity": final.velocity.model_dump(),
                }
            ),
            flush=True,
        )
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def adapter_trial(
    root, deadline, cancel=False, floor_move=False, floor_turn=False
):
    sys.path.insert(0, str(root / "apps/server/src"))
    from apris_server.ironx_adapter import IronXAdapter

    directory = root / ".runtime/ironx"
    adapter = IronXAdapter(
        directory / "state.json",
        directory / "probe-command.json",
        directory / "probe-command-status.json",
    )
    await adapter.start()
    try:
        state = await adapter.state()
        if (
            not state.connected
            or abs(state.velocity.vx) >= 0.01
            or abs(state.velocity.wz) >= 0.03
        ):
            raise RuntimeError("Require fresh stationary telemetry")
        if time.monotonic() + (5.5 if floor_move or floor_turn else 1.2) >= deadline:
            raise RuntimeError("Insufficient fallback margin")
        if cancel:
            await cancellation_trial(adapter)
            return
        if floor_move or floor_turn:
            await floor_move_trial(adapter, turn=floor_turn)
            return
        end = time.monotonic() + 0.4
        last = time.monotonic()
        while time.monotonic() < end:
            if time.monotonic() - last > 0.15:
                raise RuntimeError("Adapter loop delayed")
            await adapter.drive(0.04, 0, 0, ttl_ms=200)
            last = time.monotonic()
            state = await adapter.state()
            print(
                json.dumps({"event": "drive", "t": last, "vx": state.velocity.vx}),
                flush=True,
            )
            await asyncio.sleep(0.05)
        started = time.monotonic()
        print(json.dumps({"event": "stop_requested", "t": started}), flush=True)
        await adapter.stop()
        state = await adapter.state()
        print(
            json.dumps(
                {
                    "event": "stop_confirmed",
                    "t": time.monotonic(),
                    "latency_s": time.monotonic() - started,
                    "velocity": state.velocity.model_dump(),
                }
            ),
            flush=True,
        )
    finally:
        await adapter.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--child-deadline", type=float)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--cancel", action="store_true")
    mode.add_argument("--floor-move", action="store_true")
    mode.add_argument("--floor-turn", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.child_deadline is not None:
        asyncio.run(
            adapter_trial(
                root, args.child_deadline, args.cancel, args.floor_move, args.floor_turn
            )
        )
        return
    if not args.execute:
        print("Prepared only. No publisher or process started.")
        return
    from ironx_timeout_probe import rescue_worker

    directory = root / ".runtime/ironx"
    stamp = str(time.time_ns())
    status = directory / "probe-command-status.json"
    ctx = multiprocessing.get_context("spawn")
    ready, armed, urgent = ctx.Event(), ctx.Event(), ctx.Event()
    deadline, cutoff = ctx.Value("d", 0, lock=False), ctx.Value("d", 0, lock=False)
    bridge = child = worker = None

    def interrupt(signum, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    with (directory / ("adapter-probe-controller-" + stamp + ".jsonl")).open(
        "x"
    ) as log:
        try:
            start = time.monotonic()
            bridge = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    str(root / "scripts/ironx_command_bridge.py"),
                    "--enable",
                    "--command-file",
                    str(directory / "probe-command.json"),
                    "--status-file",
                    str(status),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            while True:
                if bridge.poll() is not None or time.monotonic() - start > 10:
                    raise RuntimeError("Bridge failed to start")
                try:
                    data = json.loads(status.read_text())
                    if data["monotonic"] > start and not data["fault"]:
                        break
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(0.02)
            worker = ctx.Process(
                target=rescue_worker,
                args=(ready, armed, urgent, deadline, cutoff, True),
            )
            worker.start()
            if not ready.wait(6) or not worker.is_alive():
                raise RuntimeError("Fallback not ready")
            deadline.value = time.monotonic() + (
                6.5 if args.floor_move or args.floor_turn else 2
            )
            armed.set()
            print(
                json.dumps({"event": "armed", "deadline": deadline.value}), flush=True
            )
            child = subprocess.Popen(
                [
                    str(root / "apps/server/.venv/bin/python"),
                    "-B",
                    __file__,
                    "--child-deadline",
                    str(deadline.value),
                ]
                + (["--cancel"] if args.cancel else [])
                + (["--floor-move"] if args.floor_move else [])
                + (["--floor-turn"] if args.floor_turn else []),
                start_new_session=True,
            )
            child.wait(timeout=10 if args.floor_move or args.floor_turn else 6)
            if child.returncode:
                raise RuntimeError("Adapter trial failed")
        finally:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            if worker is not None:
                urgent.set()
                armed.set()
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            if worker is not None:
                worker.join(timeout=4)
                print(
                    json.dumps(
                        {
                            "event": "fallback",
                            "cutoff": cutoff.value,
                            "exited": not worker.is_alive(),
                        }
                    ),
                    flush=True,
                )
            if bridge is not None:
                bridge.terminate()
                try:
                    bridge.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    bridge.kill()
                    bridge.wait()


if __name__ == "__main__":
    main()
