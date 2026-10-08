#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "server" / "src"))

from apris_server.rover_protocol import rover_wire_message_adapter  # noqa: E402


def schema() -> dict[str, object]:
    payload = rover_wire_message_adapter.json_schema()
    payload["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    payload["$id"] = "https://apris.example/schema/rover-protocol-v1.json"
    payload["title"] = "APRIS Rover WebSocket protocol v1"
    return payload


def main() -> None:
    destination = REPOSITORY_ROOT / "packages" / "protocol" / "rover-v1.schema.json"
    destination.write_text(
        json.dumps(schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

