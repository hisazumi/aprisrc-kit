"""Approved wheels-raised Adapter drive/stop probe, with independent fallback."""

import argparse
import asyncio
import json
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


async def adapter_trial(root, deadline, cancel=False):
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
        if time.monotonic() + 1.2 >= deadline:
            raise RuntimeError("Insufficient fallback margin")
        if cancel:
            await cancellation_trial(adapter)
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
    parser.add_argument("--cancel", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.child_deadline is not None:
        asyncio.run(adapter_trial(root, args.child_deadline, args.cancel))
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
            deadline.value = time.monotonic() + 2
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
                + (["--cancel"] if args.cancel else []),
                start_new_session=True,
            )
            child.wait(timeout=6)
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
