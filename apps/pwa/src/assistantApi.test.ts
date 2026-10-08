import { afterEach, describe, expect, it, vi } from "vitest";

import { assistantApi } from "./assistantApi";

describe("assistantApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("submits natural language and returns a service intent", async () => {
    const intents = [{
      id: "follow_person",
      description: "Follow a visible person",
      examples: ["Follow me"],
      keywords: ["follow"],
      response: "Okay. I will follow you."
    }];
    const decision = {
      action: "follow_person",
      destination: "desk",
      follow_distance: "normal",
      response: "Okay. I will follow you to the desk.",
      source: "rules",
      model: null
    } as const;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => decision
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(assistantApi.interpret("Help me carry this to the desk", intents))
      .resolves.toEqual(decision);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/assistant/interpret",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ text: "Help me carry this to the desk", intents })
      })
    );
  });
});
