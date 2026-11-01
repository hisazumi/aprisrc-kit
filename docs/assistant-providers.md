# Assistant providers

[日本語](assistant-providers.ja.md)

Use **Human interaction** under Playground **Advanced controls**, with the shared service
stopped for standalone commands. Service and Playground questions first match local
labels/aliases, then send unmatched microphone or **Person says** replies to
`POST /api/assistant/answer`. With Gemini or OpenAI configured, this classifies the
reply using the current question and choices; it never executes a motor command.
Rules mode, cloud failure, and ambiguous replies leave the question unanswered.
Button answers remain available. Late results after answering or stopping are ignored.
The question, choice labels/aliases, and reply text are sent to the selected provider.

In Voice conversation mode, cloud replies distinguish an answer, acknowledgement,
and clarification. "OK" can accept a Yes/No offer, but during arrival waiting it
can simply acknowledge the instructions. Acknowledgements leave the question and
motion behavior unchanged and re-arm the microphone. Clarifications are spoken,
then listening resumes. This continuation is cloud-only; rules, API failures,
silence and microphone errors require a manual retry. Overlapping local aliases
never go to the cloud: select a button to resolve the ambiguity. Stopping or
answering cancels pending listening, including after a clarification finishes.

The browser transcribes speech; the server interprets the resulting text. Select
the interpreter with `APRIS_ASSISTANT_PROVIDER=rules|openai|gemini` in the server
environment, then restart the server while the rover is stopped.

| Setting | Key | Model |
| --- | --- | --- |
| `rules` | None; existing keys are ignored | No model, no external LLM request |
| `openai` | `OPENAI_API_KEY` | `APRIS_ASSISTANT_MODEL`; existing default `gpt-6-luna` |
| `gemini` | `GEMINI_API_KEY` | `APRIS_ASSISTANT_MODEL`; default `gemini-3.8-flash` |

Explicit cloud selection without its key fails configuration rather than silently
selecting another provider. For compatibility, omitting the provider retains the
old behavior: OpenAI when `OPENAI_API_KEY` is set, otherwise rules. A Gemini key
alone does not enable external transmission. Prefer explicit selection in new setups.
Choose a model available to your API account; the configured name does not establish
availability or successful credentials. Gemini model IDs exclude a `models/` prefix.

Example (supply the key privately in the server environment, never in browser code):

```sh
export APRIS_ASSISTANT_PROVIDER=gemini
export APRIS_ASSISTANT_MODEL=gemini-3.8-flash
# Set GEMINI_API_KEY through your private environment/secret mechanism.
```

This is the Gemini Developer API `generateContent` integration, not Vertex AI.
It uses a JSON response schema and the `x-goog-api-key` header. See Google's
[REST API](https://ai.google.dev/api/generate-content) and
[structured output guide](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
OpenAI continues to use the existing Responses transport. No new SDK is required.

## Verification and safety

`GET /api/assistant/status` reports configured mode and model without keys.
`POST /api/assistant/interpret` returns `source: rules|openai|gemini`; this is the
actual decision source, including fallback, rather than merely the selected mode.
Try interpretation with a text request before running a service. Interpretation
alone does not publish motor commands, but a running service may act on its result.

Stop keywords are handled locally before any LLM request. Cloud results must pass
the same decision schema and registered-action allowlist. Blocked, truncated,
malformed, failed or unregistered Gemini results fall back to the existing local
rules. A matching local keyword can still select an application action; fallback
is not synonymous with stopping. Unknown requests become `clarify`.
Control ownership, motion leases, clearance and stopping remain separate checks.
Voice recognition is not an emergency-stop mechanism.

Only text and registered intent descriptions/examples are sent to the selected
provider; this integration does not send camera frames or audio. Provider data
handling and billing apply. Tests use mocked responses: actual cloud credentials,
latency and physical service behavior are not validated by these tests.
