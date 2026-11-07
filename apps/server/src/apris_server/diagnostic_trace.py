"""Bounded, observational diagnostics. Never a command replay source."""

import json
import time
import uuid
from collections import deque


class DiagnosticTrace:
    def __init__(self, *, max_bytes=180_000, max_entries=512, clock=time.monotonic):
        self.clock = clock
        self.id = uuid.uuid4().hex
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.entries = deque()
        self.bytes = self.cursor = self.dropped = 0
        self.last_sample = float('-inf')

    def record(self, kind, context, detail=None):
        self.cursor += 1
        entry = dict(cursor=self.cursor, monotonicTime=self.clock(), kind=kind,
                     context=context, detail=detail or {})
        try:
            raw = json.dumps(entry, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        except (TypeError, ValueError):
            self.dropped += 1
            return
        size = len(raw)
        if size > min(16384, self.max_bytes):
            self.dropped += 1
            return
        while self.entries and (self.bytes + size > self.max_bytes
                                or len(self.entries) >= self.max_entries):
            _, old_size = self.entries.popleft()
            self.bytes -= old_size
            self.dropped += 1
        self.entries.append((raw, size))
        self.bytes += size

    def sample_due(self):
        now = self.clock()
        if now - self.last_sample < .5:
            return False
        self.last_sample = now
        return True

    def export(self):
        return dict(schemaVersion=1, traceId=self.id, purpose='diagnostic-only',
                    clock='host-monotonic', cursor=self.cursor, dropped=self.dropped,
                    complete=self.dropped == 0,
                    entries=[json.loads(raw) for raw, _ in self.entries])
