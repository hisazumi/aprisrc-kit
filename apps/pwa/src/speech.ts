interface VoiceCandidate {
  name: string;
  lang: string;
  default: boolean;
  localService: boolean;
}

interface VoiceSource<T extends VoiceCandidate> {
  getVoices: () => T[];
  addEventListener: (type: "voiceschanged", listener: () => void) => void;
  removeEventListener: (type: "voiceschanged", listener: () => void) => void;
}

const preferredEnglishVoices = [
  "Samantha",
  "Ava",
  "Allison",
  "Daniel",
  "Karen",
  "Moira"
];

export function selectEnglishVoice<T extends VoiceCandidate>(
  voices: readonly T[]
): T | undefined {
  const englishVoices = voices.filter((voice) =>
    voice.lang.toLowerCase().startsWith("en")
  );
  for (const preferredName of preferredEnglishVoices) {
    const match = englishVoices.find((voice) =>
      voice.name === preferredName || voice.name.startsWith(`${preferredName} (`)
    );
    if (match) return match;
  }
  return englishVoices.find((voice) => voice.default)
    ?? englishVoices.find((voice) => voice.localService)
    ?? englishVoices[0];
}

export function waitForEnglishVoice<T extends VoiceCandidate>(
  source: VoiceSource<T>,
  timeoutMs = 1500
): Promise<T | undefined> {
  const available = selectEnglishVoice(source.getVoices());
  if (available) return Promise.resolve(available);

  return new Promise((resolve) => {
    let settled = false;
    const finish = (voice: T | undefined) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      source.removeEventListener("voiceschanged", handleVoicesChanged);
      resolve(voice);
    };
    const handleVoicesChanged = () => {
      const voice = selectEnglishVoice(source.getVoices());
      if (voice) finish(voice);
    };
    const timeout = setTimeout(
      () => finish(selectEnglishVoice(source.getVoices())),
      timeoutMs
    );
    source.addEventListener("voiceschanged", handleVoicesChanged);
  });
}

let latestSpeechRequest = 0;

export function speakEnglish(text: string): void {
  if (
    typeof window === "undefined"
    || !("speechSynthesis" in window)
    || typeof SpeechSynthesisUtterance === "undefined"
  ) return;

  const request = ++latestSpeechRequest;
  const synthesis = window.speechSynthesis;
  synthesis.cancel();
  void waitForEnglishVoice(synthesis).then((voice) => {
    if (request !== latestSpeechRequest || !voice) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.rate = 0.96;
    utterance.pitch = 1;
    utterance.voice = voice;
    synthesis.speak(utterance);
  });
}
