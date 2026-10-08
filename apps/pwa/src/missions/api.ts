import type { CourseDestination, ServiceConfig } from "../config";
import type { FrontObstacleSnapshot, MarkerEvent, PersonEvent, Pose } from "../protocol";

export type PoseListener = (pose: Readonly<Pose>) => void;
export type PersonListener = (event: Readonly<PersonEvent>) => void;
export type MarkerListener = (event: Readonly<MarkerEvent>) => void;

export type InteractionPhase =
  | "idle"
  | "acquiring"
  | "aligning"
  | "approaching"
  | "following"
  | "arrived"
  | "lost"
  | "waiting"
  | "stopped"
  | "error";

export interface MissionProgress {
  phase: string;
  detail: string;
  person?: Readonly<PersonEvent>;
}

export interface MissionTrigger {
  intent: string;
  description: string;
  examples: readonly string[];
  keywords: readonly string[];
  response: string;
}

export interface MissionInput {
  intent: string;
  destination: CourseDestination | null;
  followDistance: "near" | "normal" | "far";
}

/**
 * Hardware-independent API available to service missions.
 *
 * Motor protocols, control ownership, speed limits and command TTL deliberately
 * stay outside this interface.
 */
export interface ServiceRover {
  move(distanceM: number, speedMps?: number): Promise<void>;
  turn(angleDeg: number, speedRadS?: number): Promise<void>;
  stop(reason?: string): Promise<void>;
  getPose(): Promise<Readonly<Pose>>;
  onPose(listener: PoseListener): () => void;
  onPerson(listener: PersonListener): () => void;
  onMarker(listener: MarkerListener): () => void;
  getFrontObstacle?(): Readonly<FrontObstacleSnapshot> | null;
}

export interface MissionContext {
  rover: ServiceRover;
  config: ServiceConfig;
  signal: AbortSignal;
  report(progress: MissionProgress): void;
  say(text: string): void;
}

export interface MissionDefinition {
  id: string;
  title: string;
  description: string;
  runningDetail: string;
  script: readonly string[];
  trigger?: MissionTrigger;
  run(context: MissionContext, input?: MissionInput): Promise<void>;
}

export function defineMission(definition: MissionDefinition): MissionDefinition {
  return definition;
}
