"""Opt-in simulator localization gate; all motor effects stay in the shared runtime."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .course_map import MapBinding, MapStore, PlanarPose
from .localization import Localization, LocalizationProfile, OdometrySample, SourceSession
from .localization_contract import LocalizationScope, MarkerObservation

if TYPE_CHECKING:
    from .runner_port_experiment import RunnerPort


@dataclass(frozen=True)
class LocalizationSetup:
    map_bytes: bytes
    profile: LocalizationProfile


def demo_localization() -> LocalizationSetup:
    root = Path(__file__).resolve().parents[2]
    return LocalizationSetup(
        (root / "config/maps/demo-room.json").read_bytes(),
        LocalizationProfile.model_validate_json(
            (root / "scenarios/localization/profile.json").read_bytes()
        ),
    )


class RuntimeLocalization:
    # Read timeout and feed liveness are real-time budgets for this synthetic profile.
    read_timeout_s = 0.15
    feed_timeout_s = 0.25
    period_s = 0.02

    def __init__(self, port: RunnerPort, setup: LocalizationSetup):
        self.port = port
        self.profile = setup.profile
        self.store = MapStore()
        self.store.activate(setup.map_bytes, stopped=True)  # Data loading, not runtime permission.
        self.epoch = uuid.uuid4().hex
        self.clock_epoch = uuid.uuid4().hex
        self.source_epoch = uuid.uuid4().hex
        self.estimator: Localization | None = None
        self.last_sample: OdometrySample | None = None
        self.last_state = None
        self.binding: MapBinding | None = None
        self.reason = "initialization-required"
        self._hold = port.runtime.motion_interlock.hold("localization-required")
        self._tripped = False
        self._sequence = 0
        self._last_feed = time.monotonic()
        self._last_ingested: float | None = None
        self.task: asyncio.Task | None = None
        self.watch_task: asyncio.Task | None = None

    @property
    def blocked(self) -> bool:
        return self._hold is not None

    def start(self) -> None:
        self.task = asyncio.create_task(self._feed(), name="localization-feed")
        self.watch_task = asyncio.create_task(self._watch(), name="localization-watch")

    def fail(self, reason: str) -> None:
        if not self.blocked:
            self._hold = self.port.runtime.motion_interlock.hold("localization-quality")
        if not self._tripped:
            self.reason = reason
            self._tripped = True
            # No awaits: gate/revoke happen before any subsequent movement admission.
            self.port.inhibited = True
            owner = self.port.runtime.owner_client_id
            client = self.port.client
            self.port._revoke("localization-" + reason)
            if owner is not None and owner != client:
                self.port._start_io(self.port.runtime.remove_client(owner))
            elif owner is None and self.port.adapter.actuating:
                self.port._start_io(self.port.runtime._stop_adapter("localization-" + reason))
            self.port.emit({"kind": "localizationLost", "reason": reason})

    def check(self) -> None:
        if self.blocked:
            self.fail(self.reason)
            return
        if self.task is None or self.task.done():
            self.fail("monitor-unavailable")
            return
        if time.monotonic() - self._last_feed > self.feed_timeout_s:
            self.fail("feed-stale")
            return
        try:
            snapshot = self.estimator.snapshot()
            if snapshot.quality.status != "tracking":
                self.fail(
                    snapshot.quality.reasons[0] if snapshot.quality.reasons else "quality-low"
                )
        except (ValueError, AttributeError):
            self.fail("estimate-unavailable")

    def require_ready(self) -> None:
        self.check()
        if self.blocked:
            raise ValueError("localization-" + self.reason)

    async def _watch(self) -> None:
        # Independent of port.lock and adapter I/O. check/fail are synchronous fences;
        # runtime interlock epochs reject effects admitted before this fence.
        try:
            while True:
                await asyncio.sleep(0.01)
                self.check()
        finally:
            self.fail("monitor-closed")

    async def _feed(self) -> None:
        try:
            while True:
                try:
                    state, stamp, epoch = await asyncio.wait_for(
                        self.port.adapter.localization_state(), timeout=self.read_timeout_s
                    )
                    now = time.monotonic()
                    health = state.pose_quality
                    sensor = (
                        "unavailable"
                        if not state.connected or health.encoder_status != "ok"
                        else "degraded"
                        if health.imu_status != "ok"
                        else "ok"
                    )
                    self._sequence += 1
                    sample = OdometrySample(
                        robotId="fake-only",
                        controlEpoch=self.port.control_epoch,
                        odomEpoch=epoch,
                        clockId="host-monotonic",
                        clockEpoch=self.clock_epoch,
                        receivedTime=now,
                        sampleTime=stamp,
                        sequence=self._sequence,
                        pose=PlanarPose(xM=state.pose.x, yM=state.pose.y, yawRad=state.pose.yaw),
                        sensorStatus=sensor,
                        provenance="simulated",
                    )
                    async with self.port.lock:
                        self.last_sample = sample
                        self.last_state = state
                        self._last_feed = now
                        if self.estimator is not None:
                            if epoch != self.estimator.scope.odomEpoch:
                                self.fail("odometry-epoch-changed")
                            elif self._last_ingested is None or stamp > self._last_ingested:
                                self.estimator.add_odometry(sample)
                                self._last_ingested = stamp
                            # Equal/older frames never refresh estimator timestamps.
                        self.check()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    async with self.port.lock:
                        self.fail(
                            "read-timeout" if isinstance(error, TimeoutError) else "feed-error"
                        )
                await asyncio.sleep(self.period_s)
        finally:
            # Keep the hold even when closed or unexpectedly cancelled.
            async with self.port.lock:
                self.fail("monitor-closed")

    def initialize(self, candidate_id: str, expected_epoch: str) -> None:
        if expected_epoch != self.epoch:
            raise ValueError("stale-localization-epoch")
        if self.port.session or self.port.guard or self.port.runtime.owner_client_id:
            raise ValueError("localization-busy")
        self.port._stationary_evidence()
        sample = self.last_sample
        if (
            sample is None
            or time.monotonic() - sample.sampleTime > self.profile.maxOdomAgeS
            or sample.sensorStatus != "ok"
            or self.task is None
            or self.task.done()
            or time.monotonic() - self._last_feed > self.feed_timeout_s
        ):
            raise ValueError("fresh-healthy-odometry-required")
        # Reject a reset occurring after the last poll, even at an identical pose.
        if sample.odomEpoch != self.port.adapter.odometry_epoch:
            raise ValueError("odometry-epoch-changed")
        if (
            self.estimator is not None
            and self.estimator.requires_reset
            and sample.odomEpoch == self.estimator.scope.odomEpoch
        ):
            raise ValueError("odometry-reset-required")
        new_epoch = uuid.uuid4().hex
        scope = LocalizationScope(
            robotId="fake-only",
            controlEpoch=self.port.control_epoch,
            odomEpoch=sample.odomEpoch,
            localizationEpoch=new_epoch,
            map=self.store.active.identity,
            robotProfile="planar-simulator-v1",
            calibration="synthetic-base-v1",
            qualityProfile=self.profile.id,
        )
        candidate = Localization(
            self.store.active,
            scope,
            self.profile,
            clock=time.monotonic,
            clock_id="host-monotonic",
            clock_epoch=self.clock_epoch,
            provenance="simulated",
            sources=(SourceSession(sourceId="simulator-marker", sessionEpoch=self.source_epoch),),
        )
        candidate.add_odometry(sample)
        candidate.initialize_placement(candidate_id, stopped=True)
        if candidate.snapshot().quality.status != "tracking":
            raise ValueError("initial-quality-insufficient")
        self.estimator, self.epoch = candidate, new_epoch
        self._last_ingested = sample.sampleTime
        self.store.relocalized(new_epoch, stopped=True)
        self.port.inhibited = True
        self.reason, self._tripped = "", False
        if self._hold is not None:
            self.port.runtime.motion_interlock.release(self._hold)
            self._hold = None
        # Port inhibit, handover, estop and old runs are not cleared by localization.

    def bind(self, session: str) -> None:
        self.require_ready()
        scope = self.estimator.scope
        self.binding = self.store.bind(
            session,
            robot_profile=scope.robotProfile,
            calibration=scope.calibration,
            quality_profile=scope.qualityProfile,
        )

    def release(self) -> None:
        if self.binding:
            self.store.release(self.binding.runId)
            self.binding = None

    def observation(self, value: dict) -> dict:
        self.check()
        if self.blocked or self.estimator is None:
            raise ValueError("explicit-localization-required")
        obs = MarkerObservation.model_validate(value)
        result = self.estimator.correct(obs)
        self.check()
        return result.model_dump(mode="json")

    def snapshot(self) -> dict:
        self.check()
        state = None
        if self.estimator is not None:
            try:
                state = self.estimator.snapshot().model_dump(mode="json")
            except ValueError:
                pass
        return dict(
            enabled=True,
            blocked=self.blocked,
            reason=self.reason,
            localizationEpoch=self.epoch,
            sourceEpoch=self.source_epoch,
            sampleAvailable=self.last_sample is not None,
            snapshot=state,
            map=self.store.active.identity.model_dump(mode="json"),
            binding=self.binding.model_dump(mode="json") if self.binding else None,
        )

    async def close(self) -> None:
        if self.watch_task:
            self.watch_task.cancel()
            done, _ = await asyncio.wait({self.watch_task}, timeout=0.2)
            for task in done:
                if not task.cancelled():
                    task.exception()
        if self.task:
            self.task.cancel()
            done, _ = await asyncio.wait({self.task}, timeout=0.2)
            for task in done:
                if not task.cancelled():
                    task.exception()
        self.fail("monitor-closed")
