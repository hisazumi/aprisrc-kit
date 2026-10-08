from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from .models import RoverState


@dataclass(frozen=True, slots=True)
class BoundedMotionGoal:
    motion_id: str
    kind: Literal["linear", "rotate"]
    distance_m: float | None
    angle_rad: float | None
    max_linear_speed_mps: float
    max_angular_speed_rad_s: float
    max_duration_ms: int
    run_id: str | None = None
    effect_id: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class BoundedMotionResult:
    motion_id: str
    status: Literal["completed", "cancelled", "failed"]
    reason: str | None


class BoundedMotionExecutionError(RuntimeError):
    def __init__(self, result: BoundedMotionResult) -> None:
        super().__init__(result.reason or result.status)
        self.result = result


class RoverAdapter(ABC):
    """Hardware-independent boundary used by the Local Server."""

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def drive(self, vx: float, vy: float, wz: float, *, ttl_ms: int = 500) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    async def emergency_stop(self, reason: str) -> None:
        del reason
        await self.stop()

    async def clear_emergency_stop(self) -> None:
        return None

    @abstractmethod
    async def reset_pose(self) -> None:
        pass

    @abstractmethod
    async def state(self, command_age_ms: float | None = None) -> RoverState:
        pass


class DeviceBoundedMotionAdapter(RoverAdapter):
    """Adapter whose firmware executes one bounded motion using local feedback."""

    @abstractmethod
    async def execute_bounded_motion(self, goal: BoundedMotionGoal) -> BoundedMotionResult:
        pass
