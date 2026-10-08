import io
import json

from apris_server import doctor


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def test_doctor_prints_json_and_returns_ready(monkeypatch, capsys) -> None:
    payload = {
        "status": "ready",
        "ready": True,
        "server": {"instance_id": "test", "deployment_profile": "development"},
        "adapter": {"type": "simulator", "healthy": True},
        "clients": [],
        "control": {"owner_client_id": None, "estop_latched": False},
        "loops": {"safety": {"healthy": True}, "state": {"healthy": True}},
    }
    monkeypatch.setattr(
        doctor,
        "urlopen",
        lambda request, timeout: FakeResponse(json.dumps(payload).encode()),
    )

    assert doctor.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["server"]["instance_id"] == "test"


def test_doctor_returns_not_ready(monkeypatch, capsys) -> None:
    payload = {
        "status": "not_ready",
        "ready": False,
        "server": {"instance_id": "test", "deployment_profile": "edge"},
        "adapter": {"type": "simulator", "healthy": True},
        "clients": [],
        "control": {"owner_client_id": None, "estop_latched": False},
        "loops": {"state": {"healthy": False}},
    }
    monkeypatch.setattr(
        doctor,
        "urlopen",
        lambda request, timeout: FakeResponse(json.dumps(payload).encode()),
    )

    assert doctor.main([]) == 1
    assert "unhealthy loops: state" in capsys.readouterr().out
