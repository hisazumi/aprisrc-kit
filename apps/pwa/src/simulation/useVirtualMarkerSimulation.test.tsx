import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { courseMarkers } from "../config/courseMarkers";
import { simulatorApi } from "../simulatorApi";
import { relativeMarkerPosition, useVirtualMarkerSimulation } from "./useVirtualMarkerSimulation";

vi.mock("../simulatorApi", () => ({ simulatorApi: { injectEvent: vi.fn(async () => ({ accepted: true })) } }));

describe("virtual marker observations", () => {
  beforeEach(() => {
    vi.useFakeTimers(); vi.clearAllMocks();
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  });
  afterEach(() => { vi.useRealTimers(); });

  it("projects course coordinates into the rover frame", () => {
    const position = relativeMarkerPosition({ x: 0, y: -1, yaw: Math.PI / 2 }, courseMarkers[0]);
    expect(position.x).toBeCloseTo(1);
    expect(position.y).toBeCloseTo(0);
  });

  it("updates range from motion and emits loss when hidden", async () => {
    function Scene({ x, hidden }: { x: number; hidden: boolean }) {
      useVirtualMarkerSimulation({ x, y: 0, yaw: 0 }, hidden ? null : courseMarkers[0], true);
      return null;
    }
    const root = createRoot(document.createElement("div"));
    await act(async () => root.render(<Scene x={-1} hidden={false} />));
    expect(simulatorApi.injectEvent).toHaveBeenLastCalledWith("marker", expect.objectContaining({ relative_x_m: 1 }));
    await act(async () => root.render(<Scene x={-.6} hidden={false} />));
    await act(async () => vi.advanceTimersByTimeAsync(450));
    expect(simulatorApi.injectEvent).toHaveBeenLastCalledWith("marker", expect.objectContaining({ relative_x_m: .6 }));
    await act(async () => root.render(<Scene x={-.6} hidden />));
    await act(async () => vi.advanceTimersByTimeAsync(450));
    expect(simulatorApi.injectEvent).toHaveBeenLastCalledWith("marker", { status: "lost", confidence: 0, marker_id: 1 });
    await act(async () => root.unmount());
  });
});
