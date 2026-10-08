import { greetingStarterSettings, type GreetingStarterSettings } from "../config/greetingStarter";
import { defineMission } from "./api";
import { waitForPerson } from "./observations";

export function createGreetingMission(settings: GreetingStarterSettings = greetingStarterSettings) {
  return defineMission({
    id: "challenger-starter",
    title: "Person greeting starter",
    description: "Wait for a person, face them, and greet them.",
    runningDetail: "Waiting for a visible person",
    script: [
      "const person = await waitForPerson(rover, signal, 30_000)",
      "await rover.turn(toward(person))",
      "say(settings.greeting)"
    ],
    trigger: {
      intent: "greet_person",
      description: "Find a visible person, turn toward them, and greet them.",
      examples: ["人に挨拶して", "見つけた人に声をかけて", "Greet the person"],
      keywords: ["挨拶", "声をかけ", "greet", "say hello"],
      response: "Okay. I will look for someone."
    },
    async run({ rover, signal, report, say }) {
      report({ phase: "waiting", detail: "Waiting for a visible person" });
      const person = await waitForPerson(rover, signal, 30_000);
      const turnDeg = clamp(person.bearingDeg ?? 0, -settings.maxTurnDeg, settings.maxTurnDeg);

      if (Math.abs(turnDeg) >= settings.minTurnDeg) {
        report({
          phase: "aligning",
          detail: turnDeg > 0 ? "Turning left toward the person" : "Turning right toward the person",
          person
        });
        await rover.turn(turnDeg, 0.35);
        signal.throwIfAborted();
      }

      say(settings.greeting);
      report({ phase: "arrived", detail: "Greeting complete", person });
    }
  });
}

export const challengerStarterMission = createGreetingMission();

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
