# Try person following on iron-X

[日本語](ironx-follow.ja.md)

This is the operator entry point for supervised Carry helper trials. It is not
an unattended navigation system or a fresh ROS installation guide.

## What runs where

| Device | Role |
| --- | --- |
| iron-X | ROS driver, telemetry bridge, command watchdog bridge, authenticated network gateway |
| Student PC | Kit server with `APRIS_ADAPTER=ironx_network`, PWA development server |
| Mounted iPhone | Safari camera perception and service UI; observations go to the PC |

The PC and phone must reach the appropriate hosts on the same trusted LAN.
Use the **PC's HTTPS address**, not the robot address or `localhost`, on the phone.
The gateway's plain `ws://` connection is separate from phone-facing HTTPS.

## Prepare without moving

1. Have the robot operator prepare [network integration](ironx-network.md).
   Do not start duplicate drivers, bridges, or Node-RED motion publishers.
2. On the PC, select `ironx_network` and set the gateway URL and private token as
   described there. Keep Simulator as the default when hardware is not in use.
3. Prepare [HTTPS and phone certificate trust](../local-https.md). Use the port
   printed by the PWA server: normally 5173, or a separately selected port such
   as 5174 when running HTTP and HTTPS side by side. Certificate trust is required.
4. Open `https://<PC-LAN-IP>:<HTTPS-port>/app` in Safari, select **Carry helper**,
   and press **Start camera**. Allow camera access and select the camera facing
   forward. Fix the phone securely and confirm that the person's upper body is detected.
5. Stop other service/console sessions and release their control. Clear the
   complete swept area, including the sides and rear. Keep physical stop/power
   accessible and obtain the operator's approval before starting movement.

Camera setup alone does not start the service. No LLM API key is needed for
button-based following. Optional text/voice interpretation uses
[rules, OpenAI, or Gemini](../assistant-providers.md).

## Start and stop

1. After checking the area, press **Start service and allow movement**. This is
   permission for supervised movement, including approaching the detected person.
2. After stable detection, the rover approaches, stops, and offers help.
3. Press **Yes, help me**, then **Items are loaded** when ready. Actual cargo is
   optional for a demo. The rover follows the detected person.
4. Walk slowly and keep your upper body in the camera view. Keep Safari visible
   and the phone unlocked. Do not leave the robot unattended.
5. Use **Stop** or **We have arrived** to stop following, and **End service** to
   stop and release control. Use **Emergency stop** if necessary; if software
   stopping fails, use physical stop/power.

Carry helper no longer needs **Allow movement for 30 s**. Its start action grants
supervised consent; short-lived clearance heartbeats run only in approach/follow
phases. Loss of connection/control, E-stop, or hiding the page revokes permission.
After interruption, explicitly restart; reconnection alone must not resume motion.
If **Look for the next person** is shown, press it to return to the start screen,
then check the area again before **Start service and allow movement**.
The Console's **Confirm clear path · 30 s** is still a separate manual-driving
control. Mobile Receptionist and Live Playground keep their own permission flows.
Manual clearance is not obstacle sensing; there is no general collision avoidance.

## If it stops

| Observation | Meaning and next step |
| --- | --- |
| Target distance reached | Normal hold. Moving farther away may resume following while the service remains active. |
| `person observation stale` / target lost | Fresh person observations stopped. Check camera view, lighting, phone lock/background state and connection; these are possible causes, not a diagnosis. Restart explicitly if the service ended. |
| `front_obstacle_unknown` | A fresh clearance heartbeat is missing. Check service consent, control and connectivity; do not disable the gate. |
| `ironx_rearm_required` / E-stop | Stop is latched. Confirm physical stopping and inspect the fault before explicitly clearing it. |
| Gateway/bridge stop-confirmation fault | Operator recovery is required. Do not repeatedly clear or use server restart as an E-stop reset. |

To clear E-stop after checking the robot: open `/console` on the same PC server,
press **Acquire control**, then **Clear E-stop**. Confirm the banner disappears,
press **Release control**, and return to `/app`. Clearing E-stop does not itself
start a service. A failed clear must leave it latched. Never force ownership
away from an active operator.

Transport failures now log the RPC name and exception type. Ordinary motion
cancellation must not interrupt a pending stop acknowledgement. Confirmation
timeouts still fail closed. See [operations and logs](../operations/runbook.md).

## Settings and evidence

Current iron-X forward/reverse limit: **0.15 m/s**; angular limit: **0.2 rad/s**;
PC network command TTL cap: **200 ms**. Follow requests 0.10 m steps at 0.15 m/s;
approach requests 0.08 m at 0.05 m/s. Short moves decelerate, so these are requested
limits, not guaranteed measured speeds. Stopping distance remains unqualified.

On 2026-10-31, an operator reported successful phone-based following using the
PC/network/iron-X service path. Later trials exposed a cancellation/stop-response
race. The latest stop-confirmation fix and 0.15 m/s configuration passed software
tests but **still require supervised physical revalidation**. Do not interpret
the earlier success as validation of this final configuration. Marker guidance,
Windows operation, and unattended autonomy are not established by these trials.

For maintainers: [network setup](ironx-network.md),
[same-host console setup](ironx-quickstart.md), [Adapter](ironx-adapter.md), and
[command bridge](ironx-command-bridge.md). Historical probe speeds are trial
records, not the current service limit.
