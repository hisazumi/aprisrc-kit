import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PersonListener } from "../missions/api";
import type { useRoverSocket } from "../useRoverSocket";
import { HardwarePlaygroundInputs } from "./HardwarePlaygroundInputs";

vi.mock("./CameraPreview", () => ({ CameraPreview: ({ onPerceptionReadyChange }: { onPerceptionReadyChange: (ready: boolean) => void }) =>
  <><button onClick={() => onPerceptionReadyChange(true)}>Camera on</button><button onClick={() => onPerceptionReadyChange(false)}>Camera off</button></> }));

afterEach(() => vi.useRealTimers());

async function setup() {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  let listener: PersonListener | undefined;
  const rover = {
    status: "connected", control: { isOwner: true, estopLatched: false },
    state: { timestamp: Date.now() / 1000, connected: true, pose: { x: 0, y: 0, yaw: 0 }, velocity: { vx: .1, wz: 0 } },
    frontObstacle: { state: "CLEAR" },
    actions: { observe: vi.fn(), setPathClearance: vi.fn() },
    serviceRover: { onPerson: (next: PersonListener) => { listener = next; return () => {}; }, onMarker: () => () => {} }
  } as unknown as ReturnType<typeof useRoverSocket>;
  const onReady = vi.fn();
  const container = document.createElement("div"), root = createRoot(container);
  const render = async () => act(async () => root.render(<HardwarePlaygroundInputs rover={rover} onReady={onReady} />));
  await render();
  const click = async (name: string) => act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === name)!.click());
  const emit = async (source: "camera" | "scenario" = "camera", status: "detected" | "lost" = "detected") => act(async () => listener?.({
    eventId: "test", personId: "person", status, confidence: .95, capturedAt: Date.now() / 1000, source, bearingDeg: 10, width: .3
  }));
  return { rover, onReady, container, root, render, click, emit };
}

describe("live playground safety", () => {
  it("requires live perception, accepted camera data and explicit arming; camera-off revokes it", async () => {
    const test = await setup();
    expect(test.onReady).toHaveBeenLastCalledWith(false);
    await test.click("Camera on");
    await test.emit("scenario");
    expect(test.container.textContent).toContain("Waiting for a fresh camera person observation");
    await test.emit();
    expect(test.onReady).toHaveBeenLastCalledWith(false);
    await test.click("Confirm clear path · 30 s");
    expect(test.onReady).toHaveBeenLastCalledWith(true);
    expect(test.rover.actions.setPathClearance).toHaveBeenCalledWith(true);
    await test.click("Camera off");
    expect(test.onReady).toHaveBeenLastCalledWith(false);
    expect(test.rover.actions.setPathClearance).toHaveBeenLastCalledWith(false);
    await act(async () => test.root.unmount());
  });
  it.each(["stale", "lost", "disconnect", "ownership", "estop", "blocked"])("revokes readiness on %s", async (failure) => {
    vi.useFakeTimers();
    const test = await setup();
    await test.click("Camera on"); await test.emit(); await test.click("Confirm clear path · 30 s");
    if (failure === "stale") await act(async () => vi.advanceTimersByTimeAsync(2000));
    else if (failure === "lost") await test.emit("camera", "lost");
    else {
      if (failure === "disconnect") test.rover.state!.connected = false;
      if (failure === "ownership") test.rover.control.isOwner = false;
      if (failure === "estop") test.rover.control.estopLatched = true;
      if (failure === "blocked") test.rover.frontObstacle!.state = "BLOCKED";
      await test.render();
    }
    expect(test.onReady).toHaveBeenLastCalledWith(false);
    await act(async () => test.root.unmount());
  });
  it("expires permission even with continuing live observations", async () => {
    vi.useFakeTimers();
    const test = await setup();
    await test.click("Camera on"); await test.emit(); await test.click("Confirm clear path · 30 s");
    for (let second = 0; second < 30; second++) {
      await act(async () => vi.advanceTimersByTimeAsync(1000));
      test.rover.state!.timestamp = Date.now() / 1000;
      await test.emit(); await test.render();
    }
    expect(test.onReady).toHaveBeenLastCalledWith(false);
    expect(test.rover.actions.setPathClearance).toHaveBeenLastCalledWith(false);
    await act(async () => test.root.unmount());
  });
});
