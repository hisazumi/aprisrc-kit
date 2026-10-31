import json
import time

import pytest

from apris_server.adapter import BoundedMotionExecutionError, BoundedMotionGoal
from apris_server.ros2_readonly_adapter import Ros2ReadOnlyAdapter


def snapshot():
    return {
        "version": 1,
        "monotonic": time.monotonic(),
        "odom": {
            "received_monotonic": time.monotonic(),
            "received_at": time.time(),
            "source_age_s": 0.02,
            "frame_id": "odom",
            "child_frame_id": "base_footprint",
            "pose": {"x": 1, "y": 2, "yaw": 0.3},
            "velocity": {"vx": 0.1, "vy": 0, "wz": -0.2},
        },
        "battery": {"received_monotonic": time.monotonic(), "percent": 88},
    }


@pytest.mark.asyncio
async def test_fresh_real_telemetry(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(snapshot()))
    adapter = Ros2ReadOnlyAdapter(path)
    await adapter.start()
    state = await adapter.state()
    assert state.connected
    assert state.pose.x == 1
    assert state.velocity.wz == -0.2
    assert state.battery_percent == 88
    assert "ros2_readonly" in state.pose_quality.anomalies
    await adapter.close()
    assert not (await adapter.state()).connected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["missing", "invalid", "stale", "old_source", "frame", "nan", "future"]
)
async def test_reject_unavailable_or_invalid_telemetry(tmp_path, case):
    path = tmp_path / "state.json"
    data = snapshot()
    if case == "stale":
        data["odom"]["received_monotonic"] -= 5
    elif case == "old_source":
        data["odom"]["source_age_s"] = 5
    elif case == "frame":
        data["odom"]["frame_id"] = "map"
    elif case == "nan":
        data["odom"]["pose"]["x"] = float("nan")
    elif case == "future":
        data["monotonic"] += 50
    if case != "missing":
        path.write_text("{" if case == "invalid" else json.dumps(data))
    adapter = Ros2ReadOnlyAdapter(path)
    await adapter.start()
    assert not (await adapter.state()).connected


@pytest.mark.asyncio
async def test_no_motion_or_pose_reset(tmp_path):
    adapter = Ros2ReadOnlyAdapter(tmp_path / "unused")
    await adapter.start()
    with pytest.raises(RuntimeError, match="disabled"):
        await adapter.drive(-0.1, 0, 0)
    with pytest.raises(RuntimeError, match="disabled"):
        await adapter.reset_pose()
    goal = BoundedMotionGoal("test", "linear", 0.1, None, 0.1, 0.2, 2000)
    with pytest.raises(BoundedMotionExecutionError, match="disabled"):
        await adapter.execute_bounded_motion(goal)
    await adapter.stop()
    await adapter.emergency_stop("test")
    assert not (tmp_path / "unused").exists()
