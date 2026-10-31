import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

scripts = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location("timeout_probe", scripts / "ironx_timeout_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
sys.path.pop(0)


def sample(t, vx, topic="wheel", age=0):
    return {"topic": topic, "t": t, "age": age, "vx": vx, "vy": 0, "wz": 0}


def test_stop_before_rescue():
    samples = [sample(0.2, 0.05), sample(0.5, 0), sample(0.6, 0), sample(0.7, 0)]
    assert probe.classify(samples, 0, 0.35, 1)["result"] == "stop_observed_before_rescue"


def test_rescue_stop_not_credited():
    samples = [sample(0.2, 0.05), sample(0.9, 0.05), sample(1.1, 0), sample(1.2, 0), sample(1.3, 0)]
    assert probe.classify(samples, 0, 0.35, 1)["result"] == "no_confirmed_stop_within_test_window"


def test_no_motion_is_inconclusive():
    assert (
        probe.classify([sample(0.5, 0)], 0, 0.35, 1)["result"] == "inconclusive_no_measured_motion"
    )


def test_ekf_alone_not_credited():
    samples = [sample(0.2, 0.05), *[sample(t, 0, "ekf") for t in [0.5, 0.6, 0.7]]]
    assert probe.classify(samples, 0, 0.35, 1)["result"] == "no_confirmed_stop_within_test_window"


def test_capture_before_silence_not_credited():
    samples = [sample(0.2, 0.05), *[sample(t, 0, age=0.3) for t in [0.5, 0.6, 0.7]]]
    assert probe.classify(samples, 0, 0.35, 1)["result"] == "no_confirmed_stop_within_test_window"


def test_motion_after_apparent_stop_resets_confirmation():
    samples = [sample(0.2, 0.05), sample(0.5, 0), sample(0.6, 0), sample(0.7, 0), sample(0.8, 0.04)]
    assert probe.classify(samples, 0, 0.35, 1)["result"] == "no_confirmed_stop_within_test_window"


@pytest.mark.parametrize("urgent", [False, True])
@pytest.mark.parametrize("delayed", [False, True])
def test_rescue_sends_only_zero_at_deadline_or_on_abort(monkeypatch, urgent, delayed):
    clock = [10.0]
    sent = []
    ready = []
    created = []

    class Twist:
        def __init__(self):
            self.linear = SimpleNamespace(x=0, y=0, z=0)
            self.angular = SimpleNamespace(x=0, y=0, z=0)

    pub = SimpleNamespace(
        get_subscription_count=lambda: 1,
        publish=lambda msg: sent.append((clock[0], msg)),
    )

    def create_publisher(*args):
        created.append(clock[0])
        return pub

    node = SimpleNamespace(create_publisher=create_publisher, destroy_node=lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "rclpy",
        SimpleNamespace(init=lambda: None, create_node=lambda name: node, shutdown=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "geometry_msgs.msg", SimpleNamespace(Twist=Twist))
    monkeypatch.setattr(probe.os, "setsid", lambda: None)
    monkeypatch.setattr(probe.signal, "signal", lambda *args: None)
    monkeypatch.setattr(probe.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(probe.time, "sleep", lambda dt: clock.__setitem__(0, clock[0] + dt))
    first_zero = SimpleNamespace(value=0)
    probe.rescue_worker(
        SimpleNamespace(set=lambda: ready.append(True)),
        SimpleNamespace(wait=lambda timeout: True),
        SimpleNamespace(is_set=lambda: urgent),
        SimpleNamespace(value=11.0),
        first_zero,
        delayed,
    )
    assert ready == [True]
    assert len(sent) >= 19
    assert sent[0][0] == first_zero.value
    assert created == [first_zero.value if delayed else 10.0]
    assert 10 <= first_zero.value < 10.01 if urgent else 11 <= first_zero.value < 11.01
    assert all(
        vars(msg.linear) == dict(x=0, y=0, z=0) and vars(msg.angular) == dict(x=0, y=0, z=0)
        for _, msg in sent
    )
