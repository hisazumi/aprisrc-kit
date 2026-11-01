import { describe, expect, it, vi } from "vitest";
import { serviceConfig } from "../config";
import type { MissionContext, ServiceRover } from "../missions/api";
import { myService } from "../missions/myService";
import { runStudentService, type ServicePrompt } from "./studentService";

// Use actual approach/follow helpers: observations arrive at a safe holding distance.
function setup() {
  const listeners = new Set<Parameters<ServiceRover["onPerson"]>[0]>();
  const rover: ServiceRover = {
    move: vi.fn(async () => undefined), turn: vi.fn(async () => undefined),
    stop: vi.fn(async () => undefined), getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
    onPose: () => () => undefined, onMarker: () => () => undefined,
    onPerson: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; }
  };
  const controller = new AbortController();
  const context: MissionContext = { rover, signal: controller.signal, config: serviceConfig, report: vi.fn(), say: vi.fn() };
  const emit = (status: "detected" | "lost" = "detected", width = 0.5) => {
    for (const listener of listeners) listener({ eventId: crypto.randomUUID(), status,
      confidence: 0.99, capturedAt: Date.now() / 1000, source: "scenario", personId: "visitor",
      centerX: 0.5, centerY: 0.5, width, height: 0.8, bearingDeg: 0 });
  };
  return { rover, context, controller, emit, listeners };
}
const flush = async () => { for (let i = 0; i < 25; i++) await Promise.resolve(); };
async function reachOffer(s: ReturnType<typeof setup>) {
  s.emit(); await flush(); s.emit(); await flush();
}
describe("student service with existing motion helpers", () => {
  it("preserves voice aliases and validates canonical answer values", async () => {
    const s = setup();
    const prompt = vi.fn<ServicePrompt>(async q => q.choices[0]);
    await runStudentService({ title: "Aliases", run: async api => {
      expect(await api.ask("Help?", { yes: ["sure"], no: ["no thanks"] })).toBe(true);
      expect(await api.choose("Where?", [{ value: "desk", label: "Desk", phrases: ["my desk"] }])).toBe("desk");
      await api.confirm("Loaded?", "Loaded", ["ready"]);
    } }, s.context, prompt);
    expect(prompt.mock.calls[0][0].options?.[0].phrases).toEqual(["sure"]);
    expect(prompt.mock.calls[1][0].options?.[0]).toEqual({ value: "desk", label: "Desk", phrases: ["my desk"] });
    expect(prompt.mock.calls[2][0].options?.[0].phrases).toEqual(["ready"]);
  });
  it("supports custom choices and confirmation without carry-specific UI", async () => {
    const s = setup();
    const prompt = vi.fn<ServicePrompt>(async question => question.choices.at(-1)!);
    await runStudentService({ title: "Reception", run: async api => {
      expect(await api.choose("Destination?", ["Desk", "Reception", "Entrance"])).toBe("Entrance");
      await api.confirm("Ready?", "Let's go");
    } }, s.context, prompt);
    expect(prompt.mock.calls.map(([q]) => q)).toEqual([
      { message: "Destination?", choices: ["Desk", "Reception", "Entrance"] },
      { message: "Ready?", choices: ["Let's go"] }
    ]);
  });
  it("rejects invalid choices and unexpected answers", async () => {
    for (const choices of [[], [""], ["Desk", "Desk"]]) {
      const s = setup(); const prompt = vi.fn(async () => "Desk");
      await expect(runStudentService({ title: "invalid", run: async api => {
        await api.choose("Where?", choices);
      } }, s.context, prompt)).rejects.toThrow("Choices must");
      expect(prompt).not.toHaveBeenCalled();
    }
    const s = setup();
    await expect(runStudentService({ title: "invalid", run: async api => {
      await api.choose("Where?", ["Desk"]);
    } }, s.context, async () => "Unknown")).rejects.toThrow("Unexpected service answer");
  });
  it("requests stop at arrival before waiting for an in-flight move to finish", async () => {
    const s = setup();
    let finishMove!: () => void;
    let arrive!: () => void;
    vi.mocked(s.rover.move).mockImplementation(() => new Promise(resolve => { finishMove = resolve; }));
    let done = false;
    const run = runStudentService({ title: "follow", run: api => api.followPerson({ buttonLabel: "Done", message: "Finish?" }) },
      s.context, question => new Promise(resolve => {
        expect(question).toEqual({ message: "Finish?", choices: ["Done"] });
        arrive = () => resolve("Done");
      })).then(() => { done = true; });
    s.emit("detected", 0.1); await flush();
    expect(s.rover.move).toHaveBeenCalledTimes(1);
    arrive(); await flush();
    expect(s.rover.stop).toHaveBeenCalledWith("student following finished");
    expect(done).toBe(false);
    finishMove(); await run;
    expect(done).toBe(true);
    expect(s.listeners.size).toBe(0);
  });
  it("uses the main continuous-follow path and stops after arrival", async () => {
    vi.useFakeTimers();
    try {
      const s = setup(); s.rover.setVelocity = vi.fn(async () => {});
      let arrive!: () => void;
      const run = runStudentService({ title: "continuous", run: api => api.followPerson() }, s.context,
        question => new Promise(resolve => { arrive = () => resolve(question.choices[0]); }));
      s.emit("detected", 0.1);
      await vi.advanceTimersByTimeAsync(100);
      expect(s.rover.setVelocity).toHaveBeenCalled();
      expect(s.rover.move).not.toHaveBeenCalled();
      arrive(); await flush();
      const calls = vi.mocked(s.rover.setVelocity).mock.calls.length;
      await vi.advanceTimersByTimeAsync(100); await run;
      expect(s.rover.setVelocity).toHaveBeenCalledTimes(calls);
      expect(s.rover.stop).toHaveBeenLastCalledWith("student service finished");
      expect(s.listeners.size).toBe(0);
    } finally { vi.useRealTimers(); }
  });
  it("does not hide arrival stop failure behind a successful final stop", async () => {
    const s = setup();
    vi.mocked(s.rover.stop).mockImplementation(async reason => {
      if (reason === "student following finished") throw new Error("arrival stop unconfirmed");
    });
    await expect(runStudentService({ title: "follow", run: api => api.followPerson() }, s.context,
      async question => question.choices[0])).rejects.toThrow("arrival stop unconfirmed");
    expect(s.listeners.size).toBe(0);
  });
  it("runs consent, loading, following, arrival and confirmed final stop", async () => {
    const s = setup();
    const kinds: string[] = [];
    let arrive: (() => void) | undefined;
    const prompt: ServicePrompt = async (question, signal) => {
      const label = question.choices[0];
      kinds.push(label);
      if (label !== "We have arrived") return label;
      return new Promise((resolve, reject) => {
        arrive = () => resolve(label);
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      });
    };
    const run = runStudentService(myService, s.context, prompt);
    await reachOffer(s);
    expect(kinds).toEqual(["Yes", "Items are loaded", "We have arrived"]);
    s.emit(); await flush();
    arrive!(); await run;
    expect(s.rover.stop).toHaveBeenLastCalledWith("student service finished");
    expect(s.listeners.size).toBe(0);
  });
  it("declines without loading or following", async () => {
    const s = setup(); const prompt = vi.fn(async () => "No");
    const run = runStudentService(myService, s.context, prompt);
    await reachOffer(s); await run;
    expect(prompt).toHaveBeenCalledTimes(1);
    expect(s.listeners.size).toBe(0);
  });
  it("cancels a pending input and stops before returning", async () => {
    const s = setup();
    const run = runStudentService(myService, s.context, (_question, signal) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    }));
    const rejected = expect(run).rejects.toThrow();
    await reachOffer(s); s.controller.abort(); await rejected;
    expect(s.rover.stop).toHaveBeenLastCalledWith("student service finished");
    expect(s.listeners.size).toBe(0);
  });
  it("fails on target loss during follow and cancels the arrival input", async () => {
    const s = setup(); let inputCancelled = false;
    const run = runStudentService(myService, s.context, async (question, signal) => {
      if (question.choices[0] !== "We have arrived") return question.choices[0];
      return new Promise((_resolve, reject) => signal.addEventListener("abort", () => {
        inputCancelled = true; reject(signal.reason);
      }, { once: true }));
    });
    const rejected = expect(run).rejects.toThrow("Target lost");
    await reachOffer(s); s.emit("lost"); await rejected;
    expect(inputCancelled).toBe(true);
    expect(s.listeners.size).toBe(0);
  });
  it("propagates failure to confirm the final stop", async () => {
    const s = setup();
    vi.mocked(s.rover.stop).mockRejectedValue(new Error("stop unconfirmed"));
    await expect(runStudentService({ title: "empty", run: async () => {} }, s.context, async () => "Continue")).rejects.toThrow("stop unconfirmed");
  });
});
