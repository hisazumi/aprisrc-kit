# Console-managed service lifecycle

[日本語](managed-service.ja.md) · [Connection binding](connected-service.md)

The console server now owns the fixed `console-service.ts` Node child. It uses the
same Python runtime, not a second simulator. The browser cannot choose executables,
source code or process arguments.

## Operation

From a source checkout, with the supported Node version on PATH:

```sh
uv sync --directory apps/server --frozen
uv run --directory apps/server python -m apris_server.operator_console
```

Open the printed `/console` and `/app` URLs. Acquire operator authority, enable the
synthetic front-clear observation, confirm clearance and recover. Press **サービス開始**.
There is no separate Node terminal command. Answer the service questions in `/app`;
loading clearance still requires the independent console confirmation.
After successful completion, **再実行** starts a new run. **サービス停止** revokes the run,
inhibits movement and terminates Node. Handover survives; stop completion and explicit
recovery are required before restarting. The existing manual test-run controls remain
separate, and manual admission is disabled during managed startup. Global stop also
stops a pending managed launch.

## Lifecycle

Only one managed process may be starting/running/stopping. Each launch has a fresh ID,
and each service has a fresh run epoch. Admission verifies the reserved launch and
operator, rejecting a stopped launch or changed operator. Stale stop requests cannot
stop a newer launch; questions and answers do not carry across runs. Process cleanup
only revokes that process's own run.

Stop first revokes Python authority, then requests Node termination. After 700 ms it
attempts kill; exit and output-drain waits are bounded. Output retains only a 4 KiB tail.
Missing Node and startup failures appear in the console, rather than being hidden by a
previous successful result. There is no automatic restart/replay.

This requires a source checkout including the Node host. Default origin is loopback
port 8766; tests may use another loopback port, passed consistently to the child.
This remains simulator-only, with no multiple-service scheduler or role-specific auth.

## Validation

Local validation passed all 148 Node tests, eight Python operator API tests, TypeScript
and Ruff. Real-process tests cover stop during startup, double-start rejection, normal
completion, rerun with new epochs/questions, stale answer/stop rejection, and retained
guard preventing restart after a handover stop. API coverage includes missing Node;
DOM coverage includes button eligibility and startup failures after a prior success.
These are not new physical-stop or real-browser visual qualification claims.
