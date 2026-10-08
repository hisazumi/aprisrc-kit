import { describe, expect, it } from "vitest";

import { serviceModeForSearch, viewForPathname } from "./App";

describe("viewForPathname", () => {
  it.each([
    ["/", "app"],
    ["/app", "app"],
    ["/app/example", "app"],
    ["/console", "console"],
    ["/console/status", "console"],
    ["/lab", "lab"],
    ["/lab/tools", "lab"]
  ] as const)("maps %s to %s", (pathname, expected) => {
    expect(viewForPathname(pathname)).toBe(expected);
  });
});

describe("serviceModeForSearch", () => {
  it("opens the receptionist from a shareable service URL", () => {
    expect(serviceModeForSearch("?service=receptionist")).toBe("receptionist");
    expect(serviceModeForSearch("?service=unknown")).toBe("carry");
    expect(serviceModeForSearch("")).toBe("carry");
  });
});
