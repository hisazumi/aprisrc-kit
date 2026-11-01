import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { ManualPersonPanel } from "./ManualPersonPanel";

it("offers independent person actions without a scenario step", async () => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const host = document.createElement("div"), root = createRoot(host);
  const onMotion = vi.fn(), onPlace = vi.fn();
  try {
    await act(async () => root.render(<ManualPersonPanel enabled visible motion="still" speed={.1}
      onMotion={onMotion} onPlace={onPlace} onSpeed={vi.fn()} onSay={vi.fn()} />));
    const click = async (label: string) => { await act(async () => {
      [...host.querySelectorAll("button")].find(button => button.textContent === label)!.click();
    }); };
    await click("Leave view"); await click("Enter view"); await click("Move away"); await click("Stand still");
    expect(onPlace.mock.calls).toEqual([["leave"], ["enter"]]);
    expect(onMotion.mock.calls).toEqual([["away"], ["still"]]);
    expect(host.textContent).not.toContain("Next step");
    expect(host.querySelector('[aria-label="Person says"]')).not.toBeNull();
  } finally {
    await act(async () => root.unmount());
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
  }
});
