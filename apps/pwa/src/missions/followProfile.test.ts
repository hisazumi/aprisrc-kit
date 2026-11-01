import { expect, it } from "vitest";
import { followProfileTuning, selectFollowProfile } from "./followProfile";

it("requires explicit opt-in for iron-X and leaves other hardware on bounded motion", () => {
  expect(selectFollowProfile("ironx_network", undefined)).toBe(false);
  expect(selectFollowProfile("ironx_network", "0")).toBe(false);
  expect(selectFollowProfile("ironx_network", "1")).toBe("ironx");
  for (const adapter of [null, "ironx", "websocket_rover", "factory_http"]) {
    expect(selectFollowProfile(adapter, "1")).toBe(false);
  }
  expect(selectFollowProfile("simulator", undefined)).toBe("simulator");
});

it("keeps simulator and hardware tuning independent", () => {
  expect(followProfileTuning("ironx")).toEqual({ maxSpeed: .15, distanceGain: .6 });
  expect(followProfileTuning("simulator")).toEqual({ maxSpeed: .25, distanceGain: .8 });
  expect(followProfileTuning(false)).toBeUndefined();
});
