# Shared runtime motion authority

[日本語](shared-authority.ja.md) · [Service host](service-host.md) · [Integration plan](integration-plan.md)

This implements the runtime boundary of integration step C. `RoverRuntime` now owns a
motion interlock shared by manual/legacy commands and the experimental runner port.
The existing owner checks, limits, TTL, and E-stop checks remain in force.

## Behavior

- A runner handover guard or inhibition blocks manual and runner drive/move/turn,
  including after ownership changes. Stop and E-stop remain available.
- Each inhibition reason has a private token. Clearing one reason cannot clear another;
  clearing E-stop does not clear a handover guard.
- Requests capture an interlock epoch before asynchronous work. A hold or release
  changes that epoch, so an old delayed request cannot emit motion after clearance.
  This epoch is distinct from protocol connection epochs and operation generations.
- Handover acquisition rejects pending adapter effects, active motion tasks, and a
  live command deadline, in addition to the port's existing fake stationary evidence.
- Pending runner cleanup and legacy stop, release, disconnect, E-stop, operator-stop,
  and failed-drive cleanup hold the shared interlock across stop I/O. A newly acquired
  owner cannot move while that cleanup is pending.
- `status.control.motion_interlock` exposes reasons, epoch, and pending effect count
  for diagnosis. Tokens remain private.

`RunnerPortExperiment(runtime=...)` can use an already started runtime without owning
its lifecycle. Closing the port does not close that runtime or unrelated manual clients.
Injection accepts only the exact `PortFakeAdapter` type; this is not a real-adapter enablement.
The default subprocess host still creates its own fake runtime.

## Verification

Nine new regression tests cover manual drive/move/turn during handover, independent
inhibition reasons, delayed drive and bounded turn admission across hold/release,
pending adapter effects, shared-runtime lifetime, runner disconnect stop I/O,
legacy disconnect stop I/O, and rejection of an unqualified adapter.
The disconnect regression reproduced new-owner motion before the old stop completed.

Local checks passed: all 386 Python server tests, all 137 Node runner tests, strict
TypeScript, and Ruff. CI now runs the full server test suite as well as runner tests.
These counts describe local checks, not an observed CI result.

## Limits and next step

The interlock prevents new dispatch; acquiring it is not a stop command or physical
stop evidence. An already dispatched effect still needs cancellation/stop and evidence.
The primitive assumes one event loop; it is not a cross-process mutex.

No authenticated runner endpoint, recovery UI, or persistent guard store is added.
A held guard survives closing an injected port in the same runtime; a replacement
port has no implemented operator recovery workflow for that orphaned guard.
Legacy stop failures retain existing handling; this change does not establish a
new hardware stop-failure qualification policy. Process restart and real devices
still require a separate safety design and validation.

Next is step D: exercise actual simulator pose/odometry through the same boundary.
The current fake adapter models bounded-operation timing, not physical travel.
