import { describe, expect, it } from "vitest";
import { ContinuousFollowController } from "./continuousFollow";

describe("continuous P following", () => {
  it("limits acceleration and smoothly decelerates near the person", () => {
    const c = new ContinuousFollowController();
    let previous = 0;
    for (let i = 0; i < 100; i++) {
      const v = c.step({ width: .2, bearing: 0, observedAt: i * .05 }, i * .05, .05, true);
      expect(v.vx - previous).toBeLessThanOrEqual(.006001);
      expect(v.vx).toBeLessThanOrEqual(.15);
      previous = v.vx;
    }
    const v = c.step({ width: .7, bearing: 0, observedAt: 5 }, 5, .05, true);
    expect(v.vx).toBeCloseTo(.135);
  });

  it("stops immediately for stale observations, lost permission and stalled loops", () => {
    for (const mode of ["stale", "permission", "stall", "lost"]) {
      const c = new ContinuousFollowController();
      c.step({ width: .2, bearing: .4, observedAt: 0 }, 0, .05, true);
      expect(c.step(mode === "lost" ? null : { width: .2, bearing: .4, observedAt: 0 },
        mode === "stale" ? 2 : 0, mode === "stall" ? 1 : .05, mode !== "permission"))
        .toEqual({ vx: 0, wz: 0 });
    }
  });

  it("converges in a differential-drive simulation without reversing", () => {
    const c = new ContinuousFollowController();
    let x = 0, y = 0, yaw = .4;
    for (let i = 0; i < 1600; i++) {
      const dx = 2 - x, dy = -y;
      const bearing = Math.atan2(Math.sin(Math.atan2(dy, dx) - yaw), Math.cos(Math.atan2(dy, dx) - yaw));
      const v = c.step({ width: .6 / Math.hypot(dx, dy), bearing, observedAt: i * .05 }, i * .05, .05, true);
      expect(v.vx).toBeGreaterThanOrEqual(0);
      expect(Math.abs(v.wz)).toBeLessThanOrEqual(.2);
      x += v.vx * Math.cos(yaw) * .05;
      y += v.vx * Math.sin(yaw) * .05;
      yaw += v.wz * .05;
    }
    expect(Math.hypot(2 - x, y)).toBeGreaterThan(.95);
    expect(Math.hypot(2 - x, y)).toBeLessThan(1.1);
  });
});
