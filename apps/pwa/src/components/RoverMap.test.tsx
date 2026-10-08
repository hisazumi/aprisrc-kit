import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { RoverMap } from "./RoverMap";

describe("RoverMap", () => {
  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = false;
  });

  it("keeps the rover and person visible after they move away from the world origin", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const pose = { x: 3, y: 0, yaw: 0 };

    await act(async () => root.render(
      <RoverMap
        pose={pose}
        path={[{ x: 0, y: 0, yaw: 0 }, pose]}
        person={{ x: 4.35, y: 0 }}
      />
    ));

    expect(container.querySelector(".rover-body")?.parentElement?.getAttribute("transform"))
      .toBe("translate(310 270.75) rotate(0)");
    expect(container.querySelector(".map-person")?.getAttribute("transform"))
      .toBe("translate(310 149.25)");

    await act(async () => root.unmount());
  });

  it("centers the rover when there is no virtual person", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(
      <RoverMap pose={{ x: 7, y: -2, yaw: Math.PI / 2 }} path={[]} />
    ));

    expect(container.querySelector(".rover-body")?.parentElement?.getAttribute("transform"))
      .toBe("translate(310 210) rotate(-90)");

    await act(async () => root.unmount());
  });
});
