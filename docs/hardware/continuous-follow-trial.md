# Continuous following trial (experimental)

[日本語](continuous-follow-trial.ja.md)

Software preparation only: iron-X continuous following has not been physically
validated. Simulator checks do not qualify camera noise, Wi-Fi latency or braking.

Simulator automatically uses continuous P control with a 0.25 m/s ceiling and
distance gain 0.8. Hardware remains on bounded motion by default. Only the
`ironx_network` adapter can opt in; UGV02 and same-host iron-X remain unchanged.

Before starting the PWA development server, set:

```sh
export VITE_IRONX_CONTINUOUS_FOLLOW=1
```

Use the existing [PC/iPhone setup](ironx-follow.md), with the PC server configured
as `ironx_network`. This flag selects the controller, not movement permission.
For a production PWA, rebuild after changing the flag; for development restart
Vite, then reload the phone while the service is stopped.

The hardware profile uses max forward speed 0.15 m/s and distance gain 0.6.
Angular limit 0.2 rad/s, acceleration 0.12 m/s², deceleration 0.3 m/s² and angular
acceleration 0.5 rad/s² come from the common controller defaults. Loss/fault stops
bypass the normal slew limit. Existing server ownership, path clearance, E-stop
and command expiry remain in force. The velocity API acknowledges sending, not
physical execution. Keep an independent physical stop accessible.

After operator approval, test short forward following, left/right alignment,
person stopping and target loss, in that order. Record commanded/observed velocity
and stop distance. Do not tune maximum speed before checking stopping behavior.

To revert: stop the service, unset `VITE_IRONX_CONTINUOUS_FOLLOW`, restart/rebuild
the PWA and reload the phone. Hardware then returns to bounded move/turn following.
Reconnection alone must not resume the service. No robot deployment is implied
by changing this source flag or by passing software tests.

## University trial, 2026-11-01

The first hardware trial produced approximately 1.3 seconds of right-turn output,
then a drive reply timeout; no forward output was recorded. Telemetry subsequently
returned to near-zero velocity. This is not a successful following qualification.
Read-only measurements over the SSH tunnel showed a median round trip of 9.75 ms
and a maximum of 106.3 ms across 40 requests. They do not establish the cause of
the earlier 250 ms timeout.

The PC now allows up to 1 second for a drive acknowledgement, independently of
the unchanged 200 ms command expiry and 300 ms gateway ownership lease. This does
not prevent pauses when the network is slow. Replies taking 100 ms or more are
logged with the method and elapsed time. Operator stop/release/disconnect failures
keep E-stop latched and report `stop_unconfirmed`, without claiming the robot
stopped or aborting client cleanup. Delayed-response and failure tests pass;
physical revalidation is required. Use an SSH tunnel or TLS on shared networks.
