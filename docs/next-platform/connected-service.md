# Service host attached to the operator runtime

[日本語](connected-service.ja.md) · [Operator console](operator-console.md)

The Node host can now attach to the running Python console authority rather than
launching a second simulator. `runConsoleService` reuses `runFakeService`'s activity
runner, motion facade, questions and cleanup through a new HTTP transport binding.
The existing `myService` source is unchanged. Standalone fake/simulator demos remain supported.

## Run

From the repository root:

```sh
uv sync --directory apps/server --frozen
uv run --directory apps/server python -m apris_server.operator_console
```

Open the printed console URL. Acquire operator authority, explicitly confirm people
are clear, and recover. Enable synthetic front-clear observations. Do **not** start
a manual test run: the Node attachment will create its own run. Keep the console
visible in a separate window; a hidden operator tab stops operator renewal.

In a second terminal, set the token to the fragment after `#` in the printed URL:

```sh
export APRIS_CONSOLE_TOKEN='paste-the-current-token-here'
node apps/runner-prototype/console-service.ts
```

Open the printed `/app` URL in another visible window. Confirm the synthetic person
input, answer the existing service questions, and complete loading. A loading answer
alone does not release handover: use the **console** clearance checkbox and complete
handover there. Node waits for both the answer and operator clearance.

Follow remains a synthetic finite 0.08 m goal, with the existing 1.2-second progress
limit. Arrival must be answered before the goal ends; delayed answers cause a safe
service failure. The automated integration test answers promptly. This is not yet a
human-paced real tracking demonstration. Initial/person/loading questions can wait
within the attached host's two-minute total service budget while leases stay healthy.

Service completion closes its run and detaches the Node transport; Python and the
operator console stay alive. Stop, lease loss, server restart or transport loss does
not trigger automatic recovery or replay. A service page reload alone does not renew
or revoke the operator/run leases. Node alone renews the attached run; the console
alone renews the operator. Manual console motion/hold controls are disabled while a
service is attached; global stop, run close and operator clearance remain available.

## Questions and transport

The broker holds one current question, at most 128 question IDs and 128 speech entries.
Answers must match the current view ID, run epoch, question ID and offered choice.
Opening a new service view invalidates answers from the old view without canceling the
run. Duplicate, stale and extra-field answers are rejected. `/app` never supplies a
`humanClear` assertion. Consumption of a stationary answer also requires the Python
guard to be clear. Content is rendered as text, not HTML.

The HTTP binding uses the console's loopback/Origin/token checks and existing typed
control/motion contracts. Requests have a one-second timeout and 32-request capacity.
The transport checks a 256 KiB response limit. A sequence-numbered 128-event ring
supports polling; gaps and restart fail the connection instead of fabricating results.
It does not retry motion commands. Before reporting a motion-command error, it drains
preceding server events so a completion followed by a late renewal rejection is ordered
correctly. MotionClient still verifies exact scope and generation.

All demo pages and Node share the local bearer token. UI responsibilities are separated,
but this is **not role-separated network authentication**: a token holder can call the
other local APIs. Only the simulator is enabled. The existing production PWA and physical
rover startup paths are unchanged. The synthetic person/front inputs are not perception.

## Validation

Actual Node/Python/HTTP integration tests run the unchanged student service to completion,
check odometry displacement and final zero velocity, reload the service view and reject
its old answer, reject duplicate answers, and require independent guard clearance.
Separate cases expire the operator while Node remains alive, and SIGKILL an attached
Node process while the operator remains present. The run is revoked and guard survives.
A deterministic transport regression covers terminal-before-late-renew-error and event gaps.
HTTP validation and a DOM test exercise question limits, choice validation and the shipped
service page's scoped answer behavior and text rendering.

Local checks: 398 Python tests, 145 Node tests, strict TypeScript and Ruff passed.
This is real-process/HTTP plus DOM testing, not a real browser visual qualification or
physical stop certification. CI picks up the new tests; local checks do not claim a CI result.
Persistent guard storage, role-specific credentials, long-running tracking, and full
integration with the existing PWA remain follow-up work.
