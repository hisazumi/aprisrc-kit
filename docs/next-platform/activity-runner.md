# Consolidated activity runner core

[日本語](activity-runner.ja.md) · [Integration plan](integration-plan.md)

The reusable ActivityRunner in apps/runner-prototype/activity-runner.ts combines
activity ownership, directed mailboxes and a scoped capability facade. It has no
motion owner or handover guard of its own: motionCapability adapts the existing
MotionClient to Python's authority. This is the core of integration step B, not a
new executable experiment or a replacement of the shipped browser startup.

## Lifecycle and resources

The host supplies an admitted runId/runEpoch. The runner creates an opaque root
activity and supports arbitrary nesting within a bounded activity count. Each
activity owns its mailbox, AbortSignal, motion promises, prompts, timers and
subscription cleanup callbacks. capabilities(scope) exposes move, prompt, after,
subscribe and spawn; no unscoped stop or direct transport is exposed.

Cancellation first fences the entire descendant tree and clears its queues. Only
then does it abort motion, reject pending prompts, cancel timers and run subscription
cleanup. It joins managed work and cleanup, including already-closing descendants.
Repeated cancellation returns the same completion promise. Late answers/events or
new children under a closed parent are rejected. Cancelling a nonmoving question
cannot stop sibling movement. Prompt answers do not release Python handover guards.

Cleanup waits have a host-time limit (default 1 s). Timeout, backend uncertainty or
cleanup failure rejects the join and retains failure diagnostics. A timeout does
not mark motion stopped or make an unresolved promise disappear; pending remains
visible in snapshot. Arbitrary uncooperative JavaScript cannot be terminated by an
AbortSignal; process isolation and Python's independent deadlines remain necessary.

Defaults: 8 queued events per activity, 256 activities including closed tombstones
per runner, 64 managed resource entries per activity. Prompts reserve both a promise
and a cleanup entry. Counts bound admission; payload byte-size limits belong to the
future transport. Timers currently use host time only; no pause/reset claim is made.

## Event handling and motion

Mailboxes are directed FIFO queues; inputs are cloned on enqueue. Each dispatch
round handles at most one event per activity present at the start of that round.
setImmediate schedules further rounds so continuously generated events do not form
an endless microtask chain. Queue overflow is visible to the sender. Handlers must
return synchronously: start a capability promise and handle its result later rather
than awaiting inside the event handler. Exceptions or a returned Promise interrupt
the run. Only work registered through the facade is managed/joined by the runner.

MotionClient now queues cancellation until its operation generation is known. It
sends one scoped cancel; if a terminal arrives first, it sends none. Cancellation
acknowledgement does not resolve the movement promise: the terminal/evidence does.
The adapter renews the operation every 40 ms while active. It stops renewal on abort
or terminal; Python's fixed progress deadline still limits duration. Renewal IDs
have a bounded budget (four times the client's operation limit); exhaustion makes
pending work uncertain. Cancellation has reserved room (at most one ID per operation).
Python's own smaller request budget can reject earlier; production session rotation
is not implemented. These are experimental settings, not physical safety limits.

## Verification

Local Node suite: 121 passed, including Python subprocess tests; strict TypeScript
passed. The existing CI wildcard runs the added tests. Python source was unchanged.

Eight runner tests cover nested fencing/join, sibling independence, FIFO/overflow,
resource cleanup, handler failure, uncooperative work, scope/count bounds, and failed
or unconfirmed backend cleanup. Three MotionClient tests cover cancellation before
acceptance, early terminal suppression and bounded scoped renewal. Three subprocess
cases connect the runner to the existing Python fake port for completion (including
a move lasting longer than one unrenewed TTL), nested cancellation and Python loss.

Tests preceded the new module. A later failing cleanup test exposed that the first
implementation ignored rejected motion promises during join; the fix preserves
backend uncertainty and rejects cleanup rather than reporting success.

## Remaining integration

The old runtime.ts and process experiments remain regression fixtures; they are not
additional authorities in the new runner path. This increment does not yet implement
the full StudentServiceApi, observation ingress or the old service-worker bootstrap.
The test host still performs control admission, independent operator/run heartbeats
and closeRun after root cleanup. Local root cancellation alone does not close the
server run or clear a guard. Python-loss testing verifies uncertainty handling, not
physical stopping after Python death.

Next provide one bounded transport/host that owns those lifecycle duties, routes
failures to run closure, and adapts the student service onto this core. Then move the
guard/authority into the shared server boundary (C), and qualify actual Simulator
pose changes (D). No hardware, authenticated multi-user UI or rich simulation support
is claimed by these fake-port tests.
