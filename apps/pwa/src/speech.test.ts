import { describe, expect, it, vi } from "vitest";

import { selectEnglishVoice, waitForEnglishVoice } from "./speech";

const voice = (
  name: string,
  lang: string,
  options: { default?: boolean; localService?: boolean } = {}
) => ({
  name,
  lang,
  default: options.default ?? false,
  localService: options.localService ?? true
});

describe("selectEnglishVoice", () => {
  it("prefers the natural Samantha voice over the first English voice", () => {
    const voices = [
      voice("Fred", "en-US"),
      voice("Samantha", "en-US"),
      voice("Kyoko", "ja-JP", { default: true })
    ];

    expect(selectEnglishVoice(voices)?.name).toBe("Samantha");
  });

  it("falls back to the default English voice", () => {
    const voices = [
      voice("Novelty", "en-US"),
      voice("System English", "en-GB", { default: true })
    ];

    expect(selectEnglishVoice(voices)?.name).toBe("System English");
  });

  it("waits for the browser voice list instead of using an unvoiced fallback", async () => {
    let voices: ReturnType<typeof voice>[] = [];
    let voicesChanged: (() => void) | undefined;
    const source = {
      getVoices: () => voices,
      addEventListener: vi.fn((_type: "voiceschanged", listener: () => void) => {
        voicesChanged = listener;
      }),
      removeEventListener: vi.fn()
    };
    const selected = waitForEnglishVoice(source);

    voices = [voice("Samantha", "en-US")];
    voicesChanged?.();

    await expect(selected).resolves.toMatchObject({ name: "Samantha" });
    expect(source.removeEventListener).toHaveBeenCalledWith(
      "voiceschanged",
      expect.any(Function)
    );
  });
});
