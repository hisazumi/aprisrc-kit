import { describe, expect, it } from "vitest";
import { ContinuousFollowController, defaultFollowTuning } from "./continuousFollow";

describe("continuous P following", () => {
  it("increases simulator distance response while preserving default gain and slew limits", () => {
    const baseline = new ContinuousFollowController({ ...defaultFollowTuning, maxSpeed: .25 });
    const faster = new ContinuousFollowController({ ...defaultFollowTuning, maxSpeed: .25, distanceGain: .8 });
    let before = 0, after = 0, previous = 0;
    for (let i = 0; i < 100; i++) {
      const person = { width: .4, bearing: 0, observedAt: i * .05 };
      before = baseline.step(person, i * .05, .05, true).vx;
      after = faster.step(person, i * .05, .05, true).vx;
      expect(after - previous).toBeLessThanOrEqual(.006001);
      expect(after).toBeLessThanOrEqual(.25);
      previous = after;
    }
    expect(after).toBeGreaterThan(before);
    expect(after / before).toBeCloseTo(4 / 3);
    expect(defaultFollowTuning.distanceGain).toBe(.6);
  });
  it("allows the simulator ceiling without changing default tuning or acceleration", () => {
    const c = new ContinuousFollowController({ ...defaultFollowTuning, maxSpeed: .25 });
    let previous = 0;
    for (let i = 0; i < 100; i++) {
      const v = c.step({ width: .05, bearing: 0, observedAt: i * .05 }, i * .05, .05, true);
      expect(v.vx - previous).toBeLessThanOrEqual(.006001);
      expect(v.vx).toBeLessThanOrEqual(.25);
      previous = v.vx;
    }
    expect(previous).toBeCloseTo(.25);
    expect(defaultFollowTuning.maxSpeed).toBe(.15);
  });
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
