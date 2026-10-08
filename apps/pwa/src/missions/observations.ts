import type { PersonEvent } from "../protocol";
import type { ServiceRover } from "./api";

export class PersonObservationTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`No person was detected within ${timeoutMs} ms`);
    this.name = "PersonObservationTimeoutError";
  }
}

/** Wait for the next accepted person detection or mission cancellation. */
export function waitForPerson(
  rover: ServiceRover,
  signal: AbortSignal,
  timeoutMs = 10_000
): Promise<Readonly<PersonEvent>> {
  signal.throwIfAborted();

  return new Promise((resolve, reject) => {
    let settled = false;
    let timeout: number | undefined;
    let unsubscribe: () => void = () => undefined;

    const cleanup = () => {
      if (timeout !== undefined) window.clearTimeout(timeout);
      signal.removeEventListener("abort", onAbort);
      unsubscribe();
    };
    const finish = (operation: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      operation();
    };
    const onAbort = () => finish(() => reject(
      signal.reason ?? new DOMException("Mission cancelled", "AbortError")
    ));

    signal.addEventListener("abort", onAbort, { once: true });
    unsubscribe = rover.onPerson((event) => {
      if (event.status === "detected") finish(() => resolve(event));
    });

    if (settled) {
      unsubscribe();
      return;
    }
    timeout = window.setTimeout(
      () => finish(() => reject(new PersonObservationTimeoutError(timeoutMs))),
      timeoutMs
    );
  });
}
