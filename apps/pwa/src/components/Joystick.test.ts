import { describe, expect, it } from "vitest";

import { applyJoystickDeadZone, JOYSTICK_DEAD_ZONE } from "./Joystick";

describe("joystick dead zone", () => {
  it("suppresses center noise", () => {
    expect(applyJoystickDeadZone({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
    expect(
      applyJoystickDeadZone({ x: JOYSTICK_DEAD_ZONE * 0.5, y: -0.001 }),
    ).toEqual({ x: 0, y: 0 });
  });

  it("remaps motion continuously outside the dead zone", () => {
    const justOutside = applyJoystickDeadZone({
      x: JOYSTICK_DEAD_ZONE + 0.001,
      y: 0,
    });
    expect(justOutside.x).toBeGreaterThan(0);
    expect(justOutside.x).toBeLessThan(0.002);
    expect(justOutside.y).toBe(0);
  });

  it("snaps cross-axis noise so a horizontal turn has exactly zero linear speed", () => {
    const horizontal = applyJoystickDeadZone({ x: 0.9, y: -0.003 });
    expect(horizontal.x).toBeGreaterThan(0.8);
    expect(horizontal.y).toBe(0);
  });

  it("preserves direction and full-scale output", () => {
    const diagonal = applyJoystickDeadZone({ x: 0.6, y: -0.8 });
    expect(diagonal.x).toBeCloseTo(0.6);
    expect(diagonal.y).toBeCloseTo(-0.8);
  });
});
