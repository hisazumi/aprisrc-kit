import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from apris_server.course_map import MapLimits, MapStore, load_map

EXAMPLE = Path(__file__).parents[1] / "config/maps/demo-room.json"


def document():
    return json.loads(EXAMPLE.read_bytes())


def encoded(value):
    return json.dumps(value).encode()


def test_example_is_immutable_and_has_independent_places():
    snapshot = load_map(EXAMPLE.read_bytes())
    assert snapshot.document.routes[0].to == "desk"
    assert isinstance(snapshot.document.places, tuple)
    assert len(snapshot.identity.contentDigest) == 64
    with pytest.raises(ValidationError):
        snapshot.document.places[0].label = "changed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schemaVersion=2),
        lambda d: d.update(schemaVersion=True),
        lambda d: d.update(walls=[]),
        lambda d: d["markers"][0].update(sizeM=0),
        lambda d: d["markers"][0]["pose"].update(xM=float("nan")),
        lambda d: d["places"][0]["pose"].update(yM=float("inf")),
        lambda d: d["places"][0].update(id=""),
        lambda d: d["places"].append(d["places"][0]),
        lambda d: d["markers"].append(d["markers"][0]),
        lambda d: d["routes"][0].update(to="missing"),
        lambda d: d["initialPoseCandidates"][0].update(placeId="missing"),
        lambda d: d["places"][0]["pose"].update(xM="1"),
        lambda d: d["routes"][0].update(via=[{"xM": True, "yM": 0}]),
    ],
)
def test_invalid_maps(mutation):
    value = document()
    mutation(value)
    with pytest.raises(ValueError):
        load_map(encoded(value))


def test_duplicate_json_keys_and_invalid_encoding():
    for data in [b'{"schemaVersion":1,"schemaVersion":1}', b"\xff"]:
        with pytest.raises(ValueError):
            load_map(data)


def test_limits_at_boundary_and_over():
    data = EXAMPLE.read_bytes()
    load_map(data, MapLimits(max_bytes=len(data), max_places=2, max_coordinate_m=2))
    for limits in [
        MapLimits(max_bytes=len(data) - 1),
        MapLimits(max_places=1),
        MapLimits(max_coordinate_m=1),
        MapLimits(max_markers=0),
        MapLimits(max_routes=0),
        MapLimits(max_via=0),
    ]:
        with pytest.raises(ValueError):
            load_map(data, limits)


def test_activation_binding_and_atomic_failure():
    store = MapStore()
    original = store.activate(EXAMPLE.read_bytes(), stopped=True)
    binding = store.bind(
        "run-1", robot_profile="robot-v1", calibration="cam-v1", quality_profile="quality-v1"
    )
    assert binding.map == original.identity
    with pytest.raises(ValueError, match="active-run"):
        store.activate(EXAMPLE.read_bytes(), stopped=True)
    with pytest.raises(ValueError, match="duplicate-run"):
        store.bind("run-1", robot_profile="r", calibration="c", quality_profile="q")
    store.release("run-1")
    with pytest.raises(ValueError, match="stop-unconfirmed"):
        store.activate(EXAMPLE.read_bytes(), stopped=False)
    with pytest.raises(ValueError):
        store.activate(b"{}", stopped=True)
    assert store.active is original
    with pytest.raises(ValueError, match="map-revision-conflict"):
        store.activate(EXAMPLE.read_bytes() + b" ", stopped=True)
    assert store.active is original
    next_doc = document()
    next_doc["revision"] = "2"
    second = store.activate(encoded(next_doc), stopped=True)
    assert second.identity != original.identity
    assert binding.map == original.identity
    assert store.localization_epoch != binding.localizationEpoch


def test_store_requires_map_and_bounds_history_and_runs():
    store = MapStore(max_revisions=1, max_runs=1)
    with pytest.raises(ValueError, match="map-unavailable"):
        store.bind("r", robot_profile="r", calibration="c", quality_profile="q")
    store.activate(EXAMPLE.read_bytes(), stopped=True)
    store.bind("r", robot_profile="r", calibration="c", quality_profile="q")
    with pytest.raises(ValueError, match="run-capacity"):
        store.bind("s", robot_profile="r", calibration="c", quality_profile="q")
    store.release("r")
    value = document()
    value["revision"] = "2"
    with pytest.raises(ValueError, match="revision-capacity"):
        store.activate(encoded(value), stopped=True)
    assert store.active.identity.revision == "1"


def test_failed_load_preserves_epoch_and_success_invalidates_localization():
    store = MapStore()
    store.activate(EXAMPLE.read_bytes(), stopped=True)
    epoch = store.localization_epoch
    with pytest.raises(ValueError):
        store.activate(b"{}", stopped=True)
    assert store.localization_epoch == epoch
    store.activate(EXAMPLE.read_bytes(), stopped=True)
    assert store.localization_epoch != epoch


def test_history_conflict_after_switching_maps():
    store = MapStore()
    first = EXAMPLE.read_bytes()
    store.activate(first, stopped=True)
    value = document()
    value["mapId"] = "another-room"
    store.activate(encoded(value), stopped=True)
    with pytest.raises(ValueError, match="map-revision-conflict"):
        store.activate(first + b" ", stopped=True)
    assert store.active.identity.mapId == "another-room"


def test_zero_waypoints_is_explicit_straight_route():
    value = document()
    value["routes"][0]["via"] = []
    assert load_map(encoded(value)).document.routes[0].via == ()


def test_relocalization_epoch_cannot_change_during_bound_run():
    store = MapStore()
    store.activate(EXAMPLE.read_bytes(), stopped=True)
    old = store.localization_epoch
    with pytest.raises(ValueError, match="stop-unconfirmed"):
        store.relocalized("new", stopped=False)
    assert store.localization_epoch == old
    store.bind("run", robot_profile="r", calibration="c", quality_profile="q")
    with pytest.raises(ValueError, match="active-run"):
        store.relocalized("new", stopped=True)
    store.release("run")
    store.relocalized("new", stopped=True)
    assert (
        store.bind(
            "next", robot_profile="r", calibration="c", quality_profile="q"
        ).localizationEpoch
        == "new"
    )
