"""Versioned map data only; no motion authority or runtime endpoint is installed here."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Angle = Annotated[float, Field(allow_inf_nan=False, ge=-math.pi, le=math.pi)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Point(Contract):
    xM: Finite
    yM: Finite


class PlanarPose(Point):
    yawRad: Angle


class MarkerPose(PlanarPose):
    zM: Finite
    rollRad: Angle
    pitchRad: Angle


class Marker(Contract):
    family: Identifier
    id: Annotated[int, Field(ge=0, le=1_000_000)]
    sizeM: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    pose: MarkerPose


class Place(Contract):
    id: Identifier
    label: Annotated[str, Field(min_length=1, max_length=256)]
    pose: PlanarPose


class Route(Contract):
    id: Identifier
    from_: Identifier = Field(alias="from")
    to: Identifier
    via: tuple[Point, ...]


class InitialPoseCandidate(Contract):
    id: Identifier
    placeId: Identifier


class Units(Contract):
    length: Literal["m"]
    angle: Literal["rad"]


class CourseMap(Contract):
    schemaVersion: Annotated[int, Field(ge=1, le=1)]
    mapId: Identifier
    revision: Identifier
    frameId: Literal["map"]
    units: Units
    markers: tuple[Marker, ...]
    places: Annotated[tuple[Place, ...], Field(min_length=1)]
    routes: tuple[Route, ...]
    initialPoseCandidates: tuple[InitialPoseCandidate, ...]

    @model_validator(mode="after")
    def references(self) -> CourseMap:
        groups = [
            tuple((m.family, m.id) for m in self.markers),
            tuple(p.id for p in self.places),
            tuple(r.id for r in self.routes),
            tuple(p.id for p in self.initialPoseCandidates),
        ]
        if any(len(set(group)) != len(group) for group in groups):
            raise ValueError("duplicate-map-id")
        places = {p.id for p in self.places}
        if any(r.from_ not in places or r.to not in places for r in self.routes):
            raise ValueError("unknown-route-place")
        if any(p.placeId not in places for p in self.initialPoseCandidates):
            raise ValueError("unknown-initial-place")
        return self


class MapIdentity(Contract):
    mapId: Identifier
    revision: Identifier
    contentDigest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class MapSnapshot(Contract):
    identity: MapIdentity
    document: CourseMap


class MapLimits(Contract):
    # Resource/fixture limits, not qualified physical deployment limits.
    max_bytes: Annotated[int, Field(gt=0)] = 262144
    max_markers: Annotated[int, Field(ge=0)] = 256
    max_places: Annotated[int, Field(ge=1)] = 256
    max_routes: Annotated[int, Field(ge=0)] = 512
    max_candidates: Annotated[int, Field(ge=0)] = 256
    max_via: Annotated[int, Field(ge=0)] = 256
    max_coordinate_m: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1000.0


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate-json-key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"nonfinite-json:{value}")


def load_map(data: bytes, limits: MapLimits | None = None) -> MapSnapshot:
    limits = limits or MapLimits()
    if len(data) > limits.max_bytes:
        raise ValueError("map-size-limit")
    try:
        decoded = data.decode("utf-8")
        json.loads(decoded, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        document = CourseMap.model_validate_json(decoded)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid-map-encoding-or-depth") from exc
    for collection, limit in [
        (document.markers, limits.max_markers),
        (document.places, limits.max_places),
        (document.routes, limits.max_routes),
        (document.initialPoseCandidates, limits.max_candidates),
    ]:
        if len(collection) > limit:
            raise ValueError("map-collection-limit")
    points = [m.pose for m in document.markers] + [p.pose for p in document.places]
    for route in document.routes:
        if len(route.via) > limits.max_via:
            raise ValueError("map-via-limit")
        points.extend(route.via)
    if any(
        max(abs(p.xM), abs(p.yM), abs(getattr(p, "zM", 0))) > limits.max_coordinate_m
        for p in points
    ):
        raise ValueError("map-coordinate-limit")
    if any(m.sizeM > limits.max_coordinate_m for m in document.markers):
        raise ValueError("map-marker-size-limit")
    return MapSnapshot(
        identity=MapIdentity(
            mapId=document.mapId,
            revision=document.revision,
            contentDigest=hashlib.sha256(data).hexdigest(),
        ),
        document=document,
    )


class MapBinding(Contract):
    runId: Identifier
    map: MapIdentity
    localizationEpoch: Identifier
    robotProfile: Identifier
    calibration: Identifier
    qualityProfile: Identifier


class MapStore:
    """Single-threaded coordinator, to be called by a trusted authority in a later slice.

    `stopped` is evidence supplied by that authority, never a client permission.
    All operations are synchronous; binding and activation cannot interleave on one loop.
    The registry is memory-only. Startup must still begin inhibited/unlocalized.
    """

    def __init__(
        self, *, limits: MapLimits | None = None, max_revisions: int = 256, max_runs: int = 1
    ):
        if type(max_revisions) is not int or max_revisions < 1:
            raise ValueError("invalid-revision-capacity")
        if type(max_runs) is not int or max_runs < 1:
            raise ValueError("invalid-run-capacity")
        self.limits = limits or MapLimits()
        self.max_revisions = max_revisions
        self.max_runs = max_runs
        self._active: MapSnapshot | None = None
        self._known: dict[tuple[str, str], str] = {}
        self._runs: dict[str, MapBinding] = {}
        self._epoch = uuid4().hex

    @property
    def active(self) -> MapSnapshot | None:
        return self._active

    @property
    def localization_epoch(self) -> str:
        return self._epoch

    def activate(self, data: bytes, *, stopped: bool) -> MapSnapshot:
        if self._runs:
            raise ValueError("active-run")
        if stopped is not True:
            raise ValueError("stop-unconfirmed")
        candidate = load_map(data, self.limits)
        key = (candidate.identity.mapId, candidate.identity.revision)
        previous = self._known.get(key)
        if previous is not None and previous != candidate.identity.contentDigest:
            raise ValueError("map-revision-conflict")
        if previous is None and len(self._known) >= self.max_revisions:
            raise ValueError("revision-capacity")
        self._known[key] = candidate.identity.contentDigest
        self._active = candidate
        self._epoch = uuid4().hex
        return candidate

    def relocalized(self, epoch: str, *, stopped: bool) -> None:
        if self._runs:
            raise ValueError("active-run")
        if stopped is not True:
            raise ValueError("stop-unconfirmed")
        value = TypeAdapter(Identifier).validate_python(epoch, strict=True)
        if value == self._epoch:
            raise ValueError("new-localization-epoch-required")
        self._epoch = value

    def bind(
        self, run_id: str, *, robot_profile: str, calibration: str, quality_profile: str
    ) -> MapBinding:
        if self._active is None:
            raise ValueError("map-unavailable")
        if run_id in self._runs:
            raise ValueError("duplicate-run")
        if len(self._runs) >= self.max_runs:
            raise ValueError("run-capacity")
        binding = MapBinding(
            runId=run_id,
            map=self._active.identity,
            localizationEpoch=self._epoch,
            robotProfile=robot_profile,
            calibration=calibration,
            qualityProfile=quality_profile,
        )
        self._runs[run_id] = binding
        return binding

    def release(self, run_id: str) -> None:
        # Ending a binding does not establish stopping evidence.
        self._runs.pop(run_id, None)
