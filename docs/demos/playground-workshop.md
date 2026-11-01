# APRISRC Kit Playground hands-on

[日本語](playground-workshop.ja.md)

Use the samples as a starting point for your own APRISRC service. This workshop introduces
the Kit's development workflow, not competition tasks or judging criteria. The purpose and
interaction of your service remain yours to design; see [Purpose and scope](../positioning.md).

Allow 20-30 minutes. Try a service, change one thing, and compare the same scene before and
after. No rover, camera, smartphone, microphone, or LLM API key is required. This is a
development workspace, not the final visitor-facing app.

## Start

Clone this public repository; no access invitation is required.
Install Node.js/npm, Python 3.12 (pinned), and `uv`.
On Windows, follow [PowerShell setup](../windows-setup.md).
On macOS/Linux (Bash or zsh), run from the repository root:

```bash
npm ci
uv python install 3.12
uv sync --directory apps/server --no-dev
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev
```

Keep that terminal running. Open
[Person greeting](http://localhost:5173/playground?service=greeting).
These environment settings explicitly select the Simulator and HTTP for a desktop-only
trial, even when local HTTPS certificates exist. Do not use this startup for a physical rover
or smartphone camera trial. If the ports are occupied, use the existing APRIS server or stop
it before starting another instance. End the development server with Ctrl-C when finished.

## Shared Playground

Select **My service**, **Carry helper**, **Person greeting**, or **Mobile receptionist**
in the header. Every service uses the same start/stop, questions, person controls, map,
and **Implementation** panel. That panel loads the real service definition, not a separate
example snippet. Service and Playground run the same definition from `service/catalog.ts`.
The Service view replaces simulated inputs with the camera, including for greeting.

| Service | Trial |
| --- | --- |
| My service / Carry helper | Start service, Enter view, Yes, Items are loaded, Move away, We have arrived |
| Person greeting | Start service, Enter view; waits for detection, faces the person, then greets |
| Mobile receptionist | Set Test markers coordinates and enable Markers visible (off by default); Start service, Enter view, Entrance or Desk, Let's go |

Use **Leave view** to test lost-person handling, **Stand still** to stop the person,
and **Person says** for typed answers to the currently displayed question.
The receptionist only needs the person to start guiding; it does not monitor escort progress.
Its **Markers visible** checkbox can test marker loss. Coordinates are locked while running
and synchronized with the simulator before each trial. The map uses world metres.
Obstacle and fault controls remain under **Advanced controls**.

All services offer **Manual test** and **Scenario runner** for the person. See
[scene import/export and editing](student-service.md#define-a-test-scene) for reusable scenes.
Marker coordinates are separate from the person-scene JSON and are not persisted across reloads.

## Change the Code

Stop first. Edit the file named in **Implementation**, save, then restart the trial.
For My service, edit `apps/pwa/src/missions/studentCarry.ts`: change the offer text or
insert `await service.confirm("Are you ready?", "Ready")` before following.
The next run displays that question without any UI changes.
Greeting, carry, and receptionist definitions are in `apps/pwa/src/service/examples/`.
Greeting's wording and maximum turn remain in `config/greetingStarter.ts`; marker approach
limits remain in `missions/mobileReceptionist.ts`. These helpers are not expanded into
the definition panel. The panel is read-only source, not an editor or step debugger.

This shared UI is a simulator-validated MVP. Legacy dedicated UIs remain in source for
reference, but are no longer the default routes. Their specialized voice/LLM controls and
preview sliders are not part of the shared panel. Live marker guidance stays disabled;
other shared hardware workflows still need physical validation. No general obstacle
avoidance, route planning, or escort tracking is implied.

<details>
<summary>Historical dedicated-demo exercises (not the current shared UI)</summary>

The instructions below describe the previous dedicated screens, retained as teaching
reference. Use the shared controls and code workflow above for the current application.

## Try the three services

| Sample | Actions | Expected result |
| --- | --- | --- |
| Person greeting | Start greeting, then On the left | Faces the visible visitor and greets once |
| Follow helper | Follow me, then Walk ahead | Follows the moving virtual person; Outside view stops it |
| Marker guide | Destination: Entrance, Test scene: In view, Guide me | Approaches the marker and announces arrival |

Choose another sample only after the current trial finishes or after pressing **Stop**.
Control acquisition is automatic. **Emergency stop** latches a stop; clear it with
**Clear E-stop** before another trial (the controller must own control).
Browser speech is optional: the spoken message also appears on screen.

The left side shows the service and scene. The code panel shows the real mission source;
highlighting follows reported decisions, not every executed instruction. **This run** is
a decision trace, not a list of every repeated movement.

## Create a repeatable scene

Only **Marker guide** has the coordinate editor in this MVP.

1. Select Entrance or Desk. Select **Behind rover** in **Test scene**.
2. Press **Guide me**. The visitor triggers the service, then the rover turns in place to
   find the marker before approaching. Desk takes longer because it is farther away.
3. After it stops, change rover x/y, heading, visitor x/y, or marker x/y. Coordinates are
   course-frame metres; heading is degrees, positive counter-clockwise. Heading 0 faces +x.
4. Press **Save scene** to store one layout in this browser. **Load scene** restores it,
   including after a page reload. Loading does not start motion. Destination selection is
   separate: select the same destination yourself when comparing trials.
5. Repeat **Guide me**. Each run resets to the selected scene instead of continuing from
   the last stopping position. It also clears Simulator fault settings, but not E-stop.

**Not visible** starts with the marker hidden: the rover searches in place, stops after a
full scan or the bounded search limit, and asks for repositioning. Allow roughly a minute.
It never drives around looking for an unseen marker. A visitor placed outside the field of
view causes a visitor wait instead of marker search (timeout after 30 seconds).

**Marker initially hidden / Path initially blocked** are saved starting conditions.
**Hide marker / Other marker / Path blocked** beside the map are live inputs; use them
during a run to test loss, wrong IDs, and obstruction. Live changes are not saved in the scene.
Position editing is disabled during a run. Save one scene before editing code and load it
again for comparison. Greeting/following use their visitor controls instead of this editor.

## Exercise 1: greet the person, not the empty space

**Problem:** the rover speaks, but does not face the person.

1. In **Person greeting**, set **Maximum turn** to 0, choose **On the left**, then
   **Start greeting**. It greets without turning. This is a deliberate test setting, not a bug.
2. Change **Maximum turn** to 15. Choose **On the left** again before starting so the
   visitor is placed relative to the rover's current pose, then repeat.
3. Observe a bounded turn followed by the greeting. Change **Greeting** and repeat once more.
4. To keep the change across reloads, edit `apps/pwa/src/config/greetingStarter.ts`:

```ts
export const greetingStarterSettings = {
  greeting: "Welcome. How can I help you?",
  maxTurnDeg: 15,
  minTurnDeg: 3
};
```

The screen controls are previews. They do not write this file. The behavior is implemented
in `apps/pwa/src/missions/challengerStarter.ts`; configuration supplies its defaults.
Stop a trial before editing files. Vite updates the page after a save; reload if necessary.

**Success:** facing the visitor changes, the new greeting persists after reload, and
**Outside view** still waits instead of greeting an absent person.

## Exercise 2: leave room at the reception desk

**Problem:** imagine the reception should stop farther from a desk rather than approach closely.
Change the service's stopping policy, not the test marker position or platform speed limit.

1. In **Marker guide**, choose Desk and **In view**. Save the scene, then **Guide me**.
2. Note where it stops relative to Desk. The current target is 0.45 m with a 0.02 m arrival
   tolerance. The map's small squares represent 0.5 m; they provide a visual comparison,
   not a precision measurement.
3. Stop any running trial. In `apps/pwa/src/missions/mobileReceptionist.ts`, change just:

```ts
const ARRIVAL_DISTANCE_M = 0.65; // Previously 0.45
```

4. After the page updates, select Desk again and **Load scene**, then **Guide me**.
5. It should stop about 0.2 m farther from the marker. Do not change
   `ARRIVAL_TOLERANCE_M`, the scene, or other settings during this comparison.
6. Repeat with **Behind rover**, then hide the marker during approach or block the path.
   Finding the marker should still work; unsafe exits must still stop the rover.

**Success:** the same scene produces a visibly different stopping position without weakening
loss, obstruction, or emergency-stop behavior. Restore 0.45 afterwards unless the new policy
is the service you want. Unit-test fixtures may encode the old threshold; review them when
adopting a permanent change, rather than deleting assertions to make checks pass.

## What to edit

| Change | Location |
| --- | --- |
| Trial layout, starting visibility/blockage | Test scene; browser-local Save/Load |
| Greeting text and turn bounds | `apps/pwa/src/config/greetingStarter.ts` |
| Greeting decisions | `apps/pwa/src/missions/challengerStarter.ts` |
| Following decisions and distance presets | `apps/pwa/src/missions/comeHere.ts` |
| Marker search, approach, arrival, and announcements | `apps/pwa/src/missions/mobileReceptionist.ts` |
| Permanent course IDs/positions | `apps/pwa/src/config/courseMarkers.ts` and matching `apps/server/config/course-markers.json` |

The scene editor changes Simulator geometry without modifying those course-default files.
Service code uses the public Mission API. Do not edit socket/runtime/firmware code or bypass
ownership, command TTL, speed limits, front safety, or E-stop for these exercises.

After a source change, run from the repository root:

```bash
npm test
npm run typecheck
npm run build
```

For a new service, continue with the [Challenger quickstart](../challenger-quickstart.md)
and [Mission API](../mission-api.md). For detailed controls and limitations, see
[Service playground](service-playground.md).

An experimental [live rover mode](hardware-playground.md) adds camera/telemetry visualization
and supervised greeting/following trials. This workshop still uses only the Simulator;
the new live UI has not yet been physically qualified.

## Limits and feedback

The virtual person/markers are geometric observation inputs, not camera image recognition.
Marker guidance currently moves the rover toward a marker: the person remains stationary
and is only the initial trigger. It does not implement escort monitoring, route planning,
general obstacle avoidance, or verified physical marker guidance. Simulator success is not
hardware qualification. Scene editing currently uses numeric inputs, not map dragging.

If nothing runs, check **Local Server online**, the Simulator adapter, another controller's
ownership, and E-stop first. Marker search also needs a visible visitor to start. Failure
after a long approach may mean the bounded approach limit was reached; bring the scene
closer instead of removing the limit. Load a saved scene after reload to restore trial inputs.

When reporting feedback, include the sample/destination, scene coordinates and preset, the
one setting or code line changed, expected versus observed behavior, and the visible status
or screenshot. Most importantly: could you find the code to change without help, and could
you explain why the result changed?

</details>
