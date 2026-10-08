import type { MissionDefinition } from "./api";
import { challengerStarterMission } from "./challengerStarter";
import { carryHelperMission, comeHereMission } from "./comeHere";
import { demoScenarioMission } from "./demoScenario";
import { mobileReceptionistMission } from "./mobileReceptionist";

const reservedIntents = new Set(["stop", "wait_here", "report_status", "clarify"]);
const intentPattern = /^[a-z][a-z0-9_]{0,63}$/;

export function createMissionRegistry(
  definitions: readonly MissionDefinition[]
): readonly MissionDefinition[] {
  const ids = new Set<string>();
  const intents = new Set<string>();
  for (const definition of definitions) {
    if (!definition.id.trim()) throw new Error("Mission id must not be empty");
    if (ids.has(definition.id)) throw new Error(`Duplicate mission id: ${definition.id}`);
    ids.add(definition.id);
    const trigger = definition.trigger;
    const intent = trigger?.intent;
    if (!intent) continue;
    if (!intentPattern.test(intent)) throw new Error(`Invalid mission intent: ${intent}`);
    if (trigger.examples.length === 0) {
      throw new Error(`Mission intent requires examples: ${intent}`);
    }
    if (trigger.keywords.length === 0) {
      throw new Error(`Mission intent requires keywords: ${intent}`);
    }
    if (reservedIntents.has(intent)) throw new Error(`Reserved mission intent: ${intent}`);
    if (intents.has(intent)) throw new Error(`Duplicate mission intent: ${intent}`);
    intents.add(intent);
  }
  return Object.freeze([...definitions]);
}

/** Add a mission definition to this list to expose it in the Service App. */
export const missionRegistry = createMissionRegistry([
  challengerStarterMission,
  demoScenarioMission,
  comeHereMission,
  carryHelperMission,
  mobileReceptionistMission
]);

export type {
  InteractionPhase,
  MissionContext,
  MissionDefinition,
  MissionInput,
  MissionProgress,
  MissionTrigger,
  ServiceRover
} from "./api";
export { PersonObservationTimeoutError, waitForPerson } from "./observations";
export { mobileReceptionistMission, runMobileReceptionist } from "./mobileReceptionist";
