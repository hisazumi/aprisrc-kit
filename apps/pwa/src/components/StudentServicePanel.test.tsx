import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { serviceConfig } from "../config";
import type { ServiceRover } from "../missions/api";
import { StudentServicePanel } from "./StudentServicePanel";
vi.mock("../missions/studentCarry", () => ({ studentCarry: {
  title: "test service", run: async (service: import("../service/studentService").StudentServiceApi) => {
    if (await service.ask("offer?")) await service.waitForLoaded("load now");
  }
} }));
vi.mock("../speech", () => ({ speakEnglish: vi.fn() }));
beforeEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = false; });
it("renders input buttons, waits for loading, and completes only after stopping", async () => {
  const host = document.createElement("div"); const root = createRoot(host);
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const cancel = vi.fn(() => true);
  const props = { rover, config: serviceConfig, eligible: true, acquire: vi.fn(), cancel,
    emergencyStop: vi.fn(), clearance: vi.fn(() => true) };
  const click = async (label: string) => { await act(async () => {
    [...host.querySelectorAll("button")].find(b => b.textContent === label)!.click();
  }); };
  await act(async () => root.render(<StudentServicePanel {...props} />));
  await click("Start service"); expect(host.textContent).toContain("offer?");
  await act(async () => root.render(<StudentServicePanel {...props} cancel={() => cancel()} />));
  expect(host.textContent).toContain("offer?"); // telemetry callback changes must not abort
  await click("Yes"); expect(host.textContent).toContain("load now");
  expect(host.textContent).not.toContain("stop confirmed");
  await click("Items are loaded"); expect(host.textContent).toContain("stop confirmed");
  await click("Start service"); await click("Cancel and stop");
  expect(cancel).toHaveBeenCalled(); expect(host.textContent).not.toContain("stop confirmed");
  await click("Start service");
  await act(async () => root.render(<StudentServicePanel {...props} eligible={false} />));
  expect(host.textContent).not.toContain("offer?");
  expect(rover.stop).toHaveBeenLastCalledWith("student service finished");
  await act(async () => root.unmount());
});
