import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from apris_server.adapter import BoundedMotionResult
from apris_server.models import Capabilities, Pose, RoverState, Velocity

path = Path(__file__).resolve().parents[3] / "scripts/ironx_adapter_probe.py"
spec = importlib.util.spec_from_file_location("floor_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_floor_plan_and_completion_reporting(capsys, fail):
    moved = False

    async def state():
        return RoverState(
            timestamp=1,
            connected=True,
            capabilities=Capabilities(),
            pose=Pose(x=0.1 if moved else 0, y=0, yaw=0),
            velocity=Velocity(vx=0, vy=0, wz=0),
        )

    async def execute(goal):
        nonlocal moved
        assert goal.distance_m == 0.1
        assert goal.max_linear_speed_mps == 0.04
        assert goal.max_duration_ms == 4500
        if fail:
            raise RuntimeError("stop unconfirmed")
        moved = True
        return BoundedMotionResult(goal.motion_id, "completed", None)

    adapter = SimpleNamespace(state=state, execute_bounded_motion=execute)
    if fail:
        with pytest.raises(RuntimeError, match="stop unconfirmed"):
            await probe.floor_move_trial(adapter)
    else:
        await probe.floor_move_trial(adapter)
    events = [json.loads(s) for s in capsys.readouterr().out.splitlines()]
    results = [e for e in events if e["event"] == "floor_move_result"]
    assert len(results) == (0 if fail else 1)
    if results:
        assert results[0]["odometry_forward_m"] == 0.1


@pytest.mark.asyncio
async def test_left_turn_plan_and_wrapped_yaw(capsys):
    moved = False

    async def state():
        return RoverState(
            timestamp=1,
            connected=True,
            capabilities=Capabilities(),
            pose=Pose(x=0, y=0, yaw=math.radians(-175 if moved else 170)),
            velocity=Velocity(vx=0, vy=0, wz=0),
        )

    async def execute(goal):
        nonlocal moved
        assert goal.kind == "rotate"
        assert goal.distance_m is None
        assert goal.angle_rad == pytest.approx(math.radians(15))
        assert goal.max_angular_speed_rad_s == 0.15
        assert goal.max_duration_ms == 4500
        moved = True
        return BoundedMotionResult(goal.motion_id, "completed", None)

    await probe.floor_move_trial(
        SimpleNamespace(state=state, execute_bounded_motion=execute), turn=True
    )
    events = [json.loads(s) for s in capsys.readouterr().out.splitlines()]
    result = next(e for e in events if e["event"] == "floor_turn_result")
    assert result["odometry_yaw_deg"] == pytest.approx(15)
