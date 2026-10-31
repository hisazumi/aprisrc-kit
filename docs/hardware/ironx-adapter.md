# iron-X service Adapter (experimental)

Start with [iron-X supervised operation](ironx-quickstart.md)
([日本語](ironx-quickstart.ja.md)) for the normal setup and console workflow.

Implemented against the unchanged RoverAdapter / bounded-motion API. Automated
tests cover mailbox expiry, move/turn feedback, cancellation, stop confirmation,
and invalid input. The Adapter and file transport passed supervised wheels-raised
drive/stop and cancellation trials on 2026-10-31, followed by short floor moves
and a small left turn. The server was then switched to `ironx`; supervised console
motion with time-limited manual clearance was confirmed by the operator.
Service mission UI integration remains untested. Diagnostic trials use a temporary,
isolated command bridge; they must not run alongside the active service bridge.

## Recorded hardware trials

- Initial Adapter trial failed before motion because ROS requires float velocity
  components and the file transport supplied integer zero. Components are now
  normalized to float, with a regression test and a real ROS message construction check.
- `adapter-probe-02.jsonl`: 0.04 m/s command for approximately 0.4 seconds;
  velocity rise observed in server telemetry; stop confirmed after 0.780 seconds,
  before independent fallback stopping.
- `adapter-cancel-01.jsonl`: a bounded move was cancelled after 0.4 seconds;
  zero output followed after approximately 16 ms, and stop confirmation after
  0.782 seconds, before fallback. This does not validate target completion.
- `adapter-floor-01.jsonl` and `adapter-floor-02.jsonl`: two 10 cm forward goals
  completed with stopping before fallback. Reported forward displacement was
  9.638 cm and 9.634 cm respectively. The operator reported the first looked good
  and requested the repeat; no independent ruler measurement was recorded.
- `adapter-turn-01.jsonl`: a left 15-degree goal completed with stopping before
  fallback, reporting 14.911 degrees. The operator estimated approximately
  15 degrees visually. This is a coarse check, not precision calibration.

Logs reside under `.runtime/ironx/` on the robot and are not committed. The runner
is `scripts/ironx_adapter_probe.py`: default mode starts no publishers; use
`--execute` only with operator approval, adding `--cancel` for cancellation.
All trials ended stopped and shut down their temporary bridges. SSH, telemetry,
and the read-only server were left running.

## Initial calibration scope

For an MVP, first verify forward/turn signs, rough distance and yaw scale, and
stopping behavior on the actual floor. Encoder/EKF feedback is closed-loop but
cannot correct a biased wheel scale or detect all slip. Camera-relative following
can correct some relative-position error, but does not replace these basic checks
or validate odometry-based bounded moves. Precision tuning can follow the first
short, low-speed floor trials.

## Architecture

Kit server (separate Python environment) -> atomic local command file -> ROS Humble command bridge
(Python 3.10) -> isolated iron-X driver -> motor controller.
The existing telemetry bridge supplies EKF pose and velocity to the server.
The command bridge also requires fresh raw wheel odometry.

These processes must run on the same Linux host: timestamps use the host monotonic
clock. Use a private runtime directory writable only by the operator account.
This is not a network protocol or a multi-user security boundary. One Kit process
owns the mailbox via a file lock. Do not run another motion sender or overwrite
its mailbox manually. File mode does not subscribe to the ROS command input topic.

Every drive call writes a new ID and creation time; the bridge only consumes each
new file content once. Reading the same file does not refresh its TTL. TTL is
limited to 300 ms, and transit time consumes the lease. Files older than bridge
startup are rejected. The bridge writes its output, reason, last accepted ID and
heartbeat to a separate status file. A stale or faulted heartbeat disables motion.

Bounded moves use signed displacement along the starting heading; turns accumulate
wrapped yaw differences. They require fresh feedback, have deadlines, and fail on
excessive lateral drift or overshoot. Completion requires target tolerance plus
an acknowledged zero command and at least three fresh stationary observations
spanning 200 ms. Cancellation sends zero and waits for stop confirmation.
An unconfirmed stop raises an error rather than claiming success.

Initial limits: 0.05 m/s, 0.2 rad/s, 1 m per move, pi radians per turn, 120 seconds
maximum goal duration. Bounded speed is capped; direct Adapter calls outside speed
limits are rejected. Kit runtime limits are set accordingly for `APRIS_ADAPTER=ironx`.
Small final tolerances are 3 cm / 0.08 rad. Floor accuracy, braking, heading control
and EKF calibration remain unqualified. Pose reset remains disabled.

## Configuration for a later approved test

Do not run these activation commands while somebody is handling the robot.
Use absolute, distinct paths and an existing private directory. Example environment
for the server, with `ROOT` pointing to the repository on the robot:

```sh
export APRIS_ADAPTER=ironx
export APRIS_ROS2_STATE_FILE="$ROOT/.runtime/ironx/state.json"
export APRIS_IRONX_COMMAND_FILE="$ROOT/.runtime/ironx/command.json"
export APRIS_IRONX_BRIDGE_STATE_FILE="$ROOT/.runtime/ironx/command-status.json"
```

In a ROS-sourced shell, preflight only (no publisher):

```sh
python3 -B scripts/ironx_command_bridge.py \
  --command-file "$ROOT/.runtime/ironx/command.json" \
  --status-file "$ROOT/.runtime/ironx/command-status.json"
```

Only after operator approval, add `--enable`, then start the Kit server with the
environment above. Do not enable both ROS-topic and file-command bridges. Stop
the command bridge only after motion has stopped. Shutdown of the Kit server tries
to send zero and confirm stopping; failure is reported.

The existing front-obstacle and control-ownership checks remain in force. The
Adapter does not fabricate clear-path observations or wire LiDAR into perception.
Forward service commands can still be refused when perception is unavailable.

Floor probe modes are `--floor-move` (10 cm, up to 0.04 m/s) and `--floor-turn`
(left 15 degrees, up to 0.15 rad/s). They remain preparation-only unless
`--execute` is also specified. Motion goals have a 4.5-second deadline; an
independent fallback is armed for 6.5 seconds after launch preparation.

Next check: validate a service through the UI, including perception, ownership,
stop and cancellation. Console manual motion is already confirmed. For a new setup,
start read-only until the operator approves activation. Do not treat the read-only
`/ros2` monitor as a motion-control page.
The console is `/console` on the same server and uses the same-host `/ws` endpoint.
Forward motion still needs an explicit, valid clear-path observation; do not bypass
that gate just to demonstrate movement. Obtain explicit approval before motion.
Bridge/OS/serial failures still need an independent downstream watchdog; see
[command bridge](ironx-command-bridge.md) and [porting guide](service-hardware-porting.md).
