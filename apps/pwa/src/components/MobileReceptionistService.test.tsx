import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { serviceConfig } from "../config";
import type { MissionContext, MissionDefinition, ServiceRover } from "../missions";
import { MobileReceptionistService } from "./MobileReceptionistService";

function rover(): ServiceRover {
  return {
    move: async () => undefined,
    turn: async () => undefined,
    stop: async () => undefined,
    getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
    onPose: () => () => undefined,
    onPerson: () => () => undefined,
    onMarker: () => () => undefined
  };
}

function mission(run: MissionDefinition["run"]): MissionDefinition {
  return {
    id: "mobile-receptionist",
    title: "Mobile receptionist",
    description: "Guide a visitor",
    runningDetail: "Guiding",
    script: [],
    run
  };
}

describe("MobileReceptionistService", () => {
  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = false;
  });

  it("runs the reference scenario through the same mission and changes camera phase", async () => {
    const runScenario = vi.fn(async () => undefined);
    const cameraFacing = vi.fn();
    const run = vi.fn(async (context: MissionContext) => {
      context.report({ phase: "acquiring", detail: "Looking for a visitor" });
      context.report({ phase: "waiting", detail: "Searching for Entrance" });
      context.report({ phase: "arrived", detail: "Arrived at Entrance" });
    });
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(
      <MobileReceptionistService
        connected
        isOwner
        controlAvailable
        estopLatched={false}
        adapterType="simulator"
        rover={rover()}
        mission={mission(run)}
        config={serviceConfig}
        onAcquireControl={vi.fn()}
        onReleaseControl={vi.fn()}
        onCancelMotion={vi.fn(() => true)}
        onEmergencyStop={vi.fn()}
        onCameraFacingChange={cameraFacing}
        runScenario={runScenario}
        stopScenario={vi.fn(async () => undefined)}
        speak={vi.fn()}
      />
    ));

    const start = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Run simulated service");
    await act(async () => start?.click());

    expect(runScenario).toHaveBeenCalledWith("mobile-receptionist");
    expect(run).toHaveBeenCalledOnce();
    expect(cameraFacing).toHaveBeenNthCalledWith(1, "user");
    expect(cameraFacing).toHaveBeenCalledWith("environment");
    expect(container.textContent).toContain("Destination reached");

    await act(async () => root.unmount());
  });

  it("requires explicit supervised clearance for a hardware run", async () => {
    vi.useFakeTimers();
    let context: MissionContext | undefined;
    const clearance = vi.fn(() => true);
    const visionActive = vi.fn();
    const run = vi.fn(async (nextContext: MissionContext) => {
      context = nextContext;
      await new Promise<void>((resolve) => {
        nextContext.signal.addEventListener("abort", () => resolve(), { once: true });
      });
    });
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(
      <MobileReceptionistService
        connected
        isOwner
        controlAvailable
        estopLatched={false}
        adapterType="websocket_rover"
        rover={rover()}
        mission={mission(run)}
        config={serviceConfig}
        onAcquireControl={vi.fn()}
        onReleaseControl={vi.fn()}
        onCancelMotion={vi.fn(() => true)}
        onEmergencyStop={vi.fn()}
        onPathClearanceChange={clearance}
        onVisionActiveChange={visionActive}
        speak={vi.fn()}
      />
    ));

    const start = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Start receptionist");
    await act(async () => start?.click());
    expect(context).toBeDefined();
    expect(visionActive).toHaveBeenCalledWith(true);

    const allow = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Allow movement for 30 s");
    await act(async () => allow?.click());
    expect(clearance).toHaveBeenLastCalledWith(true);
    expect(container.textContent).toContain("Movement enabled · 30 s");

    const stop = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Stop service");
    await act(async () => stop?.click());
    expect(clearance).toHaveBeenLastCalledWith(false);
    expect(visionActive).toHaveBeenLastCalledWith(false);

    await act(async () => root.unmount());
  });
});
