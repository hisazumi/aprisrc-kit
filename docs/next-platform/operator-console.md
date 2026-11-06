# Minimal operator console

[日本語](operator-console.ja.md) · [Simulator integration](simulator-integration.md)

This adds a local `/console` binding to the existing `RunnerPort` and shared
`RoverRuntime`, always using the planar simulator. It displays ownership, inhibition,
handover, pending stop, odometry and recent operation outcomes. The browser requests
bounded move/turn goals through the existing motion contract; it never sends motor commands.

## Run and try

```sh
uv sync --directory apps/server --frozen
uv run --directory apps/server python -m apris_server.operator_console
```

Open the URL printed in the terminal. It uses `127.0.0.1:8766/console` with a fresh
bearer token in the fragment. The page removes the fragment and retains the token in
tab session storage. Restarting the server rotates the token and control epoch;
open the new printed URL. The server has no remote-bind option or hardware backend.

1. Acquire operator authority. Initial state is inhibited.
2. Explicitly check that people are clear, then recover. Recovery never starts motion.
3. Start a test run. Enable the clearly labelled synthetic front-clear observation
   for forward travel, then request 4 cm forward or a 0.1 rad left turn.
4. After motion finishes, acquire handover. Movement is blocked. A fresh clearance
   checkbox is required to complete handover; a changed guard ID resets the checkbox.
5. Try global stop. It revokes the run and inhibits motion, even during handover.
   Once stop is confirmed, explicitly recover with the current guard ID and clearance.
   A new run and new movement request are necessary to move again.
6. Reload or hide the page during handover. The guard remains. After operator lease
   expiry, acquire authority again and recover explicitly. No movement is replayed.

The operator page refreshes at 100 ms while visible. An explicitly acquired operator
renews its 400 ms lease; a test run separately renews its run lease and active motion
TTL through existing typed messages. Read-only state requests do not renew anything.
Hiding/closing the page stops renewal. These are experimental timing values, so browser
throttling or a slow machine may revoke the operator. The authority stays in Python.
This page is deliberately the operator/test driver; it is not the ordinary service UI.

The HTTP binding checks Host, Origin, a random bearer token and a 64 KiB body limit;
static assets have a restrictive CSP and no external dependencies. There is no user/role
account system. Do not expose it through a proxy or treat it as production network auth.
Synthetic front observations are an explicit simulator input, not a hardware safety source.
The bounded recent-event display is diagnostic, not a durable trace archive.

## Validation and remaining work

Four HTTP integration tests cover token/origin/host/body validation, explicit recovery,
stale guard replies, read-only reconnect with lease expiry, guard retention, server
restart epochs, actual motion/global stop and no replay after recovery. Two DOM tests
exercise the shipped HTML/JavaScript: read-only startup, fresh clearance, hidden-page
renewal suppression and no automatic authority reacquisition after restart.

Local checks passed: 397 server tests, 140 Node tests, strict TypeScript and Ruff.
A pre-existing simulator assertion was corrected to allow only 1e-12 absolute numerical
round-off after stopping, rather than requiring bitwise-equal floating-point poses.
A real Chrome visual smoke test could not run in this environment (headless process
exited at launch); DOM and HTTP behavior were tested, but visual/browser qualification
is still pending. CI includes these tests; no CI success is claimed from local results.

This is the operator portion of step E, not all its acceptance criteria. The current
PWA startup remains unchanged. The console owns one simulator runtime; it does not
attach to an already running `runFakeService` subprocess or a physical rover. General
student-service questions, ordinary `/app` reconnect independent of run lifetime,
and Node-host attachment to this persistent authority remain next integration work.
Guard state is in memory; restarting requires explicit recovery and is not proof that
people are clear. No persistent guard store or real-device qualification is added.
