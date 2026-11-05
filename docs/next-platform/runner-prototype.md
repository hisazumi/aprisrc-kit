# External runner: first contract experiment

[日本語](runner-prototype.ja.md) · [Architecture](architecture.md)

Status: isolated executable experiment, 2026-11-05. This does not replace the PWA
runtime or change any physical-rover capability/qualification claim.

## Purpose and boundary

Test run/activity identity, directed mailboxes, motion ownership, handover inhibition
and simulation cancellation before connecting the existing service facade to a server.
The runner is a browser-free Node.js process; its backend is an in-memory fake in that
same process. There is no hardware selection, network listener, robot transport, or
independent safety process. No new dependencies are required.

The files under `apps/runner-prototype/` are a disposable contract harness, not a new
student mission directory. Existing mission/config editing locations remain unchanged.
The existing student facade is not yet extracted or exercised by this experiment.

## Run

Use Node.js 22.18+ with built-in TypeScript stripping (tested here on 26.13.0).
From the repository root:

```sh
node --test apps/runner-prototype/runtime.test.ts
node apps/runner-prototype/runner.ts
```

The second command reads one JSON request per line from stdin and writes JSON responses
and operation terminal events to stdout. For example, enter these lines in order:

```json
{"id":1,"type":"start","service":"delivery"}
{"id":2,"type":"move","scope":{"runId":"run-1","activityId":"root","epoch":0},"duration":10}
{"id":3,"type":"pause"}
{"id":4,"type":"cancel","scope":{"runId":"run-1","activityId":"root","epoch":0}}
{"id":5,"type":"snapshot"}
```

Cancellation returns a response and a correlated terminal event without a `step`.
This sample starts a fresh process. In a client, use the scope returned by `start`.
EOF interrupts live runs and exits; this is not a browser-disconnect policy.

## Experimental API

| API | Contract |
| --- | --- |
| `start(service)` | New run/epoch scope; reject another active run for this service on the single fake robot |
| `activity(root, handler)` | Flat child activity; synchronous transition handler, no long-running await |
| `send(scope, event)` / `dispatch()` | Directed bounded FIFO; one transition per activity per dispatch; overflow and stale scope throw |
| `move(scope, duration)` | Synthetic timed operation, seconds; returns token plus terminal-result Promise; rejects competing movement |
| `cancel(scope)` | Fence scope first; root cancellation removes all children and prompts; resolve affected operations once |
| `prompt(scope, stationary)` / `answer(id, clearToMove)` | Correlated one-shot prompt; stationary prompts require idle motion and hold a robot-wide guard |
| `paused` / `step(seconds)` | Explicit virtual clock; pause freezes motion progress, not control dispatch |
| `reset()` | Interrupt all runs, discard complete virtual scene, advance epoch; never a physical operation |
| `globalStop()` | Interrupt all runs independently of mailbox capacity; handover guard retained |
| `snapshot()` | Fake target, epoch/time, counts, motion owner and guard |

`FakeMotion` models generation checking and virtual stop evidence. Its public methods
are test hooks, not an authorization boundary. `current(token)` is the common check
intended for future drive/renew/stop ports; only scoped stop is implemented here.
Terminal evidence means pending fake actuation is invalidated. It never means a physical
robot has stopped. Cancelled prompts retain a stationary guard until explicit fake
operator clearance; scene reset can clear it only because the entire virtual world is
removed. UI disappearance has no implementation yet.

Only start/move/cancel/pause/resume/step/reset/stop/snapshot are exposed in the stdin
harness. Activity and interaction contracts are exercised directly by unit tests.

## Acceptance evidence

| Test | Expected result |
| --- | --- |
| Concurrent delivery and order activity | Ordered directed events processed while movement remains pending |
| Root cancellation and delayed cleanup | Children fenced; stale events/reacquisition rejected; old stop cannot affect new owner |
| Ordinary question cancellation | Other activity's movement continues |
| Stationary handover | All runs inhibited; cancelling prompt does not release guard |
| Handover entry/completion | Moving robot cannot enter; explicit clearance required; duplicate answer rejected |
| Pause, cancel and reset | No virtual progress during pause; cancellation without stepping; old epoch rejected, no revival |
| Duplicate start / full mailbox | Visible rejection; global stop still works |
| Handler exception | Run interrupted and movement invalidated |
| Separate child process | Starts without browser; responds to cancel during pause; exits cleanly on EOF |

Nine tests passed on Node.js 26.13.0. Tests use synthetic inputs only. The existing
PWA/server suites are not exercised by this isolated experiment.

## Next experiment

The [separate-process experiment](process-experiment.md) now exercises the unchanged
existing service through a fake facade, runner loss and stop-evidence failures.
The following is the original next-step plan; Python integration remains outstanding.


Adapt one existing sequential service through injected motion/interaction/clock ports,
keeping its mission/config paths. Move the fake safety gateway into a **separate process**
and inject runner death, blocked event loop, control loss, delayed stop evidence and
stop-unconfirmed. Define real-time lease/progress deadlines and command TTL there.
Only after those checks connect the existing Python server.

Not implemented here: adapter stop evidence/deadline, real-time health/progress watchdog,
leases/authentication, UI roles/reconnect/loss, observation buffers, full operation state
machine, nested scopes, persistent jobs, autonomous dispatch scheduling, route/pose or
perception, ROS/Hakoniwa integration, WSL packaging, physical speed/clearance protections.
No runtime-selection ADR is adopted by this experiment. Durability is memory-only.
