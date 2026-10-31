# Supervised command-silence check

This is a diagnostic, not a certified emergency stop. Keep the wheels raised,
the power switch accessible, and obtain explicit approval before execution.
Reuse the isolated driver command topic from `ironx-motion-probe.md`.

## Preparation (no motor commands)

```sh
python3 -B scripts/ironx_timeout_probe.py
```

The default mode only subscribes. It requires fresh, stationary raw wheel and
EKF odometry, one driver subscriber, and no command publishers.

## Approved test only

```sh
python3 -B scripts/ironx_timeout_probe.py --execute > .runtime/ironx/timeout-probe-01.jsonl 2>&1
```

The test sends 0.05 m/s at 20 Hz for 0.4 seconds, then sends nothing.
A separate process sends repeated zero commands one second after the pulse
starts, leaving approximately 0.6 seconds to observe command-loss stopping.
Errors request earlier fallback stopping. The parent also sends repeated zeros
during cleanup. This software fallback cannot protect against a host, driver,
transport, or power-system failure; use the physical power switch if needed.

The JSONL records commands, raw wheel and EKF velocities, the last command time,
the fallback start time, and final observations. Only raw wheel observations
received before fallback stopping count toward the assessment. Stopping requires
three low-speed samples spanning at least 0.15 seconds after command cessation.
No observed motion is inconclusive, not a successful stop test.

Failure to confirm a stop in this short window does not prove that no watchdog
exists: its timeout may be longer. A successful observation does not establish
which layer implements stopping, nor validate all disconnection scenarios.
The independent fallback process has mocked unit tests; its real timing and the
robot's command-loss response remain unverified until this test is approved and run.
