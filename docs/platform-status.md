# Platform status

[日本語](platform-status.ja.md)

iron-X documentation updated: 2026-10-31. Last iron-X physical trial: 2026-10-31.
UGV02 trial evidence below remains dated 2026-09-25.

APRISRC Kit supports participant-created services for APRISRC. It provides Simulator
development and a supported UGV02 path for the same high-level mission. The Simulator remains
the default adapter. This is Kit capability status, not challenge rules or qualification of
participants' services; see [Purpose and scope](positioning.md).

## Available now

- Simulator Playground for greeting, following and marker guidance, with real source,
  decision highlighting, repeatable marker scenes and a hands-on change/compare workshop
- Experimental live Playground for camera observations, telemetry and high-level request
  logs; greeting/following enabled with explicit supervised permission, physical marker guidance disabled
- A service mission API for `move`, `turn`, `stop`, pose, people, and markers
- Server-owned control, speed limits, command TTL, disconnect stop, and latched E-stop
- Carry assistant and Mobile Receptionist on `/app`, manual operation and monitoring on
  `/console`, and the integrated development environment on `/lab`
- Simulator demos for person reaction, approach, following, and target loss
- A marker-based Mobile Receptionist mission with three configured destinations and a
  deterministic person/intent/marker scenario; the same Service App selects Simulator or
  UGV02 behavior from the active server adapter
- In-browser person, upper-body, and APRIS marker perception
- Local keyword rules and optional LLM structured intent limited to registered missions
- JSON scenarios, fault injection, three-state front-obstacle safety, structured logs, and replay
- Simulator, UGV02 WebSocket, diagnostic factory-HTTP, and experimental iron-X local/network adapters

## Physical rover status

The reference Waveshare UGV02 runs APRIS development firmware `0.97-apris-ws-dev`.
Connection, heartbeat/telemetry, E-stop, lease/watchdog behavior, server-disconnect stop, a
bounded 15-degree turn, and a bounded 0.05 m reverse have been verified. A floor trial also
verified supervised person following using upper-body observations from a mounted smartphone
and a 30-second movement permission.

This is not certification for unattended autonomy or general environments. Keep physical
tests within the [UGV02 self-test](hardware/ugv02-self-test.md) boundary.

## Current limitations

iron-X: PC-hosted Kit and mounted-iPhone following received a successful operator
report on 2026-10-31. Subsequent trials exposed cancellation/stop-response races.
The latest stop-confirmation fix and 0.15 m/s settings need physical revalidation;
see [current operation and evidence](hardware/ironx-follow.md).

- Live Playground has software tests and disconnected UI checks only; its actual camera/rover
  flow has not been physically verified. Earlier phone-following trials used the older service flow.
- Physical marker guidance remains unverified, including the separate Service App experimental path.
- No onboard sensor continuously establishes free space ahead. `UNKNOWN` is never treated as clear.
- Carry helper grants supervised consent through **Start service and allow movement**,
  with short-lived heartbeats during approach/following. Console retains its 30-second confirmation.
- Development firmware uses plain WebSocket and a shared token on a private LAN.
- Production WSS, per-rover credentials, and persistent idempotency are not implemented.
- IMU/battery telemetry, p95 motion error, and stopping-distance qualification remain open.
- Mission state is browser-local and is not authoritative in server `/api/status`.
- Browser speech recognition and synthesis are device-dependent demo adapters.
- iron-X telemetry, supervised drive/stop/cancel, floor move/turn and console operation
  have been checked on one robot. The service trial is not full qualification;
  Live Playground and physical marker guidance remain separate unverified paths.
- LiDAR safety integration, SLAM, and path planning are not implemented.

## Current priority

1. Hand over the Simulator workshop and editable samples so others can try and develop
   services independently; use [the handoff guide](handoff.md) as the entry point.
2. Schedule and run the Challenger pilot with a first-time teacher, then remove observed
   documentation, API, UI, and error-recovery friction.
3. Finish event-ready offline distribution and device setup.
4. When hardware is available, verify the new live Playground, the Mobile Receptionist
   marker approach, remaining UGV02 stop/accuracy tests and the forward-safety sensor boundary.

See the [Development roadmap](roadmap.md) for long-term ordering and the
[Operations runbook](operations/runbook.md) for startup and recovery.
Detailed private trial histories and external integration bundles are not shipped here. Consult the hardware guides for limits and validation order.

## Verification baseline

Latest local software run (2026-10-31): 265 server tests, 130 PWA tests and PWA
typecheck passed after the stop-confirmation and 0.15 m/s changes. No new physical
motion trial or production build is claimed for this run. Earlier baselines follow.

The iron-X work passed 185 server tests, 12 targeted console/socket tests, and the
PWA production build. These are separate runs, not a claim of a full PWA regression
or all-device validation. Console operation was also confirmed by the operator.

The live Playground implementation passed 122 PWA tests and the production build, plus
disconnected desktop/mobile UI checks. This is software evidence, not a physical trial.
