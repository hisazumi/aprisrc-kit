import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it } from "vitest";
import { useStudentScene } from "./useStudentScene";
import { studentScenes } from "./studentScene";

it("takes a definition snapshot and preserves the last frame when stopped", async () => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const root = createRoot(document.createElement("div"));
  let run!: ReturnType<typeof useStudentScene>;
  function Harness() { run = useStudentScene(); return null; }
  try {
    await act(async () => root.render(<Harness />));
    const selected = structuredClone(studentScenes[0]);
    await act(async () => run.start(selected));
    selected.name = "Changed"; selected.steps[0].points[0].x = 9;
    expect(run.definition?.name).toBe("Walk and stop");
    expect(run.definition?.steps[0].points[0].x).toBe(2);
    const previous = run.frame;
    await act(async () => run.stop());
    expect(run.active).toBe(false); expect(run.frame).toEqual(previous);
    await act(async () => run.next());
    expect(run.frame).toEqual(previous);
    await act(async () => run.start(studentScenes[3]));
    expect(run.definition?.name).toBe("Lose the person");
    expect(run.frame?.index).toBe(0);
  } finally {
    await act(async () => root.unmount());
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
  }
});
