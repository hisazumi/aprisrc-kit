# Client protocol

The PWA and Local Server communicate through `/ws` using versioned JSON messages. Hardware protocols are not exposed over this connection.

Physical rovers such as the UGV02 use the separate [APRIS Rover WebSocket protocol](rover-protocol.md). The APRIS Server translates client `move` and `turn` requests into Rover bounded motions at the `RoverAdapter` boundary. Browsers and missions never connect directly to the Rover protocol.

## Coordinate system

The platform follows the ROS REP-103 planar convention:

- positive `x`: rover forward
- positive `y`: rover left
- positive `yaw` and `wz`: counter-clockwise
- SI units throughout

The UGV02 adapter accepts only `vy = 0`. An iron-X adapter may support lateral velocity, but participant-facing exercises can keep it disabled.

## Client messages

- `client_hello`: mandatory first message identifying client role, device/session, app version and build
- `acquire_control`: request the single driver lease
- `release_control`: release the driver lease and stop
- `drive`: set `vx`, `vy`, and `wz` with a short TTL
- `stop`: non-latching controlled stop
- `move`: move a signed distance in metres using pose feedback
- `turn`: turn a signed angle in degrees using pose feedback
- `cancel_motion`: cancel the active `move` or `turn` and stop
- `estop`: latching emergency stop; accepted from any connected client
- `clear_estop`: clear the latch; accepted from the active driver
- `reset_pose`: reset Simulator odometry
- `read_front_obstacle`: read the authoritative three-state front-obstacle snapshot with request/run/effect correlation
- `perception_observation`: submit an on-device person or marker observation for validation

Every message carries `v: 1`. Except for fail-safe `estop`, the server rejects messages until a valid `client_hello` has registered the connection. A client must send fresh `drive` commands while an input is held. When the TTL expires, the server stops the rover.

`move` and `turn` carry a `request_id`. Integrations may also carry optional `run_id`
and `effect_id`; the server propagates them into motion lifecycle messages, structured
logs, and `/api/status.active_execution`. The Local Server runs only one high-level
motion at a time and refreshes an internal short-TTL command while checking pose
feedback. A new manual `drive`, `stop`, E-stop, control release, owner disconnect, or
TTL failure cancels the active motion.

## Server messages

- `hello`: connection ID, server/build/instance identity, supported protocol versions and platform capabilities
- `control`: current driver ownership and emergency-stop state
- `state`: pose, velocity, battery and connection state
- `scenario_event`: development-only person, marker or voice-intent input with its source
- `perception_event`: accepted, lost, or rejected person / marker observation and correction result
- `motion`: correlated `started`, `completed`, `cancelled`, or `failed` result for a high-level motion
- `front_obstacle`: `CLEAR | BLOCKED | UNKNOWN`, perception health, source, freshness, optional range data, and latch/clear metadata
- `event`: safety or lifecycle event
- `error`: rejected command with a stable error code

The normative client-to-server shapes are in `packages/protocol/rover-message.schema.json`. Server-to-client schema coverage is a planned compatibility task; the Pydantic and TypeScript models are currently the executable contract for that direction.

## Operational endpoints

- `GET /api/livez`: the HTTP process is responding
- `GET /api/readyz`: motion-critical loops, active adapter and structured log are healthy; returns HTTP 503 when not ready
- `GET /api/status`: read-only runtime snapshot including deployment/build identity,
  effective safety limits, clients and roles, control/E-stop, adapter state, active and
  last motion with correlation IDs, loop health, adapter and log health
- `GET /api/health`: deprecated compatibility alias for readiness

Positive `drive` and `move` are accepted only while the effective front-obstacle state
is a fresh, healthy `CLEAR`. `BLOCKED` cancels an active forward motion with the stable
reason `front_obstacle_blocked`; `UNKNOWN` uses `front_obstacle_unknown`. Backward and
in-place turn remain available when the other safety conditions allow them. A valid
`BLOCKED` observation latches until a fresh healthy `CLEAR` observation and an explicit
clear reason are both present.

`uv run --directory apps/server apris-doctor --json` fetches the same runtime snapshot for local diagnostics. Status output contains identifiers but no credentials; hosted access control and production redaction remain deployment work.

Simulator scenario control itself uses `/api/simulator/*` rather than participant-facing
WebSocket commands. `scenario_event` is broadcast over WebSocket so the same service event path
can later accept real perception results. See [Simulator scenarios](simulator-scenarios.md).

`state.pose_quality` reports the pose frame, estimator source, confidence, encoder / IMU
status, sensor anomalies, and the last marker used for correction. Camera observations never carry
drive commands. See [Perception and pose estimation](perception-and-pose.md).
