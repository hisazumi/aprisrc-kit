import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { assistantApi } from "../assistantApi";
import { serviceConfig } from "../config";
import type { MissionDefinition, ServiceRover } from "../missions";
import { HumanInteractionPanel } from "./HumanInteractionPanel";

class FakeSpeechRecognition {
  static latest: FakeSpeechRecognition | undefined;

  lang = "";
  continuous = true;
  interimResults = true;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onresult: ((event: { results: ArrayLike<{ readonly [index: number]: { transcript: string } }> }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  abort = vi.fn();

  constructor() {
    FakeSpeechRecognition.latest = this;
  }

  start(): void {
    this.onstart?.();
  }
}

describe("HumanInteractionPanel", () => {
  const originalRecognition = Object.getOwnPropertyDescriptor(window, "webkitSpeechRecognition");

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: FakeSpeechRecognition
    });
  });

  afterEach(() => {
    if (originalRecognition) {
      Object.defineProperty(window, "webkitSpeechRecognition", originalRecognition);
    } else {
      Reflect.deleteProperty(window, "webkitSpeechRecognition");
    }
    FakeSpeechRecognition.latest = undefined;
    vi.restoreAllMocks();
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = false;
  });

  it("routes a spoken transcript through the bounded assistant intent", async () => {
    const stop = vi.fn(async () => undefined);
    const rover: ServiceRover = {
      move: async () => undefined,
      turn: async () => undefined,
      stop,
      getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
      onPose: () => () => undefined,
      onPerson: () => () => undefined,
      onMarker: () => () => undefined
    };
    vi.spyOn(assistantApi, "interpret").mockResolvedValue({
      action: "stop",
      destination: null,
      follow_distance: "normal",
      response: "Stopping.",
      source: "rules",
      model: null
    });

    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(
      <HumanInteractionPanel
        disabled={false}
        rover={rover}
        missions={[]}
        config={serviceConfig}
        cancelMotion={() => true}
      />
    ));

    const speak = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Speak");
    await act(async () => speak?.click());

    const recognition = FakeSpeechRecognition.latest;
    expect(recognition?.lang).toBe("ja-JP");
    await act(async () => {
      recognition?.onresult?.({ results: [[{ transcript: "止まって" }]] });
      recognition?.onend?.();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(assistantApi.interpret).toHaveBeenCalledWith("止まって", []);
    expect(stop).toHaveBeenCalledWith("interaction stopped");
    expect(container.textContent).toContain("Stopping.");

    await act(async () => root.unmount());
  });

  it("dispatches a registered student intent to its mission", async () => {
    const rover: ServiceRover = {
      move: async () => undefined,
      turn: async () => undefined,
      stop: async () => undefined,
      getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
      onPose: () => () => undefined,
      onPerson: () => () => undefined,
      onMarker: () => () => undefined
    };
    const run = vi.fn(async () => undefined);
    const mission: MissionDefinition = {
      id: "carry-helper",
      title: "Carry helper",
      description: "Follow a person",
      runningDetail: "Following",
      script: [],
      trigger: {
        intent: "carry_help",
        description: "Follow a person while helping carry an item.",
        examples: ["荷物を運ぶのを手伝って"],
        keywords: ["運ん", "手伝って"],
        response: "Okay. I will follow you."
      },
      run
    };
    vi.spyOn(assistantApi, "interpret").mockResolvedValue({
      action: "carry_help",
      destination: "desk",
      follow_distance: "normal",
      response: "Okay. I will follow you.",
      source: "rules",
      model: null
    });

    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(
      <HumanInteractionPanel
        disabled={false}
        rover={rover}
        missions={[mission]}
        config={serviceConfig}
        cancelMotion={() => true}
      />
    ));

    const speak = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Speak");
    await act(async () => speak?.click());
    await act(async () => {
      FakeSpeechRecognition.latest?.onresult?.({
        results: [[{ transcript: "荷物を運ぶのを手伝って" }]]
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(assistantApi.interpret).toHaveBeenCalledWith(
      "荷物を運ぶのを手伝って",
      [expect.objectContaining({ id: "carry_help" })]
    );
    expect(run).toHaveBeenCalledWith(
      expect.objectContaining({ rover, config: serviceConfig }),
      {
        intent: "carry_help",
        destination: "desk",
        followDistance: "normal"
      }
    );

    await act(async () => root.unmount());
  });

  it("starts the receptionist mission for the entrance from the guide button", async () => {
    const rover: ServiceRover = {
      move: async () => undefined,
      turn: async () => undefined,
      stop: async () => undefined,
      getPose: async () => ({ x: 0, y: 0, yaw: 0 }),
      onPose: () => () => undefined,
      onPerson: () => () => undefined,
      onMarker: () => () => undefined
    };
    const run = vi.fn(async () => undefined);
    const mission: MissionDefinition = {
      id: "mobile-receptionist",
      title: "Mobile receptionist",
      description: "Guide a visitor",
      runningDetail: "Guiding",
      script: [],
      trigger: {
        intent: "guide_visitor",
        description: "Guide a visitor to a marker.",
        examples: ["Guide me"],
        keywords: ["guide"],
        response: "Okay."
      },
      run
    };

    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(
      <HumanInteractionPanel
        disabled={false}
        rover={rover}
        missions={[mission]}
        config={serviceConfig}
        cancelMotion={() => true}
      />
    ));

    const guide = [...container.querySelectorAll("button")]
      .find((button) => button.textContent === "Guide me");
    await act(async () => {
      guide?.click();
      await Promise.resolve();
    });

    expect(run).toHaveBeenCalledWith(
      expect.objectContaining({ rover, config: serviceConfig }),
      {
        intent: "guide_visitor",
        destination: "entrance",
        followDistance: "normal"
      }
    );

    await act(async () => root.unmount());
  });
});
