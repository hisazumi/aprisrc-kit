import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

scripts = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location(
    "bridge_stop_probe", scripts / "ironx_bridge_stop_probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
sys.path.pop(0)


def test_default_preflight_never_starts_publishers_or_processes(monkeypatch, capsys):
    clock = [100.0]
    callbacks = []

    def forbidden(*args, **kwargs):
        raise AssertionError("Preflight must not start publishers or processes")

    node = SimpleNamespace(
        create_subscription=lambda typ, topic, cb, qos: callbacks.append(cb),
        create_publisher=forbidden,
        get_clock=lambda: SimpleNamespace(
            now=lambda: SimpleNamespace(nanoseconds=int(clock[0] * 1e9))
        ),
        get_subscriptions_info_by_topic=lambda topic: [SimpleNamespace(node_name="ironx_driver")],
        count_publishers=lambda topic: 0,
        destroy_node=lambda: None,
    )

    def spin_once(node, timeout_sec):
        clock[0] += max(timeout_sec, 0.001)
        sec = int(clock[0])
        vector = SimpleNamespace(x=0, y=0, z=0)
        msg = SimpleNamespace(
            header=SimpleNamespace(
                stamp=SimpleNamespace(sec=sec, nanosec=int((clock[0] - sec) * 1e9)), frame_id="odom"
            ),
            child_frame_id="base_footprint",
            twist=SimpleNamespace(twist=SimpleNamespace(linear=vector, angular=vector)),
        )
        for callback in callbacks:
            callback(msg)

    monkeypatch.setitem(
        sys.modules,
        "rclpy",
        SimpleNamespace(
            init=lambda: None,
            create_node=lambda name: node,
            spin_once=spin_once,
            ok=lambda: True,
            shutdown=lambda: None,
        ),
    )
    monkeypatch.setitem(sys.modules, "rclpy.qos", SimpleNamespace(qos_profile_sensor_data=object()))
    monkeypatch.setitem(sys.modules, "geometry_msgs.msg", SimpleNamespace(TwistStamped=object))
    monkeypatch.setitem(sys.modules, "nav_msgs.msg", SimpleNamespace(Odometry=object))
    monkeypatch.setattr(probe.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(probe.signal, "signal", lambda *args: None)
    monkeypatch.setattr(probe.subprocess, "Popen", forbidden)
    monkeypatch.setattr(
        probe.multiprocessing,
        "get_context",
        lambda name: SimpleNamespace(
            Event=lambda: object(),
            Value=lambda *a, **kw: SimpleNamespace(value=0),
            Process=forbidden,
        ),
    )
    monkeypatch.setattr(sys, "argv", ["probe"])
    probe.main()
    assert '"event": "check_only"' in capsys.readouterr().out


def test_observation_window_allows_timeout_and_braking_samples():
    assert probe.RESCUE_S - probe.PULSE_S >= 0.3 + 0.3 + 0.2
