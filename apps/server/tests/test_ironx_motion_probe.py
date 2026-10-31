import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "probe", Path(__file__).resolve().parents[3] / "scripts/ironx_motion_probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("plan", [(0.05, 0, 1), (-0.03, 0, 0.5), (0, -0.15, 1)])
def test_bounded_plan(plan):
    assert probe.validate_plan(*plan)["duration_s"] <= 1


@pytest.mark.parametrize(
    "plan",
    [
        (0.06, 0, 1),
        (0, 0.21, 1),
        (0.05, 0, 2),
        (0, 0, 1),
        (0.02, 0.1, 1),
        (float("nan"), 0, 1),
        (0.05, 0, -1),
    ],
)
def test_reject_unsafe_plan(plan):
    with pytest.raises(ValueError):
        probe.validate_plan(*plan)


@pytest.mark.parametrize("age,vx", [(0.4, 0), (-0.1, 0), (0.1, float("nan"))])
def test_reject_stale_or_invalid_observations(age, vx):
    assert not probe.valid_odometry(age, vx, 0, 0)
