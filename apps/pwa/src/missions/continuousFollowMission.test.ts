import { afterEach, expect, it, vi } from "vitest";
import { runFollowMe } from "./comeHere";
import type { PersonListener, ServiceRover } from "./api";

afterEach(() => vi.useRealTimers());

it("streams velocity through the service API and stops on target loss", async () => {
  vi.useFakeTimers();
  let observe: PersonListener = () => undefined;
  const unsubscribe = vi.fn();
  const velocity = vi.fn(async () => undefined);
  const stop = vi.fn(async () => undefined);
  const move = vi.fn(async () => undefined);
  const rover: ServiceRover = {
    setVelocity: velocity, move, turn: move, stop,
    getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
    onPose: () => () => undefined, onMarker: () => () => undefined,
    onPerson: listener => { observe = listener; return unsubscribe; }
  };
  const task = runFollowMe(rover, new AbortController().signal);
  observe({ eventId: "1", status: "detected", confidence: 1, capturedAt: 0,
    source: "scenario", personId: "a", width: .1, bearingDeg: 15 });
  await vi.advanceTimersByTimeAsync(500);
  expect(velocity).toHaveBeenCalled();
  expect(move).not.toHaveBeenCalled();
  observe({ eventId: "2", personId: "a", status: "lost", confidence: 0, capturedAt: .5, source: "scenario" });
  const calls = velocity.mock.calls.length;
  await vi.advanceTimersByTimeAsync(100);
  expect(await task).toBe("lost");
  expect(velocity.mock.calls).toHaveLength(calls);
  expect(stop).toHaveBeenCalledWith("continuous follow stopped");
  expect(unsubscribe).toHaveBeenCalledOnce();
});
