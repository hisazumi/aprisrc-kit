# Try person following on iron-X

[日本語](ironx-follow.ja.md)

Experimental, supervised operation only. The shared UI still requires physical
revalidation; earlier phone-following trials do not qualify this UI.

## Prepare without moving

1. Follow [iron-X network setup](ironx-network.md). ROS, telemetry, watchdog bridge and
   gateway run on iron-X; Kit server (`APRIS_ADAPTER=ironx_network`) and PWA run on the PC.
   Do not start duplicate drivers or Node-RED motion publishers.
2. Prepare [HTTPS and certificate trust](../local-https.md). On the fixed iPhone, open
   `https://<PC-LAN-IP>:<HTTPS-port>/service?service=carry`, using the actual server port,
   not the robot's address or phone localhost.
3. Press **Start vision**, allow camera access, choose the forward-facing camera, and
   confirm upper-body observations. Keep Safari visible and the phone awake.
4. Release control in other tabs. Check sides, rear and front, keep physical stop/power
   accessible, and obtain the operator's approval before movement.

No LLM key is needed. Dedicated voice/LLM controls are not exposed in the shared panel.
The advanced mission interpreter remains a separate workflow.

## Start and stop

1. Press **Acquire control**, then **Confirm clear path · 30 s**, then **Start service**.
   Starting may approach the detected person.
2. Answer **Yes**, then **Items are loaded**. Walk slowly within the camera view.
3. **We have arrived** finishes following and confirms stopping.
   **Cancel and stop** interrupts; **Emergency stop** latches a stop.
4. Confirm physical stopping before another trial or handing control to another client.

**Current limitation:** the 30 seconds start at clearance confirmation, not at service
start or loading. Starting does not renew permission; the shared UI does not inherit the
old Carry UI's automatic renewal. Expiry removes clearance and gates forward motion;
it can interrupt the service. It does not guarantee an exact stop time for every command.
Cancel, check actual stopping and the area, then grant permission and explicitly restart.
Do not disable safety gates to extend a trial. See [shared hardware controls](../demos/hardware-playground.md).

## Recovery

- A target-distance hold can be normal; moving farther away may resume an active follow.
- Lost/stale observations: check camera view, lighting, phone foreground state and network.
- `front_obstacle_unknown`: check the separate clearance and connectivity, not only camera detection.
- E-stop or `ironx_rearm_required`: verify physical stopping and investigate the fault.
- Stop-confirmation failures: use operator recovery; do not repeatedly clear or restart
  the server as a substitute for confirming stopping.

For E-stop recovery, stop the service, release its control (or leave the owning page),
then use `/console?service=carry`: **Acquire control**, **Clear E-stop**, verify the banner,
and **Release control**. Return to Service and explicitly repeat clearance/start.
Never force ownership away from another active operator. Reconnection does not restart a service.

## Settings and evidence

Adapter limits, follow profile and network recovery are separate from UI permission.
See [continuous following trial](continuous-follow-trial.md), [Adapter](ironx-adapter.md),
and [operations](../operations/runbook.md). Do not interpret old probe speeds or bounded-step
descriptions as the selected follow profile. Inspect the active configuration before a trial.

Past operator reports of phone following are evidence for those configurations only.
The shared panel's physical flow, stopping distance, Windows operation, and physical marker
guidance are not qualified by the current simulator checks. Marker guidance is disabled
in both Service and Playground.
