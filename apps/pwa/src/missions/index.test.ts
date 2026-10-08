import { describe, expect, it } from "vitest";

import { serviceConfig } from "../config";
import type { MissionDefinition } from "./api";
import { createMissionRegistry, missionRegistry } from "./index";

function mission(id: string): MissionDefinition {
  return {
    id,
    title: id,
    description: id,
    runningDetail: id,
    script: [],
    run: async () => undefined
  };
}

describe("missionRegistry", () => {
  it("contains the configured default mission", () => {
    expect(missionRegistry.some(
      (definition) => definition.id === serviceConfig.team.defaultMissionId
    )).toBe(true);
  });

  it("rejects duplicate mission ids", () => {
    expect(() => createMissionRegistry([mission("same"), mission("same")]))
      .toThrow("Duplicate mission id: same");
  });

  it("rejects duplicate and reserved trigger intents", () => {
    const first = mission("first");
    const second = mission("second");
    first.trigger = {
      intent: "carry_help",
      description: "Carry help",
      examples: ["Help me"],
      keywords: ["help"],
      response: "Okay."
    };
    second.trigger = { ...first.trigger };

    expect(() => createMissionRegistry([first, second]))
      .toThrow("Duplicate mission intent: carry_help");

    second.trigger = { ...first.trigger, intent: "stop" };
    expect(() => createMissionRegistry([second]))
      .toThrow("Reserved mission intent: stop");
  });

  it("rejects malformed or incomplete trigger definitions", () => {
    const definition = mission("invalid");
    definition.trigger = {
      intent: "Not Valid",
      description: "Invalid",
      examples: ["example"],
      keywords: ["keyword"],
      response: "Okay."
    };
    expect(() => createMissionRegistry([definition]))
      .toThrow("Invalid mission intent: Not Valid");

    definition.trigger = { ...definition.trigger, intent: "valid", keywords: [] };
    expect(() => createMissionRegistry([definition]))
      .toThrow("Mission intent requires keywords: valid");
  });
});
