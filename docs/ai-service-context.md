# AI context: APRISRC Kit service development

[日本語](ai-service-context.ja.md)

Attach this memo **together with current source files**. It is not a complete API
specification, nor evidence that the assistant has read the repository. Human
workflow: [AI-assisted development](ai-assisted-development.md).

## Context to attach

Use files from one checkout revision, including relevant uncommitted changes:

| File | Purpose |
| --- | --- |
| `apps/pwa/src/missions/api.ts` | Authoritative mission/context/rover types |
| `apps/pwa/src/missions/index.ts` | Existing registration and exports |
| `apps/pwa/src/protocol.ts` | Observation and pose types; follow imports if needed |
| `apps/pwa/src/config/index.ts` | Configuration types and exports; follow imports |
| The mission being edited and its tests | Current behavior and local patterns |
| `apps/pwa/src/missions/challengerStarter.ts` and its test | Existing reference when starting a mission |
| `apps/pwa/package.json` | Available dependencies and check commands |

Add helper modules actually imported by the mission, relevant configuration files,
and `docs/mission-api.md` or `docs/adding-actions.md` as needed. For a dedicated
screen, include that component, its callers and tests. Request missing dependencies
of these files rather than assuming their contents. Do not request credentials.

## Architecture and ownership

APRIS is the conference, APRISRC is its robot challenge, and APRISRC Kit is the
service prototyping platform. Participants design the service; samples do not
prescribe challenge solutions or rules.

Browser observations -> mission/service state and decisions -> `ServiceRover`
-> server ownership and safety -> Simulator or hardware Adapter.

Usually add/edit a mission and configuration, and register it in `missions/index.ts`.
`missions/api.ts`, protocol, transport, Adapter, safety and firmware are platform-owned;
do not modify them merely to make generated service code compile. If the public API
cannot express the requested behavior, explain the missing capability and propose
a separately reviewed platform change. Do not silently invent an abstraction.

## API semantics to preserve

Check the attached types and implementations; these notes are not replacement declarations.

- `defineMission` describes a mission; `run(context, input?)` implements it.
  `script` is a display outline, not executable behavior.
- `move`: signed distance in metres, optional speed in metres/second.
  `turn`: signed angle in degrees (positive left), optional speed in radians/second.
  `Pose.yaw` and continuous angular velocity use radians, not degrees.
- Bounded move/turn promises represent completion or reject on failure/cancellation.
  Do not report arrival before the operation completes. `stop()` may reject when
  stopping cannot be confirmed; never suppress that failure and report success.
- `setVelocity` is optional, not a universal hardware capability. Its promise
  acknowledges transport sending, not physical execution. Prefer existing follow
  helpers when applicable; do not implement a new motor control loop in a sample.
- `getPose` is an estimate and may be unavailable. Observation coordinates, marker
  correction and image bounding-box widths are not interchangeable with metric distance.
- Observation subscriptions return unsubscribe functions. Clean them up on completion,
  cancellation and errors; avoid duplicated listeners, timers and concurrent motion.
- Honor `AbortSignal`; bound waits and repeated behavior. Treat target loss, stale
  observations, and unavailable optional APIs explicitly. Do not auto-resume after
  reconnect or emergency stop. Let the host UI manage ownership and movement consent.
- `say()` requests browser speech and does not await audible completion.
  `report()` changes progress display, not physical state.

## Natural-language triggers

An optional mission `trigger` contains intent, description, examples, keywords and
response. Keep mission IDs and intent names unique and preserve existing entries.
Consult `adding-actions.md` for naming and reserved intents. Local rules use keyword
substring matching; LLM providers select registered intents, not arbitrary executable
code. A development chat assistant and the application's runtime LLM are separate.
Editing missions does not itself require a runtime LLM key. Keys belong on the server.

Registration supports `/lab` missions and the intent catalog. Dedicated `/app` flows
and Playground samples require their own integration; do not claim they appear
automatically. Do not add dependencies, change public contracts or weaken safety
checks without an explicit scope decision.

## Expected response

Explain the intended behavior briefly, list exact changed paths, provide a small
reviewable patch, and specify verification commands and observable outcomes.
Follow existing patterns and tests. Ask for missing source instead of fabricating
APIs. Distinguish code inspection, tests actually executed, proposed checks, Simulator
observations and physical validation. Never claim hardware execution from a mock test.
