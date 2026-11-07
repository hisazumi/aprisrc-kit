"""Small simulator route capability using the existing bounded motion authority."""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .course_map import Contract, Identifier
from .localization_geometry import angle
from .route_plan import RouteProfile, feedback_duration, prepare_route, segment_distance

if TYPE_CHECKING:
    from .runner_port_experiment import RunnerPort


class RouteRequest(Contract):
    controlEpoch: Identifier
    runId: Identifier
    runEpoch: Identifier
    requestId: Identifier
    method: Literal["route", "place"]
    targetId: Identifier


def demo_route_profile():
    return RouteProfile.model_validate_json(
        (
            Path(__file__).resolve().parents[2] / "scenarios/localization/route-profile.json"
        ).read_bytes()
    )


class RouteExecution:
    def __init__(self, port: RunnerPort, profile: RouteProfile):
        self.port, self.profile = port, profile
        self.job = None
        self.task: asyncio.Task | None = None
        self.records: dict[str, tuple[RouteRequest, dict | str]] = {}
        self._key = object()
        self._last_transform = None

    @property
    def active(self):
        return self.task is not None and not self.task.done()

    def snapshot(self):
        return dict(self.job) if self.job else None

    def _pose(self):
        loc = self.port.localization
        if loc is None:
            raise ValueError("localization-required")
        loc.require_ready()
        snapshot = loc.estimator.snapshot()
        if self.job and snapshot.localizationEpoch != self.job["localizationEpoch"]:
            raise ValueError("localization-epoch-changed")
        quality = snapshot.quality
        if (
            quality.status != "tracking"
            or quality.positionErrorM is None
            or quality.headingErrorRad is None
            or quality.positionErrorM > self.profile.maxPositionErrorM
            or quality.headingErrorRad > self.profile.maxHeadingErrorRad
        ):
            raise ValueError("route-quality-insufficient")
        return snapshot

    def start(self, value):
        request = RouteRequest.model_validate(value)
        if request.controlEpoch != self.port.control_epoch:
            raise ValueError("stale-control-epoch")
        if request.requestId in self.records:
            old, job = self.records[request.requestId]
            if old != request:
                raise ValueError("id-conflict")
            if isinstance(job, str):
                raise ValueError(job)
            return dict(job)  # Historical result only, no restart.
        if len(self.records) >= 32:
            raise ValueError("route-record-capacity")
        try:
            return self._start(request)
        except ValueError as error:
            self.records[request.requestId] = (request, str(error))
            raise

    def _start(self, request):
        if self.active:
            raise ValueError("route-busy")
        self.port._control_run(request.model_dump())
        if self.port.inhibited or self.port.guard:
            raise ValueError("motion-inhibited")
        self.port._stationary_evidence()
        loc = self.port.localization
        if loc is None or loc.binding is None:
            raise ValueError("localized-run-required")
        # Ignore previous completed job when evaluating a fresh start.
        previous = self.job
        self.job = None
        try:
            snapshot = self._pose()
            plan = prepare_route(loc.store.active, request.method, request.targetId, self.profile)
            p = snapshot.mapPose
            if (
                math.hypot(p.xM - plan.points[0].xM, p.yM - plan.points[0].yM)
                + snapshot.quality.positionErrorM
                > self.profile.arrivalM
            ):
                raise ValueError("not-at-route-start")
            config = self.port.runtime.config
            move_time = feedback_duration(
                self.profile.maxStepM,
                config.move_tolerance_m,
                0.04,
                1.4,
                min(self.profile.speedMps, config.max_vx),
            )
            turn_time = feedback_duration(
                self.profile.maxTurnRad,
                config.turn_tolerance_rad,
                0.1,
                1.6,
                min(self.profile.turnSpeedRadS, config.max_wz),
            )
            if max(move_time, turn_time) + 2 / config.motion_hz >= self.port.progress_s:
                raise ValueError("motion-budget-too-short")
        except Exception:
            self.job = previous
            raise
        self.plan, self.request = plan, request
        self.job = dict(
            id=uuid.uuid4().hex,
            routeId=plan.route_id,
            runEpoch=request.runEpoch,
            runId=request.runId,
            localizationEpoch=snapshot.localizationEpoch,
            map=snapshot.map.model_dump(mode="json"),
            profile=self.profile.id,
            status="running",
            reason="",
            waypoint=1,
            actions=0,
        )
        self.records[request.requestId] = (request, self.job)
        self.deadline = time.monotonic() + self.profile.deadlineS
        self._last_transform = snapshot.mapFromOdom
        self.stop_reason = None
        self.stop_status = None
        self.task = asyncio.create_task(self._run(), name="registered-route")
        self.port.record_trace("routeStarted", dict(self.job))
        return dict(self.job)

    def revoked(self, reason):
        if self.active and not self.stop_reason:
            self.stop_reason = reason
            self.stop_status = "interrupted"

    def abort(self, reason, status="failed"):
        if not self.active or self.stop_reason:
            return
        self.stop_reason, self.stop_status = reason, status
        self.port.inhibited = True
        self.port._revoke(reason)

    def cancel(self, value):
        if (
            set(value) != {"id", "runEpoch"}
            or not self.active
            or value["id"] != self.job["id"]
            or value["runEpoch"] != self.job["runEpoch"]
        ):
            raise ValueError("stale-route")
        self.abort("route-cancelled", "cancelled")
        return dict(self.job)

    def check(self):
        if not self.active or self.stop_reason:
            return
        try:
            if self.port.session != self.request.runEpoch:
                raise ValueError("run-revoked")
            if time.monotonic() >= self.deadline:
                raise ValueError("route-deadline")
            snap = self._pose()
            transform = snap.mapFromOdom
            previous = self._last_transform
            if (
                math.hypot(transform.xM - previous.xM, transform.yM - previous.yM)
                > self.profile.maxCorrectionM
                or abs(angle(transform.yawRad - previous.yawRad)) > self.profile.maxCorrectionRad
            ):
                raise ValueError("route-large-correction")
            self._last_transform = transform
            index = self.job["waypoint"]
            a, b = self.plan.points[index - 1 : index + 1]
            p = snap.mapPose
            if segment_distance(p.xM, p.yM, a.xM, a.yM, b.xM, b.yM) > self.plan.clearance:
                raise ValueError("route-deviation")
        except ValueError as error:
            self.abort(str(error))

    async def _command(self, goal):
        self.check()
        if self.stop_reason:
            raise ValueError(self.stop_reason)
        if self.job["actions"] >= self.profile.maxActions:
            raise ValueError("route-action-budget")
        self.job["actions"] += 1
        operation = uuid.uuid4().hex
        scope = dict(
            protocolVersion=1,
            connectionEpoch=self.request.runEpoch,
            requestId=uuid.uuid4().hex,
            robotId="fake-only",
            runId=self.request.runId,
            activityId=self.job["id"],
            operationId=operation,
        )
        async with self.port.lock:
            self.port._expire(time.monotonic())
            if self.stop_reason:
                raise ValueError(self.stop_reason)
            self.port.record_trace("routeAction", dict(operationId=operation, goal=goal))
            accepted = await self.port._motion(
                dict(scope, kind="startMotion", goal=goal), route_key=self._key
            )
        if accepted["kind"] != "accepted":
            raise ValueError(accepted.get("reason", "motion-rejected"))
        last_renew = time.monotonic()
        while True:
            await asyncio.sleep(0.02)
            self.check()
            record = self.port.motion_records.get(operation, {}).get("result", {})
            if record.get("kind") == "terminal":
                if record["outcome"] != "completed" or record["evidence"]["kind"] != "simulated":
                    raise ValueError(record["outcome"])
                return
            if self.stop_reason:
                raise ValueError(self.stop_reason)
            if time.monotonic() - last_renew >= 0.15:
                async with self.port.lock:
                    self.port._expire(time.monotonic())
                    if self.stop_reason:
                        raise ValueError(self.stop_reason)
                    # The same lock excludes completion while issuing a renewal.
                    record = self.port.motion_records.get(operation, {}).get("result", {})
                    if record.get("kind") == "terminal":
                        continue
                    await self.port._motion(
                        dict(
                            scope,
                            kind="renewMotion",
                            requestId=uuid.uuid4().hex,
                            generation=accepted["generation"],
                        ),
                        route_key=self._key,
                    )
                last_renew = time.monotonic()

    async def _run(self):
        try:
            while True:
                self.check()
                if self.stop_reason:
                    raise ValueError(self.stop_reason)
                snap = self._pose()
                p = snap.mapPose
                i = self.job["waypoint"]
                target = self.plan.points[i]
                distance = math.hypot(target.xM - p.xM, target.yM - p.yM)
                reached = distance + snap.quality.positionErrorM <= self.profile.arrivalM
                if reached and i < len(self.plan.points) - 1:
                    self.job["waypoint"] += 1
                    continue
                desired = (
                    self.plan.destination.yawRad
                    if reached
                    else math.atan2(target.yM - p.yM, target.xM - p.xM)
                )
                heading = angle(desired - p.yawRad)
                if (
                    reached
                    and abs(heading) + snap.quality.headingErrorRad
                    <= self.profile.arrivalHeadingRad
                ):
                    self.check()
                    if self.stop_reason:
                        raise ValueError(self.stop_reason)
                    self.port._stationary_evidence()
                    self.job.update(status="completed", reason="route-arrived")
                    return
                if abs(heading) > self.profile.headingToleranceRad or reached:
                    turn = max(-self.profile.maxTurnRad, min(self.profile.maxTurnRad, heading))
                    await self._command(
                        dict(kind="turn", angleRad=turn, speedRadS=self.profile.turnSpeedRadS)
                    )
                else:
                    await self._command(
                        dict(
                            kind="move",
                            distanceM=min(distance, self.profile.maxStepM),
                            speedMps=self.profile.speedMps,
                        )
                    )
        except asyncio.CancelledError:
            self.abort("route-task-cancelled", "interrupted")
        except Exception as error:
            self.abort(str(error)[:128])
        finally:
            if self.job["status"] != "completed":
                # Revoke has already fenced new motion. Join stop evidence with a real deadline.
                deadline = time.monotonic() + self.port.stop_s + 0.1
                while (self.port.operation or self.port.io_tasks) and time.monotonic() < deadline:  # noqa: ASYNC110 - bounded stop join
                    await asyncio.sleep(0.01)
                unconfirmed = any(
                    record.get("result", {}).get("activityId") == self.job["id"]
                    and record["result"].get("outcome") == "stop-unconfirmed"
                    for record in self.port.motion_records.values()
                )
                confirmed = (
                    not unconfirmed
                    and not self.port.operation
                    and not self.port.io_tasks
                    and not self.port.adapter.actuating
                    and self.port.adapter.evidence.is_set()
                )
                self.job.update(
                    status=self.stop_status if confirmed else "stop-unconfirmed",
                    reason=self.stop_reason or "route-failed",
                )
                if not confirmed:
                    self.port.inhibited = True
            self.port.emit(dict(kind="routeTerminal", **self.job))

    async def close(self):
        if self.active:
            self.abort("route-host-closed", "interrupted")
            await asyncio.wait({self.task}, timeout=self.port.stop_s + 0.2)
