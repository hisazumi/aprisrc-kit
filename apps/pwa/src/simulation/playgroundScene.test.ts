import { describe, expect, it } from "vitest";
import { parseScene, scenePreset } from "./playgroundScene";
import { projectVirtualPerson } from "./virtualPerson";

describe("playground scenes", () => {
  it("round trips and separates visible, behind and hidden cases", () => {
    const front = scenePreset("front");
    expect(parseScene(JSON.stringify(front))).toEqual(front);
    expect(projectVirtualPerson(front.origin, front.entrance).visible).toBe(true);
    const behind = scenePreset("behind");
    expect(projectVirtualPerson(behind.origin, behind.entrance).visible).toBe(false);
    expect(projectVirtualPerson(behind.origin, behind.visitor).visible).toBe(true);
    expect(scenePreset("missing").hidden).toBe(true);
  });
  it("rejects malformed, nonfinite and out-of-range storage", () => {
    for (const value of ["null", "{}", "invalid", JSON.stringify({ ...scenePreset("front"), origin: { x: 11, y: 0, yaw: 0 } })]) {
      expect(() => parseScene(value)).toThrow();
    }
  });
});
