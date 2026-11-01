import type { MissionContext } from "../missions/api";
import { runComeHere, runFollowMe } from "../missions/comeHere";
import { waitForPerson } from "../missions/observations";

export interface StudentServiceApi {
  waitForPerson(): Promise<void>;
  approachPerson(): Promise<void>;
  ask(message: string): Promise<boolean>;
  waitForLoaded(message: string): Promise<void>;
  followPerson(): Promise<void>;
  /** Requests display and speech; does not wait for speech to finish. */
  say(message: string): void;
}
export interface StudentService {
  title: string;
  run(service: StudentServiceApi): Promise<void>;
}
export type PromptKind = "question" | "loaded" | "arrived";
export type ServicePrompt = (kind: PromptKind, message: string, signal: AbortSignal) => Promise<boolean>;

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
  const request = (kind: PromptKind, message: string) => checked(async () => {
    await rover.stop("waiting for service input");
    say(message);
    return prompt(kind, message, signal);
  });
  try {
    await definition.run({
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
      ask: (message) => request("question", message),
      waitForLoaded: async (message) => { await request("loaded", message); },
      followPerson: () => checked(async () => {
        const controller = new AbortController();
        const abort = () => controller.abort(signal.reason);
        signal.addEventListener("abort", abort, { once: true });
        // Both operations are cancelled and joined before allowing a restart.
        const following = runFollowMe(rover, controller.signal, { onUpdate: report });
        const arrival = prompt("arrived", "Press We have arrived when you reach your destination", controller.signal);
        try {
          const result = await Promise.race([
            following.then(() => "lost" as const),
            arrival.then(() => "arrived" as const)
          ]);
          signal.throwIfAborted();
          if (result === "lost") throw new Error("Target lost. Service interrupted.");
        } finally {
          controller.abort();
          await Promise.allSettled([following, arrival]);
          signal.removeEventListener("abort", abort);
          await rover.stop("student following finished");
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
