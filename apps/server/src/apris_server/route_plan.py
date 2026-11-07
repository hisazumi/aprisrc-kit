"""Registered, directed polyline routes; no search or obstacle avoidance."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, model_validator

from .course_map import Contract, Identifier, MapSnapshot, PlanarPose, Point
from .localization import Positive


class RouteProfile(Contract):
    id: Identifier
    bodyRadiusM: Positive  # Circumscribed body including all in-place rotation.
    stoppingMarginM: Positive
    maxPositionErrorM: Positive
    maxHeadingErrorRad: Annotated[float, Field(gt=0, le=0.5, allow_inf_nan=False)]
    arrivalM: Positive
    arrivalHeadingRad: Positive
    headingToleranceRad: Annotated[float, Field(ge=0.03, le=0.2, allow_inf_nan=False)]
    maxStepM: Annotated[float, Field(ge=0.03, le=0.1, allow_inf_nan=False)]
    maxTurnRad: Annotated[float, Field(ge=0.05, le=0.5, allow_inf_nan=False)]
    speedMps: Annotated[float, Field(ge=0.05, le=0.3, allow_inf_nan=False)]
    turnSpeedRadS: Annotated[float, Field(ge=0.1, le=1.2, allow_inf_nan=False)]
    maxCorrectionM: Positive
    maxCorrectionRad: Positive
    maxActions: Annotated[int, Field(ge=1, le=24)]
    deadlineS: Annotated[float, Field(gt=0, le=60, allow_inf_nan=False)]

    @model_validator(mode="after")
    def tolerances(self) -> RouteProfile:
        if self.arrivalM <= self.maxPositionErrorM + 0.015:
            raise ValueError("arrival-tighter-than-motion-resolution")
        if self.arrivalHeadingRad <= self.maxHeadingErrorRad + 0.027:
            raise ValueError("arrival-heading-too-tight")
        return self


@dataclass(frozen=True)
class RoutePlan:
    route_id: str
    points: tuple[Point, ...]
    destination: PlanarPose
    clearance: float


def segment_distance(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    fraction = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2)) if length2 else 0.0
    return math.hypot(x - ax - fraction * dx, y - ay - fraction * dy)


def prepare_route(world: MapSnapshot, method: str, target: str, profile: RouteProfile) -> RoutePlan:
    places = {p.id: p for p in world.document.places}
    routes = world.document.routes
    if method == "place":
        if target not in places:
            raise ValueError("unknown-destination")
        candidates = [r for r in routes if r.to == target]
        if len(candidates) != 1:
            raise ValueError("ambiguous-route" if candidates else "route-unavailable")
        route = candidates[0]
    elif method == "route":
        route = next((r for r in routes if r.id == target), None)
        if route is None:
            raise ValueError("unknown-route")
    else:
        raise ValueError("unsupported-route-method")
    if route.corridorWidthM is None:
        raise ValueError("corridor-required")
    # Reserve lateral excursion during a finite movement with heading uncertainty.
    allowance = profile.maxStepM * math.sin(
        profile.maxHeadingErrorRad + profile.headingToleranceRad
    )
    clearance = (
        route.corridorWidthM / 2
        - profile.bodyRadiusM
        - profile.stoppingMarginM
        - profile.maxPositionErrorM
        - allowance
    )
    if clearance <= 0:
        raise ValueError("corridor-too-narrow")
    destination = places[route.to].pose
    points = (places[route.from_].pose, *route.via, destination)
    length = 0.0
    for a, b in zip(points, points[1:], strict=False):
        segment = math.hypot(b.xM - a.xM, b.yM - a.yM)
        if segment < 1e-6:
            raise ValueError("zero-length-segment")
        length += segment
    if math.ceil(length / profile.maxStepM) > profile.maxActions:
        raise ValueError("route-budget")
    return RoutePlan(route.id, points, destination, clearance)


def feedback_duration(target, tolerance, floor, gain, speed):
    """Upper continuous-time estimate for the existing proportional/floor controller."""
    remaining, duration = target, 0.0
    if speed < floor:
        return max(0.0, remaining - tolerance) / speed
    plateau = speed / gain
    if remaining > max(plateau, tolerance):
        duration += (remaining - max(plateau, tolerance)) / speed
        remaining = max(plateau, tolerance)
    knee = max(floor / gain, tolerance)
    if remaining > knee:
        duration += math.log(remaining / knee) / gain
        remaining = knee
    return duration + max(0.0, remaining - tolerance) / floor
