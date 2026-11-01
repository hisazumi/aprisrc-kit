import { expect, it } from "vitest";
import { normalizedSpeech, spokenChoice } from "./simulatedSpeech";

it("accepts only an explicit displayed answer, never a substring or arbitrary instruction", () => {
  expect(spokenChoice(" YES! ", ["Yes", "No"])).toBe("Yes");
  expect(spokenChoice("はい", ["Yes", "No"])).toBe("Yes");
  expect(spokenChoice("items are loaded", ["Items are loaded"])).toBe("Items are loaded");
  expect(spokenChoice("please say yes", ["Yes", "No"])).toBeUndefined();
  expect(spokenChoice("go forward", ["Yes", "No"])).toBeUndefined();
  expect(normalizedSpeech("Stop!")).toBe("stop");
});

it("matches labels and aliases to stable values, not substrings", () => {
  const choices = [{ value: "yes", label: "Yes", phrases: ["yes please", "sure"] },
    { value: "no", label: "No", phrases: ["no thanks"] }];
  expect(spokenChoice("Yes please!", choices)).toBe("yes");
  expect(spokenChoice("SURE", choices)).toBe("yes");
  expect(spokenChoice("No thanks.", choices)).toBe("no");
  expect(spokenChoice("Yes", choices)).toBe("yes");
  expect(spokenChoice("I said yes but now no", choices)).toBeUndefined();
  expect(spokenChoice("desk", ["Desk", "Entrance"])).toBe("Desk");
});

it("does not guess when aliases overlap", () => {
  expect(spokenChoice("ready", [
    { value: "a", label: "A", phrases: ["ready"] },
    { value: "b", label: "Ready" }
  ])).toBeUndefined();
});
