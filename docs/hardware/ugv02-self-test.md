# UGV02 self-test

[日本語](ugv02-self-test.ja.md)

This procedure is for one person moving a Simulator-verified mission to the supported UGV02.
It assumes one rover with firmware and network provisioning already completed. Do not change
mission code during the handoff. Complete the
[Challenger quickstart](../challenger-quickstart.md) in the Simulator first.

This is the existing two-device starter procedure: the phone provides observations and the
PC tab runs the mission. It is not the new [Live Playground](../demos/hardware-playground.md)
procedure, which runs camera and mission on the mounted phone and still needs physical validation.
If provisioning is incomplete, start with [the handoff guide](../handoff.md), not the motion steps below.

## Reference hardware

| Role | Assumed hardware |
| --- | --- |
| Rover | Waveshare UGV02, ESP32, wheel encoders, APRIS firmware `0.97-apris-ws-dev` |
| Vision/UI | Smartphone fixed to the rover front, screen facing forward, using the front camera |
| Local server | Windows PC with PowerShell, Node.js, Python, and `uv` (macOS/Linux alternative below) |
| Network | Private LAN allowing the PC, phone, and UGV02 to communicate |
| Recovery | UGV02 physical power switch; data-capable USB cable only for firmware updates |

Do not keep USB connected during normal driving. Before substituting a phone, rover, or
perception device, read [Hardware assumptions and porting](service-hardware-porting.md).

## One-time setup

1. Follow [Local HTTPS and smartphone setup](../local-https.md) to create a development
   certificate containing the PC LAN address and trust its CA on the phone.
2. Follow [UGV02 APRIS WebSocket firmware](ugv02-websocket-firmware.md) to configure firmware,
   Wi-Fi, server address, rover ID, and token.
3. Store server values matching firmware in the ignored repository-root `.env` file.

```dotenv
APRIS_ADAPTER=websocket_rover
APRIS_ROVER_ID=ugv02-demo-1
APRIS_ROVER_TOKEN=<same development token as the rover>
```

Never commit or share `.env`, firmware `apris_rover_secrets.h`, or the CA private key.

## Every self-test

Begin with the wheels raised and one hand able to reach the physical power switch. Although
the starter turns at most 15 degrees, ensure that cables and nearby objects cannot touch the
wheels.

1. Secure the UGV02 and smartphone and verify that the camera is unobstructed.
2. Connect the PC, smartphone, and UGV02 to the same LAN.
3. Power on the UGV02 and verify `APRIS UGV02` and `0.97-apris-ws-dev` on its OLED.
4. Start APRIS in Rover mode from the repository root.

Install dependencies using the README's Windows steps first. Stop the existing Simulator.
In Windows PowerShell, set the ID and token matching your private configuration below.
The command does not automatically load `.env`. Keep the entered token out of shared
screens/logs. Changing environment variables does not reconfigure a running server.

```powershell
$env:APRIS_ADAPTER = "websocket_rover"
$env:APRIS_ROVER_ID = "ugv02-demo-1"
$env:APRIS_ROVER_TOKEN = Read-Host "Enter the private rover token"
$env:APRIS_SERVER_URL = "http://127.0.0.1:8000"
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

<details>
<summary>macOS / Linux alternative (Bash or zsh)</summary>

Load only the private `.env` you prepared yourself, never an untrusted or shared shell file.

```bash
set -a
source .env
set +a
unset APRIS_DISABLE_HTTPS
export APRIS_SERVER_URL=http://127.0.0.1:8000
npm run dev
```

</details>

5. Run `uv run --directory apps/server apris-doctor --json` on the PC and verify:
   - `status` is `ready`
   - adapter is `websocket_rover`
   - `ugv02-demo-1` is connected
   - heartbeat and telemetry are healthy and fresh
   - linear/angular velocity are zero and no motion is active
6. Open `https://<PC-LAN-IP>:5173/service?service=my-service` on the phone and press **Start vision** only.
   Do not press **Start service**: this test runs a generic mission on the PC instead.
7. Confirm a person detection box and an online connection state.
8. Open `https://localhost:5173/playground?service=greeting` on the PC, expand **Advanced controls**, and press **Acquire control** in the manual controls. Do not start the shared service.
9. Select `Person greeting starter` under **Service missions**.
10. Move outside the camera frame and press **Run selected mission**.
11. Step slightly left or right of the rover within 30 seconds.
12. Confirm that the rover turns at most 15 degrees toward you, stops, and reports
    `Greeting complete`.

Place the rover on the floor only after the raised-wheel test passes. The starter still turns
only; do not add forward motion until you understand stop controls and front-safety state.

## Stop and finish

- Use **Cancel mission** or **Release control** for a normal stop.
- Use **Emergency stop** for unexpected motion. Cut physical power if screen control fails.
- Confirm zero linear/angular velocity and no active motion in doctor or `/api/status`.
- Also observe that the wheels actually stopped; telemetry alone is not physical proof.
- Stop the phone camera, stop `npm run dev` with Ctrl-C, then power off the UGV02.
- Reconnection never resumes an interrupted mission. Re-run only after checking state.

## Forward motion is a separate step

`Person greeting starter` uses turning only and does not require forward obstacle perception.
A positive `move()` requires either fresh, healthy `CLEAR` perception or a time-limited
supervised permission. Never treat `UNKNOWN` as traversable or use Simulator-only APIs to
bypass physical-rover safety. Reverse and turning capability do not grant forward permission.

## Quick diagnosis

| Symptom | Check |
| --- | --- |
| Phone camera will not start | HTTPS URL, CA trust, camera permission, another app using the camera |
| APRIS is not `ready` | `.env` rover ID/token, OLED Wi-Fi/server address, heartbeat |
| **Acquire control** fails | Phone **Start service** state or another owner tab |
| Detection box appears but mission does not react | Phone and PC use the same server; 30-second timeout has not elapsed |
| Rover does not turn | E-stop, control owner, `bearingDeg`, and the 3-degree deadband |
| Rover turns the wrong way | Stop, then check phone orientation, camera facing, and sign convention |
| Only forward is rejected | Front obstacle is `UNKNOWN` or `BLOCKED`; do not bypass it |

Before cutting power after an unresolved failure, record the `apris-doctor --json` snapshot and
latest structured-log time when possible. Never include tokens or private keys.
