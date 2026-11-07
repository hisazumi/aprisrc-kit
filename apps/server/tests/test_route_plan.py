import json
from pathlib import Path

import pytest

from apris_server.course_map import load_map
from apris_server.route_plan import RouteProfile, prepare_route, segment_distance

ROOT = Path(__file__).parents[1]


def fixtures():
    world = load_map((ROOT / "config/maps/route-demo.json").read_bytes())
    profile = RouteProfile.model_validate_json(
        (ROOT / "scenarios/localization/route-profile.json").read_bytes()
    )
    return world, profile


def test_registered_route_keeps_waypoint_order_and_body_margin():
    world, profile = fixtures()
    plan = prepare_route(world, "route", "start-to-desk", profile)
    assert [(p.xM, p.yM) for p in plan.points] == [(0, 0), (0.16, 0), (0.16, 0.16)]
    assert plan.destination.yawRad > 1.5
    assert plan.clearance > 0


def test_missing_corridor_and_too_narrow_route_rejected():
    world, profile = fixtures()
    for width in [None, 0.3]:
        doc = world.document.model_dump(mode="json", by_alias=True)
        doc["routes"][0]["corridorWidthM"] = width
        with pytest.raises(ValueError, match="corridor"):
            prepare_route(load_map(json.dumps(doc).encode()), "route", "start-to-desk", profile)


def test_go_to_requires_unambiguous_registered_route():
    world, profile = fixtures()
    assert prepare_route(world, "place", "desk", profile).route_id == "start-to-desk"
    doc = world.document.model_dump(mode="json", by_alias=True)
    doc["routes"].append({**doc["routes"][0], "id": "alternative"})
    with pytest.raises(ValueError, match="ambiguous-route"):
        prepare_route(load_map(json.dumps(doc).encode()), "place", "desk", profile)
    with pytest.raises(ValueError, match="unknown-destination"):
        prepare_route(world, "place", "missing", profile)


def test_capsule_distance_includes_endpoints():
    assert segment_distance(1, 1, 0, 0, 2, 0) == 1
    assert segment_distance(-1, 0, 0, 0, 2, 0) == 1
    assert segment_distance(3, 0, 0, 0, 2, 0) == 1


def test_zero_length_and_long_routes_rejected_before_motion():
    world, profile = fixtures()
    doc = world.document.model_dump(mode="json", by_alias=True)
    doc["routes"][0]["via"] = [{"xM": 0, "yM": 0}]
    with pytest.raises(ValueError, match="zero-length-segment"):
        prepare_route(load_map(json.dumps(doc).encode()), "route", "start-to-desk", profile)
    doc = world.document.model_dump(mode="json", by_alias=True)
    doc["places"][1]["pose"]["xM"] = 100
    with pytest.raises(ValueError, match="route-budget"):
        prepare_route(load_map(json.dumps(doc).encode()), "route", "start-to-desk", profile)


def test_feedback_budget_accounts_for_deceleration():
    from apris_server.route_plan import feedback_duration

    assert feedback_duration(0.4, 0.026, 0.1, 1.6, 0.7) > 1.2
    assert feedback_duration(0.15, 0.026, 0.1, 1.6, 0.7) < 1.0
    assert feedback_duration(0.06, 0.015, 0.04, 1.4, 0.1) < 1.0
