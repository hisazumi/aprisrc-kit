# iron-X from a student PC (experimental)

[日本語](ironx-network.ja.md)

For the operator's PC/iPhone start, stop and recovery sequence, use
[person following](ironx-follow.md). This page is the network setup reference.

Run the Kit server and service on the student's PC, normally with Simulator.
For an approved robot turn, switch that server to `ironx_network`. ROS is not
required on the student PC; ROS, the driver, and local bridges stay on the robot.
This network path is experimental; limited supervised trials are recorded below.
Windows compatibility is a design intention; physical operation from Windows has
not been validated. Earlier [local Adapter trials](ironx-adapter.md) do not
validate this network path.

```text
PC browser / rover-mounted phone -> student's Kit server
  -> ironx_network -> authenticated WebSocket gateway on robot:8766
  -> local command mailbox -> existing ROS command/watchdog bridge -> driver
  <- gateway <- existing local telemetry and command-status files
```

## Student PC: select the backend

Complete the [participant setup](../challenger-quickstart.md) first. From the
repository root, the normal PC-only workflow is:

```sh
export APRIS_ADAPTER=simulator
export APRIS_DISABLE_HTTPS=1
npm run dev
```

PowerShell:

```powershell
$env:APRIS_ADAPTER = "simulator"
$env:APRIS_DISABLE_HTTPS = "1"
npm run dev
```

Before switching, stop any motion and confirm the robot is stationary, then stop
the running Kit server/dev process. Set the new environment in the terminal that
will restart it; changing a variable does not switch an already-running server.
Only start the network configuration after the operator has prepared the gateway
and assigned your turn:

```sh
export APRIS_ADAPTER=ironx_network
export APRIS_IRONX_URL=ws://robot:8766
export APRIS_IRONX_TOKEN=secret
unset APRIS_DISABLE_HTTPS
npm run dev
```

PowerShell:

```powershell
$env:APRIS_ADAPTER = "ironx_network"
$env:APRIS_IRONX_URL = "ws://robot:8766"
$env:APRIS_IRONX_TOKEN = "secret"
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm run dev
```

`robot` is a placeholder for the operator-provided robot hostname/address.
`secret` is an example only: use the private token supplied by the operator,
never commit it or put it in browser code. Check the student's `/api/status` for
`ironx_network`, fresh connected telemetry, and zero velocity before proceeding.
Keep existing ownership, perception freshness, and obstacle checks; a connection
does not grant permission to move. Returning to Simulator also requires stopping
and restarting the server with `APRIS_ADAPTER=simulator`.

## Robot host: operator preparation

The gateway reuses the [same-host Adapter](ironx-adapter.md) and existing local
command/telemetry bridges. It exclusively locks the command mailbox. With the
robot stopped and stopping confirmed, **stop the old on-robot Kit server using
`APRIS_ADAPTER=ironx` before starting the gateway**. Keep ROS, the isolated driver,
telemetry bridge, and command/watchdog bridge running. Do not start duplicate
bridges, direct command senders, or motion probes; do not bypass a mailbox lock
failure by deleting locks or choosing a different command file.

Use the existing private runtime directory on the robot, with three distinct
absolute paths matching the running bridges. In the robot's Kit Python
environment, with `ROOT` set to its checkout path, the launch example is:

```sh
cd "$ROOT"
export APRIS_IRONX_GATEWAY_TOKEN=secret
export APRIS_ROS2_STATE_FILE="$ROOT/.runtime/ironx/state.json"
export APRIS_IRONX_COMMAND_FILE="$ROOT/.runtime/ironx/command.json"
export APRIS_IRONX_BRIDGE_STATE_FILE="$ROOT/.runtime/ironx/command-status.json"
python -m apris_server.ironx_gateway --host 0.0.0.0 --port 8766
```

The gateway token must match the PC's `APRIS_IRONX_TOKEN`. The corresponding
optional path arguments are `--state-file`, `--command-file`, and
`--bridge-state-file`; they override the environment defaults. The default bind
address is `127.0.0.1`; the example explicitly enables LAN access. Restrict that
access to approved PCs. Startup requires confirmed stopping before service is
ready. These commands are preparation instructions, not actions performed here.

## Ownership, stopping, and recovery

- The gateway is the sole local mailbox owner and admits one network control
  owner at a time. Browser control within one Kit server is a separate layer.
- The PC adapter automatically acquires the gateway lease on its first motion
  request and releases it on stop, including completion of a bounded move/turn.
  It does **not** reserve the robot for an entire student session or mission.
  Agree on turns out of band: only the assigned student's network server should
  be active; others use Simulator. Stop the outgoing service, confirm stationary
  telemetry, and stop its network server before handing over. Do not race to
  acquire control between another student's mission steps.
- Each drive requires a fresh, single-use challenge scoped to the connection and
  ownership epoch, valid for 300 ms. Transit consumes its lifetime. The client
  caps command TTL at 200 ms; the gateway also caps it by remaining challenge
  lifetime. Only successful drive renews the 300 ms ownership lease; reading
  telemetry does not. Expired commands, expired ownership, and owner disconnect
  trigger stopping through the local watchdog/Adapter path.
- Stop confirmation failure is latched at the gateway and requires operator
  recovery and gateway restart. A timeout or zero command is not proof of a
  physical stop. Keep an independent physical stop/power control accessible;
  bridge/OS/serial failures are not covered by an upstream command watchdog.
- The client reconnects for state observation after failure, without replaying
  commands or reacquiring control. A failure while owning control or executing
  motion requires an explicit stop reset after physical stopping is confirmed.
  Emergency stop remains latched across reconnection; failed reset requests do
  not clear it. Gateway stop-confirmation faults still require operator recovery.
  Never treat restored Wi-Fi as permission to resume a previous mission.

## Network security and iPhone camera

Bearer authentication is not encryption. `ws://` sends the token and traffic in
plaintext: use it only on a trusted, isolated LAN. On an untrusted network, use a
properly configured TLS reverse proxy with `wss://`, a valid trusted certificate,
and forwarding of the Authorization header; restrict direct gateway access.
Do not expose port 8766 publicly. Phone-facing HTTPS does not encrypt the separate
PC-to-gateway connection.

For camera observations, mount the iPhone on the rover and connect it to the
**student's Kit server**, not the robot's old Kit server:
`https://<student-PC-LAN-IP>:5173/service` for the development setup. Follow
[local HTTPS and smartphone setup](../local-https.md): the certificate must cover
the student's PC address and its CA must be trusted on the iPhone. Leave
`APRIS_DISABLE_HTTPS` unset, allow camera access, and resolve certificate warnings
before testing. The phone, PC, and gateway must be mutually reachable as needed;
camera observations go to the PC running the service.

5173 is the usual HTTPS port, not a fixed requirement; use the actual HTTPS
startup URL (for example 5174 for a separate instance). Current iron-X limits are
0.15 m/s and 0.2 rad/s. Pending stop acknowledgements are protected from repeated
motion cancellation, with the existing 3-second RPC deadline retained. Timeouts
still fail closed. The latest fix and speed configuration need physical revalidation;
the earlier 0.04 m/s trials below are historical evidence, not current qualification.

## Supervised trial record (2026-10-31)

The gateway was deployed on iron-X and Kit ran on a Mac over Wi-Fi. Manual
control worked. A 200 ms joystick interval conflicted with the maximum 200 ms
network command TTL: logs showed 83 short zero-command gaps (20-41 ms) in the
inspected operation window. The joystick now sends every 50 ms; stop deadlines
were not extended.

Two supervised 2-second forward trials at 0.04 m/s each sent 40 commands, with
no command errors or intervening zero outputs in the robot bridge log. Odometry
reported approximately 7.6 cm and 7.9 cm, respectively, and near-zero velocity
after stopping. The operator reported the final trial looked good. These are
odometry estimates, not externally measured distances. The scripted trials used
the same Kit WebSocket drive interface and 50 ms interval as the joystick.

An earlier trial stopped after about 0.84 seconds because the test script failed
to renew manual path clearance; it is not a successful 2-second trial. The
corrected script renewed clearance during the bounded test only.

Idle connection failures exposed a client-side defect: lock waiting counted
toward the 250 ms RPC timeout, and cancellation of a status reader could close
the shared connection permanently. State reads now coalesce and shield the
shared request from reader cancellation. State RPCs allow 1 second, but stale
telemetry remains unavailable after 300 ms and motion TTL is unchanged. Transport
logs include the method and exception type. These software failure paths are
covered by mock tests; they do not prove that Wi-Fi itself never drops.

Restart still resets a PC-only E-stop latch if it never reached the gateway;
do not use restart as a physical E-stop reset. Windows operation, multi-student physical handoff, and
physical network-loss stopping tests remain unverified for this network path.
See [supervised operation](ironx-quickstart.md) and
[command bridge limits](ironx-command-bridge.md) before further trials.
