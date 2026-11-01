# iron-X supervised operation

[日本語](ironx-quickstart.ja.md)

Experimental iron-X Pro Max / ROS 2 Humble integration, checked on 2026-10-31.
For PC/iPhone service operation, start with [person following](ironx-follow.md).
This reference covers the alternative same-host server and manual Console setup.
Use [Adapter details](ironx-adapter.md) for contracts and historical trial evidence.
UGV02 remains the reference hardware path.

## What works and what remains

Verified on one robot: telemetry, Adapter drive/stop and cancellation, two short
floor moves, a left turn, and operator-console motion with manual path confirmation.
The two 10 cm goals reported 9.638/9.634 cm; the 15-degree goal reported 14.911 degrees.
The operator reported plausible motion and approximately 15 degrees, not a precision
measurement. Later PC/network/iPhone following received a successful operator report;
the latest stop-confirmation fix and 0.15 m/s configuration still need physical
revalidation. Marker guidance and Live Playground qualification remain open;
do not equate Service App trials with Playground validation.

## Preconditions

- ROS Humble on Ubuntu 22.04; the Kit server uses a separate Python environment.
- Existing driver isolated by remapping `/cmd_vel` to `/apris_readonly/no_commands`;
  raw wheel odometry is `/wheel/odometry`, EKF output is `/odom`.
- Only one motor driver. Do not run full bringup or a Node-RED/direct motion sender
  alongside this setup. Do not run diagnostic probes while the service bridge is active.
- Keep the physical power/stop accessible and the entire swept area clear, including
  sides and rear. Obtain approval before motion. This is supervised operation only.

See [read-only telemetry](ironx-readonly.md) for ROS setup assumptions. These steps
do not reflash firmware or configure a fresh ROS installation.

## Prepare the UI and telemetry

On the robot, set `ROOT` to the checkout directory. Keep runtime files on that same
host in a private directory. Build before starting the server so `/console` exists:

```sh
cd "$ROOT"
mkdir -p .runtime/ironx
chmod 700 .runtime/ironx
npm run build
```

In a ROS-sourced shell, run the telemetry bridge (unless already running):

```sh
python3 -B scripts/ros2_status_bridge.py \
  --output "$ROOT/.runtime/ironx/state.json" --battery-scale 1
```

For inspection only, start the Kit server with `APRIS_ADAPTER=ros2_readonly` and
`APRIS_ROS2_STATE_FILE` pointing at that file. `/ros2` has no motion buttons;
its display is not a physical emergency stop. Keep existing ROS and SSH sessions
alive rather than starting duplicate stacks.

## Enable motion only after approval

Stop the read-only Kit server, not the motor driver or telemetry bridge. First run
the publisher-free command-bridge preflight:

```sh
python3 -B scripts/ironx_command_bridge.py \
  --command-file "$ROOT/.runtime/ironx/command.json" \
  --status-file "$ROOT/.runtime/ironx/command-status.json"
```

After approval, repeat it with `--enable` in a dedicated ROS-sourced terminal.
It publishes zeros while waiting for fresh commands. In a separate terminal,
start the server using the existing Kit environment:

```sh
cd "$ROOT"
APRIS_ADAPTER=ironx \
APRIS_ROS2_STATE_FILE="$ROOT/.runtime/ironx/state.json" \
APRIS_IRONX_COMMAND_FILE="$ROOT/.runtime/ironx/command.json" \
APRIS_IRONX_BRIDGE_STATE_FILE="$ROOT/.runtime/ironx/command-status.json" \
apps/server/.venv/bin/python -B -m uvicorn apris_server.app:app --host 0.0.0.0 --port 8000
```

Check `/api/status`: adapter `ironx`, connected, and zero velocity. Use the robot's
address at port 8000 to open `/console`. Do not share a fixed robot IP in source docs.

## Console workflow

1. Acquire control in one tab. Other tabs may observe but must not compete for control.
2. Check the surroundings. Press **Confirm clear path · 30 s** before forward motion.
   It sends temporary manual confirmation, not sensor-derived clearance or a drive command.
3. Hold the joystick to move; release to stop. Limits are 0.15 m/s and 0.2 rad/s.
4. Confirmation expires after 30 seconds and is revoked on loss of connection/control,
   E-stop, a blocked observation, tab hiding, window blur, explicit revoke, or leaving
   the component. Reconfirm only after checking the path again.
5. Stop before releasing control or handing it to a service. Use E-stop when needed;
   if software stopping fails, use the physical stop/power.

`front_obstacle_unknown` means a fresh healthy front-clear observation is missing.
The console confirmation supplies a short-lived `manual` observation using the
existing server API; no Adapter fabricates `CLEAR`. The current gate covers forward
motion only. Rear/side collision avoidance is NOT implemented; manual supervision
must cover every direction. Shared Carry helper also uses separate 30-second clearance;
starting does not extend it. See [service operation and E-stop recovery](ironx-follow.md).
The old dedicated Carry consent renewal is not present in the shared UI.

## Stop and recover

Stop motion and confirm near-zero velocity, then stop the Kit server before the
command bridge. Leave telemetry running if desired. Restart a fault-latched bridge
only with the robot stationary and other publishers removed. A changed build may
need a hard reload to replace the cached PWA. Never use stale files as proof of health.

The bridge expires upstream commands after at most 300 ms, but measured braking
and confirmation take longer. Bridge/OS/serial failures are not covered by that
watchdog. Precise calibration, stopping-distance qualification and unattended
autonomy remain out of scope. Next: supervised service testing, without bypassing
ownership, perception freshness or obstacle checks.
