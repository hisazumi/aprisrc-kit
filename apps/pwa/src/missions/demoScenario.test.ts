import { describe, expect, it, vi } from "vitest";

import { runDemoScenario } from "./demoScenario";

describe("runDemoScenario", () => {
  it("runs high-level motion primitives in order", async () => {
    const calls: string[] = [];
    const rover = {
      move: vi.fn(async (distanceM: number) => {
        calls.push(`move:${distanceM}`);
      }),
      turn: vi.fn(async (angleDeg: number) => {
        calls.push(`turn:${angleDeg}`);
      }),
      stop: vi.fn(async () => undefined),
      getPose: vi.fn(async () => ({ x: 0, y: 0, yaw: 0 })),
      onPose: vi.fn(() => () => undefined),
      onPerson: vi.fn(() => () => undefined),
      onMarker: vi.fn(() => () => undefined)
    };

    await runDemoScenario(rover);

    expect(calls).toEqual(["move:0.4", "turn:90", "move:0.25"]);
  });
});
