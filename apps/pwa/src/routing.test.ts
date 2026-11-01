import { describe, expect, it } from "vitest";

import { serviceModeForSearch, viewForPathname, viewUrl } from "./navigation";

describe("viewForPathname", () => {
  it.each([
    ["/", "app"],
    ["/app", "app"],
    ["/service", "app"],
    ["/playground", "lab"],
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
    expect(serviceModeForSearch("?service=unknown")).toBe("student");
    expect(serviceModeForSearch("")).toBe("student");
  });
  it.each(["student", "my-service"])("supports the template alias %s", id => {
    expect(serviceModeForSearch(`?service=${id}`)).toBe("student");
    expect(serviceModeForSearch(`?sample=${id}`)).toBe("student");
  });
  it("keeps a selected service across every view and removes legacy sample", () => {
    for (const service of ["student", "carry", "receptionist", "greeting"] as const) {
      for (const view of ["app", "lab", "console"] as const) {
        const url = new URL(viewUrl(view, service, "?sample=follow&extra=1"), "http://localhost");
        expect(viewForPathname(url.pathname)).toBe(view);
        expect(serviceModeForSearch(url.search)).toBe(service);
        expect(url.searchParams.has("sample")).toBe(false);
        expect(url.searchParams.get("extra")).toBe("1");
      }
    }
    expect(viewUrl("lab", "student")).toBe("/playground?service=my-service");
    expect(serviceModeForSearch("?sample=follow")).toBe("carry");
    expect(serviceModeForSearch("?service=receptionist&sample=student")).toBe("receptionist");
  });
});
