[日本語](human-interaction.ja.md)

# Human interaction Simulator demo

For current shared-screen operation, use [Playground controls](service-playground.md)
and [Live Playground](hardware-playground.md). Definitions are in `service/catalog.ts`
and `service/examples/`. Old dedicated buttons, automatic consent renewal, and camera
handoff below are not current UI instructions. Physical marker guidance is disabled in
both Service and Playground.

<details>
<summary>Historical dedicated UI design and trial notes (not current operating instructions)</summary>

Status: **Implemented reference demo** (verified 2026-09-25)

This is both the original plan and the current runnable guide. Use
[Development roadmap](../roadmap.md) for future priorities.

This demo validates the first stage of the private human-interaction MVP using
the public APRIS safety and mission boundaries. A virtual person is projected
from the current Simulator pose into the same normalized person observation
shape used by the phone camera.

## Run

```bash
npm run dev
```

To use model-backed intent interpretation instead of local rules, start the
same stack with a server-side key. The key is never sent to the PWA.

```bash
OPENAI_API_KEY='<development key>' npm run dev
```

Open `http://localhost:5173/lab`, then:

1. Acquire control.
2. Select `Left`, `Ahead`, or `Right` in **Virtual person**.
3. Start the scene. This also establishes a fresh, healthy `CLEAR` state for
   the explicitly simulated demo area.
4. Press **Come here** in **Human interaction**.
5. Observe `ALIGNING`, `APPROACHING`, and `ARRIVED` while the Rover field shows
   the relative motion.
6. Press **Wait here** or **Stop** to exercise the service controls.

For continuous following, press **Follow me**, then **Start walking** in the
Virtual person panel. The person follows a 12-second gentle S-shaped route.
The rover turns to keep the person centered, advances when the person moves
away, and waits at approximately one metre until the person moves again.
**Pause walking** leaves the person at the current position so the distance
holding behaviour can be observed.

Browser speech uses an English voice for interaction acknowledgements and
safety messages.

The **Natural language** input maps free-form English or Japanese requests to
an allowlisted service intent. Application intents, descriptions, examples,
local fallback keywords, and acknowledgements are colocated with their mission
definitions. The PWA sends only those registered triggers to the Local Server.
Reserved `stop`, `wait_here`, `report_status`, and `clarify` intents remain
platform-owned, and stop phrases are resolved locally before any model call.
Select `rules`, `openai` or `gemini` using `APRIS_ASSISTANT_PROVIDER`;
see [provider configuration](../assistant-providers.md) for keys, models and legacy defaults.
Rules need no API key. Model output can never contain
velocity, motor, distance, angle, or rover-protocol commands.

Where browser speech recognition is available, **Speak** captures one Japanese
utterance and passes its transcript through the same server intent boundary.
This is a demo input adapter, not the long-term speech stack. Production speech
input should use an explicitly selected and measured transcription provider
while retaining this allowlisted intent contract.

While the scene is active, **Camera preview** switches to a Lab-only virtual
camera. Its person silhouette and detection box are rendered directly from the
normalized observation sent to the mission, so horizontal position, apparent
size, distance, and bearing remain consistent with the tracking input. The
normal phone and recorded-video controls return when the virtual scene stops.

To verify target-loss handling, start **Come here** and press **Stop scene**
while the rover is moving. The persistent person subscription immediately
sends a normal stop, cancels the bounded motion, and transitions the service to
`LOST`. Observation staleness follows the same stop path.

## Model

- Initial virtual-person distance: approximately 1.38 m
- Horizontal field of view: 70 degrees
- Bounded turn step: at most 12 degrees
- Bounded approach step: 0.08 m at 0.05 m/s
- Arrival threshold: person width at least 36% of the camera frame
- Phone upper-body arrival threshold: person width at least 65% of the frame
- Person observation interval: 450 ms
- Observation stale timeout: 1.8 s
- Simulator follow hysteresis: resume below 31% frame width, hold at 36%
- Phone upper-body follow hysteresis: resume below 52% frame width, hold at 65%
- Follow step: 0.10 m at a requested 0.15 m/s; bounded-motion deceleration may keep actual speed lower

The interaction consumes only `ServiceRover.onPerson()`, `move()`, `turn()`,
`stop()`, and the optional authoritative front-obstacle snapshot. It does not
use Simulator-specific motion calls. Replacing the virtual observation source
with browser camera observations therefore keeps the service state machine
unchanged.

## Supervised hardware pilot

Use [iron-X person following](../hardware/ironx-follow.md) for the PC/iPhone setup,
start/stop sequence and E-stop recovery. Open the PC's actual HTTPS port, use
**Start camera**, and check the area before **Start service and allow movement**.
Carry helper sends short-lived `path_clearance` heartbeats during approach/following;
there is no 30-second renewal button in this service. The server expires clearance
within one second if heartbeats stop. Connection/control loss, E-stop and hiding
the page revoke consent. Explicitly restart after interruption.

The Console still uses its separate 30-second manual confirmation. Neither flow
is sensor-derived obstacle avoidance. Browser clients cannot set arbitrary
obstacle state, source, health, confidence or timestamps. Unattended operation
and general collision avoidance remain out of scope.

## Verification

The initial browser trial placed the person 12.5 degrees left at 1.38 m. The
rover aligned, approached approximately 0.45 m, and reached `ARRIVED` with the
person at 0.92 m, 2.8 degrees, and 37% frame width. A separate loss trial
cancelled an active turn with `person lost` and left linear and angular
velocity at zero.

The first hardware-contract check used the WebSocket rover adapter without a
motion command. Owner confirmation produced `CLEAR/manual/healthy`; release
returned it to `UNKNOWN/manual/unavailable`. The connected UGV02 remained at
zero linear and angular velocity throughout.

A subsequent floor trial used the mounted phone's upper-body observations and the
time-limited **Allow movement** permission. After the indoor follow threshold was tuned, the
UGV02 turned toward the person and followed them smoothly enough for the supervised demo.
The user noted that response was still somewhat slow. This qualitative result does not
replace measured obstacle-sensor or stopping-distance qualification.

</details>
