# Planar simulator integration

[日本語](simulator-integration.ja.md) · [Shared authority](shared-authority.md) · [Integration plan](integration-plan.md)

Step D now has a runnable baseline: Node's service host can connect to the existing
planar simulator through the same Python port and shared runtime interlock.
This exercises changing pose and wheel/IMU odometry, not just elapsed fake-operation time.

## Run

From the repository root:

```sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node apps/runner-prototype/simulator-demo.ts
```

The report includes `snapshot.backend`, `snapshot.state.pose`, velocity and pose quality.
A successful run closes the service and ends with zero velocity and nonzero forward displacement.
The standalone backend is also available as:

```sh
uv run --directory apps/server python -m apris_server.runner_port_experiment --backend simulator
```

It speaks the same bounded JSON-lines protocol. `--backend fake` remains the default.
The existing `runFakeService` function name is retained for compatibility; pass
`{ backend: 'simulator' }` to select the planar backend. Only these two explicit choices
are accepted. Neither can load hardware. The protocol robot ID remains `fake-only` for
compatibility and is not a claim about the selected backend; inspect `snapshot.backend`.

## Motion and evidence

`PortSimulatorAdapter` extends `DifferentialDriveSimulator` without implementing the
native bounded-motion interface. Consequently `RoverRuntime` uses its existing
odometry feedback loops to finish move/turn commands. No second controller is added.
The simulator advances planar motion at 50 Hz; runtime feedback defaults to 20 Hz.
Existing goal tolerances are 0.015 m for translation and 1.5 degrees for rotation.
The simulator service facade uses a synthetic 0.04 m approach goal; the fake's
0.008 m goal would already be inside the translation tolerance. Fake behavior is unchanged.

The simulator stop integrates the final interval and zeros velocity under its lock.
Only after that does the adapter publish simulated stop evidence. A new drive clears
that evidence before awaiting its dispatch. Pending effects and shared inhibition
continue to be checked by the runtime. Stop evidence remains `kind: simulated` and
uses a backend-labelled epoch; no physical stop claim is made.

## Validation

Seven Python cases cover forward/reverse translation, positive/negative turns,
cancellation, command-TTL expiry, and unknown-front rejection plus handover blocking
a new manual owner. They check actual odometry displacement and unchanged pose after
stopping. A Node integration test runs the unchanged student service through the
subprocess host and checks final displacement, zero velocity, and closed lifecycle.

Local validation: 392 server tests passed before the final additional case; the final
seven-case simulator suite then passed. All 138 Node tests, strict TypeScript, Ruff,
and the simulator demo passed. CI includes the new files and simulator demo; these
local results do not assert an observed CI run.

## Scope and follow-up

Recognition, operator presence, answers, and front-clear observations remain synthetic.
`approachPerson` is a fixed displacement and `followPerson` a cancellable finite goal,
not perception-driven tracking. This does not add a map, collision geometry, Godot,
MuJoCo, or Hakoniwa. The existing simulator models ideal planar motion; encoder/IMU
faults, stale/noisy feedback, command delay, and process-loss safety need separate
qualification before claiming robustness. Fake evidence-delay injection is rejected
by the simulator backend instead of pretending to exercise that fault.

Leases and progress/stop deadlines are unchanged experimental bounds, including the
1.2-second progress deadline. Longer goals can therefore be interrupted even while
making progress. Deadline policy, feedback quality gating, and fault scenarios remain
explicit follow-up work. The next planned integration is the minimal operator UI (E),
including recovery/guard visibility; real-device enablement remains separate.

See [Minimal operator console](operator-console.md) for the operator UI binding.
