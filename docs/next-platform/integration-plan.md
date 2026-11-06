# Runner/server integration plan

Status: proposed, 2026-11-06. [日本語](integration-plan.ja.md).
This refines the [architecture](architecture.md) into the next implementation slice.
It is not a declaration that the experimental runner is production-ready.

## 1. Goal and evidence

Consolidate the in-memory runner, process-isolation experiment and Python port into
one runtime, then execute bounded movement against the existing Simulator with
observable pose changes. Keep the current application startup unchanged until the
acceptance gates below pass.

The reviewed baseline is commit ef72930eba9ad9bcc12d0d0dd7c5986c246d0a21:
33 Node tests (including 7 Python subprocess cases), 27 Python tests, TypeScript and
Ruff checks passed locally and in the relevant CI jobs. See
[Python-port evidence](python-port.md#review-regressions-fixed-2026-11-06).
These tests qualify fake behavior and process boundaries, not physical stopping.
The current PortFakeAdapter waits for synthetic durations; its goal acceptance does
not demonstrate movement, odometry accuracy or person following.

## 2. One owner per responsibility

| Component | Owns | Boundary |
| --- | --- | --- |
| Node runner | Run admission, activity tree, directed mailboxes, capability facade, prompts and cancellation | Requests motion; cannot grant robot authority |
| Python server | Robot-wide authority, generation fencing, limits, leases, stationary handover guard, stop evidence and inhibition | All motion clients pass through the same checks |
| RoverAdapter / Simulator | Backend motion and observations, documented stop-evidence provider | No service policy; test faults remain outside the physical adapter contract |
| PWA | Service inputs and projections; operator control by role | No motor transport; ordinary page lifetime does not own the run |
| Scenario harness | Synthetic observations, human responses and fault injection | Explicit test provenance; never supplies implicit production clearance |

Retain service/config files in apps/pwa/src/missions/ and apps/pwa/src/config/.
Separate browser dependencies from the StudentServiceApi implementation. Replace its
unscoped cleanup stops with operation-scoped cancellation. Preserve /app, /console
and /lab roles. The TypeScript fake gateway becomes a contract-test backend, not a
second authority in front of Python.

Initially admit one active service per robot, with multiple activities inside it.
Each activity serializes short event handlers; handlers start asynchronous work and
return. Directed business queues are bounded with visible overflow; latest sensor
values use a separate path. Cancellation closes child admission, cancels/joins all
descendants and removes their timers, subscriptions and prompts. Do not claim
general hierarchical state-machine support from the existing flat prototype.

## 3. Connection and operation contract

Start with a same-host, inherited-pipe JSON-lines transport behind an interface.
This keeps deployment small while the contract stabilizes. It is a trusted local
connection, not an authenticated network API. The later server integration must use
the same authority as legacy/manual clients; do not start a second runtime for the
same robot.

Every message carries protocolVersion, connectionEpoch and requestId; operation
messages also carry robotId, runId, activityId and operationId. The client allocates
operationId and registers its result handler **before sending**. Python assigns the
authority generation on acceptance. Subsequent renew/cancel messages must match both
the operation identity and generation. Run configuration pins map revision when maps
are introduced. Protocol validation rejects unknown or malformed variants.

| Message | Meaning |
| --- | --- |
| openRun / closeRun | Admit or fence a run; close does not assert standstill |
| startMotion | Validate a bounded SI goal, then accept or reject it |
| renewMotion | Renew only the identified operation within its fixed progress budget |
| cancelMotion | Request scoped termination; acknowledgement is not stop confirmation |
| acquireHandover / clearHandover | Acquire a stationary guard after confirmed stop; release only on authorized human clearance |
| heartbeat / snapshot | Connection health and current state; neither authorizes replay |
| globalStop / recover | Operator path independent of service mailboxes; explicit recovery with backend evidence |

Use distance in metres and angle in radians internally; convert the existing
degree-based convenience API explicitly. Eliminate the experimental duration-to-distance
API. Validate converted values before allocating authority or starting adapter work.

Lifecycle: requested → rejected, or accepted → running → terminal. A failure may
terminate after acceptance without running. Accepted means admitted; running means
the runtime reported execution. Terminal outcome is completed, cancelled, failed,
interrupted or stop-unconfirmed, with a reason and evidence metadata.
Completed/cancelled/interrupted motion may claim standstill only with backend evidence;
a failed request before actuation does not invent evidence of stopping another operation.

Reply/event order is not a correctness assumption: terminal may reach the client before
the acceptance reply. Preserve correlation through this case. Retain bounded deduplication
records for request/operation IDs for the live connection; exhaustion rejects admission
rather than silently forgetting live obligations. A repeated start cannot create a
second movement. Old epochs and generations are rejected, including normal stop calls.
Emit one terminal per accepted operation while the authority process remains alive.
A server crash can prevent delivery; reconnection exposes uncertainty, not exactly-once
execution or a fabricated terminal.

## 4. Safety and recovery

The Python authority enforces the guard across runner, joystick and legacy routes.
Only explicit human clearance releases a loading/receipt guard. Prompt cancellation,
timeout, run loss and UI loss leave it held. Global stop remains effective even while
guarded. The current service's final unloading speech is not receipt confirmation;
a guarded unloading step remains a later S2 service-policy change.

Keep separate operator authorization, runner health, per-command TTL and operation
progress budgets. Check expiry before processing a renewal as well as in the watchdog.
Heartbeats cannot extend progress. Missing required observation freshness stops the
affected capability; an unrelated service-screen disconnect need not stop other work.

Fence permission under a short state lock; execute adapter/transport I/O outside it.
The stop budget starts when termination is admitted and includes stop I/O and evidence.
If it expires, publish stop-unconfirmed and latch inhibition. Late I/O or evidence must
not clear that latch. Outstanding old I/O blocks new admission and recovery so old
cleanup cannot stop a new owner. Bound shutdown waits; a cancellation-ignoring backend
requires process containment and separately qualified downstream watchdogs.

Reconnect provides a snapshot and invalidates old prompts; it never replays motion.
After server restart require explicit operator recovery and a new run. Until durable
guard state is designed, start inhibited with human access treated as unknown.
Do not assume that losing in-memory guard state proves clearance.

## 5. First Simulator slice

1. Inject the existing DifferentialDriveSimulator behind the shared runtime boundary,
   retaining synthetic input and fault controls under apps/server/scenarios/.
2. Execute a small sequence of bounded move and turn goals through the consolidated
   runner. Assert pose change, local odometry completion and exclusive ownership.
3. Test cancellation and faults while simulated pose is actually changing.
4. Then adapt the existing service with scripted, provenance-labelled person observations
   and responses. Demonstrate approach/follow control separately before claiming that
   the unchanged service follows a person. Generic object detection and map routing follow.

Simulator stop evidence must identify the simulation epoch and confirm zero simulated
actuation/velocity after the scoped stop. A stop method returning is insufficient.
Record requested goal, observed pose, timestamps and final evidence; define numerical
tolerances from the simulator model before assertions. Keep truth separate from estimate.
Map correction must not bypass local relative-motion completion.

The first profile runs in real time and explicitly does not expose pause/reset.
Add pause/reset only after introducing separate simulation and host-monotonic clocks:
acknowledged pause freezes simulation progress/freshness budgets, while health and stop
control continue. Cancel/reset must work without a physics step; reset fences the epoch.
This is a later gate for F10, not a capability inherited from the TypeScript fake.

## 6. Implementation order and acceptance gates

Write the contract/regression cases before each implementation change.

| Step | Deliverable | Exit gate |
| --- | --- | --- |
| A | Typed envelopes, operation state/evidence schema and transport interface | Invalid SI values, duplicate start, terminal-before-reply, stale epoch/generation and bounded dedup tests |
| B | One runner with activity tree and fake capability backend | Child cleanup, mailbox overflow, prompt cancellation, worker block/kill/IPC loss; no orphan motion |
| C | Shared Python authority and guard | Manual/legacy/runner attempts all blocked by handover; expiry-before-renewal; blocked stop I/O stays responsive; late cleanup cannot reach a new owner |
| D | Real Simulator pose integration | Bounded move/turn geometry, stop during motion, delayed/missing evidence, no automatic resume; scenario and trace reproduce results |
| E | Minimal UI/operator integration | Correlated answers, stale-answer rejection, independent operator lease, ordinary UI reconnect and explicit restart recovery |

Maintain all reviewed regression tests, including failed subprocess spawn and batched
acceptance/terminal delivery. Test just before, at and after deadline boundaries with
injected clocks; use subprocess tests for actual isolation behavior. Server death and
downstream stopping are separate fault tests, not implied by runner-death success.
Run the existing server safety suite and the same applicable adapter contract tests
against the Simulator. Physical adapters require their own evidence and measured budgets.

First implementation task: **A, the shared message/lifecycle contract and its tests**.
Do not add another standalone experiment. After A–D, review the actual trace before
adding broader navigation or a rich 3D simulator.

## 7. Scope and traceability

This slice primarily advances F05/F06 (execution/lifecycle), F09 (backend boundary),
F11 (trace), F14 (one motion owner), Q01/Q03 (safety/isolation), Q04/Q06 (substitution/
provenance). F10 remains partial until clock/pause/reset qualification.
Map/localization, YOLO providers, persistent jobs, full S1–S3 policies, ROS/Hakoniwa
selection, WSL packaging and physical qualification remain subsequent work.
Experimental timeout values are not adopted as production limits; measure budgets
under Q08. This memo changes no shipped startup path or current capability claims.
