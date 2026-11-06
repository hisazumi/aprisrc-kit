# Consolidated service host and bounded transport

[日本語](service-host.ja.md) · [Activity runner](activity-runner.md) · [Integration plan](integration-plan.md)

runFakeService in apps/runner-prototype/service-host.ts now owns startup, the bounded
JSON-lines connection, typed control admission, activity execution and shutdown.
It executes the existing myService.ts unchanged using StudentServiceApi. Only the
existing fake Python port can be launched; no physical adapter selector is exposed.
This consolidates the host duties previously performed inside integration tests.

## Run the integrated example

From the repository root:

~~~sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node apps/runner-prototype/host-demo.ts
~~~

The example supplies synthetic person input, operator presence, answers and human
clearance. It prints a fake-only report. Completion should show moving=false,
session=null and closed=true. This is not a camera/following demonstration.

## Lifecycle and student facade

1. Spawn Python and read its control epoch. Inject explicit test-only front clearance.
2. Admit an operator, require initial recoveryClearance=true, explicitly recover,
   then admit a new run. Never automatically reconnect or replay a motion.
3. Create MotionClient and ActivityRunner. Renew operator permission only while
   inputs.operatorPresent() reports presence; maintain run health separately.
4. Run the student definition with scoped movement, questions and cleanup. On service
   failure, timeout, transport loss or runner failure, interrupt service waits.
5. Fence/join the activity tree while maintaining host health for stop evidence, then
   closeRun. If closure fails, attempt globalStop. Read a final diagnostic snapshot,
   close transport/stdin, await child close, and escalate to process termination if needed.

The host observes close rather than only exit, so a failed executable spawn cannot
hang cleanup. Graceful child shutdown allows 700 ms before SIGKILL, with a 1.5 s final
wait bound. The default service budget is 5 s and managed activity cleanup uses its
existing 1 s limit. These are fake-test settings, not qualified hardware budgets.
A final snapshot is a diagnostic sample; closing/stopPending alone is not stop proof.

The facade preserves ask/choose/confirm labels and phrase metadata and rejects invalid
or duplicate choices. confirm and waitForLoaded acquire a Python handover guard.
A valid service answer alone is insufficient: the input provider must separately set
humanClear=true before the host requests clearHandover. Cancellation/failure retains
the guard. An ordinary question never issues an unscoped stop.

waitForPerson is supplied by a synthetic input provider. approachPerson uses a bounded
0.008 m fake goal; followPerson uses a bounded 0.08 m fake goal and cancels/joins it on
arrival input. Natural goal completion before arrival is failure, not successful
following. greetPerson and guideTo reject as unsupported. The existing final unloading
speech still is not a guarded recipient-confirmation workflow. The service's source
is unchanged, but perception, tracking, navigation and speech execution are not claimed.

Input providers receive an activity AbortSignal. Host cancellation also bounds its own
wait even if a provider ignores that signal. Student code and providers run in Node;
arbitrary CPU-blocking code still requires process isolation for host responsiveness.
Python deadlines remain independent, but physical stopping after Python death is not
qualified here. Role authentication and ordinary browser reconnect remain future work.

## Transport limits and failure handling

JsonLineRpc in json-line-rpc.ts handles fragmented and batched UTF-8 JSON lines,
including events arriving before a reply. Limits are 64 KiB per frame, 32 pending
requests, 128 KiB of queued writable data, 16 event subscribers and a 1 s request
response deadline. Capacity rejects before admission. Framing errors, stalled writes,
stream errors/EOF and timeouts fail outstanding requests as uncertain and fence new
requests. There is no automatic retry queue. Diagnostic stderr and speech output are
bounded as well. This is trusted local pipe transport, not an authenticated network API.

Python input is also bounded: oversize or unterminated frames close the port without
interpreting their remainder as another command. Closing invokes its existing revoke/
stop path. The host's limits do not qualify every internal server queue for production.

The first full-service test found a completion/renewal race: a late renewal rejection
could interrupt the next service step. Python now acknowledges renewal during finishing
without extending TTL or the stop deadline. MotionClient ignores a renewal/cancel error
only when the exact operation scope/generation already has a terminal result. Other
errors remain failures. The fix does not permit an old command to operate on a new owner.

## Verification and next step

Local results: Node 137 tests, Python 99 tests, strict TypeScript, Ruff and host-demo
passed. New tests cover frame boundaries, pending/write capacity, timeout/EOF, unchanged
service normal/decline paths, retained handover on missing human clearance, service
exceptions, unresponsive input, missing executable, missing stop evidence, independent
operator loss and external cancellation. Regression tests cover the renewal race and
Python oversized-frame rejection. CI includes the integrated demo and all new tests.

Next is shared-server authority/guard integration (C): legacy/manual and runner paths
must enforce the same interlock. Then replace PortFakeAdapter with actual Simulator
pose/odometry execution (D). Current PWA startup is unchanged; this host is a reusable
fake-backed integration entrypoint, not a released deployment profile.

See [Shared runtime motion authority](shared-authority.md) for the subsequent runtime-boundary implementation.

See [Planar simulator integration](simulator-integration.md) for the subsequent simulator backend.
