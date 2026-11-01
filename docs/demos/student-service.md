# Student carry service

[日本語](student-service.ja.md)

Edit **one file: `apps/pwa/src/missions/studentCarry.ts`**.
Change the order, conditions, and messages inside `studentCarry.run(service)`; no React changes are needed.
The template is already registered through `App.tsx` → `StudentServicePanel`.
It is not added to the general missionRegistry because this service requires a dedicated screen for user input.
The existing Carry helper remains available for comparison.

## Quick start (Windows PowerShell)

Install Node.js 22.12+ or 24+, Python 3.11+, uv, and Git.
Run these commands from the repository root:

```powershell
npm ci
uv sync --directory apps/server --dev
npm run dev
```

Use the default Simulator without setting environment variables for a physical robot.
Open `http://localhost:5173/lab?sample=student`.
If development certificates have been generated, use `https://localhost:5173` instead.

1. Press **Acquire control** in the **Student service** panel.
2. In Simulator tools, set **Front obstacle state** to **CLEAR** and **Perception health** to **healthy**, then press **Apply state**. Press **Confirm clear path · 30 s** and renew it when it expires. This confirmation supplements the existing server safety checks; it does not replace them.
3. Press **Start service**, then **Start scene** in Virtual person. The rover approaches the virtual person at the initial position.
4. Answer **Yes**, then press **Items are loaded**. Use the Virtual person walking and placement controls to check following, then press **We have arrived** to stop.
5. Also try **No**, **Cancel and stop** while waiting for input, and **Stop scene** during following to simulate target loss.
6. Save your changes to the template. Stop any active run, reload the page, acquire control, confirm a clear path, and start again.

The service screen using real camera observations is `http://localhost:5173/app?service=student`.
Simulator person and obstacle controls stay in `/lab`. Do not acquire control from multiple screens at the same time.

## Editing example and boundaries

```ts
await service.waitForPerson();
await service.approachPerson();
if (await service.ask("Would you like help carrying your belongings?")) {
  await service.waitForLoaded("Place your belongings on the rover.");
  await service.followPerson();
  service.say("We have arrived.");
}
```

- `waitForPerson()`: waits up to 60 seconds for the next person detection. A timeout is a failure.
- `approachPerson()`: approaches using the existing comeHere component. Target loss is a failure.
- `ask(text)`: returns true for **Yes** and false for **No**. Confirms a stop before waiting for input.
- `waitForLoaded(text)`: confirms a stop, then waits for **Items are loaded**.
- `followPerson()`: uses the existing following component. **We have arrived** cancels and joins the running operation and confirms a stop before returning. Target loss is not treated as success.
- `say(text)`: requests display and speech; it does not wait for speech to finish. Speech depends on browser voice and language settings.

The runtime handles input buttons, cancellation on control loss, disconnect, emergency stop, page hiding or unmounting, target loss, and final stop confirmation. A new run cannot start until the previous run finishes. A failed stop confirmation is not reported as completion.

Motion uses the high-level ServiceRover interface. Command TTL, speed limits, ownership, front obstacle checks, and latched E-stop are preserved. Person selection and observation freshness follow the existing approach/follow contracts. The service does not authenticate a person's identity or detect luggage; **Items are loaded** is the user's confirmation.

Runtime files are `service/studentService.ts` and `components/StudentServicePanel.tsx`. This implementation does not add a general framework, voice input, unloading detection, or multiple-person identification.

## Verification scope

Automated tests use the existing approach/follow components and cover normal completion, refusal, cancellation, target loss, stop confirmation failure, and screen input. The Simulator browser flow has been checked through approach, consent, loading confirmation, following, arrival, and confirmed stop. Physical hardware, Windows startup, four simultaneous robots, physical network loss, and the new screen on a smartphone remain unverified. Existing hardware records are not evidence that this new API has been tested on hardware.
