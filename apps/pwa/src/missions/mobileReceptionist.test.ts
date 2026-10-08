import { describe, expect, it, vi } from "vitest";

import { serviceConfig } from "../config";
import type { FrontObstacleSnapshot, MarkerEvent, PersonEvent } from "../protocol";
import type { ServiceRover } from "./api";
import {
  mobileReceptionistMission,
  runMobileReceptionist
} from "./mobileReceptionist";

function person(): PersonEvent {
  return {
    eventId: crypto.randomUUID(),
    status: "detected",
    confidence: 0.96,
    capturedAt: Date.now() / 1000,
    source: "scenario",
    personId: "visitor",
    centerX: 0.5,
    centerY: 0.5,
    width: 0.2,
    height: 0.5,
    bearingDeg: 0
  };
}

function marker(
  markerId: number,
  relativeXM: number,
  relativeYM: number,
  status: MarkerEvent["status"] = "detected"
): MarkerEvent {
  return {
    eventId: crypto.randomUUID(),
    status,
    confidence: status === "detected" ? 0.95 : 0,
    capturedAt: Date.now() / 1000,
    source: "scenario",
    markerId,
    relativeXM,
    relativeYM
  };
}

function obstacle(state: FrontObstacleSnapshot["state"]): FrontObstacleSnapshot {
  return {
    state,
    observed_state: state,
    perception_health: state === "UNKNOWN" ? "unavailable" : "healthy",
    source: "scenario",
    stale: state === "UNKNOWN",
    latched: state === "BLOCKED"
  };
}

function scriptedRover(
  markers: MarkerEvent[],
  frontObstacle: FrontObstacleSnapshot = obstacle("CLEAR")
): ServiceRover & {
  move: ReturnType<typeof vi.fn>;
  turn: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
} {
  let index = 0;
  let listener: ((event: MarkerEvent) => void) | null = null;
  const emitNext = () => {
    const next = markers[index++];
    if (!next || !listener) return;
    queueMicrotask(() => {
      listener?.(next);
      if (next.markerId !== 1 && next.markerId !== 2) emitNext();
    });
  };
  return {
    move: vi.fn(async () => emitNext()),
    turn: vi.fn(async () => emitNext()),
    stop: vi.fn(async () => undefined),
    getPose: vi.fn(async () => ({ x: 0, y: 0, yaw: 0 })),
    onPose: vi.fn(() => () => undefined),
    onPerson: vi.fn((nextListener) => {
      queueMicrotask(() => nextListener(person()));
      return () => undefined;
    }),
    onMarker: vi.fn((nextListener) => {
      listener = nextListener;
      emitNext();
      return () => {
        listener = null;
      };
    }),
    getFrontObstacle: () => frontObstacle
  };
}

describe("runMobileReceptionist", () => {
  it("scans without forward motion and stops when no marker is found", async () => {
    vi.useFakeTimers();
    try {
      const rover = scriptedRover([]);
      const running = runMobileReceptionist(rover, serviceConfig, new AbortController().signal,
        "entrance", { searchWaitMs: 1, maximumSteps: 1 });
      await vi.advanceTimersByTimeAsync(40);
      expect(await running).toBe("not_found");
      expect(rover.turn).toHaveBeenCalledTimes(36);
      expect(rover.move).not.toHaveBeenCalled();
      expect(rover.stop).toHaveBeenCalledWith("destination marker not found after full scan");
    } finally { vi.useRealTimers(); }
  });
  it("checks arrival after the last allowed motion without exceeding the step limit", async () => {
    const rover = scriptedRover([marker(1, .55, 0), marker(1, .46, 0)]);
    expect(await runMobileReceptionist(rover, serviceConfig, new AbortController().signal,
      "entrance", { maximumSteps: 1 })).toBe("arrived");
    expect(rover.move).toHaveBeenCalledTimes(1);
  });
  it("stops at the step limit if the final observation is still distant", async () => {
    const rover = scriptedRover([marker(1, 1, 0), marker(1, .8, 0)]);
    await expect(runMobileReceptionist(rover, serviceConfig, new AbortController().signal,
      "entrance", { maximumSteps: 1 })).rejects.toThrow("Destination approach step limit reached");
    expect(rover.move).toHaveBeenCalledTimes(1);
    expect(rover.stop).toHaveBeenCalledWith("mobile receptionist stopped");
  });
  it("stops within arrival tolerance instead of issuing sub-tolerance movement", async () => {
    const rover = scriptedRover([marker(1, .4506, .022)]);
    const outcome = await runMobileReceptionist(rover, serviceConfig, new AbortController().signal);
    expect(outcome).toBe("arrived");
    expect(rover.move).not.toHaveBeenCalled();
    expect(rover.stop).toHaveBeenCalledWith("destination marker reached");
  });
  it("aligns, approaches, and stops at the entrance marker", async () => {
    const rover = scriptedRover([
      marker(1, 0.85, 0.32),
      marker(1, 0.82, 0.02),
      marker(1, 0.62, 0.01),
      marker(1, 0.4, 0)
    ]);
    const phases: string[] = [];

    const outcome = await runMobileReceptionist(
      rover,
      serviceConfig,
      new AbortController().signal,
      "entrance",
      { onUpdate: (progress) => phases.push(progress.phase) }
    );

    expect(outcome).toBe("arrived");
    expect(rover.turn).toHaveBeenCalledWith(15, 0.35);
    expect(rover.move).toHaveBeenNthCalledWith(1, 0.12, 0.1);
    expect(rover.move).toHaveBeenNthCalledWith(2, 0.12, 0.1);
    expect(rover.stop).toHaveBeenCalledWith("destination marker reached");
    expect(phases).toEqual([
      "acquiring",
      "waiting",
      "aligning",
      "approaching",
      "approaching",
      "arrived"
    ]);
  });

  it("ignores another destination marker and uses the requested desk", async () => {
    const rover = scriptedRover([
      marker(3, 0.5, 0),
      marker(2, 0.4, 0)
    ]);
    const say = vi.fn();

    await mobileReceptionistMission.run({
      rover,
      config: serviceConfig,
      signal: new AbortController().signal,
      report: () => undefined,
      say
    }, {
      intent: "guide_visitor",
      destination: "desk",
      followDistance: "normal"
    });

    expect(rover.move).not.toHaveBeenCalled();
    expect(rover.stop).toHaveBeenCalledWith("destination marker reached");
    expect(say).toHaveBeenCalledWith("We have arrived at the desk.");
  });

  it("stops when the destination marker is lost", async () => {
    const rover = scriptedRover([
      marker(1, 0.8, 0.3),
      marker(1, 0, 0, "lost")
    ]);

    const outcome = await runMobileReceptionist(
      rover,
      serviceConfig,
      new AbortController().signal
    );

    expect(outcome).toBe("lost");
    expect(rover.stop).toHaveBeenCalledWith("destination marker lost");
  });

  it.each(["BLOCKED", "UNKNOWN"] as const)(
    "does not move forward when the authoritative path is %s",
    async (state) => {
      const rover = scriptedRover([marker(1, 0.8, 0)], obstacle(state));

      const outcome = await runMobileReceptionist(
        rover,
        serviceConfig,
        new AbortController().signal
      );

      expect(outcome).toBe("blocked");
      expect(rover.move).not.toHaveBeenCalled();
      expect(rover.stop).toHaveBeenCalledWith("destination path is not clear");
    }
  );

  it("stops when the mission is cancelled while waiting for a marker", async () => {
    const rover = scriptedRover([]);
    const controller = new AbortController();
    const running = runMobileReceptionist(
      rover,
      serviceConfig,
      controller.signal,
      "entrance",
      { searchWaitMs: 5000 }
    );

    await vi.waitFor(() => expect(rover.onMarker).toHaveBeenCalled());
    controller.abort();

    await expect(running).rejects.toMatchObject({ name: "AbortError" });
    expect(rover.stop).toHaveBeenCalledWith("mobile receptionist stopped");
  });
});
