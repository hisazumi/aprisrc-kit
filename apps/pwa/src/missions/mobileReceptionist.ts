import type { CourseDestination, CourseMarker, ServiceConfig } from "../config";
import type { MarkerEvent } from "../protocol";
import {
  defineMission,
  type MissionProgress,
  type ServiceRover
} from "./api";
import { waitForPerson } from "./observations";

export type ReceptionistOutcome = "arrived" | "blocked" | "lost" | "not_found";

interface ReceptionistOptions {
  onUpdate?: (progress: MissionProgress) => void;
  observationTimeoutMs?: number;
  searchWaitMs?: number;
  maximumSteps?: number;
}

const DEFAULT_DESTINATION: CourseDestination = "entrance";
const SEARCH_TURN_DEG = 12;
const MAX_ALIGN_TURN_DEG = 15;
const CENTER_TOLERANCE_DEG = 5;
const ARRIVAL_DISTANCE_M = 0.45;
const ARRIVAL_TOLERANCE_M = 0.02;
const MOVE_STEP_M = 0.12;
const MOVE_SPEED_MPS = 0.1;
const TURN_SPEED_RAD_S = 0.35;

export const mobileReceptionistMission = defineMission({
  id: "mobile-receptionist",
  title: "Mobile receptionist",
  description: "Greet a visitor and guide them toward a configured destination marker.",
  runningDetail: "Looking for a visitor and destination marker",
  script: [
    "const visitor = await waitForPerson(rover, signal)",
    "const marker = await destinationObservations.next()",
    "if (offCentre(marker)) await rover.turn(bearing(marker))",
    "else if (far(marker) && pathClear()) await rover.move(0.12)",
    "else await rover.stop()"
  ],
  trigger: {
    intent: "guide_visitor",
    description: "Guide a visible visitor to the requested configured destination marker.",
    examples: [
      "入口まで案内して",
      "机まで連れていって",
      "Guide me to the entrance",
      "Show me the kitchen"
    ],
    keywords: ["案内", "連れて", "guide", "show me", "take me to"],
    response: "Okay. Let me find you and the destination marker."
  },
  async run({ rover, config, signal, report, say }, input) {
    const destination = input?.destination ?? DEFAULT_DESTINATION;
    const outcome = await runMobileReceptionist(rover, config, signal, destination, {
      onUpdate: report
    });
    if (outcome === "arrived") say(`We have arrived at the ${destination}.`);
    else if (outcome === "blocked") say("The path is not clear. I am stopping.");
    else if (outcome === "not_found") say("I could not find the destination marker. Please move me where it is visible.");
    else say("I lost the destination marker. I am stopping.");
  }
});

export async function runMobileReceptionist(
  rover: ServiceRover,
  config: ServiceConfig,
  signal: AbortSignal,
  destination: CourseDestination = DEFAULT_DESTINATION,
  options: ReceptionistOptions = {}
): Promise<ReceptionistOutcome> {
  const update = options.onUpdate ?? (() => undefined);
  const observationTimeoutMs = options.observationTimeoutMs ?? 2200;
  const searchWaitMs = options.searchWaitMs ?? 600;
  const maximumSteps = options.maximumSteps ?? 32;
  const target = destinationMarker(config, destination);
  let observations: TargetMarkerFeed | null = null;
  let searchSteps = 0;
  let searchAngle = 0;

  try {
    update({ phase: "acquiring", detail: "Looking for a visitor" });
    const visitor = await waitForPerson(rover, signal, 30_000);
    signal.throwIfAborted();
    update({
      phase: "waiting",
      detail: `Hello. Searching for the ${target.label} marker`,
      person: visitor
    });
    observations = new TargetMarkerFeed(rover, target.id, observationTimeoutMs);

    // Check the final observation even when the last allowed motion reaches the marker.
    for (let step = 0; step <= maximumSteps; step += 1) {
      signal.throwIfAborted();
      let marker: Readonly<MarkerEvent>;
      try {
        marker = await observations.next(signal, searchWaitMs);
      } catch (error) {
        if (error instanceof MarkerSearchTimeoutError && !observations.hasSeenTarget) {
          if (searchAngle >= 2 * Math.PI || searchSteps >= 36) {
            await rover.stop("destination marker not found after full scan");
            update({ phase: "waiting", detail: `Could not find ${target.label} after a full scan` });
            return "not_found";
          }
          update({ phase: "aligning", detail: `Searching for ${target.label}` });
          const before = await rover.getPose();
          await rover.turn(SEARCH_TURN_DEG, TURN_SPEED_RAD_S);
          const after = await rover.getPose();
          searchAngle += Math.abs(Math.atan2(Math.sin(after.yaw - before.yaw), Math.cos(after.yaw - before.yaw)));
          searchSteps += 1;
          step -= 1;
          continue;
        }
        throw error;
      }

      const relativeX = marker.relativeXM;
      const relativeY = marker.relativeYM;
      if (relativeX === undefined || relativeY === undefined) continue;
      const distanceM = Math.hypot(relativeX, relativeY);
      if (distanceM <= ARRIVAL_DISTANCE_M + ARRIVAL_TOLERANCE_M) {
        await rover.stop("destination marker reached");
        update({ phase: "arrived", detail: `Arrived at ${target.label}` });
        return "arrived";
      }
      if (step === maximumSteps) break;

      const bearingDeg = Math.atan2(relativeY, relativeX) * 180 / Math.PI;
      if (Math.abs(bearingDeg) > CENTER_TOLERANCE_DEG) {
        const turnDeg = clamp(bearingDeg, -MAX_ALIGN_TURN_DEG, MAX_ALIGN_TURN_DEG);
        update({
          phase: "aligning",
          detail: turnDeg >= 0
            ? `Turning left toward ${target.label}`
            : `Turning right toward ${target.label}`
        });
        await rover.turn(turnDeg, TURN_SPEED_RAD_S);
        continue;
      }

      if (!forwardPathIsClear(rover)) {
        await rover.stop("destination path is not clear");
        update({ phase: "waiting", detail: `Path to ${target.label} is not clear` });
        return "blocked";
      }

      const moveM = Math.min(MOVE_STEP_M, distanceM - ARRIVAL_DISTANCE_M);
      update({ phase: "approaching", detail: `Moving toward ${target.label}` });
      await rover.move(moveM, MOVE_SPEED_MPS);
    }

    throw new Error("Destination approach step limit reached");
  } catch (error) {
    if (observations?.unsafeReason) {
      await stopAfterFailure(rover, `destination marker ${observations.unsafeReason}`);
      update({ phase: "lost", detail: `Lost the ${target.label} marker` });
      return "lost";
    }
    await stopAfterFailure(rover, "mobile receptionist stopped");
    throw error;
  } finally {
    observations?.close();
  }
}

function destinationMarker(config: ServiceConfig, destination: CourseDestination): CourseMarker {
  const marker = config.courseMarkers.find((candidate) => candidate.destination === destination);
  if (!marker) throw new Error(`No course marker configured for destination: ${destination}`);
  return marker;
}

function forwardPathIsClear(rover: ServiceRover): boolean {
  const snapshot = rover.getFrontObstacle?.();
  return snapshot === undefined || snapshot?.state === "CLEAR";
}

class MarkerSearchTimeoutError extends Error {}
class TargetMarkerUnavailableError extends Error {}

interface WaitingMarker {
  resolve: (event: Readonly<MarkerEvent>) => void;
  reject: (error: unknown) => void;
  signal: AbortSignal;
  abort: () => void;
  timeout: number;
}

class TargetMarkerFeed {
  private latest: Readonly<MarkerEvent> | null = null;
  private waiting: WaitingMarker | null = null;
  private readonly unsubscribe: () => void;
  private staleTimer: number | undefined;
  private seen = false;
  unsafeReason: "lost" | "stale" | null = null;

  constructor(
    private readonly rover: ServiceRover,
    private readonly markerId: number,
    private readonly staleAfterMs: number
  ) {
    this.unsubscribe = rover.onMarker((event) => {
      if (event.markerId !== this.markerId) return;
      if (event.status === "lost") {
        this.markUnsafe("lost");
        return;
      }
      this.seen = true;
      this.armStaleTimer();
      const waiting = this.takeWaiting();
      if (waiting) waiting.resolve(event);
      else this.latest = event;
    });
  }

  get hasSeenTarget(): boolean {
    return this.seen;
  }

  next(signal: AbortSignal, timeoutMs: number): Promise<Readonly<MarkerEvent>> {
    signal.throwIfAborted();
    if (this.latest) {
      const event = this.latest;
      this.latest = null;
      return Promise.resolve(event);
    }
    if (this.unsafeReason) {
      return Promise.reject(new TargetMarkerUnavailableError(this.unsafeReason));
    }
    return new Promise((resolve, reject) => {
      const abort = () => {
        const waiting = this.takeWaiting();
        waiting?.reject(signal.reason ?? new DOMException("Mission cancelled", "AbortError"));
      };
      const timeout = window.setTimeout(() => {
        const waiting = this.takeWaiting();
        waiting?.reject(new MarkerSearchTimeoutError());
      }, timeoutMs);
      this.waiting = { resolve, reject, signal, abort, timeout };
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) abort();
    });
  }

  close(): void {
    this.unsubscribe();
    if (this.staleTimer !== undefined) window.clearTimeout(this.staleTimer);
    this.takeWaiting()?.reject(new DOMException("Marker feed closed", "AbortError"));
    this.latest = null;
  }

  private armStaleTimer(): void {
    if (this.staleTimer !== undefined) window.clearTimeout(this.staleTimer);
    this.staleTimer = window.setTimeout(() => this.markUnsafe("stale"), this.staleAfterMs);
  }

  private markUnsafe(reason: "lost" | "stale"): void {
    if (this.unsafeReason) return;
    this.unsafeReason = reason;
    if (this.staleTimer !== undefined) window.clearTimeout(this.staleTimer);
    void this.rover.stop(`destination marker ${reason}`).catch(() => undefined);
    this.takeWaiting()?.reject(new TargetMarkerUnavailableError(reason));
  }

  private takeWaiting(): WaitingMarker | null {
    const waiting = this.waiting;
    this.waiting = null;
    if (waiting) {
      window.clearTimeout(waiting.timeout);
      waiting.signal.removeEventListener("abort", waiting.abort);
    }
    return waiting;
  }
}

async function stopAfterFailure(rover: ServiceRover, reason: string): Promise<void> {
  try {
    await rover.stop(reason);
  } catch {
    // The server or a safety layer may already have stopped the rover.
  }
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
