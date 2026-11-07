"""M1 normalized data contracts; neither an estimator nor a motion permission."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .course_map import Contract, Identifier, MapIdentity, MarkerPose, PlanarPose

Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Sequence = Annotated[int, Field(ge=0)]
Provenance = Literal["real", "simulated", "synthetic"]


class LocalizationScope(Contract):
    robotId: Identifier
    controlEpoch: Identifier
    odomEpoch: Identifier
    localizationEpoch: Identifier
    map: MapIdentity
    robotProfile: Identifier
    calibration: Identifier
    qualityProfile: Identifier


class ClockScope(Contract):
    # Both timestamps are already normalized to this single clock/epoch.
    clockId: Identifier
    clockEpoch: Identifier
    receivedTime: Nonnegative
    sequence: Sequence


class CorrectionReference(Contract):
    observationId: Identifier
    sourceId: Identifier
    sessionEpoch: Identifier
    family: Identifier
    markerId: Annotated[int, Field(ge=0, le=1_000_000)]
    captureTime: Nonnegative


class LocalizationQuality(Contract):
    status: Literal["unlocalized", "tracking", "degraded", "lost"]
    reasons: Annotated[tuple[Identifier, ...], Field(max_length=32)]
    positionErrorM: Nonnegative | None
    headingErrorRad: Nonnegative | None
    errorModel: Identifier
    lastCorrection: CorrectionReference | None
    distanceSinceCorrectionM: Nonnegative | None
    rotationSinceCorrectionRad: Nonnegative | None

    @model_validator(mode="after")
    def meaningful_quality(self) -> LocalizationQuality:
        if self.status != "tracking" and not self.reasons:
            raise ValueError("quality-reason-required")
        if self.status == "tracking" and (
            self.positionErrorM is None or self.headingErrorRad is None
        ):
            raise ValueError("tracking-error-estimate-required")
        metrics = (self.distanceSinceCorrectionM, self.rotationSinceCorrectionRad)
        if self.lastCorrection is None and any(v is not None for v in metrics):
            raise ValueError("correction-reference-required")
        if self.lastCorrection is not None and any(v is None for v in metrics):
            raise ValueError("correction-progress-required")
        return self


class LocalizationSnapshot(LocalizationScope, ClockScope):
    sampleTime: Nonnegative
    odomPose: PlanarPose
    mapPose: PlanarPose | None
    mapFromOdom: PlanarPose | None
    odomAgeS: Nonnegative
    sensorStatus: Literal["ok", "degraded", "unavailable"]
    provenance: Provenance
    estimatorVersion: Identifier
    quality: LocalizationQuality

    @model_validator(mode="after")
    def coherent_snapshot(self) -> LocalizationSnapshot:
        if self.sampleTime > self.receivedTime:
            raise ValueError("sample-after-reception")
        if (self.mapPose is None) != (self.mapFromOdom is None):
            raise ValueError("pose-transform-pair-required")
        if self.quality.status == "unlocalized":
            if self.mapPose is not None or self.quality.lastCorrection is not None:
                raise ValueError("unlocalized-map-pose-must-be-null")
        if self.quality.status in ("tracking", "degraded") and self.mapPose is None:
            raise ValueError("localized-pose-required")
        correction = self.quality.lastCorrection
        if correction is not None and correction.captureTime > self.sampleTime:
            raise ValueError("correction-after-sample")
        if self.quality.status == "tracking" and self.sensorStatus == "unavailable":
            raise ValueError("tracking-odometry-unavailable")
        return self


class MarkerObservation(LocalizationScope, ClockScope):
    # Post-normalization contract: raw camera-coordinate input has a separate future adapter.
    captureTime: Nonnegative
    clockUncertaintyS: Nonnegative
    sourceId: Identifier
    sessionEpoch: Identifier
    observationId: Identifier
    family: Identifier
    markerId: Annotated[int, Field(ge=0, le=1_000_000)]
    frameId: Literal["base"]
    poseAmbiguous: bool
    relativePose: MarkerPose
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    provenance: Provenance

    @model_validator(mode="after")
    def capture_before_reception(self) -> MarkerObservation:
        if self.captureTime > self.receivedTime:
            raise ValueError("capture-after-reception")
        return self
