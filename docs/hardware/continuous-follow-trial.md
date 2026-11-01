# Continuous following trial (experimental)

[日本語](continuous-follow-trial.ja.md)

Short supervised iron-X trials are recorded below; they do not establish reliability
on every network. Simulator checks do not qualify camera noise, Wi-Fi latency or braking.

Simulator automatically uses continuous P control with a 0.25 m/s ceiling and
distance gain 0.8. The `ironx_network` adapter also uses continuous P control with
acceleration limits by default. UGV02 and same-host iron-X remain unchanged.

## Switching to legacy following

Stop the service first. To disable continuous following, set this in the terminal
that starts the PWA, before starting it (Windows PowerShell):

```powershell
$env:VITE_IRONX_CONTINUOUS_FOLLOW = "0"
```

On macOS/Linux:

```sh
export VITE_IRONX_CONTINUOUS_FOLLOW=0
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

Only `0` selects legacy bounded move/turn following for network iron-X. To restore
continuous following, stop the service and remove the setting:

```powershell
Remove-Item Env:VITE_IRONX_CONTINUOUS_FOLLOW -ErrorAction SilentlyContinue
```

On macOS/Linux, use `unset VITE_IRONX_CONTINUOUS_FOLLOW`. If you set it in a Vite
`.env` file, remove it there too. Setting it to `1` also enables continuous following.
Restart/rebuild the PWA and reload the phone after either change.
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

### Follow-up transport changes (hardware validation pending)

Successful gateway drive replies now include telemetry and a new single-use nonce.
The PC consumes that reply for the next drive only while its conservatively
measured age is below 100 ms; otherwise it fetches state again. This removes one
round trip per fresh consecutive command, without extending command/nonce expiry.
Old gateways retain the original state/drive path. Stops and transport faults
discard the cached reply.

After ambiguous transport loss, reconnecting without ownership no longer counts
as confirmation of a stop. A subsequent stop request must receive an explicit
gateway emergency-stop acknowledgement; the rearm latch remains set. Failed TTL
stopping is reported without crashing the safety loop or claiming a confirmed
stop. The gateway supports `--start-estopped` for maintenance restarts. The same
Wi-Fi and SSH tunnel are retained; network jitter itself has not been eliminated.

### Reading transport diagnostics

Session JSONL `adapter_command` records now include `transport` for drive success
and failure. It contains command-lock waiting, total duration, cached-reply age,
whether it was reused, preparation time and remaining TTL. Each RPC records a
request ID, method, RPC-lock waiting, send/reply duration, deadline, outcome and
the gateway's error code/message when rejected. Parameters, nonces and tokens are
not recorded. Failure records also include the browser command sequence and error
detail. Slow/failed RPC diagnostics are written to the server logger as well.
These timings start on the PC server; browser/WebSocket buffering before handling
and one-way Wi-Fi delay are not separately measured.

A mock test reproduced a 320 ms background state request delaying a queued drive
until the gateway rejected it with `lease_expired`. This supports a hypothesis,
not a determination of the prior hardware stop: its old logs did not retain the
gateway's error detail. Correlate the new fields during the next approved trial.

An approved follow-up captured `release` rejected with `not_owner`; the rejection
arrived in about 10 ms after a state reply took about 272 ms. Ownership expiry is
consistent with this sequence, not proof of a lost network connection. The PC now
distinguishes `not_owner`, `lease_expired` and `expired_nonce` responses while it
believes it owns control. It retains the socket, invalidates cached commands and
latches rearm, then confirms emergency stopping on the same connection when stop
is requested. A release rejected after expiry follows that confirmation immediately.
It never silently reacquires control. Confirmation failure remains unconfirmed.
Acquisition rejection by a client that never owned control is not treated as an
ownership-loss recovery, so it cannot stop another operator through this path.
This handling has mock coverage; hardware revalidation is still required.

### Subsequent supervised trial

On 2026-11-01, after restoring the Mac's eduroam connection and SSH tunnel, the
operator reported acceptable following. Over approximately 14.5 seconds, all 261
drive requests succeeded; 235 reused the preceding reply. Median adapter drive
duration was 14.2 ms (maximum 140.3 ms). Estimated displacement was 0.82 m from
odometry, not an external distance measurement. No ownership-expiry or transport
failure interrupted this interval. A service-stop request ended the run and
subsequent observed velocity was near zero. A TTL-expiry stop was also logged at
shutdown, followed by a `not_controller` response after control release.

Two inter-command gaps exceeded 200 ms (maximum about 235 ms), so this does not
establish uniformly smooth motion or long-duration network reliability. The trial
supports short supervised following on this setup; it did not deliberately
exercise ownership-loss recovery. Server tests: 279 passed. Evidence: PC session
`session-20261101-112524-77171b.jsonl`, drive interval approximately
11:33:39-11:33:54 Asia/Bangkok. No credentials or raw session logs are committed.
