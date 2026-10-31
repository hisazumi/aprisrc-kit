# Mission API and service templates

[日本語](mission-api.ja.md)

`apps/pwa/src/missions/` and `apps/pwa/src/config/` are the editable boundary for
service-specific behavior and configuration. Missions use only the high-level `ServiceRover`
API and never a rover-specific transport or motor command.

## Editable files

```text
apps/pwa/src/
  missions/
    api.ts                 # Public API and MissionDefinition; platform-owned
    observations.ts        # Small helpers for awaiting perception events
    challengerStarter.ts   # First person-response starter to edit
    demoScenario.ts        # Minimal motion-only mission example
    index.ts               # Mission registry exposed by the UI
  config/
    teamProfile.ts         # Team, service name, and default mission
    courseMarkers.ts       # Known marker poses in course coordinates
    index.ts               # Aggregated service configuration
```

Normally add a mission file, register it in `missions/index.ts`, and edit only `config/`.
WebSocket code, control ownership, safety, and `RoverAdapter` are outside this boundary. Put an
optional natural-language `trigger` beside the mission it starts.

## ServiceRover API

```ts
await rover.move(0.40)       // 0.40 m forward
await rover.move(-0.20)      // 0.20 m reverse
await rover.turn(90)         // 90 degrees left
await rover.turn(-45)        // 45 degrees right
await rover.stop()           // normal stop

const pose = await rover.getPose()
const unsubscribe = rover.onPose((nextPose) => {
  console.log(nextPose.x, nextPose.y, nextPose.yaw)
})
unsubscribe()

const stopPeople = rover.onPerson((event) => {
  if (event.status === "lost") void rover.stop("person lost")
})
const stopMarkers = rover.onMarker((event) => {
  console.log(event.markerId, event.poseCorrection?.applied)
})
stopPeople()
stopMarkers()
```

`move` and `turn` resolve only after motion completes and reject after cancellation or failure.
When speed is omitted, the platform default applies.

```ts
await rover.move(0.40, 0.15) // distanceM, speedMps
await rover.turn(90, 0.60)   // angleDeg, speedRadS
```

`getPose()` returns a copy of the latest server pose and rejects before an initial state is
available. `onPose()` emits the current pose immediately when available and returns an
unsubscribe function.

`onPerson()` and `onMarker()` receive only observations accepted by the Local Server. Stale,
low-confidence, malformed, or unknown-marker observations do not reach listeners. A target
that remains unseen emits `status: lost`; following missions must stop on that transition.

For a one-shot person wait, use `waitForPerson()` instead of writing subscription cleanup by
hand. It handles detection, timeout, and `Cancel mission` abort through one Promise.

```ts
const person = await waitForPerson(rover, signal, 10_000)
await rover.turn(person.bearingDeg ?? 0)
```

`stop()` resolves after a normal stop is sent to the Local Server. It is not an emergency
stop; use the UI **Emergency stop** for danger.

## Defining a mission

Follow the [Challenger quickstart](challenger-quickstart.md) and begin with
`challengerStarter.ts`. `demoScenario.ts` is the minimal motion-only example.

```ts
import { defineMission } from "./api"

export const greetingMission = defineMission({
  id: "greeting",
  title: "Greeting patrol",
  description: "Move forward, greet, and return.",
  runningDetail: "Forward 0.30 m, turn around, return",
  script: [
    "await rover.move(0.30)",
    "await rover.turn(180)",
    "await rover.move(0.30)"
  ],
  trigger: {
    intent: "greeting_patrol",
    description: "Run the short greeting patrol.",
    examples: ["挨拶してきて", "Run the greeting patrol"],
    keywords: ["挨拶", "greeting patrol"],
    response: "Okay. I will run the greeting patrol."
  },
  async run({ rover, config, signal, report, say }) {
    say("Starting the greeting patrol.")
    report({ phase: "approaching", detail: "Moving to the greeting point" })
    signal.throwIfAborted()
    await rover.move(0.30)
    signal.throwIfAborted()
    await rover.turn(180)
    signal.throwIfAborted()
    await rover.move(0.30)
    console.log(config.team.serviceName)
  }
})
```

`signal` aborts when **Cancel mission** is pressed. Check it between actions and inside waits.
An active `move` or `turn` is also stopped by Local Server `cancel_motion`.

## Natural-language trigger

For a step-by-step example, see [Add a voice-triggered action](adding-actions.md).

`trigger` is optional. When present, the PWA sends only registered triggers to the Local
Server intent interpreter.

- `intent`: stable mission identifier
- `description`: explanation used for model selection
- `examples`: representative utterances
- `keywords`: local substring matches used without an API key
- `response`: English acknowledgement for local-rule selection

The longest local keyword match wins. `stop`, `wait_here`, `report_status`, and `clarify` are
reserved platform intents; stop phrases are resolved before any model call.

The LLM schema permits only a registered `intent`, `destination`, and `follow_distance`. It
contains no velocity, motor, angle, distance, or transport command. The chosen mission's
`run()` implements behavior through `ServiceRover`.

`report()` updates the Human Interaction and Mission panels. `say()` uses the platform-selected
English voice. Service decisions remain in the mission; TTL and speed limits remain in the
Local Server.

## Registering a mission

Adding a definition to `missions/index.ts` exposes it in `/lab` **Service missions** and
**Human interaction**. `/app` is the dedicated Carry assistant experience and does not gain a
generic selector merely because a mission is registered. A service-specific `/app` flow must
explicitly choose the missions it uses.

```ts
import { demoScenarioMission } from "./demoScenario"
import { greetingMission } from "./greetingMission"

export const missionRegistry = createMissionRegistry([
  demoScenarioMission,
  greetingMission
])
```

Mission IDs must be non-empty and unique. Configure the Lab default in
`config/teamProfile.ts` as `defaultMissionId`.

## Service configuration

`teamProfile.ts` defines display names and the default mission. `courseMarkers.ts` defines
known marker poses in SI course coordinates. Both are available through
`MissionContext.config`. Service configuration must not include speed limits, TTL, or E-stop
values.

## Running and cancelling

For a generic mission, acquire control in `/lab`, select it, and press
**Run selected mission**. `/app` starts dedicated missions through the Carry assistant state
machine. Open `/console` in another tab to monitor pose and trajectory.

Only one high-level motion may run at a time. Cancel, normal stop, E-stop, control release,
and WebSocket disconnect stop motion. Manual joystick input preempts a running mission.

## Safety boundary

- The Local Server renews a short command TTL while motion is active; expiry stops the rover.
- Mission code cannot change speed limits, TTL, control ownership, or E-stop behavior.
- Missions never reference a physical-rover protocol or `RoverAdapter` implementation.
- The PWA and mission code never command a motor controller directly.
- LLM or perception output is never passed directly to `drive()`.

## Current limitations

`move` uses planar displacement from the starting pose and `turn` uses accumulated yaw.
There is no path planner or general obstacle avoidance. Physical operation still requires
measuring odometry accuracy, floor slip, stopping distance, and acceptable error.
