"""M2 bounded planar estimator. Trusted normalized inputs only; no motion control."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .course_map import Contract, Identifier, MapSnapshot, PlanarPose
from .localization_contract import (
    ClockScope,
    CorrectionReference,
    LocalizationQuality,
    LocalizationScope,
    LocalizationSnapshot,
    MarkerObservation,
    Nonnegative,
    Provenance,
)
from .localization_geometry import angle, compose, interpolate, inverse, marker_base_pose

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class LocalizationProfile(Contract):
    # All values explicit. The bundled profile is synthetic and not physically qualified.
    id: Identifier
    historySamples: Annotated[int, Field(ge=2, le=4096)]
    historySeconds: Positive
    maxSampleGapS: Positive
    maxOdomAgeS: Positive
    maxObservationAgeS: Positive
    maxClockUncertaintyS: Nonnegative
    maxOdomCoordinateM: Positive
    maxVelocityMps: Positive
    maxYawRateRadS: Positive
    minConfidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    minMarkerRangeM: Nonnegative
    maxMarkerRangeM: Positive
    maxTiltRad: Annotated[float, Field(ge=0, lt=math.pi / 2, allow_inf_nan=False)]
    maxBaseHeightM: Nonnegative
    maxInnovationM: Positive
    maxInnovationRad: Annotated[float, Field(gt=0, le=math.pi, allow_inf_nan=False)]
    initialPositionErrorM: Positive
    initialHeadingErrorRad: Positive
    markerPositionErrorM: Positive
    markerHeadingErrorRad: Positive
    positionDriftPerM: Nonnegative
    positionDriftPerRad: Nonnegative
    positionDriftPerS: Nonnegative
    headingDriftPerM: Nonnegative
    headingDriftPerRad: Nonnegative
    headingDriftPerS: Nonnegative
    degradedPositionM: Positive
    lostPositionM: Positive
    degradedHeadingRad: Positive
    lostHeadingRad: Positive
    maxAcceptedObservations: Annotated[int, Field(ge=1, le=4096)]

    @model_validator(mode="after")
    def thresholds(self) -> LocalizationProfile:
        if self.maxSampleGapS * self.maxYawRateRadS >= math.pi:
            raise ValueError("ambiguous-rotation-sampling")
        if self.minMarkerRangeM >= self.maxMarkerRangeM:
            raise ValueError("invalid-range-limits")
        if self.degradedPositionM >= self.lostPositionM:
            raise ValueError("invalid-position-limits")
        if self.degradedHeadingRad >= self.lostHeadingRad:
            raise ValueError("invalid-heading-limits")
        if max(self.initialPositionErrorM, self.markerPositionErrorM) > self.degradedPositionM:
            raise ValueError("initial-position-error-too-large")
        if max(self.initialHeadingErrorRad, self.markerHeadingErrorRad) > self.degradedHeadingRad:
            raise ValueError("initial-heading-error-too-large")
        return self


class SourceSession(Contract):
    sourceId: Identifier
    sessionEpoch: Identifier


class OdometrySample(ClockScope):
    robotId: Identifier
    controlEpoch: Identifier
    odomEpoch: Identifier
    sampleTime: Nonnegative
    pose: PlanarPose
    sensorStatus: Literal["ok", "degraded", "unavailable"]
    provenance: Provenance

    @model_validator(mode="after")
    def time_order(self) -> OdometrySample:
        if self.sampleTime > self.receivedTime:
            raise ValueError("sample-after-reception")
        return self


class CorrectionResult(Contract):
    applied: bool
    reason: Identifier


@dataclass(frozen=True)
class HistoryEntry:
    sample: OdometrySample
    distance: float
    rotation: float


class Localization:
    def __init__(
        self,
        world: MapSnapshot,
        scope: LocalizationScope,
        profile: LocalizationProfile,
        *,
        clock: Callable[[], float],
        clock_id: str,
        clock_epoch: str,
        provenance: Provenance,
        sources: tuple[SourceSession, ...],
    ):
        if scope.map != world.identity or scope.qualityProfile != profile.id:
            raise ValueError("configuration-mismatch")
        if len(sources) > 16 or len({s.sourceId for s in sources}) != len(sources):
            raise ValueError("invalid-source-sessions")
        # Validate clock/provenance metadata even before receiving the first sample.
        ClockScope(clockId=clock_id, clockEpoch=clock_epoch, receivedTime=0.0, sequence=0)
        if provenance not in ("real", "simulated", "synthetic"):
            raise ValueError("invalid-provenance")
        self.world, self.scope, self.profile = world, scope, profile
        self.clock, self.clock_id, self.clock_epoch = clock, clock_id, clock_epoch
        self.provenance = provenance
        self.sources = {s.sourceId: s.sessionEpoch for s in sources}
        self._clear()

    def _clear(self) -> None:
        self._history: deque[HistoryEntry] = deque(maxlen=self.profile.historySamples)
        self._transform: PlanarPose | None = None
        self._reference: CorrectionReference | None = None
        self._anchor_time = self._anchor_distance = self._anchor_rotation = 0.0
        self._position_error = self._heading_error = 0.0
        self._lost: str | None = None
        self._reset_required = False
        self._clock_fault = False
        self._lost_at: float | None = None
        self._last_now: float | None = None
        self._accepted: set[str] = set()
        self._source_sequence: dict[str, int] = {}
        self._last_capture: float | None = None
        self._snapshot_sequence = 0

    @property
    def history_size(self) -> int:
        return len(self._history)

    def _now(self) -> float:
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            self._lost, self._reset_required = "invalid-clock", True
            self._clock_fault = True
            raise ValueError("invalid-clock")
        if self._last_now is not None and now < self._last_now:
            self._lost, self._reset_required = "clock-regressed", True
            self._clock_fault = True
            raise ValueError("clock-regressed")
        self._last_now = now
        return float(now)

    def reset(self, scope: LocalizationScope, *, clock_epoch: str, stopped: bool) -> None:
        # Caller must revoke/end any route first. This method does not stop a robot.
        if stopped is not True:
            raise ValueError("stop-unconfirmed")
        if scope.localizationEpoch == self.scope.localizationEpoch:
            raise ValueError("new-localization-epoch-required")
        if scope.odomEpoch == self.scope.odomEpoch:
            raise ValueError("new-odometry-epoch-required")
        if self._clock_fault and clock_epoch == self.clock_epoch:
            raise ValueError("new-clock-epoch-required")
        if scope.map != self.world.identity or scope.qualityProfile != self.profile.id:
            raise ValueError("configuration-mismatch")
        ClockScope(clockId=self.clock_id, clockEpoch=clock_epoch, receivedTime=0.0, sequence=0)
        self.scope, self.clock_epoch = scope, clock_epoch
        self._clear()

    def add_odometry(self, sample: OdometrySample) -> None:
        now = self._now()
        expected = (self.scope.robotId, self.scope.controlEpoch, self.scope.odomEpoch)
        if (sample.robotId, sample.controlEpoch, sample.odomEpoch) != expected:
            raise ValueError("scope-mismatch")
        if (sample.clockId, sample.clockEpoch) != (self.clock_id, self.clock_epoch):
            raise ValueError("clock-mismatch")
        if sample.provenance != self.provenance:
            raise ValueError("provenance-mismatch")
        if sample.receivedTime > now:
            raise ValueError("reception-in-future")
        if max(abs(sample.pose.xM), abs(sample.pose.yM)) > self.profile.maxOdomCoordinateM:
            self._lost, self._reset_required = "odometry-range", True
            raise ValueError("odometry-range")
        if self._transform is not None:
            self._quality(now)
        distance = rotation = 0.0
        if self._history:
            previous = self._history[-1]
            dt = sample.sampleTime - previous.sample.sampleTime
            if dt <= 0 or sample.sequence <= previous.sample.sequence:
                raise ValueError("odometry-order")
            dp = math.hypot(
                sample.pose.xM - previous.sample.pose.xM, sample.pose.yM - previous.sample.pose.yM
            )
            dr = abs(angle(sample.pose.yawRad - previous.sample.pose.yawRad))
            if dp / dt > self.profile.maxVelocityMps or dr / dt > self.profile.maxYawRateRadS:
                self._lost, self._reset_required = "odometry-jump", True
                raise ValueError("odometry-jump")
            if dt > self.profile.maxSampleGapS:
                self._lost = "odometry-gap"
            distance, rotation = previous.distance + dp, previous.rotation + dr
        self._history.append(HistoryEntry(sample, distance, rotation))
        while len(self._history) > 1 and self._history[0].sample.sampleTime < (
            sample.sampleTime - self.profile.historySeconds
        ):
            self._history.popleft()
        if sample.sensorStatus == "unavailable":
            self._lost = "odometry-unavailable"
        if self._transform is not None:
            self._quality(now)

    def _latest(self) -> HistoryEntry:
        if not self._history:
            raise ValueError("odometry-unavailable")
        return self._history[-1]

    def _at(self, captured: float) -> tuple[PlanarPose, float, float]:
        for item in self._history:
            if item.sample.sampleTime == captured:
                if item.sample.sensorStatus != "ok":
                    raise ValueError("history-unhealthy")
                return item.sample.pose, item.distance, item.rotation
        for a, b in zip(self._history, list(self._history)[1:], strict=False):
            if a.sample.sampleTime < captured < b.sample.sampleTime:
                dt = b.sample.sampleTime - a.sample.sampleTime
                if dt > self.profile.maxSampleGapS:
                    raise ValueError("history-gap")
                if a.sample.sensorStatus != "ok" or b.sample.sensorStatus != "ok":
                    raise ValueError("history-unhealthy")
                f = (captured - a.sample.sampleTime) / dt
                return (
                    interpolate(a.sample.pose, b.sample.pose, f),
                    a.distance + f * (b.distance - a.distance),
                    a.rotation + f * (b.rotation - a.rotation),
                )
        raise ValueError("history-unavailable")

    def _healthy_for_initialization(self, now: float, stopped: bool) -> HistoryEntry:
        if stopped is not True:
            raise ValueError("stop-unconfirmed")
        if self._reset_required:
            raise ValueError("reset-required")
        latest = self._latest()
        if now - latest.sample.sampleTime > self.profile.maxOdomAgeS:
            raise ValueError("odometry-stale")
        if latest.sample.sensorStatus != "ok":
            raise ValueError("odometry-unhealthy")
        return latest

    def initialize_placement(self, candidate_id: str, *, stopped: bool) -> None:
        now = self._now()
        latest = self._healthy_for_initialization(now, stopped)
        candidate = next(
            (p for p in self.world.document.initialPoseCandidates if p.id == candidate_id), None
        )
        if candidate is None:
            raise ValueError("unknown-placement")
        place = next(p for p in self.world.document.places if p.id == candidate.placeId)
        self._transform = compose(place.pose, inverse(latest.sample.pose))
        self._anchor_time = latest.sample.sampleTime
        self._anchor_distance, self._anchor_rotation = latest.distance, latest.rotation
        self._position_error = self.profile.initialPositionErrorM
        self._heading_error = self.profile.initialHeadingErrorRad
        self._reference, self._lost, self._lost_at = None, None, None
        # Earlier queued captures must not undo the operator's placement.
        self._last_capture = latest.sample.sampleTime

    def initialize_marker(
        self, observation: MarkerObservation, *, stopped: bool
    ) -> CorrectionResult:
        return self._correct(observation, initialize=True, stopped=stopped)

    def correct(self, observation: MarkerObservation) -> CorrectionResult:
        return self._correct(observation, initialize=False, stopped=False)

    def _correct(
        self, obs: MarkerObservation, *, initialize: bool, stopped: bool
    ) -> CorrectionResult:
        try:
            self._apply_observation(obs, initialize=initialize, stopped=stopped)
        except ValueError as exc:
            return CorrectionResult(applied=False, reason=str(exc))
        return CorrectionResult(applied=True, reason="marker-corrected")

    def _apply_observation(
        self, obs: MarkerObservation, *, initialize: bool, stopped: bool
    ) -> None:
        now = self._now()
        if (
            LocalizationScope.model_validate(
                obs.model_dump(include=set(LocalizationScope.model_fields))
            )
            != self.scope
        ):
            raise ValueError("scope-mismatch")
        if (obs.clockId, obs.clockEpoch) != (self.clock_id, self.clock_epoch):
            raise ValueError("clock-mismatch")
        if self.sources.get(obs.sourceId) != obs.sessionEpoch:
            raise ValueError("source-session-mismatch")
        if obs.provenance != self.provenance:
            raise ValueError("provenance-mismatch")
        if obs.receivedTime > now:
            raise ValueError("reception-in-future")
        if now - obs.captureTime > self.profile.maxObservationAgeS:
            raise ValueError("observation-too-old")
        if obs.clockUncertaintyS > self.profile.maxClockUncertaintyS:
            raise ValueError("clock-uncertain")
        if obs.confidence < self.profile.minConfidence:
            raise ValueError("confidence-too-low")
        if obs.poseAmbiguous:
            raise ValueError("ambiguous-pose")
        if obs.observationId in self._accepted:
            raise ValueError("duplicate-observation")
        if len(self._accepted) >= self.profile.maxAcceptedObservations:
            raise ValueError("observation-capacity")
        if self._last_capture is not None and obs.captureTime <= self._last_capture:
            raise ValueError("capture-order")
        if obs.sequence <= self._source_sequence.get(obs.sourceId, -1):
            raise ValueError("source-order")
        if initialize:
            if self._transform is not None:
                self._quality(now)
            self._healthy_for_initialization(now, stopped)
        else:
            if self._transform is None:
                raise ValueError("initialization-required")
            if self._quality(now).status == "lost":
                raise ValueError("reinitialization-required")
        marker = next(
            (
                m
                for m in self.world.document.markers
                if (m.family, m.id) == (obs.family, obs.markerId)
            ),
            None,
        )
        if marker is None:
            raise ValueError("unknown-marker")
        relative = obs.relativePose
        distance = math.hypot(relative.xM, relative.yM, relative.zM)
        if not self.profile.minMarkerRangeM <= distance <= self.profile.maxMarkerRangeM:
            raise ValueError("marker-range")
        if obs.clockUncertaintyS:
            self._at(obs.captureTime - obs.clockUncertaintyS)
            self._at(obs.captureTime + obs.clockUncertaintyS)
        odom, travelled, rotated = self._at(obs.captureTime)
        candidate = marker_base_pose(
            marker.pose,
            relative,
            max_tilt=self.profile.maxTiltRad,
            max_height=self.profile.maxBaseHeightM,
        )
        if not initialize:
            current = compose(self._transform, odom)
            if (
                math.hypot(candidate.xM - current.xM, candidate.yM - current.yM)
                > self.profile.maxInnovationM
                or abs(angle(candidate.yawRad - current.yawRad)) > self.profile.maxInnovationRad
            ):
                raise ValueError("innovation-too-large")
        if initialize and self._lost_at is not None and obs.captureTime < self._lost_at:
            raise ValueError("pre-loss-observation")
        # Commit only after validation. No modification to any odometry sample.
        self._transform = compose(candidate, inverse(odom))
        self._anchor_time, self._anchor_distance, self._anchor_rotation = (
            obs.captureTime,
            travelled,
            rotated,
        )
        self._position_error = (
            self.profile.markerPositionErrorM + self.profile.maxVelocityMps * obs.clockUncertaintyS
        )
        self._heading_error = (
            self.profile.markerHeadingErrorRad + self.profile.maxYawRateRadS * obs.clockUncertaintyS
        )
        self._reference = CorrectionReference(
            observationId=obs.observationId,
            sourceId=obs.sourceId,
            sessionEpoch=obs.sessionEpoch,
            family=obs.family,
            markerId=obs.markerId,
            captureTime=obs.captureTime,
        )
        self._accepted.add(obs.observationId)
        self._source_sequence[obs.sourceId] = obs.sequence
        self._last_capture, self._lost, self._lost_at = obs.captureTime, None, None

    def _quality(self, now: float) -> LocalizationQuality:
        latest = self._latest()
        common = dict(errorModel=self.profile.id, lastCorrection=self._reference)
        if self._lost is not None and self._lost_at is None:
            self._lost_at = now
        if self._transform is None:
            return LocalizationQuality(
                status="lost" if self._lost else "unlocalized",
                reasons=(self._lost or "initialization-required",),
                positionErrorM=None,
                headingErrorRad=None,
                distanceSinceCorrectionM=None,
                rotationSinceCorrectionRad=None,
                **common,
            )
        d = latest.distance - self._anchor_distance
        r = latest.rotation - self._anchor_rotation
        elapsed = max(0.0, now - self._anchor_time)
        p = self.profile
        pe = (
            self._position_error
            + d * p.positionDriftPerM
            + r * p.positionDriftPerRad
            + elapsed * p.positionDriftPerS
        )
        he = (
            self._heading_error
            + d * p.headingDriftPerM
            + r * p.headingDriftPerRad
            + elapsed * p.headingDriftPerS
        )
        if self._lost is None:
            if now - latest.sample.sampleTime > p.maxOdomAgeS:
                self._lost = "odometry-stale"
            elif pe > p.lostPositionM or he > p.lostHeadingRad:
                self._lost = "error-limit"
        status: Literal["tracking", "degraded", "lost"] = "tracking"
        reasons: tuple[str, ...] = ()
        if self._lost:
            if self._lost_at is None:
                self._lost_at = now
            status, reasons = "lost", (self._lost,)
        elif latest.sample.sensorStatus == "degraded":
            status, reasons = "degraded", ("odometry-degraded",)
        elif pe > p.degradedPositionM or he > p.degradedHeadingRad:
            status, reasons = "degraded", ("error-growing",)
        return LocalizationQuality(
            status=status,
            reasons=reasons,
            positionErrorM=pe,
            headingErrorRad=he,
            distanceSinceCorrectionM=d if self._reference else None,
            rotationSinceCorrectionRad=r if self._reference else None,
            **common,
        )

    def snapshot(self) -> LocalizationSnapshot:
        now = self._now()
        latest = self._latest()
        quality = self._quality(now)
        self._snapshot_sequence += 1
        return LocalizationSnapshot(
            **self.scope.model_dump(),
            clockId=self.clock_id,
            clockEpoch=self.clock_epoch,
            receivedTime=now,
            sequence=self._snapshot_sequence,
            sampleTime=latest.sample.sampleTime,
            odomPose=latest.sample.pose,
            mapPose=compose(self._transform, latest.sample.pose) if self._transform else None,
            mapFromOdom=self._transform,
            odomAgeS=now - latest.sample.sampleTime,
            sensorStatus=latest.sample.sensorStatus,
            provenance=self.provenance,
            estimatorVersion="planar-m2-v1",
            quality=quality,
        )
