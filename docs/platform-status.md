# Platform status

[日本語](platform-status.ja.md)

Shared-UI documentation reviewed: 2026-11-01. No additional physical trial.
APRISRC Kit supports participant-created services; samples are not challenge requirements
or judging rules.

## Available now

- Shared Service / Playground / Console navigation with service-preserving URLs.
- One runner and question panel for My service, Carry helper, Person greeting and Mobile receptionist.
- Simulator Playground manual person inputs, simulated utterances, scene JSON and marker inputs.
- Read-only Implementation source; edit `missions/myService.ts` to try your own flow.
- Marker controls for every service; Markers visible defaults off.
- Generic missions and text/voice intents under Advanced controls. Rules / OpenAI / Gemini
  interpretation is separate from shared-panel answers.
- Server ownership, speed limits, command TTL, disconnect stop and latched E-stop.
- Simulator, UGV02 WebSocket, diagnostic factory HTTP and experimental iron-X local/network adapters.

## Current limitations

- Shared Service and physical Playground require separate 30-second manual clearance.
  Starting does not extend it. The old dedicated Carry UI's automatic renewal was not
  carried over; this is a known limitation. Only Simulator Playground auto-renews.
  See [hardware operation](demos/hardware-playground.md).
- The shared UI still needs physical qualification. Older UGV02/iron-X following trials
  are evidence for those older configurations only.
- Physical marker guidance is disabled in Service and Playground. Legacy URLs do not expose
  an alternate live path.
- Specialized preview sliders, execution-line highlighting, and old Carry-specific voice/LLM
  controls are not in the shared panel.
- Simulator observations are geometric inputs, not tests of real camera accuracy.
- Manual front clearance is not sensor-derived free space. Rear/side protection, general
  obstacle avoidance, LiDAR safety integration, SLAM, path planning, escort monitoring and
  qualified physical stopping distances are not provided.
- Service state is browser-local; reconnection alone does not resume it. Unattended operation
  is outside scope.

## Verification and next work

The shared-UI browser trial covered all four simulator flows, marker defaults and desktop/mobile
layout. After the myService rename, 183 PWA tests and the production build passed.
These checks do not qualify hardware or Windows startup.

Use the [participant quickstart](challenger-quickstart.md) and [handoff](handoff.md) for peer trials.
Before hardware use, revisit service clearance and physically revalidate the shared UI.
See [roadmap](roadmap.md) for priorities and [operations](operations/runbook.md) for recovery.
Hardware guides retain historical evidence; it must not be read as qualification of the new UI.
