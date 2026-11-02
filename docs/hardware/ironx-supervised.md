# Supervised low-speed trial profile

[日本語](ironx-supervised.ja.md)

Experimental, opt-in iron-X mode for a nearby supervisor who can stop the robot.
It is not a general unattended safety setting. Default `standard` behavior and
other robot adapters are unchanged. A supervised following trial passed; the
physical network-loss stop-time test remains pending. Do not enable it midway
through a running service.

## Settings

| Setting | Standard | supervised_low_speed |
| --- | --- | --- |
| PC velocity command budget | 200 ms maximum | 8 s, explicitly overrides caller TTL in runtime |
| Robot mailbox maximum | 300 ms | 8 s |
| Nonce lifetime | 300 ms | 8 s |
| Ownership lease | 300 ms | 10 s |
| Network telemetry age limit | 300 ms | 3 s |
| Drive reply timeout | 1 s | 3 s |
| Drive preparation state RPC | 250 ms | 3 s |
| Linear / angular speed limits | 0.15 m/s / 0.2 rad/s | unchanged |

The robot command bridge independently outputs zero at the command deadline;
reading an unchanged mailbox cannot renew it. Network waiting consumes the
original command budget. Expired or superseded commands are not retried. A
connected-but-silent PC cannot hold motor output beyond the last accepted
command's 8-second budget. At 0.15 m/s, eight seconds is up to 1.2 m before
allowing for stopping dynamics. This is a software zero-output deadline, not a
guarantee of physical stopping if ROS, the OS, serial link or motor driver fails.

Local sensor/bridge freshness remains strict. Person loss, obstacle checks,
operator stop, emergency stop and disconnect may stop sooner. Genuine transport
failure still requires rearm; this profile does not silently resume a service on
reconnection. A remote emergency-stop command itself depends on network delivery;
keep independent physical stop/power access.

## Select the profile

Stop the service and confirm physical stopping first. Update both PC and robot
software from the same revision. On the student PC, before starting Kit:

```powershell
$env:APRIS_IRONX_PROFILE = "supervised_low_speed"
```

On the robot, set this variable in **both** the gateway and command-bridge launch
environments, then restart those processes using the existing isolated setup:

```sh
export APRIS_IRONX_PROFILE=supervised_low_speed
```

For macOS/Linux PC terminals use the same `export` syntax. ROS driver and
telemetry-bridge settings are unchanged. Start the gateway with `--start-estopped`.
The PC/gateway profile names must match; the local adapter also checks the profile
reported by the command bridge. Mismatches fail closed. Inspect `/api/status`:
`config.effective_safety_limits.ironx_profile` must be `supervised_low_speed`,
with `motion_ttl_ms` 8000. The existing configuration hash alone does not identify
this environment-selected profile.

To restore standard behavior, set `APRIS_IRONX_PROFILE=standard` in all three
launch environments and restart with stopping confirmed. Do not change only one.

## Validation boundary

On 2026-11-02, the operator reported smooth following on iron-X with this profile.
The observed window contained 310 successful drive replies, no drive failures,
no stop-confirmation failures and no E-stop transition. Median drive reply time
was about 11 ms, maximum 103 ms; final measured velocity was near zero.
This window did not exercise a large delay or intentional network loss, so it
does not qualify the physical eight-second watchdog or ten-second stopping bound.

Offline tests exercise real gateway/network-adapter/runtime code on loopback,
delayed requests, profile mismatch, unchanged mailbox replay, deadline expiry,
sensor loss and emergency stop. They are not a physical network-loss test.
Before student handoff, supervise a bounded motion trial, then test loss of fresh
commands and verify actual stopping within the agreed ten seconds. Keep the
robot clear of people and obstacles and record the measured stop time. Do not
describe the network-loss stopping behavior as physically qualified until that
test is completed. Student trials must remain supervised.
