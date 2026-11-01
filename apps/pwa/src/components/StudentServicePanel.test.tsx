import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { serviceConfig } from "../config";
import type { ServiceRover } from "../missions/api";
import { StudentServicePanel } from "./StudentServicePanel";
import { assistantApi } from "../assistantApi";
vi.mock("../assistantApi", () => ({ assistantApi: { answer: vi.fn(async () => ({
  value: null, source: "rules", response: "Please select an answer."
})) } }));
const service = {
  title: "test service", run: async (service: import("../service/studentService").StudentServiceApi) => {
    if (await service.ask("offer?")) {
      const place = await service.choose("Where?", ["Desk", "Reception", "Entrance"]);
      await service.confirm(`Ready for ${place}?`, "Ready");
    }
  }
};
it("shows labels and returns canonical values for simulated voice aliases", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  const selected = vi.fn();
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const props = { service: { title: "Choices", run: async (api: import("../service/studentService").StudentServiceApi) => {
    selected(await api.choose("Where?", [{ value: "desk-id", label: "Desk", phrases: ["my desk"] }]));
  } }, rover, config: serviceConfig, eligible: true, acquire: vi.fn(), cancel: () => true,
    emergencyStop: vi.fn(), clearance: () => true, simulator: { available: true, prepare: async () => {} } };
  try {
    await act(async () => root.render(<StudentServicePanel {...props} />));
    await act(async () => [...host.querySelectorAll("button")].find(b => b.textContent === "Start simulation")!.click());
    expect([...host.querySelectorAll("button")].some(b => b.textContent === "Desk")).toBe(true);
    expect(host.textContent).not.toContain("desk-id");
    await act(async () => root.render(<StudentServicePanel {...props} speech={{ id: 1, text: "My desk!" }} />));
    expect(selected).toHaveBeenCalledWith("desk-id");
  } finally { await act(async () => root.unmount()); }
});
vi.mock("../speech", () => ({ speakEnglish: vi.fn() }));
it("uses cloud answers but ignores late responses after a button answer", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const props = { service, rover, config: serviceConfig, eligible: true, acquire: vi.fn(), cancel: () => true,
    emergencyStop: vi.fn(), clearance: () => true, simulator: { available: true, prepare: async () => {} } };
  const click = async (label: string) => { await act(async () => [...host.querySelectorAll("button")].find(b => b.textContent === label)!.click()); };
  try {
    await act(async () => root.render(<StudentServicePanel {...props} />));
    await click("Start simulation");
    vi.mocked(assistantApi.answer).mockResolvedValueOnce({ value: "Yes", source: "gemini", response: "Accepted" });
    await act(async () => root.render(<StudentServicePanel {...props} speech={{ id: 1, text: "That would be great" }} />));
    expect(host.textContent).toContain("Where?");
    let resolve!: (result: Awaited<ReturnType<typeof assistantApi.answer>>) => void;
    vi.mocked(assistantApi.answer).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    await act(async () => root.render(<StudentServicePanel {...props} speech={{ id: 2, text: "Somewhere to work" }} />));
    const signal = vi.mocked(assistantApi.answer).mock.calls.at(-1)![3];
    await click("Desk");
    expect(signal.aborted).toBe(true);
    await act(async () => resolve({ value: "Reception", source: "gemini", response: "Accepted" }));
    expect(host.textContent).toContain("Ready for Desk?");
    expect(host.textContent).not.toContain("Ready for Reception?");
  } finally { await act(async () => root.unmount()); }
});
beforeEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = false; });
it("explains unavailable starts and makes restart secondary while running", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const props = { service, rover, config: serviceConfig, eligible: true, acquire: vi.fn(), cancel: vi.fn(() => true),
    emergencyStop: vi.fn(), clearance: vi.fn(() => true) };
  try {
    await act(async () => root.render(<StudentServicePanel {...props} simulator={{ available: false,
      unavailableReason: "Another client has control.", prepare: vi.fn() }} />));
    const button = () => [...host.querySelectorAll("button")].find(b => b.textContent === "Start simulation")!;
    expect(button().disabled).toBe(true);
    expect(host.querySelector(`#${button().getAttribute("aria-describedby")}`)?.textContent).toBe("Another client has control.");
    expect(host.textContent).not.toContain("Ready to simulate");
    await act(async () => root.render(<StudentServicePanel {...props} simulator={{ available: true, prepare: vi.fn(async () => {}) }} />));
    expect(button().classList.contains("button--primary")).toBe(true);
    await act(async () => button().click());
    expect(button().classList.contains("button--primary")).toBe(false);
    expect(host.textContent).not.toContain("Another client has control.");
  } finally { await act(async () => root.unmount()); }
});
it("blocks an unsupported physical service even when control is owned", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  const run = vi.fn(async () => {});
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  try {
    await act(async () => root.render(<StudentServicePanel
      service={{ title: "Guide", run }} rover={rover} config={serviceConfig} eligible
      blockedReason="Live marker guidance is not enabled" acquire={vi.fn()} cancel={() => true}
      emergencyStop={vi.fn()} clearance={() => true} />));
    const start = [...host.querySelectorAll("button")].find(b => b.textContent === "Start service")!;
    expect(start.disabled).toBe(true);
    expect(host.textContent).toContain("Live marker guidance is not enabled");
    await act(async () => start.click());
    expect(run).not.toHaveBeenCalled();
  } finally { await act(async () => root.unmount()); }
});
it("routes simulated speech to the current question without replaying it on the next question", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const props = { service, rover, config: serviceConfig, eligible: true, acquire: vi.fn(), cancel: vi.fn(() => true),
    emergencyStop: vi.fn(), clearance: vi.fn(() => true), simulator: { available: true, prepare: vi.fn(async () => {}) } };
  try {
    await act(async () => root.render(<StudentServicePanel {...props} />));
    await act(async () => [...host.querySelectorAll("button")].find(b => b.textContent === "Start simulation")!.click());
    await act(async () => root.render(<StudentServicePanel {...props} speech={{ id: 1, text: "Yes" }} />));
    expect(host.textContent).toContain("Where?");
    await act(async () => root.render(<StudentServicePanel {...props} speech={{ id: 1, text: "Yes" }} />));
    expect(host.textContent).toContain("Where?");
    await act(async () => root.render(<StudentServicePanel {...props} speech={{ id: 2, text: "Go forward" }} />));
    expect(host.textContent).toContain("No matching answer");
    expect(rover.move).not.toHaveBeenCalled();
    await act(async () => root.render(<StudentServicePanel {...props} speech={{ id: 3, text: "Stop" }} />));
    expect(props.cancel).toHaveBeenCalled();
    expect(host.textContent).not.toContain("Where?");
  } finally { await act(async () => root.unmount()); }
});
it.each(["confirmed", "failed", "cancelled"])("replaces a trial only after stop is %s", async outcome => {
  const host = document.createElement("div"), root = createRoot(host);
  let confirm!: () => void;
  let reject!: (error: Error) => void;
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(),
    stop: vi.fn(async reason => {
      if (reason === "confirm stop before new trial") await new Promise<void>((yes, no) => { confirm = yes; reject = no; });
    }), getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const first = vi.fn(async () => {}), second = vi.fn(async () => {});
  const props = { service, rover, config: serviceConfig, eligible: true, acquire: vi.fn(),
    cancel: vi.fn(() => true), emergencyStop: vi.fn(), clearance: vi.fn(() => true) };
  const click = async (label: string) => { await act(async () => {
    [...host.querySelectorAll("button")].find(b => b.textContent === label)!.click();
  }); };
  try {
    await act(async () => root.render(<StudentServicePanel {...props} simulator={{available:true, name:"A", prepare:first}} />));
    await click("Start selected scenario"); expect(host.textContent).toContain("offer?");
    await act(async () => root.render(<StudentServicePanel {...props} simulator={{available:true, name:"B", prepare:second}} />));
    expect(host.textContent).toContain("offer?"); expect(second).not.toHaveBeenCalled();
    await click("Start selected scenario");
    expect(second).not.toHaveBeenCalled();
    expect(host.textContent).toContain("Stopping previous trial");
    if (outcome === "cancelled") await click("Cancel and stop");
    await act(async () => { if (outcome === "failed") reject(new Error("Stop unconfirmed")); else confirm(); });
    if (outcome === "confirmed") { expect(second).toHaveBeenCalledTimes(1); expect(host.textContent).toContain("offer?"); }
    else { expect(second).not.toHaveBeenCalled(); }
  } finally { await act(async () => root.unmount()); }
});
it("prepares a simulator in one action and renews clearance until cancellation", async () => {
  vi.useFakeTimers();
  const host = document.createElement("div"); const root = createRoot(host);
  const prepare = vi.fn(async () => {});
  const clearance = vi.fn(() => true);
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const props = { service, rover, config: serviceConfig, eligible: false,
    acquire: vi.fn(), cancel: vi.fn(() => true), emergencyStop: vi.fn(), clearance,
    simulator: { available: true, prepare } };
  const click = async (label: string) => { await act(async () => {
    [...host.querySelectorAll("button")].find(b => b.textContent === label)!.click();
  }); };
  try {
    await act(async () => root.render(<StudentServicePanel {...props} />));
    expect(host.textContent).not.toContain("Confirm clear path");
    await click("Start simulation");
    expect(props.acquire).toHaveBeenCalledTimes(1);
    expect(prepare).not.toHaveBeenCalled();
    await act(async () => root.render(<StudentServicePanel {...props} eligible />));
    await act(async () => vi.advanceTimersByTimeAsync(100));
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(host.textContent).toContain("offer?");
    await act(async () => vi.advanceTimersByTimeAsync(31_000));
    expect(clearance).toHaveBeenLastCalledWith(true);
    await click("Cancel and stop");
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(clearance).toHaveBeenLastCalledWith(false);
    await click("Start simulation");
    expect(host.textContent).toContain("offer?");
    await act(async () => root.render(<StudentServicePanel {...props} eligible resetToken={1} />));
    expect(host.textContent).toContain("Scene reset");
    expect(host.textContent).not.toContain("offer?");
    expect(clearance).toHaveBeenLastCalledWith(false);
  } finally {
    await act(async () => root.unmount());
    vi.useRealTimers();
  }
});
it("renders input buttons, waits for loading, and completes only after stopping", async () => {
  const host = document.createElement("div"); const root = createRoot(host);
  const rover: ServiceRover = { move: vi.fn(), turn: vi.fn(), stop: vi.fn(async () => {}),
    getPose: vi.fn(), onPose: vi.fn(), onMarker: vi.fn(), onPerson: vi.fn() };
  const cancel = vi.fn(() => true);
  const props = { service, rover, config: serviceConfig, eligible: true, acquire: vi.fn(), cancel,
    emergencyStop: vi.fn(), clearance: vi.fn(() => true) };
  const click = async (label: string) => { await act(async () => {
    [...host.querySelectorAll("button")].find(b => b.textContent === label)!.click();
  }); };
  await act(async () => root.render(<StudentServicePanel {...props} />));
  await click("Start service"); expect(host.textContent).toContain("offer?");
  await act(async () => root.render(<StudentServicePanel {...props} cancel={() => cancel()} />));
  expect(host.textContent).toContain("offer?"); // telemetry callback changes must not abort
  await click("Yes"); expect(host.textContent).toContain("Where?");
  await click("Reception"); expect(host.textContent).toContain("Ready for Reception?");
  expect(host.textContent).not.toContain("stop confirmed");
  await click("Ready"); expect(host.textContent).toContain("stop confirmed");
  await click("Start service"); await click("Cancel and stop");
  expect(cancel).toHaveBeenCalled(); expect(host.textContent).not.toContain("stop confirmed");
  await click("Start service");
  await act(async () => root.render(<StudentServicePanel {...props} eligible={false} />));
  expect(host.textContent).not.toContain("offer?");
  expect(rover.stop).toHaveBeenLastCalledWith("student service finished");
  await act(async () => root.unmount());
});
