# iron-X read-only telemetry prototype

This prototype connects ROS Humble's Python 3.10 subscriptions to the Kit server in
its separate Python environment. It does not implement motion control, physical
E-stop, or obstacle clearance. No ROS velocity publisher is created by the bridge.

Set `APRIS_ADAPTER=ros2_readonly` and `APRIS_ROS2_STATE_FILE` to the absolute path
written by `scripts/ros2_status_bridge.py`. Use `/ros2` on the Kit server to view
live pose, velocities, battery, and telemetry age without motion controls.
The existing `/api/status` and browser state stream also carry the actual telemetry.
Missing, stale, invalid, or unexpected-frame odometry is disconnected, not simulated.
Battery has its own three-second expiry. Position is the EKF `/odom` estimate and
has not been qualified against physical measurements.

In a sourced ROS Humble environment:

```bash
python3 scripts/ros2_status_bridge.py --output /absolute/private/path/ros2-state.json --battery-scale 1
```

`--battery-scale 1` is specific to the inspected iron-X driver v1.0, which publishes
0..100. Standard fractional battery percentage uses the default scale 100.
The file is for same-host processes only; monotonic timestamps do not transfer
between machines. Only the trusted robot user should be able to write it.

For initial telemetry inspection, the driver can be started separately with its
`/cmd_vel` input remapped to `/apris_readonly/no_commands`. Run the EKF with the
installed configuration and remap `/odometry/filtered` to `/odom`. This isolates
the driver from existing Node-RED `/cmd_vel` controls but is not a security boundary
against another process deliberately publishing to the remapped topic. Do not run
a second driver or the full bringup concurrently. Opening the motor serial port
can reset the controller; keep the physical stop reachable.

Future motion integration must separately qualify the controller watchdog,
completion/cancellation, control ownership, and stopping on process/network loss.
Do not use the Kit console's stop/E-stop as a physical stop in this read-only mode.
