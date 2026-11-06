"""Planar simulator bridge; stop evidence is simulated, never physical."""

import asyncio
import math
import time

from .simulator import DifferentialDriveSimulator


class PortSimulatorAdapter(DifferentialDriveSimulator):
    """Use runtime odometry feedback rather than a synthetic bounded-motion timer."""

    def __init__(self) -> None:
        super().__init__()
        self.evidence = asyncio.Event()
        self.evidence.set()
        self.evidence_at = time.monotonic()

    @property
    def actuating(self) -> bool:
        return self._vx != 0.0 or self._wz != 0.0

    async def drive(self, vx: float, vy: float, wz: float, *, ttl_ms: int = 500) -> None:
        self.evidence.clear()
        self.evidence_at = math.inf
        await super().drive(vx, vy, wz, ttl_ms=ttl_ms)

    async def stop(self) -> None:
        # Simulator.stop integrates the last interval and zeroes velocity under its lock.
        await super().stop()
        self.evidence_at = time.monotonic()
        self.evidence.set()
