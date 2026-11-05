# Runner port to the Python Local Server runtime

[日本語](python-port.ja.md) · [Previous experiment](process-experiment.md)

Status: isolated fake-only integration, 2026-11-05. The unchanged myService and its
Node worker now run through a separate Python process containing the existing
RoverRuntime. Its public add_client/handle_text/remove_client lifecycle performs
registration, control acquisition, move/cancel and disconnect stop. No motor command
is sent directly by the service. Existing runtime/adapter interfaces are unchanged.
This is not yet a FastAPI route or a remotely accessible authenticated API.

## Run

Install the existing server environment using the repository's uv setup instructions.
From the repository root (POSIX shell):

```sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node apps/runner-prototype/python-demo.ts
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node --test apps/runner-prototype/*.test.ts
uv run --directory apps/server pytest tests/test_runner_port_experiment.py tests/test_runtime.py
```

APRIS_PYTHON selects an interpreter, not an adapter. The Python entry point always
constructs PortFakeAdapter; it has no hardware selection. Without APRIS_PYTHON, the
Node suite skips the seven Python integration cases, preserving the Node-only path.
The demo defaults to python3 when run directly without that variable.

The local orchestrator forks the existing service-worker.ts and spawns
apris_server.runner_port_experiment. It forwards correlated requests/results; motion
admission and watchdogs live only in Python. Interaction/person inputs are scripted
fixtures. The earlier TypeScript Gateway is not also running.

## Port contract

JSON lines on inherited local pipes; requests have id/action and optional session/token.
Replies have kind=reply, id, ok and value/error. Unsolicited events are running,
terminal or revoked. This is a trusted local test protocol; no network/authentication
contract is inferred. Request IDs correlate replies, not durable idempotency keys.

| Request | Contract |
| --- | --- |
| admit | Create a new random session, register a runtime client, acquire control; reject busy/inhibited/guarded state |
| move(session, duration) | Accept one fake bounded operation, return {session,generation}; runtime may subsequently reject it |
| heartbeat(session, token?) | Renew live-session lease; only matching token renews that operation's authorization TTL |
| stop(session, token) | Validate token, then cancel through runtime; await separate terminal evidence |
| hold / clear | Guard admission during stationary interaction; clear requires confirmed=true |
| revoke | Fence session before runtime disconnect/cancellation; global local-operator path |
| recover | With no session/motion, explicitly assert fake standstill and human clearance |
| snapshot | Fake target, session, runtime owner, operation, inhibition, guard and synthetic actuation |
| fixture | Test-only front CLEAR/BLOCKED/etc. and delayed/missing evidence; unavailable to student capabilities |

Acceptance means the port accepted the request, not that motion has started. Running
is emitted from the runtime's started notification. Terminal statuses are completed,
cancelled, failed, interrupted or stop-unconfirmed. The token correlates all operation
events. Revocation while awaiting arrival evidence produces interrupted, not completed.
Stopped means fake-stop evidence only. Runtime completion or stop-call return alone
cannot substitute for evidence. Late evidence cannot clear stop-unconfirmed.

The service's experimental duration request is mapped to a bounded MoveCommand with
speed 0.1 m/s and distance duration * 0.1 m. Runtime schema, ownership, E-stop, connection,
pose-capability and front-clearance checks still apply. The fake implements the existing
DeviceBoundedMotionAdapter contract and records goals. It waits a synthetic duration,
invalidates synthetic actuation on stop, and independently signals stop evidence.
It does not simulate tracking, movement/odometry accuracy, or physical dynamics.

The orchestrator explicitly injects a synthetic CLEAR fixture before normal trials.
Without it, forward movement is rejected by the existing runtime; the port does not
manufacture CLEAR from a move request. Synthetic answers include human-clearance
confirmation for loading. Recipient unloading remains the unmodified service's final
message, not a complete guarded S2 handover.

## Deadlines and failure handling

All Python deadlines use host monotonic time: runner lease 400 ms, operation-command
authorization TTL 250 ms, fixed operation progress budget 1.2 s and stop evidence 200 ms.
The Node worker renews every 40 ms; Python checks every 10 ms. These are experimental
values, not measured hardware-safe limits or real-time guarantees. The operation TTL
is additional authorization: it does not replace runtime/device command TTLs.
Heartbeat alone cannot extend the operation TTL; continued token renewals cannot extend
its fixed progress budget. Python virtual pause/reset is not implemented and is not
exposed; the earlier TypeScript pause tests do not qualify this backend.

Lease/TTL/progress expiry or runner IPC loss fences the session, removes the runtime
client and initiates scoped finalization. Stop-unconfirmed latches inhibition and blocks
new admission until explicit fake recovery. A handover guard survives session loss.
Only this port is exposed in the experiment. Its guard is not yet integrated with
arbitrary external clients of a shared FastAPI server; do not claim robot-wide guarding
across such clients until that enforcement is moved into the shared server boundary.

The orchestrator's scripted input is deliberately trusted. It is not a UI reconnect,
operator-session or permission model. Python-process death/downstream watchdog behavior
is still unqualified. No physical adapter may be plugged into this experimental module.

## Evidence and next step

Local verification: 31 Node tests (24 prior + 7 Python subprocess cases), 21 Python tests
(7 port + 14 existing runtime regressions), strict TypeScript check, Ruff and the Python
connected service demo passed. Cases include normal/decline, runner kill/block/IPC loss,
delayed/missing evidence, forward rejection without CLEAR, E-stop rejection, stale tokens,
handover retention, arrival/revocation race and independent TTL/progress expiry.
The CI workflow adds a Python job using the server's frozen dependency lock.

Next: review this port contract before merging it into the actual server API. Consolidate
mailbox/activity and operation ownership into one runner, define shared-server guard
and operator lease enforcement, and specify adapter-specific stop evidence. Then connect
an actual simulator adapter with pose and registered movement; retain fault injection.
Hardware, observation loss, UI recovery, authentication, persistent jobs and packaging
remain subsequent work. This experiment changes no shipped PWA/server startup path.
