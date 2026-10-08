import type { PersonEvent } from "../protocol";
import {
  defineMission,
  type InteractionPhase,
  type MissionProgress,
  type ServiceRover
} from "./api";

export type ComeHerePhase = InteractionPhase;

export type ComeHereOutcome = "arrived" | "lost";

export type ComeHereUpdate = MissionProgress;

interface ComeHereOptions {
  onUpdate?: (update: ComeHereUpdate) => void;
  observationTimeoutMs?: number;
  maximumSteps?: number;
}

interface FollowMeOptions {
  onUpdate?: (update: ComeHereUpdate) => void;
  observationTimeoutMs?: number;
  holdWidth?: number;
  resumeWidth?: number;
  followDistance?: "near" | "normal" | "far";
}

const SIMULATED_ARRIVAL_WIDTH = 0.36;
const CAMERA_ARRIVAL_WIDTH = 0.65;
const SIMULATED_CENTER_TOLERANCE = 0.09;
const CAMERA_CENTER_TOLERANCE = 0.16;
const MAX_TURN_DEG = 12;
const MOVE_STEP_M = 0.08;
const MOVE_SPEED_MPS = 0.05;
const TURN_SPEED_RAD_S = 0.35;
const FOLLOW_HOLD_WIDTH = 0.36;
const FOLLOW_RESUME_WIDTH = 0.31;
const FOLLOW_MOVE_STEP_M = 0.1;
const FOLLOW_SPEED_MPS = 0.1;
const FOLLOW_DISTANCE_WIDTHS = {
  near: { hold: 0.44, resume: 0.38 },
  normal: { hold: FOLLOW_HOLD_WIDTH, resume: FOLLOW_RESUME_WIDTH },
  far: { hold: 0.29, resume: 0.25 }
} as const;
const CAMERA_FOLLOW_DISTANCE_WIDTHS = {
  near: { hold: 0.78, resume: 0.68 },
  normal: { hold: 0.65, resume: 0.52 },
  far: { hold: 0.52, resume: 0.42 }
} as const;

export const comeHereMission = defineMission({
  id: "come-here",
  title: "Come to me",
  description: "Find the visible person, align with them, and approach.",
  runningDetail: "Aligning with the person and approaching",
  script: [
    "const person = await observations.next()",
    "if (personIsOffCentre(person)) await rover.turn(bearing)",
    "else if (personIsFar(person)) await rover.move(0.08)",
    "else await rover.stop()"
  ],
  trigger: {
    intent: "come_here",
    description: "Approach the person who is currently visible to the rover.",
    examples: ["こっちに来て", "私のところまで来て", "Come here", "Come to me"],
    keywords: ["こっち", "来て", "きて", "come here", "come to me"],
    response: "Okay. I am coming."
  },
  async run({ rover, signal, report, say }) {
    const outcome = await runComeHere(rover, signal, { onUpdate: report });
    say(outcome === "arrived" ? "I am here." : "I lost sight of you. Stopping.");
  }
});

export const carryHelperMission = defineMission({
  id: "carry-helper",
  title: "Carry helper",
  description: "Follow a visible person while they lead the rover to a destination.",
  runningDetail: "Following the person at a safe distance",
  script: [
    "const person = await observations.next()",
    "if (person.status === 'lost') await rover.stop()",
    "else if (personIsOffCentre(person)) await rover.turn(bearing)",
    "else if (personIsFar(person)) await rover.move(0.10)",
    "else await rover.stop()"
  ],
  trigger: {
    intent: "follow_person",
    description: "Follow the person while helping them carry or transport something.",
    examples: [
      "荷物を運ぶのを手伝って",
      "机までついてきて",
      "Help me carry this",
      "Follow me"
    ],
    keywords: ["運ん", "手伝って", "ついて", "carry", "bring", "follow", "help me with"],
    response: "Okay. I will follow you."
  },
  async run({ rover, signal, report, say }, input) {
    const distance = input?.followDistance ?? "normal";
    await runFollowMe(rover, signal, {
      onUpdate: report,
      followDistance: distance
    });
    say("I lost sight of you. Stopping.");
  }
});

export async function runComeHere(
  rover: ServiceRover,
  signal: AbortSignal,
  options: ComeHereOptions = {}
): Promise<ComeHereOutcome> {
  const observationTimeoutMs = options.observationTimeoutMs ?? 1800;
  const maximumSteps = options.maximumSteps ?? 30;
  const update = options.onUpdate ?? (() => undefined);
  const observations = new PersonObservationFeed(rover, observationTimeoutMs);

  update({ phase: "acquiring", detail: "Looking for you" });
  try {
    for (let step = 0; step < maximumSteps; step += 1) {
      signal.throwIfAborted();
      let person: Readonly<PersonEvent>;
      try {
        person = await observations.next(signal, observationTimeoutMs);
      } catch (error) {
        if (error instanceof PersonObservationTimeoutError) {
          await rover.stop("person observation stale");
          update({ phase: "lost", detail: "I lost sight of you" });
          return "lost";
        }
        throw error;
      }
      if (person.status === "lost") {
        await rover.stop("person lost");
        update({ phase: "lost", detail: "I lost sight of you", person });
        return "lost";
      }

      const centerX = person.centerX;
      const width = person.width;
      const bearingDeg = person.bearingDeg;
      if (centerX === undefined || width === undefined || bearingDeg === undefined) {
        continue;
      }
      if (width >= arrivalWidth(person)) {
        await rover.stop("person reached");
        update({ phase: "arrived", detail: "I am here", person });
        return "arrived";
      }

      if (Math.abs(centerX - 0.5) > centerTolerance(person)) {
        const turnDeg = clamp(bearingDeg, -MAX_TURN_DEG, MAX_TURN_DEG);
        update({
          phase: "aligning",
          detail: turnDeg >= 0 ? "Turning left toward you" : "Turning right toward you",
          person
        });
        await rover.turn(turnDeg, TURN_SPEED_RAD_S);
      } else {
        if (!forwardPathIsClear(rover)) {
          update({
            phase: "approaching",
            detail: "Tap Allow movement to let me approach",
            person
          });
          continue;
        }
        update({ phase: "approaching", detail: "Coming closer", person });
        await rover.move(MOVE_STEP_M, MOVE_SPEED_MPS);
      }
    }
    throw new Error("Approach step limit reached");
  } catch (error) {
    if (observations.unsafeReason) {
      await stopAfterFailure(rover);
      update({ phase: "lost", detail: "I lost sight of you" });
      return "lost";
    }
    await stopAfterFailure(rover);
    throw error;
  } finally {
    observations.close();
  }
}

export async function runFollowMe(
  rover: ServiceRover,
  signal: AbortSignal,
  options: FollowMeOptions = {}
): Promise<"lost"> {
  const observationTimeoutMs = options.observationTimeoutMs ?? 1800;
  const update = options.onUpdate ?? (() => undefined);
  const observations = new PersonObservationFeed(rover, observationTimeoutMs);
  const followDistance = options.followDistance ?? "normal";
  let holdingDistance = false;

  update({ phase: "acquiring", detail: "Looking for you" });
  try {
    while (true) {
      signal.throwIfAborted();
      let person: Readonly<PersonEvent>;
      try {
        person = await observations.next(signal, observationTimeoutMs);
      } catch (error) {
        if (error instanceof PersonObservationTimeoutError) {
          await rover.stop("person observation stale");
          update({ phase: "lost", detail: "I lost sight of you" });
          return "lost";
        }
        throw error;
      }
      if (person.status === "lost") {
        await rover.stop("person lost");
        update({ phase: "lost", detail: "I lost sight of you", person });
        return "lost";
      }

      const centerX = person.centerX;
      const width = person.width;
      const bearingDeg = person.bearingDeg;
      if (centerX === undefined || width === undefined || bearingDeg === undefined) continue;
      const sourceWidths = followWidths(person, followDistance);
      const holdWidth = options.holdWidth ?? sourceWidths.hold;
      const resumeWidth = options.resumeWidth ?? sourceWidths.resume;

      if (Math.abs(centerX - 0.5) > centerTolerance(person)) {
        const turnDeg = clamp(bearingDeg, -MAX_TURN_DEG, MAX_TURN_DEG);
        update({
          phase: "aligning",
          detail: turnDeg >= 0 ? "Turning left to follow you" : "Turning right to follow you",
          person
        });
        await rover.turn(turnDeg, TURN_SPEED_RAD_S);
        continue;
      }

      if (width >= holdWidth) {
        if (!holdingDistance) await rover.stop("follow distance reached");
        holdingDistance = true;
      } else if (width <= resumeWidth) {
        holdingDistance = false;
      }

      if (holdingDistance) {
        update({ phase: "following", detail: "Keeping a safe distance", person });
      } else {
        if (!forwardPathIsClear(rover)) {
          update({
            phase: "following",
            detail: "Tap Allow movement to let me follow",
            person
          });
          continue;
        }
        update({ phase: "following", detail: "Following you", person });
        await rover.move(FOLLOW_MOVE_STEP_M, FOLLOW_SPEED_MPS);
      }
    }
  } catch (error) {
    if (observations.unsafeReason) {
      await stopAfterFailure(rover, "follow-me mission stopped");
      update({ phase: "lost", detail: "I lost sight of you" });
      return "lost";
    }
    await stopAfterFailure(rover, "follow-me mission stopped");
    throw error;
  } finally {
    observations.close();
  }
}

function arrivalWidth(person: Readonly<PersonEvent>): number {
  return person.source === "camera" || person.source === "recorded"
    ? CAMERA_ARRIVAL_WIDTH
    : SIMULATED_ARRIVAL_WIDTH;
}

function centerTolerance(person: Readonly<PersonEvent>): number {
  return person.source === "camera" || person.source === "recorded"
    ? CAMERA_CENTER_TOLERANCE
    : SIMULATED_CENTER_TOLERANCE;
}

function followWidths(
  person: Readonly<PersonEvent>,
  distance: "near" | "normal" | "far"
): { hold: number; resume: number } {
  return person.source === "camera" || person.source === "recorded"
    ? CAMERA_FOLLOW_DISTANCE_WIDTHS[distance]
    : FOLLOW_DISTANCE_WIDTHS[distance];
}

function forwardPathIsClear(rover: ServiceRover): boolean {
  const snapshot = rover.getFrontObstacle?.();
  return snapshot === undefined || snapshot?.state === "CLEAR";
}

class PersonObservationTimeoutError extends Error {}

interface WaitingObservation {
  resolve: (event: Readonly<PersonEvent>) => void;
  reject: (error: unknown) => void;
  signal: AbortSignal;
  abort: () => void;
}

class PersonObservationFeed {
  private latest: Readonly<PersonEvent> | null = null;
  private waiting: WaitingObservation | null = null;
  private readonly unsubscribe: () => void;
  private staleTimer: number | undefined;
  unsafeReason: "lost" | "stale" | null = null;

  constructor(rover: ServiceRover, staleAfterMs: number) {
    const stopUnsafeMotion = (reason: "lost" | "stale") => {
      if (this.unsafeReason) return;
      this.unsafeReason = reason;
      void rover.stop(
        reason === "lost" ? "person lost" : "person observation stale"
      ).catch(() => undefined);
      if (reason === "stale") this.rejectWaiting(new PersonObservationTimeoutError());
    };
    const armStaleTimer = () => {
      if (this.staleTimer !== undefined) window.clearTimeout(this.staleTimer);
      this.staleTimer = window.setTimeout(() => stopUnsafeMotion("stale"), staleAfterMs);
    };

    this.unsubscribe = rover.onPerson((event) => {
      if (event.status === "lost") {
        if (this.staleTimer !== undefined) window.clearTimeout(this.staleTimer);
        stopUnsafeMotion("lost");
      } else {
        armStaleTimer();
      }
      if (this.waiting) {
        const waiting = this.takeWaiting();
        waiting?.resolve(event);
      } else {
        this.latest = event;
      }
    });
    armStaleTimer();
  }

  next(signal: AbortSignal, _timeoutMs: number): Promise<Readonly<PersonEvent>> {
    if (this.latest) {
      const event = this.latest;
      this.latest = null;
      return Promise.resolve(event);
    }
    if (this.unsafeReason === "stale") {
      return Promise.reject(new PersonObservationTimeoutError());
    }
    return new Promise((resolve, reject) => {
      const abort = () => {
        const waiting = this.takeWaiting();
        waiting?.reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      };
      this.waiting = { resolve, reject, signal, abort };
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) abort();
    });
  }

  close(): void {
    this.unsubscribe();
    if (this.staleTimer !== undefined) window.clearTimeout(this.staleTimer);
    this.rejectWaiting(new DOMException("Observation feed closed", "AbortError"));
    this.latest = null;
  }

  private takeWaiting(): WaitingObservation | null {
    const waiting = this.waiting;
    this.waiting = null;
    if (waiting) waiting.signal.removeEventListener("abort", waiting.abort);
    return waiting;
  }

  private rejectWaiting(error: unknown): void {
    this.takeWaiting()?.reject(error);
  }
}

async function stopAfterFailure(
  rover: ServiceRover,
  reason = "come-here mission stopped"
): Promise<void> {
  try {
    await rover.stop(reason);
  } catch {
    // The Local Server or E-stop may already have stopped the rover.
  }
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
