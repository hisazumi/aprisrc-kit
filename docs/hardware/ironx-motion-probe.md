# Supervised iron-X pulse test

This is a separate commissioning tool, not a motion-capable Kit adapter. Keep the
Kit in `ros2_readonly` mode. The telemetry monitor remains available during a test.

Use the existing sourced ROS Humble shell, with the driver input remapped to
`/apris_readonly/no_commands` and EKF output on `/odom`. Do not start the full
bringup or another motor driver concurrently.

The default invocation subscribes to odometry and inspects the ROS graph. It does
not create a velocity publisher:

```bash
python3 -B scripts/ironx_motion_probe.py
```

After explicit operator approval, a clear test area or raised wheels, and a person
ready at the physical stop, the following requests 0.05 m/s forward for one second:

```bash
python3 -B scripts/ironx_motion_probe.py --execute
```

Nominal travel is 5 cm; actual direction, distance, and stopping delay are not yet
qualified. This is time-bounded velocity control, not a distance-completion promise.
The probe refuses non-finite values, mixed translation/rotation, speeds exceeding
0.05 m/s or 0.20 rad/s, and durations exceeding one second. It checks fresh odometry,
an initially stationary rover, and a single driver subscriber with no competing
velocity publisher. During the pulse it aborts on stale odometry, delayed loop
iterations, or competing publishers. It repeats zero commands for one second on
normal completion, ordinary failure, SIGINT, or SIGTERM and reports observed stop.
JSON lines record requested velocities and odometry for later inspection.

The STM32 command-timeout behavior is still unknown. SIGKILL, OS/process crashes,
driver/serial failure, or network partitions can defeat software stopping. This
tool does not establish watchdog safety and must not be used unattended. Physical
stop observation and later watchdog qualification are separate checks.
