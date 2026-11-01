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
