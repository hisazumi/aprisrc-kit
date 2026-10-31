# APRISRC Kit participant quickstart

[日本語](challenger-quickstart.ja.md)

This guide helps an APRISRC participant create their own service using APRISRC Kit.
The starter demonstrates the API; it is not a prescribed challenge solution. Participants
choose the service purpose and interaction. See [Purpose and scope](positioning.md).

This is the shortest path to creating a small person-responsive rover service without
changing APRIS platform code or firmware. Start in the Simulator. Allow 30-45 minutes.

## 1. Start the development environment

Requirements: Node.js, npm, Python 3.11 or later, and `uv`.

```bash
npm install
uv sync --directory apps/server --dev
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev
```

Open `http://localhost:5173/lab`. These settings explicitly select the Simulator and
desktop HTTP even if certificates exist. No UGV02 is required. Stop an existing server
before changing adapters. For a guided change/compare trial use the
[Playground workshop](demos/playground-workshop.md); this guide uses the generic Mission Panel.

## 2. Run the starter unchanged

1. Press **Acquire control**.
2. In **Virtual person**, choose `Left` or `Right`, then press **Start scene**.
3. Select `Person greeting starter` under **Service missions**.
4. Press **Run selected mission**.
5. Confirm that the rover turns at most 15 degrees toward the person and reports
   `Greeting complete`.

If nothing moves, check connection status, control ownership, E-stop, and the Virtual person
`visible` state, in that order.

## 3. Change one service

Edit only this file first:

```text
apps/pwa/src/missions/challengerStarter.ts
```

Start by changing `greeting`, `maxTurnDeg`, or `minTurnDeg` in
`apps/pwa/src/config/greetingStarter.ts`. You can preview greeting and maximum-turn changes
in the [Service playground](demos/service-playground.md). The browser reloads after a
save. You can then combine public API calls inside `run()`:

```ts
say("I found someone.")
await rover.turn(10)
await rover.move(-0.10, 0.05)
await rover.stop("service completed")
```

Forward motion is allowed only while front safety is `CLEAR`. For a first experiment, prefer
turning, reversing, speech, and conditions based on `person.bearingDeg`. Mission code must not
change speed limits, communication TTL, control ownership, or E-stop behavior.

## 4. Add a voice or text trigger

For a complete new-action example, registration, and a change-and-try exercise, see
[Add a voice-triggered action](adding-actions.md).

Define the intent, representative utterances, local-rule keywords, and acknowledgement in the
same mission's optional `trigger`. Entering a matching phrase in the `/lab` **Human
interaction** panel starts the mission without an API key.

```ts
trigger: {
  intent: "greet_person",
  description: "Find and greet a visible person.",
  examples: ["人に挨拶して", "Greet the person"],
  keywords: ["挨拶", "greet"],
  response: "Okay. I will look for someone."
}
```

Speech recognition or an LLM may select a registered mission, but cannot generate distance,
speed, motor, or rover-protocol commands.

## 5. Check the work

```bash
npm run test:starter
npm run typecheck
```

Update `apps/pwa/src/missions/challengerStarter.test.ts` when starter behavior changes. For a
new mission, create a new file and register it in `apps/pwa/src/missions/index.ts`.

## 6. Optional hardware handoff

After the starter works in the Simulator, run the same mission on the supported UGV02. The
one-person connection, raised-wheel, floor, stop, and diagnosis procedure is in
[UGV02 self-test](hardware/ugv02-self-test.md). For another rover or perception device, read
[Hardware assumptions and porting](hardware/service-hardware-porting.md).

## Editable boundary

A Challenger normally edits only:

- `apps/pwa/src/missions/<service>.ts`
- the corresponding `<service>.test.ts`
- `apps/pwa/src/missions/index.ts`
- `apps/pwa/src/config/`

`useRoverSocket.ts`, server runtime, adapters, firmware, and protocol schemas belong to the
platform. When the public API lacks a required capability, record an API request instead of
bypassing the platform boundary.
