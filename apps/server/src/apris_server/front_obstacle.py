from __future__ import annotations

import math
import time
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import FrontObstacleSnapshot, StrictModel

FrontObstacleState = Literal["CLEAR", "BLOCKED", "UNKNOWN"]
PerceptionHealth = Literal["healthy", "degraded", "unavailable"]
FrontObstacleSource = Literal["manual", "scenario", "camera", "sensor", "replay"]


class FrontObstacleObservationInput(StrictModel):
    state: FrontObstacleState
    perception_health: PerceptionHealth
    source: FrontObstacleSource = "manual"
    observed_at: float | None = Field(default=None, gt=0.0)
    heartbeat_at: float | None = Field(default=None, gt=0.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    distance_m: float | None = Field(default=None, ge=0.0, le=20.0)
    lateral_m: float | None = Field(default=None, ge=-20.0, le=20.0)

    @field_validator("observed_at", "heartbeat_at", "distance_m", "lateral_m")
    @classmethod
    def finite_number(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("value must be finite")
        return value

    @model_validator(mode="after")
    def clear_requires_healthy_source(self) -> FrontObstacleObservationInput:
        if self.state == "CLEAR" and self.perception_health != "healthy":
            raise ValueError("CLEAR requires healthy perception")
        return self


class ClearFrontObstacleInput(StrictModel):
    reason: str = Field(min_length=1, max_length=160)


class FrontObstacleStateStore:
    def __init__(self, stale_after_s: float = 1.0) -> None:
        if stale_after_s <= 0:
            raise ValueError("stale_after_s must be positive")
        self.stale_after_s = stale_after_s
        self.observed_state: FrontObstacleState = "UNKNOWN"
        self.perception_health: PerceptionHealth = "unavailable"
        self.source: FrontObstacleSource | None = None
        self.observed_at: float | None = None
        self.heartbeat_at: float | None = None
        self.confidence: float | None = None
        self.distance_m: float | None = None
        self.lateral_m: float | None = None
        self.latched = False
        self.latched_at: float | None = None
        self.cleared_at: float | None = None
        self.clear_reason: str | None = None

    def observe(
        self,
        observation: FrontObstacleObservationInput,
        *,
        received_at: float | None = None,
    ) -> FrontObstacleSnapshot:
        now = received_at or time.time()
        observed_at = observation.observed_at or now
        heartbeat_at = observation.heartbeat_at or now
        if observed_at > now + 1.0 or heartbeat_at > now + 1.0:
            raise ValueError("front-obstacle timestamps cannot be in the future")
        self.observed_state = observation.state
        self.perception_health = observation.perception_health
        self.source = observation.source
        self.observed_at = observed_at
        self.heartbeat_at = heartbeat_at
        self.confidence = observation.confidence
        self.distance_m = observation.distance_m
        self.lateral_m = observation.lateral_m
        if (
            observation.state == "BLOCKED"
            and observation.perception_health == "healthy"
            and now - heartbeat_at <= self.stale_after_s
        ):
            if not self.latched:
                self.latched_at = now
            self.latched = True
            self.clear_reason = None
            self.cleared_at = None
        return self.snapshot(now)

    def clear_latch(self, reason: str, *, now: float | None = None) -> FrontObstacleSnapshot:
        checked_at = now or time.time()
        current = self.snapshot(checked_at)
        if (
            self.observed_state != "CLEAR"
            or self.perception_health != "healthy"
            or current.stale
        ):
            raise ValueError("a fresh healthy CLEAR observation is required to clear the latch")
        self.latched = False
        self.cleared_at = checked_at
        self.clear_reason = reason
        return self.snapshot(checked_at)

    def snapshot(self, now: float | None = None) -> FrontObstacleSnapshot:
        checked_at = now or time.time()
        observation_age_ms = self._age_ms(checked_at, self.observed_at)
        heartbeat_age_ms = self._age_ms(checked_at, self.heartbeat_at)
        stale = self.heartbeat_at is None or checked_at - self.heartbeat_at > self.stale_after_s
        if self.latched:
            state: FrontObstacleState = "BLOCKED"
        elif (
            not stale
            and self.perception_health == "healthy"
            and self.observed_state in ("CLEAR", "BLOCKED")
        ):
            state = self.observed_state
        else:
            state = "UNKNOWN"
        return FrontObstacleSnapshot(
            state=state,
            observed_state=self.observed_state,
            perception_health=self.perception_health,
            source=self.source,
            observed_at=self.observed_at,
            heartbeat_at=self.heartbeat_at,
            observation_age_ms=observation_age_ms,
            heartbeat_age_ms=heartbeat_age_ms,
            stale_after_ms=self.stale_after_s * 1000.0,
            stale=stale,
            confidence=self.confidence,
            distance_m=self.distance_m,
            lateral_m=self.lateral_m,
            latched=self.latched,
            latched_at=self.latched_at,
            cleared_at=self.cleared_at,
            clear_reason=self.clear_reason,
        )

    @staticmethod
    def _age_ms(now: float, timestamp: float | None) -> float | None:
        return None if timestamp is None else max(0.0, (now - timestamp) * 1000.0)
