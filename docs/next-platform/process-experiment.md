# Separate-process service and fake safety gateway

[日本語](process-experiment.ja.md) · [First experiment](runner-prototype.md)

Status: second isolated experiment, 2026-11-05. Runs the existing
[myService](../../apps/pwa/src/missions/myService.ts) unchanged in a separate Node.js
process through a fake StudentServiceApi. Mission/config locations and PWA behavior
remain unchanged. The first mailbox/epoch experiment remains separate; these are not
yet a unified production runtime.

## Run

Node.js 22.18+; initial local verification used 26.13.0. From the repository root:

```sh
node apps/runner-prototype/demo.ts
node --test apps/runner-prototype/*.test.ts
```

The demo prints separate gateway/runner PIDs, fake motion results, prompts and synthetic
answers, and service completion. Answers Yes / Items are loaded / We have arrived are
scripted test inputs, never evidence of actual human clearance. No dependency install
is needed for execution. With the repository's npm dependencies installed:

```sh
node node_modules/typescript/bin/tsc -p apps/runner-prototype/tsconfig.json
```

The gateway process (process-experiment.ts) forks service-worker.ts. The worker imports
the actual existing mission and supplies its API; the browser-oriented runStudentService
implementation is not imported. Greeting and route capabilities reject as unsupported.
Person input is synthetic, approach is an 80 ms fake operation, and following is bounded
to one second. No perception, tracking or vehicle kinematics is implemented. Short
timings suit automated tests, not manual interaction. The existing service has no clock
calls to migrate; pending movement uses the gateway's injected clock with virtual pause.

## Responsibility and deadlines

The gateway remains responsive when the runner blocks its event loop. It admits one
session, fences tokens by session/generation, manages handover inhibition and expires
authorization. Old stop/renew cannot affect another owner. Responses and terminal results
are correlated. Stop bypasses student event queues. No physical device is connected.

| Deadline | Experiment value | Renewal / clock |
| --- | --- | --- |
| Command TTL | 250 ms | Current token only; host monotonic time |
| Runner lease | 400 ms | Live-session heartbeat; host monotonic time |
| Operation progress | 1 s | Fixed at start, not renewable; virtual time |
| Stop evidence | 200 ms | Host monotonic time, including pause |
| Worker RPC / terminal wait | 2 s / 3 s | Client-side bounds; timeout is an error, not stop evidence |

Runner heartbeat/current-token renewal occurs every 40 ms; gateway checks every 10 ms.
These are experimental parameters, not measured safe physical stopping limits. OS
scheduling can delay checks; no real-time guarantee is claimed. Heartbeat alone cannot
extend command TTL; even continued command renewal cannot extend the progress deadline.
Acknowledged pause freezes virtual progress; host lease and TTL keep running.

Stopping invalidates pending fake actuation immediately, while evidence can be delayed
or suppressed. New movement is blocked pending evidence. Missing or late evidence yields
stop-unconfirmed, revokes the session and latches inhibition. It never becomes arrival.
Revocation during pending arrival evidence changes the terminal result to interrupted.
Explicit recovery asserts fake standstill and human clearance; it does not define a
physical recovery protocol.

Loading acquires a robot-wide guard. An answer additionally requires clearToMove=true;
Items are loaded alone does not clear the guard. Session/question IDs reject stale
and duplicate answers. Runner loss during handover retains inhibition.
The existing service ends with a request to take the belongings: **recipient unloading
inhibition/confirmation has not been added**. This remains a service-policy extension
needed for full S2 handover.

## Local operator/test protocol

Requests are newline JSON with id/type; responses have id/ok/value/error. Events
(prompt, terminal, revoked, say, service-result, worker-exited) arrive independently.
Match responses by ID and prompts by ID plus session, not by global ordering.

| Type | Fields / effect |
| --- | --- |
| start | Admit and launch unchanged service; return session and PIDs |
| answer | promptId/session/answer; stationary prompts require clearToMove=true |
| snapshot | Fake target, owner, inhibition, pause and runner state |
| pause / resume | Virtual progress only, not host watchdogs |
| stop | Revoke session; acknowledgement alone is not stop evidence |
| recover | confirmed=true asserts fake standstill and human clearance |
| fault | mode: kill/block/disconnect/stalled/missing-evidence/delayed-evidence/normal-evidence |

Block stalls only the runner for 1.5 s; disconnect closes IPC. Delayed evidence is
100 ms; missing evidence never arrives. Fault injection is test-only, not a RoverAdapter
requirement. Start a fresh process per trial. EOF revokes the session, terminates the
runner and keeps gateway timers alive through the stop-evidence window. This is a
trusted local harness/inherited IPC, not an authenticated multi-user/network API.

## Verification and remaining work

All 24 tests, strict typecheck and demo passed locally on Node.js 26.13.0,
including revocation during pending arrival evidence. The GitHub Actions workflow
also runs the tests, typecheck and demo on Node.js 22 and 24; inspect its results
for those environments.

Coverage: original nine contracts; eight deterministic gateway cases (TTL, lease,
progress, delayed/missing evidence, fencing, guard and arrival/revocation race); seven
subprocess cases (normal/decline, kill/block/IPC loss during pause, missing/delayed evidence).
Existing PWA/Python source and runtime paths are unchanged; their suites were not rerun.

Next define Python-server admission/running/terminal messages, stop evidence and lease
ownership, then attach through a fake adapter. Preserve speed/clearance/E-stop/device
protections. Add operator-session loss, camera loss, gateway death and downstream
device-watchdog tests before hardware trials. A gateway crash cannot be protected by
the fake backend in that same process.

Still absent: Python integration, production facade/clock abstraction, UI reconnect and
role authorization, physical stop evidence/TTL/speed/clearance verification, persistent
jobs, map/localization/perception, mailbox integration, gateway-crash qualification,
WSL packaging and ROS/Hakoniwa. Stop evidence refers only to synthetic actuation invalidation.
