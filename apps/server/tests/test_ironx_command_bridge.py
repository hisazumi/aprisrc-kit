import importlib.util
import sys
from pathlib import Path

import pytest

scripts = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location("command_bridge", scripts / "ironx_command_bridge.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.pop(0)


def send(lease, stamp=100, wall=100, mono=10, vx=0.05, wz=0, vy=0):
    return lease.accept(stamp, wall, mono, vx, vy, 0, 0, 0, wz)


def test_startup_never_moves():
    assert module.CommandLease().output(10, True) == (0, 0)


def test_integer_json_components_become_ros_floats():
    lease = module.CommandLease()
    assert send(lease, vx=0, wz=0)
    assert all(type(v) is float for v in lease.output(10.01, True))


def test_timeout_and_repeated_zero():
    lease = module.CommandLease()
    assert send(lease)
    assert lease.output(10.29, True) == (0.05, 0)
    for t in (10.3, 10.4, 11):
        assert lease.output(t, True) == (0, 0)


def test_transport_age_consumes_lease():
    lease = module.CommandLease()
    assert send(lease, wall=100.2)
    assert lease.output(10.11, True) == (0, 0)


def test_refresh_then_fresh_restart():
    lease = module.CommandLease()
    assert send(lease)
    assert send(lease, stamp=100.2, wall=100.2, mono=10.2)
    assert lease.output(10.4, True) == (0.05, 0)
    assert lease.output(10.6, True) == (0, 0)
    assert send(lease, stamp=101, wall=101, mono=11)
    assert lease.output(11.1, True) == (0.05, 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(vx=float("nan")),
        dict(wz=float("inf")),
        dict(vx=0.151),
        dict(wz=0.201),
        dict(vy=0.01),
        dict(stamp=99),
        dict(stamp=101),
    ],
)
def test_invalid_command_clears_previous_motion(kwargs):
    lease = module.CommandLease()
    assert send(lease)
    assert not send(lease, **kwargs)
    assert lease.output(10.01, True) == (0, 0)


def test_replay_cannot_extend_lease():
    lease = module.CommandLease()
    assert send(lease)
    assert not send(lease, mono=10.1)
    assert lease.output(10.11, True) == (0, 0)


def test_telemetry_recovery_does_not_restore_old_command():
    lease = module.CommandLease()
    assert send(lease)
    assert lease.output(10.1, False) == (0, 0)
    assert lease.output(10.2, True) == (0, 0)


def test_fault_requires_restart():
    lease = module.CommandLease()
    assert send(lease)
    lease.latch("competing_publisher")
    assert not send(lease, stamp=101, wall=101, mono=11)
    assert lease.output(11, True) == (0, 0)
