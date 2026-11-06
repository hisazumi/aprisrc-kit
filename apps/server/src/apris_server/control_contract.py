"""Control-v1 contracts for the trusted local runner-port experiment."""

from __future__ import annotations

from typing import Any

from .motion_contract import _generation, _keys, _object, _text

CONTROL_FIELDS = {
    "openOperator": (),
    "globalStop": (),
    "snapshot": (),
    "operatorHeartbeat": ("operatorId", "sequence"),
    "openRun": ("operatorId", "runId"),
    "closeRun": ("runId", "runEpoch"),
    "runnerHeartbeat": ("runId", "runEpoch", "sequence"),
    "acquireHandover": ("runId", "runEpoch"),
    "clearHandover": ("operatorId", "guardId", "confirmed"),
    "recover": ("operatorId", "guardId", "confirmed"),
}
BASE = ("protocolVersion", "connectionEpoch", "requestId", "robotId", "kind")


def parse_control_message(value: Any) -> dict:
    m = _object(value)
    if type(m.get("protocolVersion")) not in (int, float) or m["protocolVersion"] != 1:
        raise ValueError("unsupported-version")
    s = {k: _text(m.get(k)) for k in BASE if k not in ("protocolVersion", "kind")}
    s["protocolVersion"] = 1
    kind = _text(m.get("kind"))
    if kind == "controlReply":
        fields = (
            "command",
            "operatorId",
            "runId",
            "runEpoch",
            "guardId",
            "inhibited",
            "stopPending",
        )
        _keys(m, (*BASE, *fields))
        if type(m["command"]) is not str or m["command"] not in CONTROL_FIELDS:
            raise ValueError("invalid-command")
        s.update(kind=kind, command=m["command"])
        for key in ("operatorId", "runId", "runEpoch", "guardId"):
            s[key] = None if m[key] is None else _text(m[key])
        if (s["runId"] is None) != (s["runEpoch"] is None):
            raise ValueError("invalid-run-state")
        for key in ("inhibited", "stopPending"):
            if type(m[key]) is not bool:
                raise ValueError("invalid-boolean")
            s[key] = m[key]
        return s
    if kind not in CONTROL_FIELDS:
        raise ValueError("unknown-kind")
    _keys(m, (*BASE, *CONTROL_FIELDS[kind]))
    s["kind"] = kind
    for key in CONTROL_FIELDS[kind]:
        if key == "confirmed":
            if m[key] is not True:
                raise ValueError("clearance-required")
            s[key] = True
        elif key == "sequence":
            s[key] = _generation(m[key])
        elif key == "guardId" and kind == "recover" and m[key] is None:
            s[key] = None
        else:
            s[key] = _text(m[key])
    return s
