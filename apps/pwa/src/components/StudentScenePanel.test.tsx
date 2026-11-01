import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StudentScenePanel, StudentSceneExecution } from "./StudentScenePanel";
import { parseStudentScene, studentScenes, StudentSceneRunner } from "../simulation/studentScene";

beforeEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(() => { (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = false; });
it("ignores blank checks without removing newlines during editing", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  document.body.append(host);
  let scene = structuredClone(studentScenes[0]);
  const render = () => root.render(<StudentScenePanel scene={scene} onChange={next => { scene = next; render(); }} />);
  try {
    await act(async () => render());
    const textarea = host.querySelector("textarea")!;
    const type = async (value: string) => act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(textarea, value);
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await type("Stops safely\n\n");
    expect(scene.checks).toEqual(["Stops safely"]);
    expect(textarea.value).toBe("Stops safely\n\n");
    expect(() => parseStudentScene(scene)).not.toThrow();
    await type("");
    expect(scene.checks).toEqual([]);
    expect(() => parseStudentScene(scene)).not.toThrow();
    await act(async () => { scene = structuredClone(studentScenes[1]); render(); });
    expect(textarea.value).toBe(studentScenes[1].checks.join("\n"));
  } finally { await act(async () => root.unmount()); host.remove(); }
});
it("marks edited presets Custom and restores the original on reselection", async () => {
  const host = document.createElement("div"), root = createRoot(host);
  let scene = structuredClone(studentScenes[0]);
  const render = () => root.render(<StudentScenePanel scene={scene} onChange={next => { scene = next; render(); }} />);
  try {
    await act(async () => render());
    const select = host.querySelector("select")!;
    expect(select.value).toBe(studentScenes[0].name);
    await act(async () => { scene = { ...scene, person: { x: 3, y: 1 } }; render(); });
    expect(select.value).toBe("custom");
    await act(async () => { select.value = studentScenes[0].name; select.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(scene).toEqual(studentScenes[0]);
    expect(scene).not.toBe(studentScenes[0]);
    expect(select.value).toBe(studentScenes[0].name);
  } finally { await act(async () => root.unmount()); }
});
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
