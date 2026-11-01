# Offline iron-X delay reproduction

[日本語](ironx-delay-reproduction.ja.md)

## Scope

**Current experiment:** ownership alone is 2 seconds (`OWNERSHIP_LEASE_SECONDS`),
nonce validity remains 300 ms (`NONCE_SECONDS`), and the PC command TTL ceiling
remains 200 ms. No NOP or heartbeat is added. The robot-side gateway has **not**
been updated or restarted; the live robot still uses its previous 300 ms lease.
The earlier 300 ms experiments below are historical baselines, explicitly selected
in tests with a temporary test-only override.

Experimental branch: `experiment/ironx-delay-reproduction`, based on `5c7844d`.
Keep this work in a separate worktree. Do not restart the demonstration servers,
change their environment, switch their checkout, or deploy this experiment to iron-X.
Only this experimental worktree changes recovery classification. The demonstration
checkout, safety thresholds, speed limits and command TTL remain unchanged.

The November 1 trial logs showed ownership expiry (`not_owner`) and a `stopping`
reply classified as transport loss. These tests reproduce the **failure mechanisms**,
not the exact recorded packet timing or the physical cause of every trial failure.
Raw logs, private tokens and robot addresses are not included.

## Run

From this experimental worktree, using Python 3.11 or newer and the server dev dependencies:

```powershell
cd apps/server
uv sync --group dev
$env:PYTHONPATH = "src"
uv run pytest tests/test_ironx_delay_reproduction.py -v
```

macOS/Linux: use `export PYTHONPATH=src` instead of the PowerShell assignment.
Run the same command repeatedly to check scheduling sensitivity. For related coverage:

```sh
uv run pytest tests/test_ironx_delay_reproduction.py tests/test_ironx_network_adapter.py tests/test_ironx_gateway.py -q
```

The tests bind **only `127.0.0.1` on an automatically allocated port** and use a
fixed test token. They do not load the real gateway URL, ROS configuration, or
mailbox files. Temporary servers and watchdog tasks are closed after each test.
They do not require the browser, iPhone, SSH tunnel, or robot. Local socket access
must be permitted by the execution environment.

## Experiments

The production `IronXNetworkAdapter` and `IronXGateway` communicate over real
loopback WebSockets. A test-only gateway delays request handling or completed
responses. The production ownership watchdog runs; a fake robot records drive
and stop calls without controlling motors.

| Case | Injected condition | Observed / asserted result |
| --- | --- | --- |
| Small variable delay | Drive replies delayed 10, 20, 40, 10, 20 ms; 20 ms between calls | Five commands accepted; no rearm required; explicit stop releases ownership. |
| Ownership expiry | After one command, wait 160 ms; delay the next state reply 180 ms | The 300 ms lease expires; next drive is rejected with `not_owner`; stop confirmation uses the surviving connection; no automatic replay. |
| Stop in progress | Delay the next drive request 360 ms; hold fake stop confirmation with an event | Watchdog begins stopping; gateway returns `stopping`. Baseline closed the connection; the experimental fix retains it, waits for stop confirmation, and still requires explicit rearm. |
| Reply timeout | Delay the state reply 400 ms | The state RPC times out; no drive reaches the fake robot; subsequent drive is blocked pending rearm. |
| Non-owner rejection | Reject acquisition while gateway is not ready | A client without ownership does not issue stop confirmation or stop another controller's robot. |

The stop-in-progress test first reproduced the baseline defect, then became a
regression test for the experimental fix: classify `stopping` only for an owned
drive, keep the connection, invalidate cached commands, require rearm, and confirm
stop before claiming success. It checks that confirmation remains pending while
the fake stop is held. The hold is always released during test cleanup.
Actual timeouts still follow the transport-failure path. This does not eliminate
ownership expiry or improve the underlying network; it avoids a misleading
disconnect classification and permits confirmation on the surviving connection.

## Limits and follow-up

Execution record (2026-11-01, macOS, Python 3.12.13): all four experiments passed;
three further runs passed 4/4 each (1.24-1.26 seconds per run). The combined
experiment/network-adapter/gateway suite passed 69 tests in 9.46 seconds. Ruff
passed for the added test file. The demonstration checkout remained at `5c7844d`
with no changes to tracked files. No production restart, SSH command or physical
motion was performed as part of this experiment.

After the experimental recovery change, all 284 server tests passed in 31.49 seconds;
Ruff passed on both changed Python files. The non-owner case deliberately retains
the existing acquisition-failure path (including its local stop error) and verifies
that no remote stop is sent. General rejection classification remains future work.
No change has been merged into main or deployed to the demonstration server.

## Reducing avoidable lease expiry

Checkpoint `750f811` saves the initial reproductions and the stopping-response fix.
The next experimental change targets redundant display polling, not lease duration.
While the PC owns control, fresh connected telemetry (conservatively aged under
100 ms) is reused for display instead of starting a state RPC that can hold the
same connection's RPC lock ahead of the next drive. The timestamp is not reset,
ownership is not renewed by reads, and stale/idle/rearm-required state is not
eligible for this shortcut. Existing in-flight-command polling behavior remains.

New regression: after one drive, delay standalone state replies by 320 ms. Baseline
started that redundant RPC, returned stale/disconnected telemetry and expired the
lease. With the change, 12 display/drive cycles (20 ms between cycles) reuse fresh
telemetry and accept 13 total commands without the delayed extra read. Separate
tests verify that a 120 ms-old cache is refreshed and idle polling still uses RPC.

This does **not** tolerate arbitrary 320 ms delays on drive messages, prevent all
lease expiry, or automatically reacquire expired control. The original delayed
state, delayed drive and actual timeout experiments remain and must still stop or
reject motion. Lease (300 ms), command TTL ceiling (200 ms), telemetry freshness
threshold and speed limits are unchanged. A separate telemetry connection or a
different scheduling protocol would require further design and testing.

Validation after this change: 287 server tests passed in 31.93 seconds; the final
eight delay experiments passed in 1.71 seconds, including assertions that display
reuse changes neither the ownership deadline nor the cached acquisition time.
Ruff passed on both Python files. This is offline evidence only, not physical
validation or proof of robustness on the university network.

## Ownership-only two-second experiment

The gateway previously used one constant both for ownership and nonce timestamps.
These are now separate; the nonce issue-time calculation also retains the 300 ms
constant. Acquisition and successful drive set a 2 s ownership deadline. State
reads, reacquisition by the same owner, and failed drive do not renew it. Explicit
release, disconnect, E-stop and failed-drive stopping remain unchanged.

Additional checks:

- With the injected clock, ownership survives 1.999 s and expires exactly at 2 s;
  another client cannot acquire it before expiry.
- After 400 ms or 1.5 s without drive, the same owner can send a **fresh** nonce and
  command. A real loopback WebSocket test also confirms recovery after a 400 ms gap.
- An old nonce remains invalid after 300 ms, even while ownership is valid.
- The actual mailbox writer and command-bridge lease logic (using temporary files
  and mocked telemetry/stop feedback) produce zero output by 210 ms for a 200 ms
  command while the gateway still owns control at 400 ms. This is software output
  validation, not measured wheel stopping.
- Existing expiry tests now wait for 2 s. Historical 300 ms reproductions explicitly
  override only the ownership constant within those tests.

A remaining failure is exposed by a 320 ms background state RPC: the old nonce is
pruned, a queued drive gets `invalid_nonce`, and the existing PC error path still
classifies it as transport failure. The test characterizes this remaining defect;
it is not fixed by lengthening ownership. No broader recovery change is included.
Likewise an expired drive can still revoke ownership through the unchanged error
path. Two-second ownership does not promise uninterrupted following.

Validation: all 293 server tests passed (38.53 s), including the temporary-mailbox
watchdog test. Ruff passed for all six touched Python files. No live gateway/server
restart, remote deployment, E-stop reset or movement was performed in this step.

- These are fixed delay schedules using real wall-clock time, not a seeded
  packet-loss model or exact replay. A heavily loaded test host can affect timing.
- Fake robot state is stationary; it does not integrate wheel physics or implement
  the motor-side command TTL watchdog. Assertions on accepted TTL and gateway stops
  do not establish stopping distance, braking, tracking smoothness, or wheel motion.
- Browser camera timing, browser-to-PC transport, SSH buffering and Wi-Fi are not
  simulated. A received gateway error is evidence of a response, not proof of an
  actual radio disconnection.
- After the demonstration, use these reproductions to design distinct handling for
  received stop/expiry refusals versus transport failures. Test stale-command discard
  and stop confirmation before considering any deadline changes.
- Keep production deployment and physical stopping tests separate. Do not merge or
  deploy experimental changes before the demonstration.
