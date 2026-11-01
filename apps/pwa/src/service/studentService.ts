import type { MissionContext } from "../missions/api";
import { runComeHere, runFollowMe } from "../missions/comeHere";
import { waitForPerson } from "../missions/observations";
import { createGreetingMission } from "../missions/challengerStarter";
import { runMobileReceptionist } from "../missions/mobileReceptionist";
import type { CourseDestination } from "../config";
import { choiceOption, type ServiceChoice, type ServiceChoiceInput } from "./simulatedSpeech";
export type { ServiceChoice, ServiceChoiceInput } from "./simulatedSpeech";

export interface StudentServiceApi {
  greetPerson(): Promise<void>;
  guideTo(destination: CourseDestination): Promise<void>;
  waitForPerson(): Promise<void>;
  approachPerson(): Promise<void>;
  ask(message: string, phrases?: { yes?: readonly string[]; no?: readonly string[] }): Promise<boolean>;
  confirm(message: string, buttonLabel?: string, phrases?: readonly string[]): Promise<void>;
  choose(message: string, choices: readonly ServiceChoiceInput[]): Promise<string>;
  waitForLoaded(message: string): Promise<void>;
  followPerson(options?: { message?: string; buttonLabel?: string; phrases?: readonly string[] }): Promise<void>;
  /** Requests display and speech; does not wait for speech to finish. */
  say(message: string): void;
}
export interface StudentService {
  title: string;
  run(service: StudentServiceApi): Promise<void>;
}
export interface ServiceQuestion { message: string; choices: readonly string[]; options?: readonly ServiceChoice[] }
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
  const question = async (message: string, choices: readonly ServiceChoiceInput[], inputSignal: AbortSignal) => {
    const options = choices.map(choice => {
      const option = choiceOption(choice);
      return { ...option, ...(option.phrases ? { phrases: [...option.phrases] } : {}) };
    });
    if (!options.length || options.some(choice => !choice.value.trim() || !choice.label.trim()
      || choice.phrases?.some(phrase => !phrase.trim())) || new Set(options.map(choice => choice.value)).size !== options.length) {
      throw new Error("Choices must be non-empty, distinct labels");
    }
    const labels = options.map(choice => choice.value);
    const answer = await prompt({ message, choices: labels,
      ...(choices.some(choice => typeof choice !== "string") ? { options } : {}) }, inputSignal);
    inputSignal.throwIfAborted();
    if (!labels.includes(answer)) throw new Error("Unexpected service answer");
    return answer;
  };
  const request = (message: string, choices: readonly ServiceChoiceInput[]) => checked(async () => {
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
      ask: async (message, phrases) => await request(message, phrases ? [
        { value: "Yes", label: "Yes", phrases: phrases.yes },
        { value: "No", label: "No", phrases: phrases.no }
      ] : ["Yes", "No"]) === "Yes",
      confirm: async (message, buttonLabel = "Continue", phrases) => {
        await request(message, [phrases ? { value: buttonLabel, label: buttonLabel, phrases } : buttonLabel]);
      },
      choose: request,
      waitForLoaded: async (message) => { await request(message, ["Items are loaded"]); },
      followPerson: (options = {}) => checked(async () => {
        const controller = new AbortController();
        const abort = () => controller.abort(signal.reason);
        signal.addEventListener("abort", abort, { once: true });
        // Both operations are cancelled and joined before allowing a restart.
        const following = runFollowMe(rover, controller.signal, { onUpdate: report });
        const arrival = question(options.message ?? "Press We have arrived when you reach your destination",
          [options.phrases ? { value: options.buttonLabel ?? "We have arrived",
            label: options.buttonLabel ?? "We have arrived", phrases: options.phrases }
            : options.buttonLabel ?? "We have arrived"], controller.signal);
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
