# Start iron-X or UGV02

[日本語](startup.ja.md)

Daily startup from a **Windows PC / PowerShell**, after the robot has been provisioned.
Complete [Windows setup](../windows-setup.md) and a Simulator trial first. Run PC commands
from the repository root. This guide does not flash firmware or command movement.
The shared hardware UI and Windows hardware operation still require physical validation.

## Before starting

1. Stop the current service and confirm the wheels have stopped, then stop any existing
   Kit development server with Ctrl+C. Changing variables does not change a running server.
2. Agree on one operator and one PC for this robot. Other students keep using Simulator.
3. Use a trusted LAN. Have the operator provide addresses and tokens privately.
4. For a mounted-phone camera, complete [HTTPS setup](../local-https.md) first, including
   certificates for the PC's current LAN address and trust on the phone. An iPhone can
   connect to a Windows PC; Safari runs on the phone, not the PC.
5. Keep physical stop/power accessible. Startup and a connected status are not permission
   to move. Obtain the operator's approval separately before any motion.

| | iron-X | UGV02 with APRIS WebSocket firmware |
| --- | --- | --- |
| PC adapter | `ironx_network` | `websocket_rover` |
| Connection direction | PC connects to the robot gateway, normally port 8766 | Robot connects to the PC, port 8000, `/ws/rover` |
| Values needed | Gateway URL and private gateway token | Rover ID and private rover token matching firmware |
| Robot-side preparation | ROS, telemetry bridge, command/watchdog bridge, gateway | APRIS firmware, Wi-Fi, PC server address, ID/token |

## iron-X

### Robot-side prerequisite

Ask the robot operator to start the provisioned stack and verify it is ready. Powering on
alone does not establish that these processes are running:

1. ROS and the isolated driver, without competing Node-RED or direct motion publishers.
2. Telemetry bridge and command/watchdog bridge using the same private runtime paths.
   Enabling the command bridge requires operator approval.
3. Authenticated gateway listening on the agreed LAN address/port. The old on-robot
   `APRIS_ADAPTER=ironx` server must not also own its command mailbox.

The Linux commands run **on iron-X**, not on Windows. See
[ROS/telemetry setup](ironx-readonly.md), [command bridge](ironx-command-bridge.md), and
[gateway startup](ironx-network.md#robot-host-operator-preparation). Keep existing working
ROS/SSH sessions; do not start duplicates. A student PC does not need ROS or WSL.

### Start on the Windows PC

Enter the operator-provided gateway URL, for example `ws://<robot-address>:8766`
with the actual address substituted. Do not put the token in the URL.

```powershell
$env:APRIS_ADAPTER = "ironx_network"
$env:APRIS_IRONX_URL = Read-Host "Robot gateway URL"
$env:APRIS_IRONX_TOKEN = Read-Host "Private gateway token"
$env:APRIS_SERVER_URL = "http://127.0.0.1:8000"
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

`ws://` is unencrypted: use only the trusted trial LAN. The token must match the gateway's
`APRIS_IRONX_GATEWAY_TOKEN`. Keep token entry out of shared screens and recordings.
The `ironx` adapter is for a server running on the robot itself; do not select it on Windows.

Continuous following is an explicit trial option, not enabled by this snippet. Only for an
agreed continuous-follow trial, set `$env:VITE_IRONX_CONTINUOUS_FOLLOW="1"` **before** starting
Vite; see [the trial guide](continuous-follow-trial.md). Leave the existing profile unchanged
for connection-only checks.

## UGV02

### Robot-side prerequisite

Use a provisioned UGV02 with **APRIS WebSocket firmware**, not the factory 0.96 HTTP interface.
It needs Wi-Fi credentials, the **PC's LAN address** as `APRIS_SERVER_HOST`, port 8000, and
the same rover ID/token as the server. The OLED's rover IP is not the server address.
If the PC or network changed, ask the operator to update provisioning using the
[firmware guide](ugv02-websocket-firmware.md). This startup procedure does not reflash it.

### Start on the Windows PC

Enter the configured rover ID and token; do not assume every unit uses the example ID.

```powershell
$env:APRIS_ADAPTER = "websocket_rover"
$env:APRIS_ROVER_ID = Read-Host "Configured rover ID"
$env:APRIS_ROVER_TOKEN = Read-Host "Private rover token"
$env:APRIS_SERVER_URL = "http://127.0.0.1:8000"
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

Then power on the provisioned rover, or wait for its firmware to reconnect if already on.
Confirm the expected APRIS firmware and Wi-Fi status on its display. The PC does not need
the rover IP in these variables: the rover initiates the connection. Permit inbound port
8000 on the PC only from the trusted trial LAN; do not disable Windows Firewall.
USB is needed for provisioning, not ordinary Wi-Fi operation; remove it before floor trials.

## Check without moving

Keep the startup terminal open. In a second PowerShell window at the repository root:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status | ConvertTo-Json -Depth 10
```

Confirm the selected adapter (`ironx_network` or `websocket_rover`), connection, fresh
telemetry, no active motion, and zero reported velocity. Also observe that the wheels are
stationary; telemetry alone is not physical proof. Do not clear faults merely to pass a check.

- PC: open the printed Vite URL with `/console?service=carry`. Observe only; do not acquire
  control or operate the joystick yet.
- Mounted phone: `https://<PC-LAN-IP>:<HTTPS-port>/service?service=carry` (normally 5173).
  Use the **PC address for both robot types**, not the iron-X gateway URL or UGV02 OLED IP.
- Press **Start vision** only and verify camera observations. Do not press **Start service**
  during connection checks. Resolve certificate warnings first.

For approved motion, follow [iron-X following](ironx-follow.md), [UGV02 self-test](ugv02-self-test.md),
or [shared hardware controls](../demos/hardware-playground.md). The shared service currently
requires **Acquire control → Confirm clear path · 30 s → Start service**. Start does not renew
the 30-second permission. Physical marker guidance remains disabled.

## Stop or return to Simulator

Cancel the service, confirm physical stopping, release control, stop the camera, then use
Ctrl+C on the PC server. For iron-X, coordinate with its operator before stopping robot-side
processes; do not shut down a shared stack without agreement. For UGV02, power off after stopping.
Reconnection is never authorization to resume a trial.

To use Simulator again in PowerShell:

```powershell
$env:APRIS_ADAPTER = "simulator"
$env:APRIS_DISABLE_HTTPS = "1"
$env:APRIS_SERVER_URL = "http://127.0.0.1:8000"
npm.cmd run dev
```

Open `http://localhost:5173/playground?service=my-service`, using the printed port if different.
These variables apply to the current terminal, and `.env` is not automatically loaded by
these commands. Never commit tokens or private configuration.

<details>
<summary>macOS / Linux alternative (student PC)</summary>

Use the same prerequisites and connection checks. The shell equivalents are:

```bash
# iron-X: replace values with the operator-provided private settings
export APRIS_ADAPTER=ironx_network
export APRIS_IRONX_URL='ws://<robot-address>:8766'
export APRIS_IRONX_TOKEN='<private-gateway-token>'

# OR UGV02: use these instead of the three iron-X settings above
# export APRIS_ADAPTER=websocket_rover
# export APRIS_ROVER_ID='<configured-rover-id>'
# export APRIS_ROVER_TOKEN='<private-rover-token>'

export APRIS_SERVER_URL=http://127.0.0.1:8000
unset APRIS_DISABLE_HTTPS
npm run dev
```

Supply tokens privately and avoid shared terminal history or recordings. Check status in a
second terminal with `curl http://127.0.0.1:8000/api/status`. After stopping, return to Simulator
with `APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev`.

</details>

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Adapter is still Simulator | Stop the previous server; set variables in the terminal used to restart it. |
| iron-X cannot connect | Robot gateway process, URL/port, matching token, LAN routing and competing owner. See [network setup](ironx-network.md). |
| UGV02 does not appear | Firmware's PC server address/port, ID/token, Wi-Fi, PC firewall. Changing only the PC variables cannot update the firmware's server address. |
| Phone cannot open the page | PC address, actual HTTPS port, certificate trust, firewall and Wi-Fi client isolation. |
| Service stops after a short time | Check clearance expiry, observation freshness and displayed fault; do not assume a network fault or disable checks. |

No robot was operated to validate these documentation changes. Windows hardware execution
and the current shared service UI remain subject to supervised physical qualification.
