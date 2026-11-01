import type { Pose } from "../protocol";
import type { VirtualPersonTarget } from "./virtualPerson";

export type SceneTrigger = { type: "manual" } | { type: "delay"; seconds: number };
export interface SceneStep {
  action: "walk" | "stand" | "disappear";
  trigger: SceneTrigger;
  points: VirtualPersonTarget[];
  speedMps: number;
}
export interface StudentScene {
  version: 1;
  name: string;
  rover: Pose;
  person: VirtualPersonTarget;
  steps: SceneStep[];
  checks: string[];
}

const walk = (x: number, y: number, trigger: SceneTrigger = { type: "manual" }): SceneStep => ({
  action: "walk", trigger, points: [{ x, y }], speedMps: 0.1
});
export const studentScenes: StudentScene[] = [
  { version: 1, name: "Walk and stop", rover: { x: 0, y: 0, yaw: 0 }, person: { x: 1.35, y: 0 },
    steps: [walk(2, 0)], checks: ["Approaches and asks before following", "Follows the walking person", "Stops at a safe distance"] },
  { version: 1, name: "Wait in front", rover: { x: 0, y: 0, yaw: 0 }, person: { x: 1.35, y: 0 },
    steps: [], checks: ["Approaches the person", "Accepts Yes and No without moving while awaiting input"] },
  { version: 1, name: "Enter from outside view", rover: { x: 0, y: 0, yaw: 0 }, person: { x: 1.35, y: 1.2 },
    steps: [walk(1.35, 0, { type: "delay", seconds: 2 }), walk(2, 0)],
    checks: ["Waits while the person is outside view", "Detects the entering person"] },
  { version: 1, name: "Lose the person", rover: { x: 0, y: 0, yaw: 0 }, person: { x: 1.35, y: 0 },
    steps: [walk(2, 0), { action: "disappear", trigger: { type: "manual" }, points: [], speedMps: 0.1 }],
    checks: ["Stops when the person disappears", "Does not report successful arrival on target loss"] }
];

/** Validate imported files before they can alter the simulation. Coordinates are world metres. */
export function parseStudentScene(input: unknown): StudentScene {
  const object = (value: unknown): Record<string, unknown> => {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected an object");
    return value as Record<string, unknown>;
  };
  const number = (value: unknown, min: number, max: number) => {
    if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
      throw new Error(`Expected a number between ${min} and ${max}`);
    }
    return value;
  };
  const text = (value: unknown) => {
    if (typeof value !== "string" || !value.trim() || value.length > 300) throw new Error("Expected a label of 1-300 characters");
    return value;
  };
  const point = (value: unknown) => { const p = object(value); return { x: number(p.x, -10, 10), y: number(p.y, -10, 10) }; };
  const scene = object(input), rover = object(scene.rover);
  if (scene.version !== 1) throw new Error("Unsupported scene version");
  if (!Array.isArray(scene.steps) || scene.steps.length > 20) throw new Error("Use at most 20 steps");
  if (!Array.isArray(scene.checks) || scene.checks.length > 20) throw new Error("Use at most 20 checks");
  const steps = scene.steps.map((value): SceneStep => {
    const step = object(value), trigger = object(step.trigger);
    if (!["walk", "stand", "disappear"].includes(String(step.action))) throw new Error("Unknown scene action");
    if (trigger.type !== "manual" && trigger.type !== "delay") throw new Error("Unknown start condition");
    if (!Array.isArray(step.points) || step.points.length > 20 || (step.action === "walk" && !step.points.length)) throw new Error("Walking requires 1-20 waypoints");
    return {
      action: step.action as SceneStep["action"],
      trigger: trigger.type === "manual" ? { type: "manual" } : { type: "delay", seconds: number(trigger.seconds, 0, 120) },
      points: step.points.map(point), speedMps: number(step.speedMps, 0.01, 0.5)
    };
  });
  return { version: 1, name: text(scene.name), rover: { ...point(rover), yaw: number(rover.yaw, -Math.PI, Math.PI) },
    person: point(scene.person), steps, checks: scene.checks.map(text) };
}

export interface SceneFrame {
  person: VirtualPersonTarget;
  visible: boolean;
  index: number;
  phase: "waiting" | "walking" | "complete";
  manual: boolean;
}

/** A deterministic, sequential runner; time is supplied by the caller for testing. */
export class StudentSceneRunner {
  private index = 0;
  private started: number | null = null;
  private readyAt: number;
  private origin: VirtualPersonTarget;
  private person: VirtualPersonTarget;
  private visible = true;
  constructor(private scene: StudentScene, now: number) {
    this.person = { ...scene.person }; this.origin = { ...scene.person }; this.readyAt = now;
  }
  next(now: number): SceneFrame {
    this.update(now);
    if (this.started === null && this.scene.steps[this.index]?.trigger.type === "manual") this.started = now;
    return this.update(now);
  }
  update(now: number): SceneFrame {
    while (this.index < this.scene.steps.length) {
      const step = this.scene.steps[this.index];
      if (this.started === null) {
        if (step.trigger.type === "manual" || now < this.readyAt + step.trigger.seconds) break;
        this.started = this.readyAt + step.trigger.seconds;
      }
      if (step.action === "walk") {
        this.visible = true;
        let remaining = Math.max(0, now - this.started) * step.speedMps;
        let previous = this.origin;
        let distance = 0;
        let walking = false;
        for (const point of step.points) {
          const length = Math.hypot(point.x - previous.x, point.y - previous.y);
          distance += length;
          if (remaining < length) {
            this.person = { x: previous.x + (point.x - previous.x) * remaining / length,
              y: previous.y + (point.y - previous.y) * remaining / length };
            walking = true; break;
          }
          remaining -= length; previous = point; this.person = { ...point };
        }
        if (walking) break;
        this.readyAt = this.started + distance / step.speedMps;
      } else {
        this.visible = step.action !== "disappear";
        this.readyAt = this.started;
      }
      this.origin = { ...this.person }; this.started = null; this.index += 1;
    }
    return { person: { ...this.person }, visible: this.visible, index: this.index,
      phase: this.index === this.scene.steps.length ? "complete" : this.started === null ? "waiting" : "walking",
      manual: this.started === null && this.scene.steps[this.index]?.trigger.type === "manual" };
  }
}
