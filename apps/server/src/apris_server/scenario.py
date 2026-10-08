from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .front_obstacle import (
    ClearFrontObstacleInput,
    FrontObstacleObservationInput,
)
from .models import (
    EventMessage,
    PerceptionEventMessage,
    PerceptionObservation,
    ScenarioEventMessage,
)
from .simulator import DifferentialDriveSimulator, SimulatorFaults
from .structured_log import StructuredLog


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ScenarioEventKind = Literal["person", "marker", "voice_intent"]


class ScenarioEventInput(StrictModel):
    kind: ScenarioEventKind
    payload: dict[str, Any] = Field(default_factory=dict)


class EventAction(StrictModel):
    at_ms: int = Field(ge=0, le=3_600_000)
    type: Literal["event"]
    kind: ScenarioEventKind
    payload: dict[str, Any] = Field(default_factory=dict)


class FaultsAction(StrictModel):
    at_ms: int = Field(ge=0, le=3_600_000)
    type: Literal["faults"]
    faults: SimulatorFaults


class ClearFaultsAction(StrictModel):
    at_ms: int = Field(ge=0, le=3_600_000)
    type: Literal["clear_faults"]


class ResetAction(StrictModel):
    at_ms: int = Field(ge=0, le=3_600_000)
    type: Literal["reset"]


class FrontObstacleAction(StrictModel):
    at_ms: int = Field(ge=0, le=3_600_000)
    type: Literal["front_obstacle"]
    observation: FrontObstacleObservationInput


class ClearFrontObstacleAction(StrictModel):
    at_ms: int = Field(ge=0, le=3_600_000)
    type: Literal["clear_front_obstacle"]
    reason: str = Field(min_length=1, max_length=160)


ScenarioAction = Annotated[
    EventAction
    | FaultsAction
    | ClearFaultsAction
    | ResetAction
    | FrontObstacleAction
    | ClearFrontObstacleAction,
    Field(discriminator="type"),
]


class ScenarioDocument(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    actions: list[ScenarioAction] = Field(min_length=1)

    @model_validator(mode="after")
    def actions_are_ordered(self) -> ScenarioDocument:
        times = [action.at_ms for action in self.actions]
        if times != sorted(times):
            raise ValueError("scenario actions must be ordered by at_ms")
        return self


class ReplayRequest(StrictModel):
    speed: float = Field(default=10.0, ge=0.1, le=100.0)


class EventBroadcaster(Protocol):
    async def broadcast(self, message: BaseModel) -> None: ...

    async def prepare_simulator_scenario(self, reason: str) -> None: ...

    async def ingest_perception(
        self, observation: PerceptionObservation
    ) -> PerceptionEventMessage: ...

    async def reset_pose_estimate(self) -> None: ...

    async def ingest_front_obstacle(self, observation: FrontObstacleObservationInput): ...

    async def clear_front_obstacle_latch(self, reason: str): ...

    async def front_obstacle_snapshot(self): ...


class ScenarioController:
    def __init__(
        self,
        runtime: EventBroadcaster,
        simulator: DifferentialDriveSimulator,
        structured_log: StructuredLog,
        scenario_directory: Path,
    ) -> None:
        self.runtime = runtime
        self.simulator = simulator
        self.log = structured_log
        self.scenarios = self._load_scenarios(scenario_directory)
        self._task: asyncio.Task[None] | None = None
        self._active_id: str | None = None
        self._active_kind: Literal["scenario", "replay"] | None = None
        self._run_id: str | None = None
        self._configured_front_obstacle: FrontObstacleObservationInput | None = None
        self._front_obstacle_heartbeat_task: asyncio.Task[None] | None = None

    @staticmethod
    def _load_scenarios(directory: Path) -> dict[str, ScenarioDocument]:
        scenarios: dict[str, ScenarioDocument] = {}
        for path in sorted(directory.glob("*.json")):
            scenario = ScenarioDocument.model_validate_json(path.read_text(encoding="utf-8"))
            if scenario.id in scenarios:
                raise ValueError(f"duplicate scenario id: {scenario.id}")
            scenarios[scenario.id] = scenario
        return scenarios

    def list_scenarios(self) -> list[dict[str, Any]]:
        return [
            {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "duration_ms": scenario.actions[-1].at_ms,
                "action_count": len(scenario.actions),
            }
            for scenario in self.scenarios.values()
        ]

    async def status(self) -> dict[str, Any]:
        return {
            "active_id": self._active_id,
            "active_kind": self._active_kind,
            "run_id": self._run_id,
            "faults": (await self.simulator.faults()).model_dump(),
            "log_session_id": self.log.session_id,
            "log_filename": self.log.filename,
            "front_obstacle": (
                await self.runtime.front_obstacle_snapshot()
            ).model_dump(mode="json"),
        }

    async def run(self, scenario_id: str) -> dict[str, Any]:
        scenario = self.scenarios.get(scenario_id)
        if scenario is None:
            raise KeyError(scenario_id)
        await self.stop("replaced by a new scenario")
        await self.runtime.prepare_simulator_scenario(f"scenario started: {scenario.id}")
        await self.simulator.clear_faults()
        self._active_id = scenario.id
        self._active_kind = "scenario"
        self._run_id = uuid.uuid4().hex[:8]
        self._task = asyncio.create_task(
            self._run_scenario(scenario, self._run_id),
            name=f"simulator-scenario-{scenario.id}",
        )
        return await self.status()

    async def _run_scenario(self, scenario: ScenarioDocument, run_id: str) -> None:
        started_at = time.monotonic()
        outcome = "completed"
        self.log.record(
            "scenario_lifecycle",
            "scenario_started",
            {"scenario_id": scenario.id, "run_id": run_id},
        )
        await self.runtime.broadcast(EventMessage(event="scenario_started", detail=scenario.id))
        try:
            for action in scenario.actions:
                delay = action.at_ms / 1000.0 - (time.monotonic() - started_at)
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._execute_action(action, scenario.id, "scenario")
        except asyncio.CancelledError:
            outcome = "stopped"
            raise
        except Exception as exc:
            outcome = "failed"
            self.log.record(
                "scenario_lifecycle",
                "scenario_failed",
                {"scenario_id": scenario.id, "run_id": run_id, "error": str(exc)},
            )
            await self.runtime.broadcast(
                EventMessage(event="scenario_failed", detail=f"{scenario.id}: {exc}")
            )
        finally:
            await self.simulator.stop()
            await self.clear_faults(source="scenario")
            if self._task is asyncio.current_task():
                self._task = None
                self._active_id = None
                self._active_kind = None
                self._run_id = None
            if outcome != "failed":
                self.log.record(
                    "scenario_lifecycle",
                    f"scenario_{outcome}",
                    {"scenario_id": scenario.id, "run_id": run_id},
                )
                await self.runtime.broadcast(
                    EventMessage(event=f"scenario_{outcome}", detail=scenario.id)
                )

    async def _execute_action(
        self,
        action: ScenarioAction,
        scenario_id: str | None,
        source: Literal["manual", "scenario", "replay"],
    ) -> None:
        if isinstance(action, EventAction):
            await self.inject_event(
                ScenarioEventInput(kind=action.kind, payload=action.payload),
                source=source,
                scenario_id=scenario_id,
            )
        elif isinstance(action, FaultsAction):
            await self.set_faults(action.faults, source=source)
        elif isinstance(action, ClearFaultsAction):
            await self.clear_faults(source=source)
        elif isinstance(action, ResetAction):
            await self.simulator.stop()
            await self.simulator.reset_pose()
            await self.simulator.clear_faults()
            await self.runtime.reset_pose_estimate()
            self.log.record("scenario_action", "simulator_reset", {"source": source})
            await self.runtime.broadcast(EventMessage(event="simulator_reset"))
        elif isinstance(action, FrontObstacleAction):
            await self.set_front_obstacle(
                action.observation,
                source=source,
            )
        elif isinstance(action, ClearFrontObstacleAction):
            await self.clear_front_obstacle(
                ClearFrontObstacleInput(reason=action.reason),
                source=source,
            )

    async def inject_event(
        self,
        event: ScenarioEventInput,
        *,
        source: Literal["manual", "scenario", "replay"] = "manual",
        scenario_id: str | None = None,
    ) -> ScenarioEventMessage | PerceptionEventMessage:
        event_id = uuid.uuid4().hex[:10]
        self.log.record(
            "scenario_event",
            event.kind,
            {
                "kind": event.kind,
                "payload": event.payload,
                "source": source,
                "scenario_id": scenario_id,
            },
        )
        if event.kind in ("person", "marker"):
            payload = dict(event.payload)
            status = payload.pop("status", "detected")
            confidence = payload.pop("confidence", 0.0 if status == "lost" else 0.95)
            return await self.runtime.ingest_perception(
                PerceptionObservation(
                    observation_id=event_id,
                    kind=event.kind,
                    status=status,
                    confidence=confidence,
                    captured_at=time.time(),
                    source=source,
                    payload=payload,
                )
            )
        message = ScenarioEventMessage(
            event_id=event_id,
            kind=event.kind,
            payload=event.payload,
            source=source,
            scenario_id=scenario_id,
        )
        await self.runtime.broadcast(message)
        return message

    async def set_faults(
        self,
        faults: SimulatorFaults,
        *,
        source: Literal["manual", "scenario", "replay"] = "manual",
    ) -> SimulatorFaults:
        await self.simulator.set_faults(faults)
        self.log.record(
            "simulator_faults",
            "faults_set",
            {"faults": faults.model_dump(), "source": source},
        )
        await self.runtime.broadcast(
            EventMessage(event="simulator_faults_set", detail=source)
        )
        return await self.simulator.faults()

    async def clear_faults(
        self,
        *,
        source: Literal["manual", "scenario", "replay"] = "manual",
    ) -> None:
        await self.simulator.clear_faults()
        self.log.record("simulator_faults_clear", "faults_cleared", {"source": source})
        await self.runtime.broadcast(
            EventMessage(event="simulator_faults_cleared", detail=source)
        )

    async def set_front_obstacle(
        self,
        observation: FrontObstacleObservationInput,
        *,
        source: Literal["manual", "scenario", "replay"] = "manual",
    ):
        applied = observation.model_copy(update={"source": source})
        self._configured_front_obstacle = applied.model_copy(
            update={"observed_at": None, "heartbeat_at": None}
        )
        snapshot = await self.runtime.ingest_front_obstacle(applied)
        if (
            self._front_obstacle_heartbeat_task is None
            or self._front_obstacle_heartbeat_task.done()
        ):
            self._front_obstacle_heartbeat_task = asyncio.create_task(
                self._front_obstacle_heartbeat_loop(),
                name="simulator-front-obstacle-heartbeat",
            )
        return snapshot

    async def _front_obstacle_heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(1.0)
                observation = self._configured_front_obstacle
                if observation is not None:
                    await self.runtime.ingest_front_obstacle(observation)
        except asyncio.CancelledError:
            raise

    async def clear_front_obstacle(
        self,
        request: ClearFrontObstacleInput,
        *,
        source: Literal["manual", "scenario", "replay"] = "manual",
    ):
        reason = f"{source}: {request.reason}"
        return await self.runtime.clear_front_obstacle_latch(reason)

    async def replay_inputs(self, speed: float = 10.0) -> dict[str, Any]:
        entries = [
            entry
            for entry in self.log.replayable_inputs()
            if self._is_original_replay_input(entry)
        ]
        if not entries:
            raise ValueError("No scenario inputs are available to replay")
        await self.stop("replaced by log replay")
        await self.runtime.prepare_simulator_scenario("log replay started")
        await self.simulator.clear_faults()
        self._active_id = "log-inputs"
        self._active_kind = "replay"
        self._run_id = uuid.uuid4().hex[:8]
        self._task = asyncio.create_task(
            self._run_replay(entries, speed, self._run_id),
            name="simulator-log-replay",
        )
        return await self.status()

    async def _run_replay(
        self,
        entries: list[dict[str, Any]],
        speed: float,
        run_id: str,
    ) -> None:
        first_elapsed = entries[0]["elapsed_ms"]
        started_at = time.monotonic()
        outcome = "completed"
        self.log.record("scenario_lifecycle", "replay_started", {"run_id": run_id})
        await self.runtime.broadcast(EventMessage(event="replay_started", detail=run_id))
        try:
            for entry in entries:
                offset = (entry["elapsed_ms"] - first_elapsed) / 1000.0 / speed
                delay = offset - (time.monotonic() - started_at)
                if delay > 0:
                    await asyncio.sleep(delay)
                data = entry["data"]
                if entry["category"] == "scenario_event":
                    await self.inject_event(
                        ScenarioEventInput(kind=data["kind"], payload=data["payload"]),
                        source="replay",
                        scenario_id=data.get("scenario_id"),
                    )
                elif entry["category"] == "perception_observation":
                    original = data["observation"]
                    await self.runtime.ingest_perception(
                        PerceptionObservation.model_validate(
                            {
                                **original,
                                "observation_id": uuid.uuid4().hex[:10],
                                "captured_at": time.time(),
                                "source": "replay",
                            }
                        )
                    )
                elif entry["category"] == "simulator_faults":
                    await self.set_faults(
                        SimulatorFaults.model_validate(data["faults"]),
                        source="replay",
                    )
                elif entry["category"] == "simulator_faults_clear":
                    await self.clear_faults(source="replay")
        except asyncio.CancelledError:
            outcome = "stopped"
            raise
        finally:
            await self.simulator.stop()
            await self.clear_faults(source="replay")
            if self._task is asyncio.current_task():
                self._task = None
                self._active_id = None
                self._active_kind = None
                self._run_id = None
            self.log.record("scenario_lifecycle", f"replay_{outcome}", {"run_id": run_id})
            await self.runtime.broadcast(EventMessage(event=f"replay_{outcome}", detail=run_id))

    @staticmethod
    def _is_original_replay_input(entry: dict[str, Any]) -> bool:
        data = entry["data"]
        if entry["category"] == "perception_observation":
            source = data.get("observation", {}).get("source")
            return source in ("camera", "recorded")
        return data.get("source") != "replay"

    async def stop(self, reason: str = "operator requested") -> bool:
        task = self._task
        if task is None or task.done() or task is asyncio.current_task():
            return False
        self.log.record("scenario_lifecycle", "run_stop_requested", {"reason": reason})
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return True

    async def close(self) -> None:
        await self.stop("server shutdown")
        if self._front_obstacle_heartbeat_task is not None:
            self._front_obstacle_heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._front_obstacle_heartbeat_task
            self._front_obstacle_heartbeat_task = None
        await self.simulator.clear_faults()
