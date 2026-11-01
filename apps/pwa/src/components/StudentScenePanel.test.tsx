import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StudentScenePanel, StudentSceneExecution } from "./StudentScenePanel";
import { studentScenes, StudentSceneRunner } from "../simulation/studentScene";

beforeEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = false; });
it("keeps definition selection and execution progress independent", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  const onChange = vi.fn(), onNext = vi.fn();
  const run = new StudentSceneRunner(studentScenes[0], 0);
  const render = (selected: number, active = true) => <>
    <StudentScenePanel scene={studentScenes[selected]} onChange={onChange} />
    <StudentSceneExecution scene={studentScenes[0]} frame={run.update(0)} active={active} onNext={onNext} />
  </>;
  try {
    await act(async () => root.render(render(0)));
    const select = host.querySelector("select")!;
    expect(select.disabled).toBe(false);
    expect(host.querySelector("fieldset")!.disabled).toBe(false);
    await act(async () => { select.value = studentScenes[3].name; select.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(onChange).toHaveBeenCalledWith(studentScenes[3]);
    await act(async () => root.render(render(3)));
    expect(host.querySelector('[aria-label="Trial execution"]')!.textContent).toContain("Running: Walk and stop");
    expect(host.querySelector('[aria-label="Trial execution"]')!.textContent).not.toContain("Disappear");
    const next = host.querySelector<HTMLButtonElement>('[aria-label="Next step"]')!;
    await act(async () => next.click());
    expect(onNext).toHaveBeenCalledTimes(1);
    await act(async () => root.render(render(3, false)));
    expect(next.disabled).toBe(true);
    expect(host.textContent).toContain("Last trial: Walk and stop");
    expect(host.textContent).toContain("Stopped");
  } finally { await act(async () => root.unmount()); }
});
