export interface ServiceChoice {
  value: string;
  label: string;
  phrases?: readonly string[];
}
export type ServiceChoiceInput = string | ServiceChoice;
export function choiceOption(choice: ServiceChoiceInput): ServiceChoice {
  return typeof choice === "string" ? { value: choice, label: choice } : choice;
}
export function normalizedSpeech(text: string): string {
  return text.trim().toLocaleLowerCase().replace(/[.!?。！？]+$/u, "").trim();
}
export function spokenChoice(text: string, choices: readonly ServiceChoiceInput[]): string | undefined {
  const value = normalizedSpeech(text);
  const aliases: Record<string, string> = { "はい": "yes", "いいえ": "no" };
  const matches = choices.map(choiceOption).filter(choice =>
    [choice.label, ...(choice.phrases ?? [])].some(phrase => normalizedSpeech(phrase) === (aliases[value] ?? value)));
  return matches.length === 1 ? matches[0].value : undefined;
}
