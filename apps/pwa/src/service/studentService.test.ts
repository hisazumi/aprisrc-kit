import { describe, expect, it, vi } from "vitest";
import { serviceConfig } from "../config";
import type { MissionContext, ServiceRover } from "../missions/api";
import { studentCarry } from "../missions/studentCarry";
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
  const emit = (status: "detected" | "lost" = "detected") => {
    for (const listener of listeners) listener({ eventId: crypto.randomUUID(), status,
      confidence: 0.99, capturedAt: Date.now() / 1000, source: "scenario", personId: "visitor",
      centerX: 0.5, centerY: 0.5, width: 0.5, height: 0.8, bearingDeg: 0 });
  };
  return { rover, context, controller, emit, listeners };
}
const flush = async () => { for (let i = 0; i < 25; i++) await Promise.resolve(); };
async function reachOffer(s: ReturnType<typeof setup>) {
  s.emit(); await flush(); s.emit(); await flush();
}
describe("student service with existing motion helpers", () => {
  it("runs consent, loading, following, arrival and confirmed final stop", async () => {
    const s = setup();
    const kinds: string[] = [];
    let arrive: (() => void) | undefined;
    const prompt: ServicePrompt = async (kind, _message, signal) => {
      kinds.push(kind);
      if (kind !== "arrived") return true;
      return new Promise((resolve, reject) => {
        arrive = () => resolve(true);
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      });
    };
    const run = runStudentService(studentCarry, s.context, prompt);
    await reachOffer(s);
    expect(kinds).toEqual(["question", "loaded", "arrived"]);
    s.emit(); await flush();
    arrive!(); await run;
    expect(s.rover.stop).toHaveBeenLastCalledWith("student service finished");
    expect(s.listeners.size).toBe(0);
  });
  it("declines without loading or following", async () => {
    const s = setup(); const prompt = vi.fn(async () => false);
    const run = runStudentService(studentCarry, s.context, prompt);
    await reachOffer(s); await run;
    expect(prompt).toHaveBeenCalledTimes(1);
    expect(s.listeners.size).toBe(0);
  });
  it("cancels a pending input and stops before returning", async () => {
    const s = setup();
    const run = runStudentService(studentCarry, s.context, (_kind, _message, signal) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    }));
    const rejected = expect(run).rejects.toThrow();
    await reachOffer(s); s.controller.abort(); await rejected;
    expect(s.rover.stop).toHaveBeenLastCalledWith("student service finished");
    expect(s.listeners.size).toBe(0);
  });
  it("fails on target loss during follow and cancels the arrival input", async () => {
    const s = setup(); let inputCancelled = false;
    const run = runStudentService(studentCarry, s.context, async (kind, _message, signal) => {
      if (kind !== "arrived") return true;
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
    await expect(runStudentService({ title: "empty", run: async () => {} }, s.context, async () => true)).rejects.toThrow("stop unconfirmed");
  });
});
