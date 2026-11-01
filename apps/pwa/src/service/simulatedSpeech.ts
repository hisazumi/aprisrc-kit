export function normalizedSpeech(text: string): string {
  return text.trim().toLocaleLowerCase().replace(/[.!?。！？]+$/u, "").trim();
}
export function spokenChoice(text: string, choices: readonly string[]): string | undefined {
  const value = normalizedSpeech(text);
  const aliases: Record<string, string> = { "はい": "yes", "いいえ": "no" };
  return choices.find(choice => normalizedSpeech(choice) === (aliases[value] ?? value));
}
