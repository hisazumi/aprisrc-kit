# Service playground

[日本語](service-playground.ja.md)

Use [the workshop](playground-workshop.md) to start the Simulator. The shared header
selects My service, Carry helper, Person greeting, or Mobile receptionist. Use
`/playground?service=my-service`; changing the view preserves the service.

## Manual testing

### Voice answers

Authors can add alternative phrases without changing the buttons or service logic:

```ts
const accepted = await service.ask("Would you like help?", {
  yes: ["yes please", "sure", "please help me"],
  no: ["no thanks", "not now"]
});
await service.confirm("Place your belongings on the rover.", "Items are loaded",
  ["ready", "all set", "loaded"]);
const destination = await service.choose("Where?", [
  { value: "desk", label: "Desk", phrases: ["my desk", "the desk please"] },
  { value: "entrance", label: "Entrance", phrases: ["the entrance please"] }
]);
await service.followPerson({ phrases: ["we are here", "arrived"] });
```

`label` appears on the button; `value` is returned to the program. The label itself
and each entry in `phrases` are accepted. Existing string choices still work.
`ask` returns a boolean; its optional `yes` and `no` arrays add phrases.
`confirm` accepts phrases as its third argument, and `followPerson` accepts a
`phrases` option for arrival. Carry helper and My service demonstrate these aliases.
The same matching applies to microphone input and Playground's simulated speech.
Matching ignores capitalization and trailing sentence punctuation, but is not a
substring search or general language understanding. Ambiguous aliases do not select
an answer. Avoid overlapping phrases; **Stop** remains reserved for stopping.

**Voice conversation** defaults to on in Service and off in Playground; either
screen lets you change it. Start the service and allow microphone access when
prompted. In this mode, each question starts English recognition after its spoken
prompt finishes. Say a displayed choice, such as **Yes**, **No**, **Items are loaded**,
or **We have arrived**. Buttons remain available. This uses choice matching, not an LLM.

With the mode off, **Answer by voice** listens once. If nothing matches or microphone
access fails, retry with that button or select a choice; the service does not advance.
Recognition stops on cancellation, loss of control, leaving the page, or answering.
Normal voice commands remain separate from answers to the current question.

Use HTTPS (or localhost) and a browser supporting speech recognition. Browsers may
require another tap before listening; if recognition is unavailable, use the answer
buttons. Automatic listening is not a substitute for the emergency-stop control.

1. Keep **Manual test** selected and press **Start service**. Simulator control and
   synthetic clear-path input are prepared automatically.
2. Press **Enter view**. Use **Move away**, **Come closer**, **Walk left**, **Walk right**,
   and **Stand still** to move the virtual person. **Leave view** tests target loss.
3. Answer the service's displayed questions. My service and Carry helper use **Yes**,
   **Items are loaded**, and **We have arrived**. Person greeting faces and greets once.
4. **Person says** / **Say** simulates recognized text for the current question.
   It is not microphone recognition or an LLM conversation.
5. **Cancel and stop** ends a trial. Stop before changing service or test mode.
   **Restart service** stops the previous trial before starting another.

## Markers and scenarios

**Test markers** is available for every service. Marker positions on the map do not mean
they are detected: **Markers visible** defaults to **off**. Enable it to supply observations,
which also depend on the simulated field of view. Coordinates are locked while running.

For Mobile receptionist, set Entrance/Desk coordinates before starting, enable
**Markers visible**, press **Start service**, **Enter view**, choose the destination,
and press **Let's go**. The rover searches in place for an unseen marker, then approaches
when detected; search and approach have bounds. It does not drive around searching.
The visitor triggers guidance but is not escorted or monitored along the route.
Physical marker guidance is disabled in both Service and Playground.

For repeatable environments, stop and choose **Scenario runner**. Edit or import a scene,
then press **Start selected scenario**. Use **Next step** for manually triggered steps.
Export JSON before reloading to keep edits. See [scene definitions](student-service.md#define-a-test-scene).
Manual person controls and scenarios are common to all services.

## Code and diagnostics

**Implementation** shows the actual service definition, read-only, full-width below the
service/map row. It is not an editor or statement-level debugger. My service is
`apps/pwa/src/missions/myService.ts`; built-in examples are in `apps/pwa/src/service/examples/`.
Stop before editing files, then reload and repeat the same trial.

Greeting settings remain in `config/greetingStarter.ts`. Specialized preview sliders,
old **Follow me** / **Guide me** buttons, and source-line highlighting are not in the shared UI.
**Advanced controls** contains the generic mission, interaction, diagnostics, and fault tools.
Do not run a generic mission and a shared service at the same time.

Simulator observations are geometric inputs, not recognition of rendered camera images.
For actual cameras and robots, use [Live Playground](hardware-playground.md).
