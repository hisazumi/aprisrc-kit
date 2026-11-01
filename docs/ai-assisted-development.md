# Write service code with an AI assistant

[日本語](ai-assisted-development.ja.md)

## Shared services versus generic missions

Start ordinary service edits in `apps/pwa/src/missions/myService.ts`.
Give the AI that file, `service/studentService.ts`, `service/catalog.ts`, and relevant tests.
The instructions below concern lower-level missions and triggers, available under Playground
**Advanced controls**. Stop the shared service before running a generic mission.
The shared selector is managed by `service/catalog.ts`; mission registration alone does not
add an entry. Shared-panel answers and generic voice/LLM intent execution are separate paths.
See the [quickstart](challenger-quickstart.md) for current operation.


For APRISRC Kit participants using a web chat or a coding assistant. This guide
contains a development workflow, not a workshop assignment. You choose the service.
Start with the [participant setup](challenger-quickstart.md). You still need a
local development environment to apply and test code; a chat response is not a
running service or evidence that it works.

## 1. Describe the service before asking for code

Write down the observation, the condition/state to check, the action, and the
feedback the user should see or hear. Also specify when the service finishes,
what happens when a person or marker disappears, and how to cancel it.

Choose the surface you are changing:

- A reusable mission: normally edit `apps/pwa/src/missions/` and `config/`.
- A dedicated service screen or state machine: include the relevant component
  and its tests, and explicitly agree on that broader scope.
- A hardware connection: separate platform/Adapter work, not a mission change.

Registering a mission exposes it in `/playground`; it does not automatically add it to
the `/service` service flow or create a Playground sample.

## 2. Give the assistant a small, current context bundle

Attach [the AI context memo](ai-service-context.md), the current source files
listed there, and your service requirements. Supply file contents, not just
GitHub links: the assistant may not be able to retrieve links or private files.
Keep filenames visible. When pasting, label each code block with its repository
path. If an import is missing, provide that file when requested.

Record the checkout revision with `git rev-parse HEAD`. Include `git status --short`
and the current contents of relevant modified files: a commit ID alone does not
describe uncommitted work. Never attach `.env`, `.certs`, access tokens, SSH keys,
or unreviewed runtime logs. Remove personal information and credentials from errors.

Do not upload the whole checkout by default. It contains dependencies, generated
files, and possibly private configuration. The context memo has a minimal file list.

## 3. Request a scoped change

Copy and complete this request, then attach the files:

```text
I am developing a service with APRISRC Kit.
Revision: <commit ID>; relevant uncommitted changes: <describe or none>.
Goal and interaction: <what the user experiences>.
Observation -> condition/state -> action -> feedback: <describe>.
Completion, cancellation, and lost-target behavior: <describe>.
Allowed files: <paths>; target screen: </playground or explicitly named component>.
Validation environment: Simulator only.

Read the attached AI context memo and source files first.
Do not invent APIs. Ask for missing files rather than guessing.
Keep the change within the allowed files; explain any necessary scope expansion.
Return the changed file paths and a unified diff (or complete contents for each
small changed file), plus tests and exact verification steps.
Separate checks you actually ran from checks I must run locally.
Do not change transport, safety limits, dependencies, or firmware for this task.
```

For an existing file, a complete replacement must retain unrelated code and registry
entries. Review the diff before applying it. Use a branch/checkpoint so the change
can be reviewed and undone without discarding other work.

## 4. Apply and verify locally

Use the [quickstart](challenger-quickstart.md) to explicitly select Simulator,
then verify `/api/status` reports `adapter_type: simulator` before running a mission.
Use the URL printed by your development server; ports and HTTPS settings can vary.
Do not switch a shared real-robot server just to run your development test.

From the repository root:

```powershell
npm.cmd run typecheck --workspace @apris/pwa
npm.cmd run test --workspace @apris/pwa
npm.cmd run build --workspace @apris/pwa
```

For a narrow change, also identify which existing or new tests exercise the changed
behavior. Then run the mission in `/playground` and check normal completion, cancellation,
lost/stale observations, and repeated execution. Verify the relevant `/service` flow
separately if you changed it. Passing type checks does not prove service behavior;
Simulator success does not validate real camera noise, Wi-Fi, braking, or hardware.
Hardware tests require the operator's setup and explicit permission before motion.

## 5. Send useful feedback to the assistant

Provide the command you ran, the exact error, expected versus observed behavior,
adapter type, and the current changed files. A screenshot helps locate UI problems,
but include text errors too. If nothing moved, report connection, ownership,
E-stop, and observation state; do not ask the assistant to bypass those checks.

Before committing, inspect `git diff` and confirm that no secrets, generated files,
or unrelated changes are included. Record what was actually tested and what remains
unverified. Use [Mission API](mission-api.md), [action registration](adding-actions.md),
and [platform status](platform-status.md) for the corresponding references.
