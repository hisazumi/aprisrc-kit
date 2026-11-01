import { expect, it, vi } from "vitest";
import { serviceConfig } from "../config";
import type { MissionContext } from "../missions/api";
import { runMobileReceptionist } from "../missions/mobileReceptionist";
import { runStudentService } from "./studentService";

vi.mock("../missions/mobileReceptionist", () => ({ runMobileReceptionist: vi.fn() }));
it.each(["arrived", "blocked", "lost", "not_found"] as const)("guidance outcome %s only succeeds on arrival and always stops", async outcome => {
  vi.mocked(runMobileReceptionist).mockResolvedValueOnce(outcome);
  const stop = vi.fn(async () => {});
  const context = { config: serviceConfig, signal: new AbortController().signal,
    rover: { stop }, report: vi.fn(), say: vi.fn() } as unknown as MissionContext;
  const result = runStudentService({ title: "Guide", run: service => service.guideTo("desk") }, context, vi.fn());
  if (outcome === "arrived") await expect(result).resolves.toBeUndefined();
  else await expect(result).rejects.toThrow(`Guidance stopped: ${outcome}`);
  expect(stop).toHaveBeenCalledWith("student service finished");
});
