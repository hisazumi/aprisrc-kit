import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MarkerListener, PersonListener } from "../missions/api";
import type { PersonEvent } from "../protocol";
import { simulatorApi } from "../simulatorApi";
import type { useRoverSocket } from "../useRoverSocket";
import { ServicePlayground } from "./ServicePlayground";

vi.mock("../simulation/useVirtualPersonSimulation", () => ({
  useVirtualPersonSimulation: () => ({ projection: null, error: "" })
}));
vi.mock("../speech", () => ({ speakEnglish: vi.fn() }));
vi.mock("./CameraPreview", () => ({ CameraPreview: ({ onPerceptionReadyChange }: { onPerceptionReadyChange: (ready: boolean) => void }) =>
  <button onClick={() => onPerceptionReadyChange(true)}>Test live camera</button> }));
vi.mock("../simulation/useVirtualMarkerSimulation", () => ({
  useVirtualMarkerSimulation: () => ({ error: "" })
}));
vi.mock("../simulatorApi", () => ({ simulatorApi: {
  setFrontObstacle: vi.fn(async () => ({ front_obstacle: { latched: false } })),
  clearFrontObstacle: vi.fn(async () => undefined),
  placePose: vi.fn(async () => ({ pose: { x: -.8, y: -.15, yaw: 0 } }))
} }));

function socket() {
  const listeners = new Set<PersonListener>();
  let markerListener: MarkerListener | null = null;
  const cancelMotion = vi.fn(() => true);
  const acquire = vi.fn();
  const rover = {
    status: "connected",
    state: { pose: { x: 0, y: 0, yaw: 0 }, timestamp: Date.now() / 1000, connected: true,
      velocity: { vx: 0, vy: 0, wz: 0 } },
    control: { isOwner: true, ownerClientId: "tester", estopLatched: false },
    frontObstacle: { state: "CLEAR" },
    actions: { acquire, cancelMotion, observe: vi.fn(), setPathClearance: vi.fn(), estop: vi.fn() },
    serviceRover: {
      onPerson: (next: PersonListener) => { listeners.add(next); return () => { listeners.delete(next); }; },
      onMarker: (next: MarkerListener) => { markerListener = next; return () => { markerListener = null; }; },
      turn: vi.fn(async () => undefined),
      move: vi.fn(async () => undefined),
      stop: vi.fn(async () => undefined)
    }
  } as unknown as ReturnType<typeof useRoverSocket>;
  return { rover, cancelMotion, acquire,
    emitMarker: (markerId: number, status: "detected" | "lost" = "detected", relativeXM = .4) => markerListener?.({
      eventId: "marker", markerId, status, confidence: .96, capturedAt: Date.now() / 1000,
      source: "scenario", relativeXM, relativeYM: 0
    }),
    emit: (overrides: Partial<PersonEvent> = {}) => listeners.forEach((listener) => listener({
    eventId: "visitor", personId: "visitor", status: "detected", confidence: .95, capturedAt: Date.now() / 1000,
    source: "scenario", bearingDeg: 12, centerX: .5, width: .2, ...overrides
  })) };
}

describe("ServicePlayground", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/lab?sample=greeting");
    vi.clearAllMocks();
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it("starts from the behind-rover preset and locks scene edits during the trial", async () => {
    window.history.replaceState(null, "", "/lab?sample=receptionist");
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    const button = (name: string) => [...container.querySelectorAll("button")].find((b) => b.textContent === name)!;
    await act(async () => button("Behind rover").click());
    expect(container.querySelector<HTMLInputElement>('input[aria-label="visitor x"]')?.value).toBe("-2.15");
    await act(async () => button("Guide me").click());
    expect(simulatorApi.placePose).toHaveBeenCalledWith(expect.objectContaining({ yaw: Math.PI }));
    expect(container.querySelector("fieldset")?.disabled).toBe(true);
    await act(async () => button("Stop").click());
    expect(container.querySelector("fieldset")?.disabled).toBe(false);
    await act(async () => root.unmount());
  });

  it("guides to the chosen marker, ignores the other marker, and reports arrival", async () => {
    window.history.replaceState(null, "", "/lab?sample=receptionist");
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    const select = container.querySelector("select")!;
    await act(async () => { select.value = "desk"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Guide me")!.click());
    expect(simulatorApi.placePose).toHaveBeenCalledWith({ x: -.8, y: -.15, yaw: 0,
      markers: [{ id: 1, x_m: 0, y_m: 0 }, { id: 2, x_m: 2, y_m: 0 }] });
    await act(async () => mock.emit());
    await act(async () => mock.emitMarker(1));
    expect(mock.rover.serviceRover.move).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Searching for the Desk marker");
    await act(async () => mock.emitMarker(2));
    expect(mock.rover.serviceRover.stop).toHaveBeenCalledWith("destination marker reached");
    expect(container.querySelector(".greeting-service h3")?.textContent).toBe("We have arrived at the desk.");
    await act(async () => root.unmount());
  });

  it("stops the marker-guidance service when its target disappears", async () => {
    window.history.replaceState(null, "", "/lab?sample=receptionist");
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Guide me")!.click());
    await act(async () => mock.emit());
    await act(async () => mock.emitMarker(1, "detected", .8));
    expect(mock.rover.serviceRover.move).toHaveBeenCalled();
    await act(async () => mock.emitMarker(1, "lost"));
    expect(mock.rover.serviceRover.stop).toHaveBeenCalledWith("destination marker lost");
    expect(container.querySelector(".greeting-service h3")?.textContent).toBe("I lost the destination marker. I am stopping.");
    await act(async () => root.unmount());
  });

  it("does not start follow motion when simulated scene preparation fails", async () => {
    window.history.replaceState(null, "", "/lab?sample=follow");
    vi.mocked(simulatorApi.setFrontObstacle).mockRejectedValueOnce(new Error("Simulator unavailable"));
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Follow me")!.click());
    expect(mock.rover.serviceRover.move).not.toHaveBeenCalled();
    expect(mock.cancelMotion).toHaveBeenCalled();
    expect(container.textContent).toContain("Simulator unavailable");
    await act(async () => root.unmount());
  });

  it("runs the existing follow mission, moves on detection, and stops on target loss", async () => {
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Follow helper")!.click());
    expect(window.location.search).toBe("?sample=follow");
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Follow me")!.click());
    expect(simulatorApi.setFrontObstacle).toHaveBeenCalledWith("CLEAR", "healthy");
    await act(async () => mock.emit());
    expect(mock.rover.serviceRover.move).toHaveBeenCalledWith(.1, .15);
    expect(container.querySelector(".is-executing")?.textContent).toContain("rover.move");
    await act(async () => mock.emit({ status: "lost" }));
    expect(mock.rover.serviceRover.stop).toHaveBeenCalledWith("person lost");
    expect(container.querySelector(".greeting-service h3")?.textContent).toBe("I lost sight of you. Stopping.");
    expect([...container.querySelectorAll("button")].find((b) => b.textContent === "Follow helper")?.disabled).toBe(false);
    await act(async () => root.unmount());
  });

  it("uses the chosen follow distance and cancels when ownership is lost", async () => {
    window.history.replaceState(null, "", "/lab?sample=follow");
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    const select = container.querySelector("select")!;
    await act(async () => { select.value = "far"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Follow me")!.click());
    await act(async () => mock.emit({ width: .32 }));
    expect(mock.rover.serviceRover.move).not.toHaveBeenCalled();
    expect(mock.rover.serviceRover.stop).toHaveBeenCalledWith("follow distance reached");
    const disconnected = { ...mock.rover, control: { ...mock.rover.control, isOwner: false } };
    await act(async () => root.render(<ServicePlayground rover={disconnected} adapterType="simulator" />));
    expect(mock.cancelMotion).toHaveBeenCalled();
    expect(container.textContent).toContain("Service stopped");
    await act(async () => root.unmount());
  });

  it("waits for a visitor, executes the real starter, and shows its greeting and trace", async () => {
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    const start = [...container.querySelectorAll("button")].find((b) => b.textContent === "Start greeting")!;
    await act(async () => start.click());
    expect(container.textContent).toContain("Waiting for a visible person");
    const rerendered = { ...mock.rover, actions: { ...mock.rover.actions, cancelMotion: vi.fn(() => true) } };
    await act(async () => root.render(<ServicePlayground rover={rerendered} adapterType="simulator" />));
    await act(async () => mock.emit());
    expect(mock.rover.serviceRover.turn).toHaveBeenCalledWith(12, .35);
    expect(container.querySelector(".greeting-service h3")?.textContent).toBe("Hello. I can see you.");
    expect(container.querySelector(".is-executing")?.textContent).toContain("say(settings.greeting)");
    await act(async () => root.unmount());
  });

  it("cancels an observation wait and never greets from a later input", async () => {
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Start greeting")!.click());
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Stop")!.click());
    await act(async () => mock.emit());
    expect(mock.cancelMotion).toHaveBeenCalled();
    expect(mock.rover.serviceRover.turn).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Service stopped");
    await act(async () => root.unmount());
  });

  it.each(["websocket_rover", "ironx_network"] as const)("starts a supervised %s greeting without Simulator calls and filters synthetic events", async (adapterType) => {
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType={adapterType} />));
    const click = async (text: string) => act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === text)!.click());
    await click("Test live camera");
    await act(async () => mock.emit({ source: "camera" }));
    await click("Confirm clear path · 30 s");
    await click("Start greeting");
    await act(async () => mock.emit({ source: "scenario" }));
    await act(async () => mock.emit({ source: "recorded" }));
    expect(mock.rover.serviceRover.turn).not.toHaveBeenCalled();
    await act(async () => mock.emit({ source: "camera" }));
    expect(mock.rover.serviceRover.turn).toHaveBeenCalledWith(12, .35);
    expect(simulatorApi.placePose).not.toHaveBeenCalled();
    expect(simulatorApi.setFrontObstacle).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Turn requested: 12.0 deg");
    await act(async () => root.unmount());
  });

  it("acquires control before starting and keeps unarmed physical services disabled", async () => {
    const mock = socket();
    mock.rover.control.isOwner = false;
    mock.rover.control.ownerClientId = null;
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="simulator" />));
    await act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Start greeting")!.click());
    expect(mock.acquire).toHaveBeenCalledOnce();
    expect(mock.rover.serviceRover.turn).not.toHaveBeenCalled();
    await act(async () => root.unmount());
    const physicalRoot = createRoot(container);
    await act(async () => physicalRoot.render(<ServicePlayground rover={socket().rover} adapterType="websocket_rover" />));
    expect([...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "Start greeting")?.disabled).toBe(true);
    expect(container.textContent).not.toContain("Visitor location");
    expect(container.querySelector('[aria-label="Live rover inputs"]')).not.toBeNull();
    expect([...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "Emergency stop")?.disabled).toBe(false);
    await act(async () => physicalRoot.unmount());
  });

  it("cancels a live follow trial on camera target loss without injecting Simulator inputs", async () => {
    window.history.replaceState(null, "", "/lab?sample=follow");
    const mock = socket();
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<ServicePlayground rover={mock.rover} adapterType="websocket_rover" />));
    const click = async (text: string) => act(async () => [...container.querySelectorAll("button")].find((b) => b.textContent === text)!.click());
    await click("Test live camera");
    await act(async () => mock.emit({ source: "camera" }));
    await click("Confirm clear path · 30 s");
    await click("Follow me");
    await act(async () => mock.emit({ source: "camera", centerX: .5, bearingDeg: 0 }));
    await act(async () => mock.emit({ source: "camera", status: "lost" }));
    expect(mock.cancelMotion).toHaveBeenCalled();
    expect(simulatorApi.placePose).not.toHaveBeenCalled();
    expect(simulatorApi.setFrontObstacle).not.toHaveBeenCalled();
    expect([...container.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Follow me")?.disabled).toBe(true);
    await act(async () => root.unmount());
  });
});
