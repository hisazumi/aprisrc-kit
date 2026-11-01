import type { MissionContext } from "../missions/api";
import { runComeHere, runFollowMe } from "../missions/comeHere";
import { waitForPerson } from "../missions/observations";
import { createGreetingMission } from "../missions/challengerStarter";
import { runMobileReceptionist } from "../missions/mobileReceptionist";
import type { CourseDestination } from "../config";

export interface StudentServiceApi {
  greetPerson(): Promise<void>;
  guideTo(destination: CourseDestination): Promise<void>;
  waitForPerson(): Promise<void>;
  approachPerson(): Promise<void>;
  ask(message: string): Promise<boolean>;
  confirm(message: string, buttonLabel?: string): Promise<void>;
  choose(message: string, choices: readonly string[]): Promise<string>;
  waitForLoaded(message: string): Promise<void>;
  followPerson(options?: { message?: string; buttonLabel?: string }): Promise<void>;
  /** Requests display and speech; does not wait for speech to finish. */
  say(message: string): void;
}
export interface StudentService {
  title: string;
  run(service: StudentServiceApi): Promise<void>;
}
export interface ServiceQuestion { message: string; choices: readonly string[] }
export type ServicePrompt = (question: ServiceQuestion, signal: AbortSignal) => Promise<string>;

/** Runs only through the existing safety-enforced ServiceRover boundary. */
export async function runStudentService(
  definition: StudentService,
  context: MissionContext,
  prompt: ServicePrompt
): Promise<void> {
  const { rover, report, say } = context;
  const lifecycle = new AbortController();
  const signal = lifecycle.signal;
  const abort = () => lifecycle.abort(context.signal.reason);
  context.signal.addEventListener("abort", abort, { once: true });
  if (context.signal.aborted) abort();
  let unsubscribe = () => {};

  const checked = async <T>(operation: () => Promise<T>): Promise<T> => {
    signal.throwIfAborted();
    const value = await operation();
    signal.throwIfAborted();
    return value;
  };
  const question = async (message: string, choices: readonly string[], inputSignal: AbortSignal) => {
    if (!choices.length || choices.some(choice => !choice.trim()) || new Set(choices).size !== choices.length) {
      throw new Error("Choices must be non-empty, distinct labels");
    }
    const labels = [...choices];
    const answer = await prompt({ message, choices: labels }, inputSignal);
    inputSignal.throwIfAborted();
    if (!labels.includes(answer)) throw new Error("Unexpected service answer");
    return answer;
  };
  const request = (message: string, choices: readonly string[]) => checked(async () => {
    await rover.stop("waiting for service input");
    say(message);
    return question(message, choices, signal);
  });
  try {
    await definition.run({
      greetPerson: () => checked(() => createGreetingMission().run({ ...context, signal })),
      guideTo: (destination) => checked(async () => {
        // Guiding turns toward a marker, so the visitor can leave the camera view.
        unsubscribe(); unsubscribe = () => {};
        const outcome = await runMobileReceptionist(rover, context.config, signal, destination, { onUpdate: report });
        if (outcome !== "arrived") throw new Error(`Guidance stopped: ${outcome}`);
      }),
      waitForPerson: () => checked(async () => {
        report({ phase: "waiting", detail: "Waiting for a person" });
        await waitForPerson(rover, signal, 60_000);
        unsubscribe();
        unsubscribe = rover.onPerson((person) => {
          if (person.status === "lost") lifecycle.abort(new Error("Target lost. Service interrupted."));
        });
      }),
      approachPerson: () => checked(async () => {
        const outcome = await runComeHere(rover, signal, { onUpdate: report });
        if (outcome !== "arrived") throw new Error("Target lost. Service interrupted.");
      }),
      ask: async (message) => await request(message, ["Yes", "No"]) === "Yes",
      confirm: async (message, buttonLabel = "Continue") => { await request(message, [buttonLabel]); },
      choose: request,
      waitForLoaded: async (message) => { await request(message, ["Items are loaded"]); },
      followPerson: (options = {}) => checked(async () => {
        const controller = new AbortController();
        const abort = () => controller.abort(signal.reason);
        signal.addEventListener("abort", abort, { once: true });
        // Both operations are cancelled and joined before allowing a restart.
        const following = runFollowMe(rover, controller.signal, { onUpdate: report });
        const arrival = question(options.message ?? "Press We have arrived when you reach your destination",
          [options.buttonLabel ?? "We have arrived"], controller.signal);
        try {
          const result = await Promise.race([
            following.then(() => "lost" as const),
            arrival.then(() => "arrived" as const)
          ]);
          signal.throwIfAborted();
          if (result === "lost") throw new Error("Target lost. Service interrupted.");
        } finally {
          controller.abort();
          // Abort alone cannot cancel an in-flight distance-based move.
          const stopping = rover.stop("student following finished");
          const results = await Promise.allSettled([following, arrival, stopping]);
          signal.removeEventListener("abort", abort);
          if (results[2].status === "rejected") throw results[2].reason;
        }
      }),
      say: (message) => { signal.throwIfAborted(); say(message); }
    });
    signal.throwIfAborted();
  } finally {
    // A rejected stop must remain an error, including at arrival/cancellation.
    unsubscribe();
    context.signal.removeEventListener("abort", abort);
    await rover.stop("student service finished");
  }
}
