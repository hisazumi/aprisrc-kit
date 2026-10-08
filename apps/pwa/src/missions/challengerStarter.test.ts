import { describe, expect, it, vi } from "vitest";

import { serviceConfig } from "../config";
import type { PersonEvent } from "../protocol";
import type { ServiceRover } from "./api";
import { challengerStarterMission, createGreetingMission } from "./challengerStarter";

function detectedPerson(bearingDeg: number): PersonEvent {
  return {
    eventId: crypto.randomUUID(),
    status: "detected",
    confidence: 0.96,
    capturedAt: Date.now() / 1000,
    source: "scenario",
    personId: "teacher",
    centerX: 0.35,
    centerY: 0.5,
    width: 0.2,
    height: 0.5,
    bearingDeg
  };
}

function roverWithPerson(event: PersonEvent): ServiceRover & {
  turn: ReturnType<typeof vi.fn>;
} {
  return {
    move: vi.fn(async () => undefined),
    turn: vi.fn(async () => undefined),
    stop: vi.fn(async () => undefined),
    getPose: vi.fn(async () => ({ x: 0, y: 0, yaw: 0 })),
    onPose: vi.fn(() => () => undefined),
    onPerson: vi.fn((listener) => {
      queueMicrotask(() => listener(event));
      return () => undefined;
    }),
    onMarker: vi.fn(() => () => undefined)
  };
}

describe("challengerStarterMission", () => {
  it("uses preview settings in the same mission without changing defaults", async () => {
    const rover = roverWithPerson(detectedPerson(-24));
    const say = vi.fn();
    await createGreetingMission({ greeting: "Welcome to my service", maxTurnDeg: 0, minTurnDeg: 3 }).run({
      rover, config: serviceConfig, signal: new AbortController().signal, report: vi.fn(), say
    });
    expect(rover.turn).not.toHaveBeenCalled();
    expect(say).toHaveBeenCalledWith("Welcome to my service");
    await challengerStarterMission.run({
      rover, config: serviceConfig, signal: new AbortController().signal, report: vi.fn(), say
    });
    expect(rover.turn).toHaveBeenCalledWith(-15, 0.35);
    expect(say).toHaveBeenLastCalledWith("Hello. I can see you.");
  });
  it("turns toward a detected person and reports completion", async () => {
    const rover = roverWithPerson(detectedPerson(24));
    const say = vi.fn();
    const details: string[] = [];

    await challengerStarterMission.run({
      rover,
      config: serviceConfig,
      signal: new AbortController().signal,
      report: (progress) => details.push(progress.detail),
      say
    });

    expect(rover.turn).toHaveBeenCalledWith(15, 0.35);
    expect(say).toHaveBeenCalledWith("Hello. I can see you.");
    expect(details).toEqual([
      "Waiting for a visible person",
      "Turning left toward the person",
      "Greeting complete"
    ]);
  });

  it("greets without turning when the person is already centred", async () => {
    const rover = roverWithPerson(detectedPerson(1));

    await challengerStarterMission.run({
      rover,
      config: serviceConfig,
      signal: new AbortController().signal,
      report: () => undefined,
      say: vi.fn()
    });

    expect(rover.turn).not.toHaveBeenCalled();
  });
});
