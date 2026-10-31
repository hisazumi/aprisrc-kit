import { describe, expect, it, vi } from "vitest";

import type { PersonEvent } from "../protocol";
import type { ServiceRover } from "./api";
import { runComeHere, runFollowMe } from "./comeHere";

function person(overrides: Partial<PersonEvent>): PersonEvent {
  return {
    eventId: crypto.randomUUID(),
    status: "detected",
    confidence: 0.95,
    capturedAt: Date.now() / 1000,
    source: "scenario",
    personId: "virtual-person",
    centerX: 0.5,
    centerY: 0.5,
    width: 0.2,
    height: 0.5,
    bearingDeg: 0,
    ...overrides
  };
}

function scriptedRover(events: PersonEvent[]): ServiceRover & {
  move: ReturnType<typeof vi.fn>;
  turn: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
} {
  let index = 0;
  let listener: ((event: PersonEvent) => void) | null = null;
  const emitNext = () => {
    const next = events[index++];
    if (next && listener) queueMicrotask(() => listener?.(next));
  };
  return {
    move: vi.fn(async () => emitNext()),
    turn: vi.fn(async () => emitNext()),
    stop: vi.fn(async () => undefined),
    getPose: vi.fn(async () => ({ x: 0, y: 0, yaw: 0 })),
    onPose: vi.fn(() => () => undefined),
    onPerson: vi.fn((nextListener: (event: PersonEvent) => void) => {
      listener = nextListener;
      emitNext();
      return () => {
        listener = null;
      };
    }),
    onMarker: vi.fn(() => () => undefined)
  };
}

describe("runComeHere", () => {
  it("aligns, approaches, and stops when the person is near", async () => {
    const rover = scriptedRover([
      person({ centerX: 0.25, bearingDeg: 20 }),
      person({ centerX: 0.5, bearingDeg: 0, width: 0.22 }),
      person({ centerX: 0.5, bearingDeg: 0, width: 0.4 })
    ]);
    const phases: string[] = [];

    const outcome = await runComeHere(rover, new AbortController().signal, {
      onUpdate: (update) => phases.push(update.phase)
    });

    expect(outcome).toBe("arrived");
    expect(rover.turn).toHaveBeenCalledWith(12, 0.35);
    expect(rover.move).toHaveBeenCalledWith(0.08, 0.05);
    expect(rover.stop).toHaveBeenCalledWith("person reached");
    expect(phases).toEqual(["acquiring", "aligning", "approaching", "arrived"]);
  });

  it("uses a closer upper-body threshold for phone camera observations", async () => {
    const rover = scriptedRover([
      person({ source: "camera", width: 0.5 }),
      person({ source: "camera", width: 0.7 })
    ]);

    const outcome = await runComeHere(rover, new AbortController().signal);

    expect(outcome).toBe("arrived");
    expect(rover.move).toHaveBeenCalledOnce();
    expect(rover.move).toHaveBeenCalledWith(0.08, 0.05);
    expect(rover.stop).toHaveBeenCalledWith("person reached");
  });

  it("stops when the person is lost", async () => {
    const rover = scriptedRover([person({ status: "lost", confidence: 0 })]);

    const outcome = await runComeHere(rover, new AbortController().signal);

    expect(outcome).toBe("lost");
    expect(rover.move).not.toHaveBeenCalled();
    expect(rover.turn).not.toHaveBeenCalled();
    expect(rover.stop).toHaveBeenCalledWith("person lost");
  });

  it("waits for operator path clearance before a forward step", async () => {
    let emitPerson: (event: PersonEvent) => void = () => undefined;
    let pathClear = false;
    const move = vi.fn(async () => emitPerson(person({ width: 0.4 })));
    const rover: ServiceRover = {
      move,
      turn: vi.fn(async () => undefined),
      stop: vi.fn(async () => undefined),
      getPose: vi.fn(async () => ({ x: 0, y: 0, yaw: 0 })),
      onPose: vi.fn(() => () => undefined),
      onPerson: vi.fn((nextListener) => {
        emitPerson = nextListener;
        queueMicrotask(() => emitPerson(person({ width: 0.2 })));
        return () => {
          emitPerson = () => undefined;
        };
      }),
      onMarker: vi.fn(() => () => undefined),
      getFrontObstacle: () => ({
        state: pathClear ? "CLEAR" : "UNKNOWN",
        observed_state: pathClear ? "CLEAR" : "UNKNOWN",
        perception_health: pathClear ? "healthy" : "unavailable",
        source: "manual",
        stale: !pathClear,
        latched: false
      })
    };
    const details: string[] = [];
    const running = runComeHere(rover, new AbortController().signal, {
      onUpdate: (update) => details.push(update.detail)
    });

    await vi.waitFor(() => expect(details).toContain("Tap Allow movement to let me approach"));
    expect(move).not.toHaveBeenCalled();

    pathClear = true;
    emitPerson(person({ width: 0.2 }));
    await expect(running).resolves.toBe("arrived");
    expect(move).toHaveBeenCalledWith(0.08, 0.05);
  });

  it("does not miss a lost event emitted while a motion is completing", async () => {
    const rover = scriptedRover([
      person({ centerX: 0.25, bearingDeg: 20 }),
      person({ status: "lost", confidence: 0 })
    ]);

    const outcome = await runComeHere(rover, new AbortController().signal);

    expect(outcome).toBe("lost");
    expect(rover.turn).toHaveBeenCalledOnce();
    expect(rover.stop).toHaveBeenCalledWith("person lost");
  });

  it("cancels an active motion as soon as a lost event arrives", async () => {
    let listener: ((event: PersonEvent) => void) | null = null;
    let rejectTurn: ((error: Error) => void) | null = null;
    const lost = person({ status: "lost", confidence: 0 });
    const stop = vi.fn(async (reason?: string) => {
      if (reason === "person lost" && rejectTurn) {
        const reject = rejectTurn;
        rejectTurn = null;
        reject(new Error("motion cancelled"));
      }
    });
    const rover: ServiceRover = {
      move: vi.fn(async () => undefined),
      turn: vi.fn(() => new Promise<void>((_resolve, reject) => {
        rejectTurn = reject;
        queueMicrotask(() => listener?.(lost));
      })),
      stop,
      getPose: vi.fn(async () => ({ x: 0, y: 0, yaw: 0 })),
      onPose: vi.fn(() => () => undefined),
      onPerson: vi.fn((nextListener) => {
        listener = nextListener;
        queueMicrotask(() => listener?.(person({ centerX: 0.2, bearingDeg: 20 })));
        return () => {
          listener = null;
        };
      }),
      onMarker: vi.fn(() => () => undefined)
    };

    const outcome = await runComeHere(rover, new AbortController().signal);

    expect(outcome).toBe("lost");
    expect(rover.turn).toHaveBeenCalledOnce();
    expect(stop).toHaveBeenCalledWith("person lost");
  });

  it("treats stale observations as target loss", async () => {
    const rover = scriptedRover([]);

    const outcome = await runComeHere(rover, new AbortController().signal, {
      observationTimeoutMs: 5
    });

    expect(outcome).toBe("lost");
    expect(rover.stop).toHaveBeenCalledWith("person observation stale");
  });

  it("stops after cancellation", async () => {
    const rover = scriptedRover([]);
    const controller = new AbortController();
    const running = runComeHere(rover, controller.signal, { observationTimeoutMs: 5000 });
    controller.abort();

    await expect(running).rejects.toMatchObject({ name: "AbortError" });
    expect(rover.stop).toHaveBeenCalledWith("come-here mission stopped");
  });
});

describe("runFollowMe", () => {
  it("approaches, then holds distance until cancelled", async () => {
    const rover = scriptedRover([
      person({ centerX: 0.5, bearingDeg: 0, width: 0.2 }),
      person({ centerX: 0.5, bearingDeg: 0, width: 0.38 })
    ]);
    const controller = new AbortController();
    const running = runFollowMe(rover, controller.signal, {
      onUpdate: (update) => {
        if (update.detail === "Keeping a safe distance") controller.abort();
      }
    });

    await expect(running).rejects.toMatchObject({ name: "AbortError" });
    expect(rover.move).toHaveBeenCalledWith(0.1, 0.15);
    expect(rover.stop).toHaveBeenCalledWith("follow distance reached");
    expect(rover.stop).toHaveBeenCalledWith("follow-me mission stopped");
  });

  it("uses upper-body distance hysteresis for phone camera observations", async () => {
    const rover = scriptedRover([
      person({ source: "camera", centerX: 0.64, bearingDeg: -9, width: 0.48 }),
      person({ source: "camera", width: 0.7 })
    ]);
    const controller = new AbortController();
    const running = runFollowMe(rover, controller.signal, {
      onUpdate: (update) => {
        if (update.detail === "Keeping a safe distance") controller.abort();
      }
    });

    await expect(running).rejects.toMatchObject({ name: "AbortError" });
    expect(rover.move).toHaveBeenCalledWith(0.1, 0.15);
    expect(rover.turn).not.toHaveBeenCalled();
    expect(rover.stop).toHaveBeenCalledWith("follow distance reached");
  });

  it("stops when the followed person is lost", async () => {
    const rover = scriptedRover([person({ status: "lost", confidence: 0 })]);

    const outcome = await runFollowMe(rover, new AbortController().signal);

    expect(outcome).toBe("lost");
    expect(rover.move).not.toHaveBeenCalled();
    expect(rover.stop).toHaveBeenCalledWith("person lost");
  });
});
