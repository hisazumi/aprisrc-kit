# Add a voice-triggered action

[日本語](adding-actions.ja.md)

Start with the [participant quickstart](challenger-quickstart.md). This exercise adds
an action in `/lab` without changing the server, firmware, or LLM prompt.
Use the Simulator first. The example introduces the robot without moving it, so
you can check intent selection separately from motion.

## 1. Write the action

Create `apps/pwa/src/missions/introduceRobot.ts`:

```ts
import { defineMission } from "./api";

export const introduceRobotMission = defineMission({
  id: "introduce-robot",
  title: "Introduce the robot",
  description: "Explain what this robot can do.",
  runningDetail: "Introducing the robot",
  script: ["Say the introduction", "Report completion"],
  trigger: {
    intent: "introduce_robot",
    description: "Introduce the robot and explain its available services.",
    examples: ["Introduce yourself", "Tell me about this robot"],
    keywords: ["introduce yourself", "about this robot"],
    response: "Sure. Let me introduce myself."
  },
  async run({ signal, say, report }) {
    signal.throwIfAborted();
    say("Hello! I can follow you or guide you to a marked destination.");
    report({ phase: "arrived", detail: "Introduction requested" });
  }
});
```

Change the spoken sentence to match your actual service. `say()` requests browser
speech; it does not wait for speech to finish. The report is not proof that audio
has finished or was audible.

## 2. Register it

In `apps/pwa/src/missions/index.ts`, add:

```ts
import { introduceRobotMission } from "./introduceRobot";
```

Add `introduceRobotMission,` inside the existing
`createMissionRegistry([...])` list. Keep its existing entries.
Both `id` and `trigger.intent` must be unique. Intent names use lowercase letters,
digits and underscores and start with a letter. Do not use reserved intents
`stop`, `wait_here`, `report_status`, or `clarify`.

Registration adds the mission to `/lab` **Service missions** and the **Human
interaction** intent catalog. It does not automatically add it to a dedicated
`/app` service flow or create a Playground sample.

## 3. Try and change it

1. Start the Simulator as described in the quickstart and open `/lab`.
2. Acquire control, select **Introduce the robot**, and run it manually.
3. In **Human interaction**, enter `Introduce yourself`. With `rules`, this
   matches the registered keyword; no microphone or API key is required.
4. Change the sentence in `say()`, save, and repeat. Listen for the new sentence.
5. With a configured LLM, try `Could you explain what you can do?`. Confirm which
   action was selected; a model's choice is not guaranteed. Under `rules`, this
   paraphrase need not match.

See [Assistant providers](assistant-providers.md) for selecting `rules`, `openai`,
or `gemini`. Keep API keys on the server, never in mission code.

| Edit | Effect |
| --- | --- |
| `trigger.description`, `examples` | Help the LLM choose this action |
| `trigger.keywords` | Substring matching for rules and cloud-error fallback |
| `trigger.response` | Acknowledgement for local rules |
| `run()` | Actual service behavior |
| `say()` / `report()` | Spoken output / progress display |
| `script` | Display-only outline, not executable code |

The LLM returns the registered intent as `action: "introduce_robot"`; the app
calls its `run()`. It does not generate movement code. Similar descriptions or
keywords across missions can make selection ambiguous. For a greeting variation,
edit `challengerStarter.ts` first instead of registering a competing greeting.

## 4. Test before adding motion

Run from the repository root:

```sh
npm run test:starter
npm run typecheck
```

Existing starter tests do not test your new action. Add
`apps/pwa/src/missions/introduceRobot.test.ts`, using
`challengerStarter.test.ts` as a pattern. Check the requested speech, progress,
and cancellation before execution. Also try an unrelated phrase and confirm it
does not unexpectedly select your action.

To add person-responsive motion, study `challengerStarter.ts`: it waits for a
person with `waitForPerson`, limits the turn angle, and checks cancellation.
Use only the [Mission API](mission-api.md), await motion calls, and check
`signal.throwIfAborted()` between steps. Test no person, left/right person,
timeout and cancellation in the Simulator. Simulator success is not physical
validation; follow the hardware guide before running the same code on a rover.
