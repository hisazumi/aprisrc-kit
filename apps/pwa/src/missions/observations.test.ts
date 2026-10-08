import { describe, expect, it, vi } from "vitest";

import type { PersonEvent } from "../protocol";
import type { ServiceRover } from "./api";
import { PersonObservationTimeoutError, waitForPerson } from "./observations";

function person(status: PersonEvent["status"]): PersonEvent {
  return {
    eventId: crypto.randomUUID(),
    status,
    confidence: status === "detected" ? 0.95 : 0,
    capturedAt: Date.now() / 1000,
    source: "scenario",
    personId: "starter-person",
    centerX: 0.5,
    centerY: 0.5,
    width: 0.2,
    height: 0.5,
    bearingDeg: 0
  };
}

function roverWithPersonEvents(events: PersonEvent[]): ServiceRover {
  return {
    move: vi.fn(async () => undefined),
    turn: vi.fn(async () => undefined),
    stop: vi.fn(async () => undefined),
    getPose: vi.fn(async () => ({ x: 0, y: 0, yaw: 0 })),
    onPose: vi.fn(() => () => undefined),
    onPerson: vi.fn((listener) => {
      for (const event of events) queueMicrotask(() => listener(event));
      return () => undefined;
    }),
    onMarker: vi.fn(() => () => undefined)
  };
}

describe("waitForPerson", () => {
  it("ignores lost events and resolves with the next detection", async () => {
    const detected = person("detected");
    const result = await waitForPerson(
      roverWithPersonEvents([person("lost"), detected]),
      new AbortController().signal
    );

    expect(result).toBe(detected);
  });

  it("rejects when the mission is cancelled", async () => {
    const controller = new AbortController();
    const waiting = waitForPerson(roverWithPersonEvents([]), controller.signal);
    controller.abort();

    await expect(waiting).rejects.toMatchObject({ name: "AbortError" });
  });

  it("reports a useful timeout", async () => {
    await expect(waitForPerson(
      roverWithPersonEvents([]),
      new AbortController().signal,
      1
    )).rejects.toBeInstanceOf(PersonObservationTimeoutError);
  });
});
