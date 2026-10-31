# Service hardware assumptions and porting

[日本語](service-hardware-porting.ja.md)

An experimental implementation now exists for iron-X ROS 2 Humble:
[operation and limits](ironx-quickstart.md), [Adapter contract](ironx-adapter.md).
It uses same-host files between Kit and the ROS command bridge, not the UGV02 wire
protocol. Supervised console motion is checked; running the same services is still
a separate validation step. The abstract mission API remains unchanged.

## Reference configuration

```text
Phone camera / PWA
  person and marker observations
            |
            v
APRIS Server on Mac or PC
  ownership, validation, safety, logs
            |
            v
Waveshare UGV02 ESP32
  APRIS Rover protocol, encoder motion, motor watchdog
```

The phone/browser owns perception, user interaction and mission execution in the owning tab.
The PC server validates observations and owns motion authorization and safety; the UGV02 owns
motor-adjacent closed-loop control and disconnect stop. Missions use only
`ServiceRover` and never branch on a hardware model.

The reference setup is one UGV02, a securely mounted phone, a Mac/PC and a private LAN.
Use [the handoff guide](../handoff.md) to select setup versus self-test. Printed markers are
not needed for greeting/following. Live Playground supports the mounted phone's own camera;
it still needs physical verification and does not enable physical marker guidance.

## Replacements that do not require platform code

| Replacement | Conditions |
| --- | --- |
| Smartphone | HTTPS, `getUserMedia`, WebAssembly, and adequate camera performance |
| Mac or PC | Node.js, Python, `uv`, and LAN-reachable HTTPS/WSS |
| Wi-Fi router | No client isolation between phone, PC, and rover; ESP32-compatible network |
| Phone mount | Stable forward-facing camera, level framing, no wheel or power obstruction |

After changing a phone, verify permissions, person detection range, bearing sign, and
WebSocket reconnection. Camera field of view may require retuning frame-width distance
thresholds.

## Using another rover

Connect a different wheeled rover at the APRIS `RoverAdapter` boundary instead of changing
missions. The adapter or device firmware must provide:

- connection state and capabilities
- SI-unit pose, linear/angular velocity, and telemetry
- leased manual velocity and explicit stop
- bounded linear motion and bounded rotation
- distinct accepted, running, completed, cancelled, and failed results
- fixed firmware or motor-controller speed limits
- command lease/watchdog, disconnect stop, and latched E-stop
- no automatic motion resume after reconnection

For a device-initiated connection, implement the
[APRIS Rover WebSocket protocol](../rover-protocol.md). A ROS 2 robot may use an edge process
to translate `cmd_vel`, odometry, and IMU to `RoverAdapter`. Browsers and missions must never
connect directly to a motor protocol.

Apply the same move/turn/stop semantics, TTL, cancel, disconnect, and E-stop tests as the
Simulator. Validate without motors, with raised wheels, and then at minimum floor speed.

## Using stock UGV02 firmware

The v0.96 `factory_http` adapter is limited to communication diagnosis and dead-man manual
control. It intentionally rejects automatic `move()` and `turn()`. Use APRIS WebSocket
firmware or another adapter satisfying bounded-motion and stop guarantees for missions.

## Replacing perception hardware

A camera, depth sensor, or PC vision process must register as a Client-protocol client and
send structured person or marker observations. Do not import a sensor SDK into a mission.

A person observation needs at least:

- stable person ID
- `detected | lost`
- confidence and capture time
- normalized center, width, and height
- bearing with zero at rover forward
- observation source

Only observations passing freshness, confidence, and payload checks reach `onPerson()`.
Front-safety sensing is separate and must supply `CLEAR | BLOCKED | UNKNOWN`, perception
health, and heartbeat. Absence of a detection is never automatically `CLEAR`.

## Porting checklist

1. Identify the replaced component and preserved responsibility boundary.
2. Freeze expected mission results in the Simulator.
3. Add adapter or perception-client contract tests.
4. Validate motor-free, raised-wheel, and minimum-speed floor operation in that order.
5. Verify zero output after TTL, process loss, network loss, and E-stop.
6. Run the same unchanged mission in the Simulator and on hardware.
7. Record capability differences, calibration, recovery, and unverified items.

If supporting a new rover appears to require model names, GPIO, PWM, or wheel commands in a
mission, the port is crossing the wrong boundary. First look for a reusable high-level action.
