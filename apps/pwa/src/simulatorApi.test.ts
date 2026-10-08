import { afterEach, describe, expect, it, vi } from "vitest";

import { simulatorApi } from "./simulatorApi";

const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
  vi.restoreAllMocks();
});

describe("simulatorApi", () => {
  it("serializes a manual scenario event", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ type: "scenario_event" })
    }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await simulatorApi.injectEvent("marker", { marker_id: 1 });

    expect(fetchMock).toHaveBeenCalledWith("/api/simulator/events", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ kind: "marker", payload: { marker_id: 1 } })
    }));
  });

  it("reports a Local Server error detail", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 409,
      json: async () => ({ detail: "No scenario inputs are available to replay" })
    })) as unknown as typeof fetch;

    await expect(simulatorApi.replayInputs()).rejects.toThrow(
      "No scenario inputs are available to replay"
    );
  });

  it("serializes independent front-obstacle state and health", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ front_obstacle: { state: "BLOCKED" } })
    }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await simulatorApi.setFrontObstacle("BLOCKED", "healthy");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/simulator/front-obstacle",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          state: "BLOCKED",
          perception_health: "healthy",
          source: "manual",
          confidence: 1
        })
      })
    );
  });
});
