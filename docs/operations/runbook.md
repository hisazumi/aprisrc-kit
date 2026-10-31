# Operations runbook

This is the minimum recovery path for development operation. The runtime snapshot and doctor command are authoritative for process readiness; Simulator controls remain development-only.

## Start development services

From the APRIS repository:

```bash
npm install
uv sync --directory apps/server --dev
npm run dev
```

Expected endpoints are `http://localhost:8000` for FastAPI and `http://localhost:5173` for Vite, or HTTPS when local certificates are installed. `/api/livez` reports process liveness and `/api/readyz` reports motion readiness.

The default adapter is Simulator. To start the device-initiated Rover mode for fake-rover
development, provide an explicit target and credential:

```bash
APRIS_ADAPTER=websocket_rover \
APRIS_ROVER_ID=ugv02-demo-1 \
APRIS_ROVER_TOKEN='<provisioned development token>' \
npm run dev
```

Before the rover connects, `/api/livez` remains alive but `/api/readyz` must return 503.
After connection, verify `/api/status.server.adapter_type`, the selected rover ID/epoch,
`heartbeat_healthy`, `clock_healthy`, telemetry age and firmware safety limits. Simulator
scenario/fault/manual-obstacle endpoints intentionally return 409 in this mode. Do not
put the token in a URL, shell history committed to the repository, log, or diagnostic bundle.

## Start unmodified UGV02 over factory Wi-Fi HTTP

Read the current private STA address from the OLED, raise the wheels, keep the physical
power switch within immediate reach, and start the diagnostic adapter:

```bash
APRIS_ADAPTER=factory_http \
APRIS_FACTORY_HTTP_HOST='<OLED STA IP>' \
npm run dev
```

Startup succeeds only after two zero-speed commands and valid `T=130` feedback. Confirm
`/api/readyz` is 200 and `/api/status.adapter.type` is `factory_http`, then use the
dead-man joystick at `/console`. The adapter converts velocity to factory `T=1` wheel
commands, preserves curvature while limiting both wheels to `0.08 m/s`, and locally
expires each command after at most 800 ms. It redundantly sends zero speed after expiry,
on control release, on disconnect, on E-stop and during shutdown.

The console applies an 8% radial joystick dead zone with per-axis snapping and refreshes
held commands every 200 ms. The adapter treats those messages as local dead-man lease
refreshes, sends a changed wheel target immediately, and coalesces an unchanged target to
one factory `T=1` request per second. Factory feedback is polled every 500 ms. These
conservative rates reduce request contention on the v0.96 HTTP endpoint; local command
expiry and joystick release still send stop immediately. Per-axis snapping ensures a
horizontal turn has exactly zero forward velocity, so sub-pixel pointer offsets do not
trigger the fail-closed forward guard.

The Console motion trace retains the last 12 seconds of commanded and observed linear and
angular velocity. Use it during raised-wheel checks to distinguish an APRIS stop from a
factory-feedback dropout. Factory observations update only on `T=130` polls and are
diagnostic rather than qualified ground truth.

Do not interpret a jagged observed line alone as motor pulsing. Raised-wheel comparison
found that `T=130` can alternate between zero, doubled angular velocity and asymmetric
linear velocity during a steady in-place turn. Correlate the trace with direct observation
or an independent wheel measurement before changing command timing again.

This is a diagnostic path, not the production Rover protocol. Automatic `move` and
`turn` fail with `factory_http_manual_control_only`. Battery percentage is intentionally
unavailable because the factory endpoint reports voltage but no qualified state-of-charge
mapping. Forward joystick input is also rejected while front-obstacle state is `UNKNOWN`;
do not bypass that fail-closed rule with Simulator-only endpoints. Initial tests can use
reverse and in-place rotation with the wheels raised. The factory firmware's own watchdog
and physical power removal remain the final fallbacks.

`factory_http` is rejected for hosted deployment and accepts only a private or loopback
IPv4 address. The current DHCP address is operational input and must not be committed.

## Stop

Stop the active mission first, then the foreground `npm run dev` process with Ctrl-C.
Confirm reported zero motion and, for hardware, observe the wheels stop. Physical power
removal remains the fallback. Existing firmware stop trials are recorded in the
[firmware guide](../hardware/ugv02-websocket-firmware.md); broader hardware qualification
remains incomplete. New Live Playground trials follow their own explicit permission procedure.

## Collect status and logs

Collect the authoritative runtime snapshot first:

```bash
uv run --directory apps/server apris-doctor --json
```

Then collect repository state:

```bash
git status --short
git rev-parse --short HEAD
```

The snapshot includes active URLs only indirectly; also record the URL used and the newest JSONL log under the reported log directory. Do not include credentials in an issue or diagnostic archive.

Before Simulator forward-motion tests, inspect `/api/status.front_obstacle`. Startup is
intentionally `UNKNOWN`. In Development Lab, set a healthy `CLEAR` only after verifying
the simulated path, or use the development API:

```bash
curl -X PUT http://localhost:8000/api/simulator/front-obstacle \
  -H 'Content-Type: application/json' \
  -d '{"state":"CLEAR","perception_health":"healthy","source":"manual","confidence":1}'
```

After `BLOCKED`, a later CLEAR observation does not release the latch. Verify the path,
submit fresh healthy CLEAR, then use Development Lab `Clear latch` with a reason. Never
carry this Simulator-only procedure over as a substitute for camera/sensor heartbeat.

## Recovery order

For iron-X Carry helper, first follow the operator-specific
[stop diagnosis and E-stop recovery](../hardware/ironx-follow.md#if-it-stops)
([日本語](../hardware/ironx-follow.ja.md)). A normal target-distance hold needs no
server restart. The network Adapter reconnects for observation only; a motion
fault may require explicit stop reset. The maintenance sequence below is for
cases that actually require a server/configuration restart, not every service stop.
Preserve E-stop at the gateway before restarting a PC process: a PC-only latch
that never reached the gateway is not persistent across process restart.

1. Stop the mission and latch E-stop if hardware is connected; use physical power if required.
2. Stop APRIS, then restart with the intended adapter configuration.
3. Inspect doctor, connection, telemetry, firmware limits, observations and stopped wheels.
4. Clear E-stop/acquire control only after the path and every component are checked.
5. Restart explicitly; reconnection must never resume motion.

## UGV02 provisioning and recovery

Use [UGV02 APRIS WebSocket firmware](../hardware/ugv02-websocket-firmware.md) for
application-only provisioning and layout/recovery prerequisites. Establish the actual
board/partition layout and a recoverable image before writing. Never use generic full-flash
upload or erase as a troubleshooting shortcut.
