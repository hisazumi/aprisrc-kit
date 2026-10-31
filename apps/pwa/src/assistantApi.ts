export interface AssistantIntentDefinition {
  id: string;
  description: string;
  examples: readonly string[];
  keywords: readonly string[];
  response: string;
}

export interface AssistantDecision {
  action: string;
  destination: "desk" | "kitchen" | "entrance" | null;
  follow_distance: "near" | "normal" | "far";
  response: string;
  source: "rules" | "openai" | "gemini";
  model: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body
      ? { "Content-Type": "application/json", ...init.headers }
      : init?.headers
  });
  const body = await response.json() as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail ?? `Assistant API returned ${response.status}`);
  return body;
}

export const assistantApi = {
  interpret: (text: string, intents: readonly AssistantIntentDefinition[]) => request<AssistantDecision>(
    "/api/assistant/interpret",
    { method: "POST", body: JSON.stringify({ text, intents }) }
  )
};
