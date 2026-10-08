from __future__ import annotations

import json
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any


class StructuredLog:
    """Bounded in-memory log mirrored to a JSON Lines session file."""

    def __init__(self, directory: Path, max_entries: int = 10_000) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.filename = f"session-{self.session_id}.jsonl"
        self.path = self.directory / self.filename
        self._started_at = time.monotonic()
        self._sequence = 0
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._last_success_at: float | None = None
        self._last_error: str | None = None
        self._file = self.path.open("a", encoding="utf-8")
        self.record("lifecycle", "session_started", {"session_id": self.session_id})

    def record(
        self,
        category: str,
        name: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._sequence += 1
        entry = {
            "seq": self._sequence,
            "session_id": self.session_id,
            "timestamp": time.time(),
            "elapsed_ms": round((time.monotonic() - self._started_at) * 1000.0, 3),
            "category": category,
            "name": name,
            "data": data or {},
        }
        self._entries.append(entry)
        try:
            self._file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._file.flush()
        except OSError as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            raise
        self._last_success_at = time.time()
        return entry

    def health(self) -> dict[str, Any]:
        healthy = not self._file.closed and self._last_error is None
        return {
            "enabled": True,
            "healthy": healthy,
            "session_id": self.session_id,
            "filename": self.filename,
            "directory": str(self.directory),
            "last_success_at": self._last_success_at,
            "error": self._last_error,
        }

    def recent(self, limit: int = 100, *, include_state: bool = False) -> list[dict[str, Any]]:
        entries = list(self._entries)
        if not include_state:
            entries = [entry for entry in entries if entry["category"] != "state"]
        return entries[-limit:]

    def replayable_inputs(self) -> list[dict[str, Any]]:
        replayable = {
            "scenario_event",
            "perception_observation",
            "simulator_faults",
            "simulator_faults_clear",
        }
        return [entry for entry in self._entries if entry["category"] in replayable]

    def clear_memory(self) -> None:
        self._entries.clear()
        self.record("lifecycle", "memory_log_cleared")

    def close(self) -> None:
        if self._file.closed:
            return
        self.record("lifecycle", "session_stopped")
        self._file.close()
