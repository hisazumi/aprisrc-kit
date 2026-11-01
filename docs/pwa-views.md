# PWA views

[日本語](pwa-views.ja.md)

One PWA build exposes three URLs for distinct roles. All views share the Local Server,
WebSocket protocol, mission API, and UI components.

The shared header selects a service independently of the view: **Service**, **Playground**,
or **Console**. Every URL includes `?service=my-service`, `carry`, `receptionist`, or
`greeting`. Changing views preserves the service; changing services preserves the view.
Reload, Back, and shared links restore both selections. Running services must be stopped
before using either navigation control. Navigation never selects a different hardware adapter.

**My service** is the editable template in `missions/studentCarry.ts`. Its initial flow is
a carry-assistant example, not a restriction on what participants can build. Its `title`
controls the displayed name; its stable URL identifier is `my-service`.

Legacy `/app`, `/lab`, `?service=student`, and `?sample=student|greeting|follow|receptionist`
links remain accepted and are normalized to the new URLs. `follow` maps to `carry`.
Without a selection, My service is the default.

## `/service`: Service App

The smartphone-facing experience for the selected service, initially My service.
The installed PWA starts at `/service?service=my-service`; its existing app identity is retained.

- Front-camera upper-body perception
- Carry assistant start, consent, loading, following, and cancellation
- Time-limited supervised movement permission
- Service phase, person direction, battery, and connection state
- Normal stop and emergency stop

It intentionally omits the generic Mission Panel, Simulator detail, event log, and manual
joystick. Use `/playground` to select and test arbitrary missions.

## `/console`: Operator Console

The PC monitoring and manual-control view.

- Rover field and trajectory
- Dead-man joystick
- Pose, velocity, and battery
- Control owner, safety state, and recent events
- Emergency stop

Use it primarily for observation and acquire control only for manual operation.

The console now offers **Confirm clear path · 30 s** to the connected control
owner. It sends the existing time-limited manual clearance observation, not a
motion command. Permission expires or is revoked on disconnect, ownership loss,
E-stop, blocked state, tab hiding, window blur, explicit revoke or component exit.
This is not sensor-derived clearance, and rear/side obstacle protection is not
implemented. Check the whole swept area. Other views keep their existing controls.
The iron-X console workflow is described in [iron-X operation](hardware/ironx-quickstart.md).

## `/playground`: Playground

For first-time trials, use `/playground?service=greeting`, `follow`, or `receptionist` via the
[Playground workshop](demos/playground-workshop.md). These show behavior beside real source.
The Simulator provides virtual inputs and marker scene editing. With `websocket_rover`,
[Live Playground](demos/hardware-playground.md) replaces them with camera observations and
telemetry; only greeting/following are enabled, and physical verification is pending.

The integrated development view combines service UI, console, and Simulator tools. It
includes the virtual person, reproducible scenarios, perception values, Human Interaction,
and the generic Mission Panel. Use `/service` for final smartphone experience checks.

## Control ownership

Each browser tab or device is a separate WebSocket client. Exactly one client may own motion
control.

- While `/service` runs a service, `/console` can observe and issue E-stop without ownership.
- Release `/service` control before acquiring manual control in `/console`.
- Navigating away from the owner view disconnects it; the server stops motion and releases control.
- Any connected view may issue emergency stop.

Navigation uses the same tab. To observe a running service, open its Console URL in a
separate tab without acquiring control. View separation never moves safety authority
into the browser. Switching views does not preserve an active run or unsaved scene edits.
