import { expect, it, vi } from "vitest";
import { serviceCatalog } from "./catalog";
import { myService } from "../missions/myService";
import type { StudentServiceApi } from "./studentService";

function api(): StudentServiceApi {
  return { waitForPerson: vi.fn(async () => {}), approachPerson: vi.fn(async () => {}),
    ask: vi.fn(async () => true), confirm: vi.fn(async () => {}), choose: vi.fn(async () => "Desk"),
    waitForLoaded: vi.fn(async () => {}), followPerson: vi.fn(async () => {}), say: vi.fn(),
    greetPerson: vi.fn(async () => {}), guideTo: vi.fn(async () => {}) };
}
it("provides actual source and a single runnable definition for every service", () => {
  for (const entry of Object.values(serviceCatalog)) {
    expect(entry.source).toContain("async run(service)");
    expect(entry.source).toContain(entry.definition.title);
    expect(entry.file).toMatch(/\.ts$/);
  }
});
it("uses the editable My service file independently of the built-in carry example", () => {
  expect(serviceCatalog.student.definition).toBe(myService);
  expect(serviceCatalog.student.file).toBe("missions/myService.ts");
  expect(serviceCatalog.student.source).toContain("export const myService");
  expect(serviceCatalog.carry.definition).not.toBe(myService);
});
it.each(["student", "carry"] as const)("%s asks consent and waits for loading before following", async id => {
  const service = api();
  await serviceCatalog[id].definition.run(service);
  expect(service.ask).toHaveBeenCalledOnce();
  expect(service.confirm).toHaveBeenCalledWith("Place your belongings on the rover.", "Items are loaded", ["ready", "all set", "loaded"]);
  expect(service.followPerson).toHaveBeenCalledOnce();
  expect(vi.mocked(service.confirm).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(service.followPerson).mock.invocationCallOrder[0]);
  const refused = api(); vi.mocked(refused.ask).mockResolvedValue(false);
  await serviceCatalog[id].definition.run(refused);
  expect(refused.followPerson).not.toHaveBeenCalled();
});
it("greeting and reception use the same generic API", async () => {
  const greeting = api(); await serviceCatalog.greeting.definition.run(greeting);
  expect(greeting.greetPerson).toHaveBeenCalledOnce();
  const receptionist = api(); await serviceCatalog.receptionist.definition.run(receptionist);
  expect(receptionist.choose).toHaveBeenCalledWith("Destination?", ["Entrance", "Desk"]);
  expect(receptionist.guideTo).toHaveBeenCalledWith("desk");
  expect(vi.mocked(receptionist.confirm).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(receptionist.guideTo).mock.invocationCallOrder[0]);
});
