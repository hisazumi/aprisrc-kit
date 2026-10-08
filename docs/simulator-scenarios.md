# Simulator scenarios, fault injection, and logs

[日本語](simulator-scenarios.ja.md)

The Simulator is the standard repeatable test component, not only a visual substitute for
hardware. Development controls live under `/lab` **Simulator Tools** and are intentionally
absent from `/app` and `/console`.

## Scenario files

Store reproducible input in `apps/server/scenarios/*.json`. Startup validation rejects
duplicate IDs, unordered times, unknown action types, and out-of-range values.

```json
{
  "id": "perception-inputs",
  "name": "Perception input sequence",
  "description": "Inject reproducible service inputs.",
  "actions": [
    {
      "at_ms": 0,
      "type": "event",
      "kind": "person",
      "payload": {
        "status": "detected",
        "confidence": 0.94,
        "person_id": "demo-person",
        "center_x": 0.5,
        "center_y": 0.5,
        "width": 0.2,
        "height": 0.5
      }
    }
  ]
}
```

Supported actions:

- `event`: publish `person`, `marker`, or `voice_intent`
- `faults`: apply a complete Simulator fault configuration
- `clear_faults`: remove all faults
- `reset`: stop, reset pose, and clear faults
- `front_obstacle`: inject state, health, confidence, and optional range/lateral data
- `clear_front_obstacle`: clear the latch only with fresh healthy `CLEAR` and a reason

`at_ms` is relative to scenario start and must be ascending. Starting, completing, cancelling,
or failing a scenario stops the rover; completion also clears faults.

## Injected events

Person and marker actions pass through the same validation and `perception_event` path as
camera observations. `source` identifies `manual`, `scenario`, or `replay`. Known markers may
also correct pose. Voice intent remains a `scenario_event`.

## Fault settings

| Field | Meaning |
| --- | --- |
| `command_latency_ms` | Delay before Simulator applies `drive` |
| `state_latency_ms` | Delay before state publication |
| `drop_next_commands` | Number of upcoming `drive` commands to discard |
| `pose_noise_m` | Maximum deterministic x/y noise |
| `yaw_noise_deg` | Maximum deterministic yaw noise |
| `stale_state_ms` | Age offset applied to pose and velocity |
| `battery_percent` | Display override; `null` restores simulated value |
| `encoder_fault` | Mark encoder input faulty and reduce odometry confidence |
| `imu_fault` | Mark IMU input faulty and reduce odometry confidence |
| `seed` | Phase for deterministic noise |

Faults exist only inside the Simulator adapter. They never disable normal stop, E-stop,
ownership, speed limits, or command TTL. `stop()` is never delayed or dropped.

## Front obstacle state

Development Lab controls `CLEAR | BLOCKED | UNKNOWN` independently from `healthy | degraded |
unavailable`. Only healthy perception may establish `CLEAR`. The Simulator controller refreshes
configured state every second; stopping that heartbeat returns runtime state to `UNKNOWN`.

`BLOCKED` remains latched even after a later `CLEAR` observation. **Clear latch** or a
`clear_front_obstacle` action requires fresh healthy `CLEAR` and an explicit reason. State,
health, freshness, latch, and clear reason appear in `/api/status`, Simulator status,
WebSocket messages, and structured logs.

## Structured logs

Each Local Server session creates a JSON Lines file under ignored `.runtime/logs/`, or
`APRIS_LOG_DIR`. Categories include client input, adapter commands, state, server output,
scenario/perception events, faults, lifecycle, and front-obstacle changes. Each line includes
session ID, sequence, Unix time, and `elapsed_ms`.

## Safe replay

**Replay inputs** replays scenario events, camera/recorded perception observations, and fault
settings in relative-time order. It excludes scenario-derived duplicate observations and never
replays `drive`, `move`, `turn`, or motor commands. Replay stops active motion before start and
stops plus clears faults at the end.

To reproduce movement, write an explicit scenario or test that invokes the public mission API.

## Development API

```text
GET    /api/simulator/scenarios
POST   /api/simulator/scenarios/{id}/run
POST   /api/simulator/scenarios/stop
GET    /api/simulator/status
POST   /api/simulator/events
PUT    /api/simulator/faults
DELETE /api/simulator/faults
PUT    /api/simulator/front-obstacle
POST   /api/simulator/front-obstacle/clear
GET    /api/simulator/logs
DELETE /api/simulator/logs
POST   /api/simulator/logs/replay
```

These endpoints are development-only and are not part of the mission API or required from a
physical adapter.

## Included scenarios

- `perception-inputs`: person, marker, then voice intent
- `perception-loss`: person detected/lost and low-confidence marker rejection
- `fault-injection-demo`: latency, drops, stale state, noise, low battery, then clear
- `front-obstacle-latch`: CLEAR, BLOCKED, another CLEAR, then explicit reasoned clear

```bash
uv run --directory apps/server pytest
uv run --directory apps/server ruff check src tests
npm test
```
