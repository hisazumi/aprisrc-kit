# Live rover playground

[日本語](hardware-playground.ja.md)

The shared UI is simulator-tested; it still needs physical qualification. Earlier hardware
following results used a different UI and do not validate this version.

## Prepare and start

1. Provision the robot using [UGV02 self-test](../hardware/ugv02-self-test.md) or
   [iron-X network setup](../hardware/ironx-network.md). Keep competing motion publishers stopped.
2. Start the Kit server with the appropriate physical adapter. The browser does not choose
   the adapter. Use [HTTPS](../local-https.md) on the mounted phone.
3. Open `/playground?service=greeting`. Press **Start vision**, allow camera access,
   choose the forward-facing camera, and check accepted person observations and fresh telemetry.
4. Have the operator clear the entire swept area and approve the test. Begin with raised wheels.
   Press **Acquire control**, **Confirm clear path · 30 s**, then **Start service**.
   The last button can start movement; camera setup alone does not.
5. Observe the bounded greeting turn and stopping. **Cancel and stop** interrupts a trial;
   **Emergency stop** latches the stop. Have physical stop/power accessible.
6. After qualification, choose `/playground?service=carry` for a short supervised trial:
   **Yes**, **Items are loaded**, then **We have arrived** to finish.

## Current permission limitation

Both physical Service and Playground use the separate **30-second manual clearance** control.
Starting a service does not grant or extend it. The interval begins when clearance is confirmed,
including time spent answering questions. It expires even while following. Expiry revokes
clearance; forward motion is gated and the service may fail or stop. This is not a guarantee
of an exact 30-second stop time for every direction or command.

If clearance expires, cancel, confirm actual stopping and the surrounding area, then grant
clearance and explicitly start again. Reconnection is not authorization to resume.
The older dedicated Carry UI's automatic consent renewal is not present in the shared UI.
This is a known workflow regression, not a new safety requirement or a firmware change.

Page hiding, focus loss, control loss, disconnect, and E-stop can revoke clearance earlier.
Clearance is an operator observation, not obstacle sensing; it does not protect the sides/rear.
Only **Simulator Playground** automatically prepares and renews simulated clearance.
Even Service connected to a simulator uses the separate manual control.

## What is available

Playground shows the common service panel, actual service definition under **Implementation**,
camera observations, map/telemetry and **Advanced controls**. It does not provide the old
specialized source-line highlighting or preview sliders. Synthetic person/marker controls
are simulator-only. Physical marker guidance is disabled in Service and Playground;
the old `/app?service=receptionist` URL is an alias, not an alternate live path.

Use [PWA views](../pwa-views.md) for navigation and [iron-X following](../hardware/ironx-follow.md)
for the PC/phone setup and E-stop recovery. Never treat simulator tests, telemetry alone,
or old hardware trials as proof of this UI's physical stopping behavior.
