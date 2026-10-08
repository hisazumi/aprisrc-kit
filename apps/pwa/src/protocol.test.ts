import { describe, expect, it } from "vitest";

import { isServerMessage } from "./protocol";

describe("protocol guard", () => {
  it("accepts a versioned server message", () => {
    expect(isServerMessage({ v: 1, type: "event", event: "started", detail: "" })).toBe(true);
  });

  it("rejects an unknown envelope", () => {
    expect(isServerMessage({ v: 2, type: "event" })).toBe(false);
    expect(isServerMessage(null)).toBe(false);
  });
});
