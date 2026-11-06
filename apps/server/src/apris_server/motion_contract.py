"""Strict motion-v1 wire validation. No robot authority or adapter calls."""

from __future__ import annotations

import math
from typing import Any

SCOPE_KEYS = (
    "protocolVersion",
    "connectionEpoch",
    "requestId",
    "robotId",
    "runId",
    "activityId",
    "operationId",
)
JS_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680\u2000\u2001"
    "\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028"
    "\u2029\u202f\u205f\u3000\ufeff"
)


def _object(value: Any) -> dict:
    if type(value) is not dict:
        raise ValueError("invalid-object")
    return value


def _keys(value: dict, names: tuple | list) -> None:
    if set(value) != set(names):
        raise ValueError("invalid-fields")


def _text(value: Any, limit: int = 64) -> str:
    if (
        type(value) is not str
        or not value.strip(JS_WHITESPACE)
        or len(value.encode("utf-16-le", errors="surrogatepass")) // 2 > limit
    ):
        raise ValueError("invalid-string")
    return value


def _number(value: Any, low: float, high: float) -> float:
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError("invalid-number")
    return value


def _generation(value: Any) -> int:
    n = _number(value, 1, 2**53 - 1)
    if int(n) != n:
        raise ValueError("invalid-generation")
    return int(n)


def _goal(value: Any) -> dict:
    g = _object(value)
    if g.get("kind") == "move":
        _keys(g, ("kind", "distanceM", "speedMps"))
        distance = _number(g["distanceM"], -5, 5)
        if abs(distance) < 1e-9:
            raise ValueError("zero-distance")
        return dict(kind="move", distanceM=distance, speedMps=_number(g["speedMps"], 0.05, 0.30))
    if g.get("kind") == "turn":
        _keys(g, ("kind", "angleRad", "speedRadS"))
        angle = _number(g["angleRad"], -4 * math.pi, 4 * math.pi)
        if abs(angle * 180 / math.pi) < 1e-9:
            raise ValueError("zero-angle")
        return dict(kind="turn", angleRad=angle, speedRadS=_number(g["speedRadS"], 0.1, 1.2))
    raise ValueError("invalid-goal")


def _evidence(value: Any) -> dict:
    e = _object(value)
    kind = e.get("kind")
    if kind in ("unknown", "not-started"):
        _keys(e, ("kind",))
        return dict(kind=kind)
    if kind not in ("simulated", "physical"):
        raise ValueError("invalid-evidence")
    _keys(e, ("kind", "epoch", "observedAt"))
    return dict(
        kind=kind,
        epoch=_text(e["epoch"]),
        observedAt=_number(e["observedAt"], 0, float.fromhex("0x1.fffffffffffffp+1023")),
    )


def parse_motion_message(value: Any) -> dict:
    v = _object(value)
    if type(v.get("protocolVersion")) not in (int, float) or v["protocolVersion"] != 1:
        raise ValueError("unsupported-version")
    s = {k: _text(v.get(k)) for k in SCOPE_KEYS if k != "protocolVersion"}
    s["protocolVersion"] = 1
    kind = v.get("kind")
    if kind == "startMotion":
        _keys(v, (*SCOPE_KEYS, "kind", "goal"))
        return dict(s, kind=kind, goal=_goal(v["goal"]))
    if kind in ("renewMotion", "cancelMotion", "accepted", "running", "commandAck"):
        _keys(v, (*SCOPE_KEYS, "kind", "generation"))
        return dict(s, kind=kind, generation=_generation(v["generation"]))
    if kind == "rejected":
        _keys(v, (*SCOPE_KEYS, "kind", "reason"))
        return dict(s, kind=kind, reason=_text(v["reason"], 256))
    if kind == "terminal":
        _keys(v, (*SCOPE_KEYS, "kind", "generation", "reason", "outcome", "evidence"))
        e = _evidence(v["evidence"])
        outcome = v["outcome"]
        valid = (
            (outcome == "stop-unconfirmed" and e["kind"] == "unknown")
            or (outcome == "failed" and e["kind"] != "unknown")
            or (
                outcome in ("completed", "cancelled", "interrupted")
                and e["kind"] in ("simulated", "physical")
            )
        )
        if not valid:
            raise ValueError("invalid-outcome-evidence")
        return dict(
            s,
            kind=kind,
            generation=_generation(v["generation"]),
            reason=_text(v["reason"], 256),
            outcome=outcome,
            evidence=e,
        )
    raise ValueError("unknown-kind")
