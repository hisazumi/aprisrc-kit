# Reproducible service scenarios and traces

[日本語](service-scenarios.ja.md) · [Console operation](managed-service.md)

`apps/server/scenarios/runner/service-flows.json` defines synthetic inputs and expected
results separately from the executor. Each case uses the existing `myService`, operator
API and managed Node host in a fresh Python planar simulator on an allocated loopback
port. It never connects to the user's active console or physical robot.

| ID | Input | Expected result |
| --- | --- | --- |
| normal | Person, acceptance, loading answer plus independent clearance, arrival delayed 1.8 s | Completion; stationary waiting after finite motion |
| decline | Person followed by declining the offer | Normal completion without loading/following |
| operator-disconnect | Stop operator heartbeat and synthetic front updates during loading guard | Interrupted service, retained guard and inhibition |
| service-reconnect | Replace the service view during the offer, send an old-view answer, then answer from the new view | Reject stale answer, preserve run epoch, complete |

All cases assert zero final velocity, closed run, no pending I/O, expected guard,
position interval, question count and final speech where applicable. Delayed arrival
also checks unchanged pose after stopping. Declining is a successful business branch.

## Run

From the repository root, with the existing Node and Python dependencies:

```sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" \
  node apps/runner-prototype/scenario-demo.ts /tmp/aprisrc-scenario-traces
```

The command prints each verdict and writes one JSON per scenario ID. Any failure makes
the exit code nonzero. Reusing a directory replaces previous files for the same cases.
To run through the test runner:

```sh
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" \
APRIS_SCENARIO_TRACE_DIR=/tmp/aprisrc-scenario-traces \
  node --test apps/runner-prototype/service-scenarios.test.ts
```

Traces include the scenario/expectations, start time, relative elapsed time, questions,
answers, explicit clearance, reconnection, final result/pose/velocity/guard and motion
events. Failures retain the current state where available. No bearer tokens or auth
headers are logged. Inputs are bounded to 32 cases, traces to 256 entries each; unknown
fields, duplicate IDs, unsafe filenames and invalid values are rejected before startup.

This reapplies scenario inputs to a fresh environment. It does not replay recorded
motor commands or reuse historical operation generations to actuate anything. UUIDs,
timestamps and measured positions vary; reproducibility means satisfying the same
expected conditions for the same input, not bitwise-identical timing.

## Validation and limits

All four scenarios passed locally, along with all 153 Node tests and strict TypeScript.
CI's Python integration job runs them and uploads traces on success/failure with 14-day
retention. This configuration does not imply that a CI run has already been observed.

Disconnection here means stopping application-level operator updates, not an OS network
partition. View reconnection exercises the API, not browser rendering or timer throttling.
Existing integration tests continue to cover Node SIGKILL, double start and stale stop.
Real hardware, cameras, wireless failures and physical stopping remain outside this suite.
The cases provide a baseline for adding map/localization and perception-provider inputs.
