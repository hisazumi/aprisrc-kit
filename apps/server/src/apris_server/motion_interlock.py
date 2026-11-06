"""Event-loop-local inhibition shared by every motion entrypoint of a runtime.

Tokens are private server handles, not authorization credentials or physical stop evidence.
"""

from contextlib import contextmanager
from uuid import uuid4


class MotionInterlock:
    def __init__(self) -> None:
        self.epoch = 0
        self.pending_effects = 0
        self._holds: dict[str, str] = {}

    @property
    def blocked(self) -> bool:
        return bool(self._holds)

    def hold(self, reason: str) -> str:
        token = uuid4().hex
        self._holds[token] = reason
        self.epoch += 1
        return token

    def release(self, token: str) -> None:
        if token not in self._holds:
            raise ValueError("stale-interlock-token")
        del self._holds[token]
        self.epoch += 1  # Requests predating a hold remain fenced after its release.

    def require(self, epoch: int, *, own_effect: bool = False) -> None:
        if self.blocked or epoch != self.epoch or (self.pending_effects and not own_effect):
            raise RuntimeError("motion_inhibited: held or stale interlock epoch")

    @contextmanager
    def effect(self, epoch: int):
        self.require(epoch)
        self.pending_effects += 1
        try:
            yield
        finally:
            self.pending_effects -= 1

    def snapshot(self) -> dict:
        return {
            "blocked": self.blocked,
            "epoch": self.epoch,
            "pending_effects": self.pending_effects,
            "reasons": sorted(self._holds.values()),
        }
