import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ServiceConfig } from "../config";
import type { MissionDefinition, ServiceRover } from "../missions";
import { MissionPanel } from "./MissionPanel";

const config: ServiceConfig = {
  team: { teamName: "Test", serviceName: "Test service", defaultMissionId: "first" },
  courseMarkers: []
};

const rover: ServiceRover = {
  move: async () => undefined,
  turn: async () => undefined,
  stop: async () => undefined,
  getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
  onPose: () => () => undefined,
  onPerson: () => () => undefined,
  onMarker: () => () => undefined
};

function definition(id: string, run: MissionDefinition["run"]): MissionDefinition {
  return {
    id,
    title: `${id} mission`,
    description: `${id} description`,
    runningDetail: `${id} running`,
    script: [`await rover.${id}()`],
    run
  };
}

describe("MissionPanel", () => {
  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = false;
  });

  it("selects and runs a registered mission", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const firstRun = vi.fn(async () => undefined);
    const secondRun = vi.fn(async () => undefined);
    const missions = [definition("first", firstRun), definition("second", secondRun)];

    await act(async () => {
      root.render(
        <MissionPanel
          disabled={false}
          rover={rover}
          missions={missions}
          config={config}
          defaultMissionId="first"
          cancelMotion={() => true}
        />
      );
    });

    const select = container.querySelector("select");
    expect(select?.value).toBe("first");

    await act(async () => {
      if (!select) return;
      select.value = "second";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });

    await act(async () => {
      container.querySelector<HTMLButtonElement>("button.button--primary")?.click();
      await Promise.resolve();
    });

    expect(firstRun).not.toHaveBeenCalled();
    expect(secondRun).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("second mission completed");

    await act(async () => root.unmount());
  });
});
