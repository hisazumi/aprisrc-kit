import { defineMission, type ServiceRover } from "./api";

export async function runDemoScenario(rover: ServiceRover, signal?: AbortSignal): Promise<void> {
  signal?.throwIfAborted();
  await rover.move(0.40);
  signal?.throwIfAborted();
  await rover.turn(90);
  signal?.throwIfAborted();
  await rover.move(0.25);
}

export const demoScenarioMission = defineMission({
  id: "move-and-turn-demo",
  title: "Move and turn demo",
  description: "A minimal service mission composed only from high-level motion primitives.",
  runningDetail: "Forward 0.40 m → left 90° → forward 0.25 m",
  script: [
    "await rover.move(0.40)",
    "await rover.turn(90)",
    "await rover.move(0.25)"
  ],
  async run({ rover, signal }) {
    await runDemoScenario(rover, signal);
  }
});
