import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { serviceConfig } from "../config";
import type { MissionContext, MissionDefinition, ServiceRover } from "../missions";
import type { PersonEvent } from "../protocol";
import { AutonomousCarryService } from "./AutonomousCarryService";

function detected(index: number): PersonEvent {
  return {
    eventId: `person-${index}`,
    status: "detected",
    confidence: 0.95,
    capturedAt: index,
    source: "camera",
    personId: "visitor",
    centerX: 0.5,
    centerY: 0.5,
    width: 0.2,
    height: 0.5,
    bearingDeg: 0
  };
}

function createApproachMission(
  run: MissionDefinition["run"] = async (context) => {
    context.report({ phase: "arrived", detail: "I am here", person: detected(90) });
  }
): MissionDefinition {
  return {
    id: "come-here",
    title: "Come to me",
    description: "Approach a person",
    runningDetail: "Approaching",
    script: [],
    run
  };
}

describe("AutonomousCarryService", () => {
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

  it("offers help after stable detection, starts the mission, and surfaces target loss", async () => {
    let personListener: ((person: Readonly<PersonEvent>) => void) | undefined;
    const stop = vi.fn(async () => undefined);
    const rover: ServiceRover = {
      move: async () => undefined,
      turn: async () => undefined,
      stop,
      getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
      onPose: () => () => undefined,
      onPerson: (listener) => {
        personListener = listener;
        return () => {
          personListener = undefined;
        };
      },
      onMarker: () => () => undefined
    };
    let missionContext: MissionContext | undefined;
    let approachContext: MissionContext | undefined;
    const approachRun = vi.fn(async (context: MissionContext) => {
      approachContext = context;
    });
    const run = vi.fn(async (context: MissionContext) => {
      missionContext = context;
    });
    const mission: MissionDefinition = {
      id: "carry-helper",
      title: "Carry helper",
      description: "Follow a person",
      runningDetail: "Following",
      script: [],
      trigger: {
        intent: "follow_person",
        description: "Follow a person",
        examples: ["Follow me"],
        keywords: ["follow"],
        response: "Okay. I will follow you."
      },
      run
    };
    const speak = vi.fn();
    const release = vi.fn();
    const cancel = vi.fn(() => true);
    const pathClearance = vi.fn(() => true);
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(
      <AutonomousCarryService
        connected
        isOwner
        controlAvailable
        estopLatched={false}
        batteryPercent={80}
        rover={rover}
        approachMission={createApproachMission(approachRun)}
        mission={mission}
        config={serviceConfig}
        onAcquireControl={vi.fn()}
        onReleaseControl={release}
        onCancelMotion={cancel}
        onEmergencyStop={vi.fn()}
        onPathClearanceChange={pathClearance}
        speak={speak}
      />
    ));

    const start = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Start service");
    await act(async () => start?.click());
    expect(container.textContent).toContain("I am ready to help");

    await act(async () => {
      personListener?.(detected(1));
      personListener?.(detected(2));
    });
    expect(container.textContent).toContain("Hello there");
    expect(container.textContent).not.toContain("Yes, help me");

    await act(async () => personListener?.(detected(3)));
    expect(approachRun).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("I am coming closer");
    expect(container.textContent).not.toContain("Yes, help me");

    const allowMovement = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Allow movement for 30 s");
    await act(async () => allowMovement?.click());
    expect(pathClearance).toHaveBeenLastCalledWith(true);
    expect(container.textContent).toContain("Movement enabled · 30 s");

    const cancelMovement = [...container.querySelectorAll("button")]
      .find((button) => button.textContent?.startsWith("Movement enabled"));
    await act(async () => cancelMovement?.click());
    expect(pathClearance).toHaveBeenLastCalledWith(false);

    await act(async () => approachContext?.report({
      phase: "arrived",
      detail: "I am here",
      person: detected(90)
    }));
    expect(container.textContent).toContain("Would you like some help?");
    expect(speak).toHaveBeenCalledWith("Hello. Would you like help carrying something?");

    const accept = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Yes, help me");
    await act(async () => {
      accept?.click();
      await Promise.resolve();
    });
    expect(container.textContent).toContain("Place your items on the rover");
    expect(run).not.toHaveBeenCalled();

    const loaded = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Items are loaded");
    await act(async () => {
      loaded?.click();
      await Promise.resolve();
    });
    expect(run).toHaveBeenCalledWith(
      expect.objectContaining({ rover, config: serviceConfig }),
      { intent: "follow_person", destination: null, followDistance: "normal" }
    );

    await act(async () => missionContext?.report({
      phase: "following",
      detail: "Following you",
      person: detected(4)
    }));
    expect(container.textContent).toContain("I am following you");

    await act(async () => missionContext?.report({
      phase: "lost",
      detail: "I lost sight of you"
    }));
    expect(container.textContent).toContain("TARGET LOST");
    expect(container.textContent).toContain("I lost sight of you");

    const end = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "End service");
    await act(async () => {
      end?.click();
      await Promise.resolve();
    });
    expect(cancel).toHaveBeenCalled();
    expect(stop).toHaveBeenCalledWith("carry service stopped");
    expect(release).toHaveBeenCalled();

    await act(async () => root.unmount());
  });

  it("requests control before arming when the service app is an observer", async () => {
    const acquire = vi.fn();
    const rover: ServiceRover = {
      move: async () => undefined,
      turn: async () => undefined,
      stop: async () => undefined,
      getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
      onPose: () => () => undefined,
      onPerson: () => () => undefined,
      onMarker: () => () => undefined
    };
    const mission: MissionDefinition = {
      id: "carry-helper",
      title: "Carry helper",
      description: "Follow a person",
      runningDetail: "Following",
      script: [],
      run: async () => undefined
    };
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(
      <AutonomousCarryService
        connected
        isOwner={false}
        controlAvailable
        estopLatched={false}
        batteryPercent={null}
        rover={rover}
        approachMission={createApproachMission()}
        mission={mission}
        config={serviceConfig}
        onAcquireControl={acquire}
        onReleaseControl={vi.fn()}
        onCancelMotion={() => true}
        onEmergencyStop={vi.fn()}
        speak={vi.fn()}
      />
    ));

    const start = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Start service");
    await act(async () => start?.click());

    expect(acquire).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("Starting…");
    expect(container.textContent).toContain("Ready when you are");

    await act(async () => root.unmount());
  });

  it("withdraws an unanswered offer instead of repeatedly approaching", async () => {
    vi.useFakeTimers();
    let personListener: ((person: Readonly<PersonEvent>) => void) | undefined;
    const rover: ServiceRover = {
      move: async () => undefined,
      turn: async () => undefined,
      stop: async () => undefined,
      getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
      onPose: () => () => undefined,
      onPerson: (listener) => {
        personListener = listener;
        return () => undefined;
      },
      onMarker: () => () => undefined
    };
    const mission: MissionDefinition = {
      id: "carry-helper",
      title: "Carry helper",
      description: "Follow a person",
      runningDetail: "Following",
      script: [],
      run: async () => undefined
    };
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(
      <AutonomousCarryService
        connected
        isOwner
        controlAvailable
        estopLatched={false}
        batteryPercent={90}
        rover={rover}
        approachMission={createApproachMission()}
        mission={mission}
        config={serviceConfig}
        onAcquireControl={vi.fn()}
        onReleaseControl={vi.fn()}
        onCancelMotion={() => true}
        onEmergencyStop={vi.fn()}
        speak={vi.fn()}
      />
    ));
    const start = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Start service");
    await act(async () => start?.click());
    await act(async () => {
      personListener?.(detected(1));
      personListener?.(detected(2));
      personListener?.(detected(3));
    });
    expect(container.textContent).toContain("Would you like some help?");

    await act(async () => vi.advanceTimersByTime(12_000));

    expect(container.textContent).toContain("No problem");
    expect(container.textContent).not.toContain("Yes, help me");

    await act(async () => root.unmount());
  });
});
