"""Explicit, matching PC/gateway profiles for supervised low-speed trials."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IronXProfile:
    name: str = "standard"
    command_ms: int = 200
    local_command_ms: int = 300
    nonce_s: float = 0.3
    ownership_s: float = 0.3
    telemetry_ms: int = 300
    state_rpc_s: float = 0.25
    drive_rpc_s: float = 1


def load_profile():
    name = os.environ.get("APRIS_IRONX_PROFILE", "standard")
    if name == "standard":
        return IronXProfile()
    if name == "supervised_low_speed":
        return IronXProfile(name, 8000, 8000, 8, 10, 3000, 3, 3)
    raise ValueError("Unknown APRIS_IRONX_PROFILE")
