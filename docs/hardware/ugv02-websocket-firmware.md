# UGV02 APRIS WebSocket firmware

Status: flashed; raised-wheel fail-safe transport, bounded floor turn/reverse, and supervised
phone following validated; broader floor qualification pending

This firmware extends the calibrated `JuzzyDee/ugv_base_ros_smooth` derivative with the
APRIS Rover WebSocket protocol. It is the shortest path from the already observed smooth
UGV02 motion to the autonomous carry MVP. Broader motion and safety qualification remains open.

## Implemented boundary

The firmware initiates a plain WebSocket connection to `/ws/rover`, authenticates with a
Bearer token and implements Rover protocol v1 hello, heartbeat, telemetry, command
acknowledgement and motion status messages. Motor behavior uses the existing calibrated
encoder speed estimator, feed-forward and PID loop.

Firmware-enforced limits are fixed at:

| Limit | Value |
|---|---:|
| Linear speed | 0.08 m/s |
| Angular speed | 0.70 rad/s |
| Linear distance | 0.50 m |
| Rotation angle | pi rad |
| Motion duration | 10 s |
| Motion/velocity lease | 1 s |

The firmware rejects stale connection epochs, non-increasing server sequences, expired
commands, commands issued too far in the future and motion beyond these limits. Active
motion stops on lease expiry, maximum duration, WebSocket disconnect, stop, cancel or
E-stop. Stop, cancel and E-stop remain available before NTP synchronization, after epoch
and sequence validation. E-stop is latched. A bounded in-memory terminal history prevents
recent duplicate `motion_id` values from starting a second movement.

This development build deliberately omits the vendor Web UI, arm, gimbal, ESP-NOW and IMU
DMP paths so that the WebSocket client fits the existing 1280 KiB `app0` partition. OLED,
battery voltage acquisition, encoder odometry, Wi-Fi configuration in LittleFS, motor
control and a reduced USB recovery console remain. Battery percentage and IMU capability
are advertised as unavailable until they are qualified.

## Development limitations

- Transport is `ws://`, not certificate-verified `wss://`. Use only on the isolated local
  development LAN. Do not expose port 8000 to another network.
- NTP supplies command time. The reported 50 ms uncertainty is a development assumption,
  not a measured bound. Clock behavior must be measured before floor qualification.
- Terminal motion history contains the eight most recent motions and is not persistent
  across a reboot.
- The build has 22,360 bytes of application headroom. Recheck size after every dependency
  or feature change.
- Forward motion remains blocked by APRIS while front-obstacle state is `UNKNOWN`. The
  server must establish fresh healthy `CLEAR` through qualified sensing or a time-limited
  supervised operator permission. Person detection alone is not obstacle sensing; do not
  bypass the rule in firmware.

## Provisioning

### Before starting

For an already provisioned unit showing `APRIS UGV02` / `0.97-apris-ws-dev`, first try the
[self-test](ugv02-self-test.md); do not reflash merely to run a new service. The new
[Live Playground](../demos/hardware-playground.md) uses the same firmware, but its physical
UI flow is not yet verified. Stock v0.96 cannot run automatic missions via `factory_http`.

Use a data-capable USB cable matching the board's **central ESP32 programming port** and
the Mac/PC connector, not the separate LiDAR connector. Connector/board revisions may differ;
identify the actual programming port before choosing a cable. Do not dismantle the battery
box or connect to board headers based only on the `ROS Driver for Robots` marking.
Compare `ls /dev/cu.*` before/after connection on macOS to identify the serial callout.
If no new device appears, check cable/port recognition before flashing. Opening serial may reset
the board. Keep wheels raised, the power switch accessible, and close serial monitors before esptool.

These application-only instructions assume the reference unit's existing layout: `app0`
at `0x10000`, size `0x140000`, with `app0` selected for boot. A different board or unknown
partition/boot state is not covered. Establish its layout and a recoverable image first;
do not guess offsets or erase flash. Keep pre-update backups privately outside Git.
Factory restore on another board is not covered by a universally verified procedure here. If recovery cannot be established for your unit, stay with the Simulator
or get help from a firmware maintainer before writing.

### Server identity and network

Create the ignored local file from the committed example:

```bash
cd firmware/upstream/ugv_base_ros_smooth/ROS_Driver
cp apris_rover_secrets.example.h apris_rover_secrets.h
```

Set `APRIS_SERVER_HOST` to the Mac's LAN address, not `localhost`, and set the same long
random token in `APRIS_ROVER_TOKEN` that will be passed to APRIS Server. Keep the token out
of Git, URLs, screenshots and diagnostic output. `APRIS_ROVER_ID` must match the server
configuration.

The firmware host is the **PC** LAN address on port 8000, not the rover OLED address or the
phone HTTPS port 5173. A changed PC/LAN address requires updating the compiled header and
rebuilding/reflashing, unless that address is preserved by your LAN configuration.
Keep server ID/token in the ignored root `.env` as described in self-test. `npm run dev`
does not automatically source that file. Do not reuse another person's token in a shared guide.

The UGV02 must already have working STA credentials in LittleFS. The APRIS build preserves
that partition. If the network changes, the reduced 115200-baud USB console retains the
factory Wi-Fi commands `T=401` through `T=408`, plus E-stop (`T=0`), E-stop clear
(`T=999`), status (`T=130`) and reboot (`T=600`). Motor speed, PWM and ROS velocity
commands are intentionally unavailable over USB in this profile. Every Wi-Fi mutation
latches E-stop before touching the network; clear it only after provisioning is complete.

With the APRIS profile running, use a 115200-baud serial terminal and send one JSON object
per line. For a changed LAN, `{"T":403,"ssid":"<SSID>","password":"<PASSWORD>"}`
connects STA; after confirming a valid LAN IP using `{"T":130}`, `{"T":401,"cmd":2}`
selects STA boot mode and saves current configuration. Reboot with `{"T":600}` and recheck
the saved connection. These are provisioning actions, not motion tests. Keep wheels raised;
clear E-stop only after network and stopped telemetry checks. Do not paste real credentials
or Wi-Fi information output into issues. This sequence is based on the current firmware code;
fresh provisioning on another unit/network still needs verification.

## Build

The public tree contains only `data/wifiConfig.example.json`; real Wi-Fi configuration
files are ignored. Provision credentials locally through the serial path above. Do not
upload the filesystem or turn the example into a shared credentials file. Application-only
flashing preserves an already configured unit's LittleFS partition.

Install the pinned firmware toolchain from the repository root. This root `.venv` is
separate from the server environment in `apps/server/.venv`. Create it only if absent:

```bash
uv venv .venv
uv pip install --python .venv/bin/python pip platformio==6.1.18
```

Install esptool in an appropriate local environment and verify `esptool version` before
using the flash commands below. The application/server dependencies alone do not install
these firmware tools. The first PlatformIO build downloads toolchains and libraries and
requires Internet; it is not an offline-ready provisioning kit.

Then, from the repository root:

```bash
cd firmware/upstream/ugv_base_ros_smooth
../../../.venv/bin/pio run -e apris
```

The application image is `.pio/build/apris/firmware.bin`. The recorded development build
was 1,288,360 bytes; `app0` permits 1,310,720 bytes. Check **your** build's size rather than
assuming this historical value remains valid. A plain `pio run -e esp32dev` still
builds the unmodified community feature set and does not enable APRIS.

## Flash only the application

Before writing, raise all wheels, keep the physical power switch reachable and identify
the current central USB-port callout under `/dev/cu.*`. Do not use the LIDAR USB-C port.

Only replace `app0`; do not use PlatformIO's generic upload target and do not write its
generated partition table, bootloader or filesystem:

```bash
esptool --chip esp32 --port '<TARGET-CALLOUT>' --baud 115200 \
  --before default-reset --after hard-reset write-flash \
  --flash-mode keep --flash-freq keep --flash-size keep \
  0x10000 .pio/build/apris/firmware.bin
```

Then verify the same region:

```bash
esptool --chip esp32 --port '<TARGET-CALLOUT>' --baud 115200 \
  --before default-reset --after hard-reset verify-flash \
  0x10000 .pio/build/apris/firmware.bin
```

On boot, the OLED must show `APRIS UGV02` and `0.97-apris-ws-dev`. If it does not, stop and
restore the known-good community or factory `app0` image before further testing.

## First connection, no motion

Start APRIS Server with exactly the rover ID and token compiled into the local secrets
header:

```bash
APRIS_ADAPTER=websocket_rover \
APRIS_ROVER_ID=ugv02-demo-1 \
APRIS_ROVER_TOKEN='<same development token>' \
npm run dev
```

Do not send a motion command yet. Verify `/api/status` reports:

- connected rover `ugv02-demo-1` with firmware `0.97-apris-ws-dev`;
- a fresh heartbeat and telemetry;
- `heartbeat_healthy=true` and bounded clock uncertainty;
- zero linear/angular velocity and no active motion;
- the fixed firmware safety limits above.

## Hardware validation order

1. Keep wheels raised and verify connection/reconnection without motor output.
2. With wheels raised, issue E-stop and confirm clear does not resume motion.
3. With wheels raised, use the lowest short leased reverse or in-place rotation command;
   confirm signs and automatic stop.
4. While raised and moving, stop the server, interrupt Wi-Fi and let the lease expire in
   separate trials. Measure time until motor output stops.
5. Test bounded linear and rotation completion, duplicate `motion_id` replay and maximum
   duration. Confirm terminal status is sent only after zero output.
6. Only after these pass, perform a marked-floor minimum-speed test and record stopping
   distance plus distance/angle error. Keep forward blocked until perception is healthy.

The current build result is not permission to begin a floor trial. Record measured
watchdog timing, speed, stopping distance and p95 distance/angle error before calling this
firmware demo-qualified.

## Qualification summary

The reference unit previously passed application-only flash/verify, connection and fresh
telemetry, E-stop/clear without resume, lease/server-disconnect stop, bounded 15-degree
turn and 0.05 m reverse. Supervised phone following was observed through the older service
flow. These are limited reference-unit observations, not general hardware certification.

Open items include uncommanded RF loss, duplicate/max-duration trials, clock uncertainty,
motion calibration/error distributions and measured stopping distance. Skid-turn velocity
can differ substantially from a requested low-speed angular velocity. Do not infer actual
wheel motion from instantaneous telemetry alone. The new live Playground and physical
marker approach remain unverified.

Detailed private experiment timelines are not published in this snapshot. Record new
measurements for your unit before expanding a supervised test; do not claim unattended autonomy.
