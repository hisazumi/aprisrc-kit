from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_status(base_url: str, timeout_s: float) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}/api/status",
        headers={"Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - operator-selected URL
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("APRIS status response must be a JSON object")
    return payload


def _summary(status: dict[str, Any]) -> str:
    server = status.get("server", {})
    adapter = status.get("adapter", {})
    control = status.get("control", {})
    clients = status.get("clients", [])
    loops = status.get("loops", {})
    unhealthy_loops = [name for name, health in loops.items() if not health.get("healthy")]
    return "\n".join(
        [
            f"status: {status.get('status', 'unknown')}",
            f"instance: {server.get('instance_id', 'unknown')}",
            f"profile: {server.get('deployment_profile', 'unknown')}",
            f"adapter: {adapter.get('type', 'unknown')} "
            f"({'healthy' if adapter.get('healthy') else 'unhealthy'})",
            f"clients: {len(clients)}",
            f"control owner: {control.get('owner_client_id') or 'none'}",
            f"E-stop: {'latched' if control.get('estop_latched') else 'clear'}",
            f"unhealthy loops: {', '.join(unhealthy_loops) if unhealthy_loops else 'none'}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect an APRIS Server runtime snapshot")
    parser.add_argument("--url", default="http://localhost:8000", help="APRIS Server base URL")
    parser.add_argument("--timeout", type=float, default=2.0, help="HTTP timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print the full status as JSON")
    args = parser.parse_args(argv)

    try:
        status = fetch_status(args.url, args.timeout)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"apris-doctor: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_summary(status))
    return 0 if status.get("ready") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
