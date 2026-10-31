# iron-X command watchdog bridge

Status: implemented with unit tests and one supervised wheels-raised command-loss
test. The telemetry bridge and `/ros2` monitor remain read-only.
The mission API is unchanged; service-to-motion integration is not enabled here.

An experimental same-host Kit Adapter is now available in
[iron-X Adapter](ironx-adapter.md). Its file-command path is separately tested in
software and has not yet been motion-tested on the robot.

## Contract

Run on the robot with ROS Humble and the existing isolated driver setup described
in `ironx-motion-probe.md`. Input is `/apris/command_velocity`,
`geometry_msgs/TwistStamped`, frame `base_footprint`. Use robot ROS time for stamps
and refresh commands at 20 Hz. Only linear.x and angular.z are supported;
limits are 0.05 m/s and 0.2 rad/s. Other components must be zero.

The bridge publishes `Twist` at 50 Hz to `/apris_readonly/no_commands`, the
driver's currently remapped command topic. Do not publish directly to that topic
or run the earlier direct-motion probes while the bridge is enabled.

A command expires 300 ms after its source timestamp, using a monotonic deadline
after receipt. Expiry produces repeated zero commands, not silence. Transport
age reduces the remaining lease. Invalid, future, duplicate and out-of-order
commands clear motion. Missing wheel telemetry clears motion; recovery alone
does not restore the previous command. Fresh commands can resume after a timeout.
Competing publishers, driver connection changes and control-loop delays latch a
stop requiring bridge restart. ROS graph discovery is not an ownership lock:
another publisher can still bypass this protection, so isolate the command path.

## Start

First stop command senders and keep the wheels raised. Default mode only checks
the driver graph and fresh stationary wheel telemetry; it creates no publisher:

```sh
python3 -B scripts/ironx_command_bridge.py
```

Only after explicit operator approval:

```sh
python3 -B scripts/ironx_command_bridge.py --enable > .runtime/ironx/command-bridge.jsonl 2>&1
```

JSONL logs input acceptance, output velocities, monotonic time and stop reasons.
Normal exit, SIGINT and SIGTERM send repeated zeros for one second.

## Validation and limits

The prior direct-driver test retained roughly 0.05 m/s for about 0.65 seconds
after the last command. Only fallback zero commands stopped it. This does not
exclude a longer controller watchdog, but a short command-loss stop is unproven.

Supervised test procedure: send stamped commands briefly, stop the sender, and correlate
`command_timeout`, zero output and raw wheel velocity. Use an independent bounded
fallback stop as in `ironx-command-silence.md`, adapted so it does not compete with
the bridge during the observation window. Do not run the old direct probe unchanged.
Keep power accessible and obtain approval before motion.

On 2026-10-31, the wheels-raised run recorded `command_timeout` and zero output
0.304 seconds after the last input command. Raw wheel velocity first reached zero
at approximately 0.794 seconds and stayed zero in subsequent samples, before the
fallback cutoff at approximately 0.944 seconds after the last command. The final
observation was stationary, and the fallback process exited. Logs on the robot:
`.runtime/ironx/bridge-stop-probe-01.jsonl` and
`.runtime/ironx/bridge-stop-controller-1793430486874859959.jsonl`.
Related automated tests: 39 passed. This single test validates upstream command
cessation with a live bridge, not floor braking distance or bridge/OS failure.

The prepared runner is `scripts/ironx_bridge_stop_probe.py`. Without arguments it
only checks stationary wheel telemetry and the isolated graph, creating no command
publishers or subprocesses. With `--execute` (operator approval required), it
starts a temporary bridge, sends 0.05 m/s for 0.4 seconds, then stops sending.
A separate fallback process creates its direct zero-command publisher only at
1.3 seconds after pulse start (or earlier on an abort), so its presence cannot
trigger the bridge's competing-publisher stop during the observation window.
Discovery adds latency to the fallback; it is not a hard real-time safety limit.
Only wheel samples before fallback creation count toward the stop assessment.
The bridge output/reason log is stored separately under `.runtime/ironx/` and its
path is printed by the runner. Both logs use the same host monotonic clock.
Check for `command_timeout` in that log before attributing the stop to the watchdog;
stopping due to another fault is not a successful timeout test.
The runner stops its own bridge at the end and leaves the existing telemetry
bridge, driver, server, and SSH connection intact.

```sh
# Non-motion preparation
python3 -B scripts/ironx_bridge_stop_probe.py
# Only after explicit approval
python3 -B scripts/ironx_bridge_stop_probe.py --execute > .runtime/ironx/bridge-stop-probe-01.jsonl 2>&1
```

300 ms is the command lease, not a guaranteed physical stopping time. Scheduling,
transport and braking add latency. This bridge protects loss of the upstream
sender only while the bridge and downstream path work. SIGKILL, process hangs,
OS failure, serial failure and motor-controller failure require an independent
downstream watchdog or hardware stop; they are NOT covered by this implementation.
