import json

from apris_server.structured_log import StructuredLog


def test_structured_log_persists_and_filters_entries(tmp_path) -> None:
    structured_log = StructuredLog(tmp_path)
    structured_log.record("state", "rover_state", {"x": 1})
    structured_log.record(
        "scenario_event",
        "marker",
        {"kind": "marker", "payload": {"markerId": 1}, "source": "manual"},
    )
    structured_log.record("adapter_command", "drive", {"vx": 0.2})
    structured_log.record(
        "perception_observation",
        "person",
        {"observation": {"source": "recorded"}},
    )

    recent = structured_log.recent()
    assert all(entry["category"] != "state" for entry in recent)
    assert any(entry["name"] == "drive" for entry in recent)
    replayable = structured_log.replayable_inputs()
    assert replayable[-1]["category"] == "perception_observation"
    assert all(entry["category"] != "adapter_command" for entry in replayable)

    path = structured_log.path
    health = structured_log.health()
    assert health["healthy"] is True
    assert health["last_success_at"] is not None
    structured_log.close()
    persisted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert persisted[0]["name"] == "session_started"
    assert persisted[-1]["name"] == "session_stopped"
