# My service

[日本語](student-service.ja.md)

Edit **one file: `apps/pwa/src/missions/myService.ts`**.
Change the order, conditions, and messages inside `myService.run(service)`; no React changes are needed.
The template is already registered through `App.tsx` → `StudentServicePanel`. The panel receives a `service` prop; it does not import the carry template itself.
It uses the shared question panel and `service/catalog.ts`, not the generic missionRegistry.
The existing Carry helper remains available for comparison.

## Quick start (Windows PowerShell)

Install Node.js 22.12+ or 24+, uv, and Git. Python 3.12 is pinned and installed below.
Run these commands from the repository root:

```powershell
uv python install 3.12
npm.cmd ci
uv sync --directory apps/server --no-dev
$env:APRIS_ADAPTER="simulator"
$env:APRIS_DISABLE_HTTPS="1"
$env:APRIS_SERVER_URL="http://127.0.0.1:8000"
npm.cmd run dev
```

These settings explicitly select the desktop Simulator, not a physical robot.
Open `http://localhost:5173/playground?service=my-service`.
HTTP is explicitly selected even when certificates exist. For an existing Python environment
or startup errors, see [Windows setup](../windows-setup.md).

1. Select **My service** in the shared header and open **Playground**. The default is **Manual test**. Press **Start service**; control and simulated clear-path permission are prepared automatically.
2. Use **Enter view** to put the person in front of the rover. Answer **Yes**, then **Items are loaded**.
3. In **Test person**, press **Move away**, **Come closer**, **Walk left**, or **Walk right**. Walking continues until **Stand still**, a placement action, service termination, page hiding, or the simulation's movement boundary. Speed controls the person, not the robot.
4. Use **Leave view** to test target loss, or **We have arrived** to finish normally. **Reset person** places the person 1.35 m ahead of the current rover; it does not reset the rover or restart the service. After a target-loss failure, use Enter view and Start service to try again.

### Simulated speech

Type in **Person says** and press **Say**. This simulates a recognized utterance without a microphone or speech synthesizer. While a question is waiting, its displayed answer label is accepted (case-insensitive, ignoring terminal punctuation): `Yes`, `No`, `Items are loaded`, `We have arrived`, or a custom choice. `はい` and `いいえ` are aliases for Yes and No. `Stop` or `停止` cancels the service. Other text produces **No matching answer**, or **No question is waiting**, and never launches another mission. An utterance is consumed once, not queued for a later question. This input is not an LLM conversation or an arbitrary spoken-command interpreter.

Manual controls move one virtual person in the environment; the existing geometric perception path generates observations from the rover's current pose. Enter/Leave are immediate placements inside/outside its field of view. These controls exist only in the simulator lab and do not control a real person's movement or send microphone audio.

### Repeatable scenarios

Stop the current service before switching to **Scenario runner**. The versioned scene editor, presets, import/export, and running-trial controls remain available there. Choose a preset and press **Start selected scenario**; after answering the service's questions, use **Next step** to advance the environment. Switching presets during a scenario trial still edits only the selected definition.

Simulator movement permission renews only while the service is running. Cancellation, control loss, or hiding the page revokes it. This shortcut is available only in the simulator lab; physical startup uses separate manual clearance; see [Live Playground](hardware-playground.md). It does not clear E-stop or an obstacle latch automatically. Use **Advanced controls** for explicit recovery, manual driving, or fault injection. Another controlling tab must release control first.

Also try **No**, **Cancel and stop**, and the **Lose the person** preset (target loss). After editing the template, stop the active run, reload, and press **Start selected scenario** again.

## Define a test scene

The scene describes the environment; `myService.ts` describes the robot service. No service code changes are needed to try a different scene.

- **Wait in front**: a stationary person, useful for Yes/No and loading confirmation.
- **Enter from outside view**: the person starts outside the camera field, begins walking after 2 seconds, and enters view. The second walk waits for Next step.
- **Walk and stop**: after loading confirmation, press Next step to walk to the endpoint and remain there.
- **Lose the person**: advance once to walk; after that finishes, advance again to disappear. The service should stop with target loss, not successful arrival.

Under **Edit scene**, edit the rover pose, person position, and ordered steps. Actions are Walk (one or more waypoints), Stand, and Disappear. Each step starts on **Next step** or **After delay**. Delays count from the previous step's completion (the first counts from scene startup). A walk finishes at its last waypoint; use a delayed Stand for a timed pause. Next step never skips an active walk. Start conditions do not inspect the service state: wait for consent/loading before manually advancing a follow test.

Coordinates use the same world frame as the map: metres, +x forward at zero heading, +y left. The UI shows heading in degrees; JSON uses radians. Walking speed is the person's speed, not the rover's. Detection is derived from their relative position and camera field of view; this is geometric simulation, not rendered-image recognition.

**Selected scenario** is an editable definition, not an execution. Preset selection, editing, import and export remain available during a trial and do not change that trial. **Running** shows the separate snapshot used for the current trial, including its own Next step button. **Last trial** retains the final action progress after stopping or completion; action completion alone does not mean the service succeeded.

Press **Start selected scenario** to run a fresh copy from its initial state. If a trial is running, it is cancelled and joined, and stopping is confirmed before starting the replacement. A failed stop confirmation or cancellation during switching prevents the new trial from starting. No Reset scene step is needed. The definition selected at the moment Start is pressed is used even if you edit the selection while stopping. Cancellation, control loss, and hidden pages stop the scene clock. The simulator pose-reset API also clears injected faults. E-stop and obstacle latches are not automatically cleared.

**Export JSON** saves the scene; **Import JSON** validates and loads a scene without starting it. Export before reloading to retain edits. Files are versioned (`version: 1`), limited to 64 KB on import, 20 steps and 20 waypoints per step, coordinates within +/-10 m, delay 0-120 s, and person speed 0.01-0.5 m/s. See [an example scene](scenes/person-enters.json). The checklist records what a human should observe, not an automatic pass/fail result. Multiple people, obstacle geometry, and service-answer automation are outside this MVP.

The service screen using real camera observations is `http://localhost:5173/service?service=my-service`.
Simulator person and obstacle controls stay in `/playground`. Do not acquire control from multiple screens at the same time.

## Editing example and boundaries

All four services now use this panel in both Service and Playground. Choose the service
in the shared header. Playground also shows **Implementation**, loading the actual source
file listed above the code; My service shows `missions/myService.ts`.
The examples live in `service/examples/` and are registered with their sources in
`service/catalog.ts`. The common runner owns questions, cancellation and final stopping.
`greetPerson()` reuses the existing greeting mission; `guideTo("desk" | "entrance")`
reuses marker guidance and fails rather than announcing arrival when blocked or lost.
The source panel is read-only and does not highlight individual executed statements.
Physical marker guidance is disabled in this shared MVP; simulator checks do not qualify hardware.

```ts
await service.waitForPerson();
await service.approachPerson();
if (await service.ask("Would you like help carrying your belongings?")) {
  await service.confirm("Place your belongings on the rover.", "Items are loaded");
  await service.followPerson();
  service.say("We have arrived.");
}
```

- `waitForPerson()`: waits up to 60 seconds for the next person detection. A timeout is a failure.
- `approachPerson()`: approaches using the existing comeHere component. Target loss is a failure.
- `ask(text)`: returns true for **Yes** and false for **No**. Confirms a stop before waiting for input.
- `confirm(text, buttonLabel = "Continue")`: confirms a stop, then waits for the button you name.
- `choose(text, choices)`: confirms a stop and displays one button per choice. Returns the selected label. Use a non-empty list of distinct, non-blank strings.
- `waitForLoaded(text)`: compatibility shorthand for `confirm(text, "Items are loaded")`.
- `followPerson({ message?, buttonLabel? })`: uses the existing following component, including continuous following when enabled by the adapter profile. Defaults to **We have arrived**. Arrival requests a stop immediately, then joins the running operation and confirms stopping before returning. Target loss is not treated as success.
- `say(text)`: requests display and speech; it does not wait for speech to finish. Speech depends on browser voice and language settings.

### Reuse the screen

Questions and buttons come from your service code, not carry-specific screen logic:

```ts
const destination = await service.choose("Where would you like to go?", ["Desk", "Reception"]);
await service.confirm(`Ready for ${destination}?`, "Ready");
service.say(`You selected ${destination}.`);
```

This example selects and displays a destination; it does not navigate there. Connect a supported movement behavior explicitly. Call these operations sequentially with `await`; the panel shows one question at a time. Cancellation rejects the pending question rather than choosing an answer.

To change your own service, edit `myService.ts`; no panel changes are required. The existing selector resolves definitions and their raw source through `service/catalog.ts`. Adding a new selector entry also requires a stable identifier and URL handling in `navigation.ts`, plus tests. Do not replace the common panel just to change questions. Acquisition, clearance, cancellation, and emergency-stop controls remain shared.

The runtime handles input buttons, cancellation on control loss, disconnect, emergency stop, page hiding or unmounting, target loss, and final stop confirmation. A new run cannot start until the previous run finishes. A failed stop confirmation is not reported as completion.

Motion uses the high-level ServiceRover interface. Command TTL, speed limits, ownership, front obstacle checks, and latched E-stop are preserved. Person selection and observation freshness follow the existing approach/follow contracts. The service does not authenticate a person's identity or detect luggage; **Items are loaded** is the user's confirmation.

Runtime files are `service/studentService.ts` and `components/StudentServicePanel.tsx`. This implementation does not add a general framework, voice input, unloading detection, or multiple-person identification.

## Verification scope

Automated tests use the existing approach/follow components and cover normal completion, refusal, cancellation, target loss, stop confirmation failure, and screen input. The Simulator browser flow has been checked through approach, consent, loading confirmation, following, arrival, and confirmed stop. Physical hardware, Windows startup, four simultaneous robots, physical network loss, and the new screen on a smartphone remain unverified. Existing hardware records are not evidence that this new API has been tested on hardware.

The shared-screen update additionally tests custom choices and confirmation labels, invalid answers, arrival during an in-flight bounded move, arrival stop failure, and the continuous-follow path from main. These are automated tests with a test rover, not new physical-hardware evidence; the browser-flow statement above describes the original template validation.
