import { expect, it } from "vitest";
import { followProfileTuning, selectFollowProfile } from "./followProfile";

it("defaults network iron-X to continuous following with an explicit opt-out", () => {
  expect(selectFollowProfile("ironx_network", undefined)).toBe("ironx");
  expect(selectFollowProfile("ironx_network", "")).toBe("ironx");
  expect(selectFollowProfile("ironx_network", "0")).toBe(false);
  expect(selectFollowProfile("ironx_network", "1")).toBe("ironx");
});

it("leaves other adapters unchanged regardless of the hardware flag", () => {
  for (const flag of [undefined, "0", "1"]) {
    for (const adapter of [null, "ironx", "websocket_rover", "factory_http"]) {
      expect(selectFollowProfile(adapter, flag)).toBe(false);
    }
    expect(selectFollowProfile("simulator", flag)).toBe("simulator");
  }
});

it("keeps simulator and hardware tuning independent", () => {
  expect(followProfileTuning("ironx")).toEqual({ maxSpeed: .15, distanceGain: .6 });
  expect(followProfileTuning("simulator")).toEqual({ maxSpeed: .25, distanceGain: .8 });
  expect(followProfileTuning(false)).toBeUndefined();
});
