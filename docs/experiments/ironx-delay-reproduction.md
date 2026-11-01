# Offline iron-X delay reproduction

[日本語](ironx-delay-reproduction.ja.md)

## Scope

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
