# APRIS Rover WebSocket protocol

[日本語](rover-protocol.ja.md)

Status: **Development protocol v1 implemented and exercised on UGV02; production WSS,
rover-scoped credentials, and full hardware qualification remain pending**

APRIS Server and rover firmware communicate over the device-initiated `/ws/rover` WebSocket.
This protocol has a separate version and schema from the browser
[Client protocol](protocol.md) and is never exposed to missions or the PhysiCode Bridge.

## Responsibility boundary

APRIS Server arbitrates ownership, mission execution, obstacle state, and limits, and converts
Client `move` / `turn` into one bounded motion. Rover firmware executes near encoders and the
IMU and reports a terminal result only after motor output is zero.

```text
Client / PhysiCode Bridge
        | move(distance) / turn(angle)
        v
APRIS Server
        | one bounded motion + renewable execution lease
        v
Rover firmware
        | local wheel-speed loop, odometry, stop
        v
Motor driver
```

Programs and whole missions are never sent to the rover. Automatic motions are not expanded
into high-rate wheel streaming. Only manual teleoperation uses short leased velocity commands.

## Units and signs

Use SI and planar ROS REP-103 conventions:

- positive `x` and `distance_m`: forward
- positive `yaw`, `angle_rad`, and `angular_speed_rad_s`: counter-clockwise / left
- velocity: metres per second and radians per second
- duration and TTL: integer milliseconds

UGV02 differential drive does not accept `vy`. APRIS converts Client `turn.angle_deg` to
radians before sending Rover protocol messages.

## Connection and identity

1. A rover validates server identity and authenticates. Development currently sends shared
   `APRIS_ROVER_TOKEN` in `Authorization: Bearer`; never place it in URL, query, or logs.
2. The first application message is `rover_hello` with protocol versions, `rover_id`,
   `boot_id`, firmware/build, hardware revision, capabilities, and fixed safety limits.
3. The server negotiates a version and assigns a fresh `connection_epoch`. Duplicate IDs,
   authentication failure, and unsupported versions never become motion-ready.
4. Heartbeats report `clock_offset_ms` and `clock_uncertainty_ms`. Missing, stale, or unsafe
   clock state rejects new motion, velocity, and renewals; stop/cancel/E-stop are still tried.
5. Disconnect immediately stops motors and makes active motion terminal `cancelled`.
   Reconnection creates a new epoch and never resumes motion.

`boot_id` changes on firmware boot so the server can distinguish reboot from reconnection.

## Common command envelope

Motion-related server commands include:

- protocol version and message type
- `connection_epoch`
- strictly increasing epoch-local `seq`
- unique `command_id`
- server issue time and freshness TTL
- optional `run_id`, `effect_id`, and `request_id`

Firmware rejects another epoch, non-increasing sequence, expired command, or unsafe clock
uncertainty. Freshness starts at server issue time, not rover receive time. The authoritative
field ranges are in [`packages/protocol/rover-v1.schema.json`](../packages/protocol/rover-v1.schema.json).

The server assigns sequence before send and awaits `command_ack` with a timeout. A
`start_motion` acknowledgement means accepted, not completed. Only terminal `motion_status`
for the same `motion_id` completes the Client motion. APRIS renews at roughly half the lease;
if health or acknowledgements prevent renewal, it attempts cancel/stop and never assumes
success.

## Server-to-rover commands

### `start_motion`

Starts one bounded, stoppable action:

- idempotency key `motion_id`
- `kind: linear | rotate`
- `distance_m` or `angle_rad`
- maximum linear/angular speed
- absolute `max_duration_ms`
- short renewable `lease_ms`

Firmware rejects values outside capabilities and fixed limits. A duplicate `motion_id` returns
known progress or terminal result and never starts a second movement.

### `renew_motion_lease`

Renews only the execution permission for the same motion. It cannot change target, limits, or
epoch. Expired motion is terminal and cannot be revived.

### `cancel_motion`

Stops active motion and transitions to `cancelled`. Cancelling an already terminal motion may
be idempotently successful but never reruns it.

### `set_velocity`

Sets manual `linear_velocity_mps` and `angular_velocity_rad_s` under a short lease. Updates
exist only while the operator holds input. It is mutually exclusive with bounded motion.

### `stop` and `estop`

`stop` is normal stop. `estop` is also latched in firmware. Both outrank motion and velocity
and must be safe when repeated. Clearing E-stop changes no target and never resumes motion.

## Rover-to-server messages

- `rover_hello`: identity, version, capabilities, and fixed limits
- `heartbeat`: boot/epoch, health, and clock data
- `command_ack`: accepted or stable rejection code
- `motion_status`: state, progress, and terminal reason for `motion_id`
- `telemetry`: encoder, odometry, velocity, IMU, battery, motor, fault, E-stop/watchdog
- `event`: reboot, watchdog stop, driver fault, and other lifecycle/safety events

`completed` is emitted only after reaching the target and stopping motors. APRIS maps
application outcomes such as PhysiCode `blocked` at the Client/World boundary; firmware never
contains educational-language semantics.

## Motion state machine

```text
                  +--> completed
accepted --> running --> cancelled
    |             +--> failed
    +-----------------> cancelled / failed
```

Terminal states never return to accepted/running. Lease expiry, maximum duration, disconnect,
cancel, stop, E-stop, watchdog, motor/encoder fault, and invalid control state all stop motors.
If the server loses a result, it never guesses success; unresolved terminal state is failure.

## Contract tests

- duplicate `motion_id` never moves twice
- stale epoch, sequence, TTL, and unsafe clock are rejected
- lease, disconnect, cancel, stop, E-stop, and max duration stop the fake rover
- reconnect creates a new epoch and never resumes unfinished motion
- completion follows zero motor velocity
- manual velocity and bounded motion are exclusive
- server configuration cannot raise firmware limits
- Simulator and WebSocket adapter expose equivalent high-level terminal semantics

Models live in `apps/server/src/apris_server/rover_protocol.py`, registry/dispatch in
`rover_registry.py`, the physical boundary in `websocket_rover_adapter.py`, and the motor-free
state machine in `fake_rover.py`. Regenerate schema with
`scripts/generate-rover-protocol-schema.py`; contract tests detect model/schema/fixture drift.
