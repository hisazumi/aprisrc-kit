import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

import { Joystick } from "./Joystick";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

afterEach(() => vi.useRealTimers());

it("transmits every 50 ms only while held and stops on release", async () => {
  vi.useFakeTimers();
  const container = document.createElement("div");
  const root = createRoot(container);
  const onDrive = vi.fn();
  const onStop = vi.fn();
  try {
    await act(async () => root.render(
      <Joystick disabled={false} onDrive={onDrive} onStop={onStop} />
    ));
    const pad = container.querySelector("[role=application]") as HTMLDivElement;
    pad.setPointerCapture = vi.fn();
    await act(async () => vi.advanceTimersByTime(200));
    expect(onDrive).not.toHaveBeenCalled();
    await act(async () => pad.dispatchEvent(
      new MouseEvent("pointerdown", { bubbles: true, clientY: -1 })
    ));
    expect(onDrive).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTime(49));
    expect(onDrive).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTime(1));
    expect(onDrive).toHaveBeenCalledTimes(2);
    await act(async () => vi.advanceTimersByTime(150));
    expect(onDrive).toHaveBeenCalledTimes(5);
    await act(async () => pad.dispatchEvent(new MouseEvent("pointerup", { bubbles: true })));
    expect(onStop).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTime(200));
    expect(onDrive).toHaveBeenCalledTimes(5);
  } finally {
    await act(async () => root.unmount());
  }
});
