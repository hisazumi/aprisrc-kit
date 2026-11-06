# Motion contract v1: first integration increment

[日本語](motion-contract.ja.md) · [Integration plan](integration-plan.md)

Implemented in apps/runner-prototype/motion-contract.ts, with 16 cases in
motion-contract.test.ts. This is the motion portion of step A. It is reusable contract
code, not another executable experiment. Existing startup and wire protocols are
unchanged; Python adoption and run/guard/operator messages remain integration work.

## Wire rules

All messages carry protocolVersion=1, connectionEpoch, requestId, robotId, runId,
activityId and operationId. IDs are nonblank strings of at most 64 characters.
The complete scope of a start is echoed by its accepted/running/rejected/terminal
messages. renewMotion/cancelMotion have their own requestId and reference the original
operationId plus generation; their command acknowledgements are outside this first
motion-result stream. Unknown fields and versions are rejected.

The runner allocates operationId before sending. Python will assign generation;
connectionEpoch must be fresh per connection, including after server restart.
Generation is a positive safe integer and only has meaning together with the epoch.
No globally unique generation across restarts is claimed.

| Variant | Additional fields |
| --- | --- |
| startMotion | goal: move(distanceM, speedMps) or turn(angleRad, speedRadS) |
| renewMotion, cancelMotion | generation |
| accepted, running | generation |
| rejected | reason |
| terminal | generation, outcome, reason, evidence |

Limits match the existing Python MoveCommand/TurnCommand: distance ±5 m, nonzero
magnitude at least 1e-9 m, speed 0.05–0.30 m/s; angle ±4π rad, angular speed
0.10–1.20 rad/s. The existing minimum nonzero turn is 1e-9 degrees; this check uses
explicit radian conversion. The later Python bridge must convert radians to degrees
at that legacy boundary. These are compatibility validation bounds, not a declaration
that every robot/scene may safely use the maxima. Python retains final limit checks.
All numeric inputs must be finite numbers, without string coercion.

## Results and evidence

Completed, cancelled and interrupted results require simulated or physical evidence.
Failed may carry evidence or not-started (this operation never actuated).
Stop-unconfirmed requires unknown evidence. The latter is not ordinary cancellation.
Evidence carries its backend epoch and observedAt, a nonnegative monotonic timestamp
in seconds within that epoch. It is never compared across backend epochs or with wall
time. The operation envelope identifies the operation/generation that it certifies.
Validation checks shape and semantics, not truth: only the backend authority can issue
credible evidence, and actual adapters still need qualification.

MotionClient registers correlation before transport.send. Synchronous terminal delivery
before acceptance therefore resolves normally, without a temporary early-event queue.
The first correlated progress/terminal fixes the generation; mismatching epochs,
identities and later generations do not settle the operation. The first terminal wins.
Malformed inbound data or rejection after acceptance closes the connection and rejects
pending promises as operation-uncertain; it never manufactures stopped/completed.
Transport loss/send failure does likewise. Connection disposal does not send a stop:
the server's independent lease/watchdog must stop motion. That integration is still pending.

MotionTransport delivers complete messages and disconnect notifications. Implementations
must bound framing/buffers, report parse/stream failure and avoid automatic motion retries.
The interface here is synchronous send, with asynchronous notifications; a future transport
must report later write errors through disconnect. No concrete stream transport is added.

## Bounded records and reference admission

MotionClient retains operation/request IDs, including completed tombstones, for the
connection lifetime (default 256). Duplicate starts and capacity exhaustion reject before
sending. No unresolved or completed obligation is silently evicted. Production session
rotation needs explicit close/recovery semantics before this limit is made configurable.

StartLedger is a reference server-admission model for conformance tests. A byte-order-
independent canonical request retry returns the original generation and duplicate=true;
only duplicate=false may schedule work. Conflicting reuse of either ID and full capacity
reject. It models neither robot ownership nor result replay. Python remains the eventual
owner; placing this model in TypeScript does not move authority into Node.

## Verification and next work

The initial 11 test cases were written before the module; their first execution failed
because it did not exist. After implementation those cases passed, and five additional
validation/lifecycle cases passed. This is test-first development of new code, not proof
that a previous production bug was reproduced. The existing 33 Node tests, including
7 Python subprocess trials, also passed. Strict TypeScript checking passed.
The existing CI wildcard includes these tests on Node 22/24 and the Python integration job.

Next adopt this contract at the Python boundary, with shared serialized fixtures to check
cross-language agreement; add run/guard/operator contracts and command acknowledgements.
Then consolidate the activity runner (B) and common authority (C). Step A is not complete
until both ends use the contract. Actual Simulator pose integration remains step D.
