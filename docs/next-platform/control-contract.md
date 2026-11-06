# Run, handover and operator control contract

[日本語](control-contract.ja.md) · [Integration plan](integration-plan.md) · [Motion contract](motion-contract.md)

Implemented in the existing fake RunnerPort, not the shared FastAPI application.
TypeScript and Python decode the same 22 serialized control fixtures. The current
application startup and hardware adapters are unchanged.

## Identity and trust

The local experiment exposes {action: "control", message: <control-v1>} over its
existing inherited-pipe transport. Read controlEpoch from the legacy snapshot during
bootstrap. Every message carries protocolVersion=1, connectionEpoch=controlEpoch,
requestId and robotId=fake-only. The control epoch is server-generated per port instance.
The separately generated runEpoch is the motion contract's connectionEpoch/session.
Old control epochs, run epochs, operator IDs and guard IDs cannot authorize new actions.

This is a trusted local test boundary. openOperator is not login or proof of a human's
identity; a caller with pipe access is trusted. The eventual network/session boundary
must enforce /app, /console and /lab roles and protect the issued identifiers.
No assertion of authenticated multi-user operation is made here.

## Commands

| Command | Fields beyond the common envelope | Effect |
| --- | --- | --- |
| openOperator | none | Issue operatorId and start its independent lease; inhibit motion until explicit recovery |
| operatorHeartbeat | operatorId, sequence | Extend only the operator lease for a newer sequence |
| openRun | operatorId, runId | Require live operator, no guard/inhibition/old I/O; issue runEpoch |
| runnerHeartbeat | runId, runEpoch, sequence | Extend only the run lease for a newer sequence |
| closeRun | runId, runEpoch | Revoke that run and initiate scoped stop; keep any guard |
| acquireHandover | runId, runEpoch | Confirm stationary evidence, acquire guardId, inhibit movement |
| clearHandover | operatorId, guardId, confirmed=true | Explicit human clearance releases that guard; does not clear other inhibition |
| globalStop | none | Revoke current run and latch inhibition, independent of run identity/queue capacity |
| recover | operatorId, guardId or null, confirmed=true | Require exact current guard identity, no run/motion/pending I/O and backend stop evidence; clear guard/inhibition |
| snapshot | none | Observe state without renewing any lease |

All accepted controls return controlReply with the command name, operatorId, runId,
runEpoch, guardId (nullable), inhibited and stopPending. Close/stop acknowledgement means
accepted termination, not confirmed standstill. A motion terminal still supplies the
separate stop evidence. stopPending means an operation or old I/O remains, including
ordinary motion; it is not a physical-stop measurement. Invalid controls return an error
in the existing outer reply. A runId is used only once per port lifetime.

A guard outlives questions, run close and operator loss. A stale close cannot terminate a
new run. clearHandover/recover require backend evidence and matching guard identity, so a
late human response cannot release a different handover. Experimental evidence is still
fake-only: this does not qualify human access on a physical rover.

## Leases, duplicate requests and stop paths

The operator lease is independent of the runner lease and motion TTL/progress budget.
Its current experimental value is 400 ms, not a measured production value. Expiry is
checked before request dispatch and by the watchdog. Operator expiry revokes the run,
initiates stopping and latches inhibition; a delayed heartbeat cannot revive the operator.
A new operator and explicit recovery are required. Runner heartbeat cannot keep the
operator alive, and neither heartbeat renews motion TTL or its progress deadline.

Heartbeat sequence numbers are positive safe integers. Only a larger sequence extends
its lease; repeated/older sequences acknowledge current state without extending time.
They use fixed-size per-owner state, not an ever-growing heartbeat deduplication log.
Snapshot has no lease effect. Ordinary browser lifecycle is not represented as an
operator heartbeat: the future UI integration must preserve that distinction.

Other controls retain successful replies and rejected-request reasons by requestId
(default 256 records per port lifetime). Exact retry returns historical acknowledgement
or rejection without executing again; conflicting reuse rejects. In particular, retrying
an old successful open/close does not reopen or close a later run. A returned historical
reply is not a fresh snapshot or renewed authority. Full storage rejects new business
controls. Global stop, snapshot and both sequenced heartbeats bypass that storage limit.
Global stop deliberately applies to the current robot state even when repeated; never
automatically replay it on reconnect. Production retention/session rotation is still open.

After openOperator enables typed-control mode, legacy admit/heartbeat/move/hold/clear/
recover calls cannot bypass it. The typed motion action, test fixtures, read-only legacy
snapshot and stop-only legacy revoke remain available. Internally all paths share the
same port lock and expiry checks. This is not yet the global guard across other FastAPI
clients; that remains integration step C.

## Verification and next step

Tests were written before implementation. The 22 fixture cases passed after decoder
implementation, while five port-behavior tests still failed before wiring. After wiring,
additional operation-stop and epoch/retry cases were added. Coverage includes:

- Guard blocks motion and survives run close; explicit matching clearance permits a new run.
- Operator expiry beats renewal, preserves guard and interrupts an actuating fake operation.
- Global stop acknowledges with stopPending before terminal evidence arrives.
- Duplicate heartbeat cannot extend time; snapshot does not renew leases.
- Full request storage still permits stop and state inspection.
- Missing evidence blocks recovery; legacy calls cannot bypass typed-control mode.
- Old control epoch and cached old close cannot terminate a new run.

Local validation: Node 107 tests, Python 97 tests including existing motion/port/runtime
regressions, strict TypeScript and Ruff. A Node subprocess case executes typed operator
admission, recovery, run start, handover clearance and motion through the actual Python
port. CI includes the new fixtures, Python tests and lint targets.

Next consolidate the activity tree/mailboxes and capability facade into one runner (B),
and replace the test stream harness with a bounded production transport. Then enforce
shared authority/guard across server clients (C), followed by actual Simulator pose changes
(D). Persistent guard state, authenticated UI recovery and physical stop qualification
remain separate work; the fresh typed-control path starts inhibited after every restart.
