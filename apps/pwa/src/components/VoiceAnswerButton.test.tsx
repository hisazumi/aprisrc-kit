import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import type { SpeechRecognitionInstance } from "../speechRecognition";
import { VoiceAnswerButton } from "./VoiceAnswerButton";

it("waits for speech, accepts one answer, and discards late answers after mode changes", async () => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  const instances: Fake[] = [];
  class Fake implements SpeechRecognitionInstance {
    lang = ""; continuous = true; interimResults = true;
    onstart = null; onend = null; onerror = null;
    onresult: SpeechRecognitionInstance["onresult"] = null;
    start = vi.fn(); abort = vi.fn();
    constructor() { instances.push(this); }
  }
  vi.stubGlobal("SpeechRecognition", Fake);
  const host = document.createElement("div"), root = createRoot(host);
  const answer = vi.fn(), status = vi.fn();
  let finish!: () => void;
  const ready = new Promise<void>(resolve => { finish = resolve; });
  const render = (automatic: boolean, key = "first") => root.render(<VoiceAnswerButton key={key}
    disabled={false} automatic={automatic} ready={ready} onAnswer={answer} onStatus={status} />);
  try {
    await act(async () => render(true));
    expect(instances).toHaveLength(0);
    await act(async () => finish());
    expect(instances).toHaveLength(1);
    expect(instances[0].lang).toBe("en-US");
    const result = { results: [[{ transcript: "Yes" }]] };
    await act(async () => { instances[0].onresult?.(result); instances[0].onresult?.(result); });
    expect(answer).toHaveBeenCalledTimes(1);
    await act(async () => render(true, "next"));
    expect(instances).toHaveLength(2);
    await act(async () => render(false, "next"));
    expect(instances[1].abort).toHaveBeenCalled();
    await act(async () => instances[1].onresult?.(result));
    expect(answer).toHaveBeenCalledTimes(1);
    await act(async () => host.querySelector("button")!.click());
    expect(instances).toHaveLength(3);
    await act(async () => root.unmount());
    expect(instances[2].abort).toHaveBeenCalled();
    instances[2].onresult?.(result);
    expect(answer).toHaveBeenCalledTimes(1);
  } finally {
    vi.unstubAllGlobals();
    (globalThis as any).IS_REACT_ACT_ENVIRONMENT = false;
  }
});
