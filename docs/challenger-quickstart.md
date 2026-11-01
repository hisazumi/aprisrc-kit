# APRISRC Kit participant quickstart

[日本語](challenger-quickstart.ja.md)

Build your own service for APRISRC; the carry example is a starting point, not a prescribed
challenge solution. Start with the Simulator, without a robot, camera, or LLM key.

## Start

Requirements: Node.js 22.12+ or 24+, npm, Python 3.12 and uv.
From the repository root on macOS/Linux:

```bash
npm ci
uv python install 3.12
uv sync --directory apps/server --no-dev
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev
```

Windows users: follow [Windows setup](windows-setup.md).
Open `http://localhost:5173/playground?service=my-service`, or the port printed at startup.

## Try the unchanged service

1. Keep **Manual test** selected. Press **Start service**, then **Enter view**.
2. Answer **Yes**, then **Items are loaded**.
3. Press **Move away**, then **Stand still**. Observe following and holding distance.
4. Press **We have arrived** and check **Service complete (stop confirmed)**.
5. Repeat with **No**, **Leave view**, or **Cancel and stop**.

If unavailable, check connection, Simulator adapter, E-stop and another tab owning control.
Simulator Playground prepares and renews synthetic clearance; this is not obstacle sensing.
Markers are optional for this service and **Markers visible** defaults off.

## Change your service

Edit `apps/pwa/src/missions/myService.ts`, shown in **Implementation**.
Change its title, offer text, or the sequence of awaited API calls. For example, add
`await service.confirm("Ready to follow?", "Ready");` immediately before
`await service.followPerson(...)`. A new confirmation should appear before following.

Stop before editing, reload, and repeat the same manual inputs. The code panel is read-only.
For API details, choices and scene JSON, see [My service guide](demos/student-service.md).
Built-in examples are separate files in `service/examples/`; `service/catalog.ts` connects
definitions and source to the selector. Registering a low-level mission does not add a service.

## Test and extend

```bash
npm test
npm run typecheck
npm run build
```

Add tests for normal completion, refusal, target loss, cancellation and failed stopping.
Do not change ownership, command TTL, speed limits or E-stop to make a service pass.

For a lower-level movement action, see [Mission API](mission-api.md) and
[Add a voice-triggered action](adding-actions.md). Registered missions and the text/voice
interpreter are under Playground **Advanced controls**. Stop the shared service first.
A mission trigger does not automatically become an answer or action in the shared panel.

For AI-assisted changes, provide [the development guide](ai-assisted-development.md),
[context memo](ai-service-context.md), and current source, not screenshots alone.

## Hardware later

Use [UGV02 self-test](hardware/ugv02-self-test.md) or [iron-X following](hardware/ironx-follow.md).
The shared hardware UI requires separate control acquisition, **Confirm clear path · 30 s**,
and **Start service**; it does not inherit automatic consent renewal from the old Carry UI.
See [Live Playground](demos/hardware-playground.md) before any motion.
Physical marker guidance is disabled; simulator success does not qualify hardware.
