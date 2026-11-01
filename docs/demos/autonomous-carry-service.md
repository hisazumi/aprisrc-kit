# Autonomous carry service MVP

[日本語](autonomous-carry-service.ja.md)

For current shared-screen operation, use [Playground controls](service-playground.md)
and [Live Playground](hardware-playground.md). Definitions are in `service/catalog.ts`
and `service/examples/`. Old dedicated buttons, automatic consent renewal, and camera
handoff below are not current UI instructions. Physical marker guidance is disabled in
both Service and Playground.

<details>
<summary>Historical dedicated UI design and trial notes (not current operating instructions)</summary>

Status: **Implemented reference service**, documentation reviewed 2026-10-31.
For physical operation and evidence boundaries, see [iron-X person following](../hardware/ironx-follow.md).

## Purpose

A smartphone mounted at the rover front provides camera perception, spoken interaction, and
the user display. After stable person detection, the rover proactively offers help. After
consent and loading confirmation, it follows the person through the existing `Carry helper`
mission.

The MVP demonstrates service initiative, safe interruption, and returning to readiness rather
than advanced autonomous navigation.

## User flow

```text
PAUSED -> READY -> NOTICING -> APPROACHING -> OFFERING HELP
       -> LOADING -> FOLLOWING -> ARRIVED -> PAUSED (explicit restart)
```

- **Start service and allow movement** acquires control and grants supervised movement consent.
  Stable detection can trigger approach motion; check the area before pressing it.
- Clearance heartbeats run during approach/following without a 30-second renewal button.
  Connection/control loss, E-stop and hiding the page revoke consent. Restart explicitly.
- Three consecutive observations of the same person are required before an offer.
- The rover approaches slowly, stops at conversation distance, and offers help.
- Consent may arrive from a button, text, or supported-browser Japanese speech input.
- The rover remains stopped while items are loaded, then starts `carryHelperMission`.
- **We have arrived**, a stop utterance, normal stop, or E-stop interrupts following.
- A declined or timed-out person is not asked again until leaving the frame.
- Target loss stops motion and never silently switches to another person.

## Screen ownership

- `/app`: user-facing service phase, direction, conversation, stop, and camera
- `/lab`: virtual person, scenarios, perception values, and the same service UI
- `/console`: manual driving, safety state, trajectory, and operational monitoring

The Service App defaults to the front camera. **Start camera** enables camera and person
perception; video stays on-device and only normalized observations reach the Local Server.

## Scenario matrix

| Situation | Expected behavior |
| --- | --- |
| No person in frame | Remain `READY`; do not move |
| Person enters | Offer only after three stable observations |
| Brief passerby | Return from `NOTICING` to `READY`; do not offer |
| Person ID changes | Restart stability count |
| User declines or times out | Wait for that person to leave before re-offering |
| Stable target | Approach slowly, stop, then offer help |
| User accepts | Remain stopped in `LOADING` |
| Loading confirmed | Start the existing following mission |
| Target lost while following | Stop and report `TARGET LOST` |
| Stop or E-stop | Abort the mission and prohibit unsafe resume |
| Arrival confirmed | Stop and report `ARRIVED` |
| Service ended | Stop, then release control |

Reducer, component, and reproducible Lab tests cover these transitions.

## Reproducible Lab test

1. Open `/lab` and press Carry assistant **Start service and allow movement**.
2. Run `Service: passerby leaves quickly`; confirm `NOTICING` returns to `READY`.
3. Run `Service: person enters the frame`; confirm `APPROACHING`, stop, then `OFFERING HELP`.
4. Press **Yes, help me** and confirm no motion during `LOADING`.
5. Put the Virtual person ahead, start walking, then press **Items are loaded**.
6. Confirm `FOLLOWING` and Simulator movement.
7. Press **We have arrived** and confirm zero velocity and `ARRIVED`.
8. Press **End service** and confirm control is released.

## MVP limitations

- One target at a time; re-identification depends on `personId`.
- The system does not infer whether a person carries an item; consent is mandatory.
- There is no automatic return-to-waiting point, path planning, or general obstacle avoidance.
- Camera and speech require HTTPS and user permission. Upper-body detection uses MediaPipe Pose
  Landmarker Lite and can work without legs or waist in frame.
- First use downloads a pinned pose model and WASM; offline events need self-hosting or a
  deliberate cache policy.
- Physical use requires camera, observation, confidence, and stopping-distance calibration.

</details>
