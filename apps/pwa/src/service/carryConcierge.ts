import type { MissionProgress } from "../missions";
import type { PersonEvent } from "../protocol";

export const REQUIRED_STABLE_DETECTIONS = 3;
export const OFFER_REPLY_TIMEOUT_MS = 12_000;

export type CarryConciergePhase =
  | "paused"
  | "waiting"
  | "noticing"
  | "approaching"
  | "offering"
  | "loading"
  | "following"
  | "cooldown"
  | "complete"
  | "lost"
  | "stopped"
  | "error";

export interface CarryConciergeState {
  phase: CarryConciergePhase;
  detail: string;
  detectionStreak: number;
  targetPersonId: string | null;
  person?: Readonly<PersonEvent>;
}

export type CarryConciergeEvent =
  | { type: "arm" }
  | { type: "disarm" }
  | { type: "person"; person: Readonly<PersonEvent> }
  | { type: "accept" }
  | { type: "loaded" }
  | { type: "decline" }
  | { type: "offer_timeout" }
  | { type: "mission_progress"; progress: MissionProgress }
  | { type: "complete" }
  | { type: "stop" }
  | { type: "reset" }
  | { type: "error"; detail: string };

export const initialCarryConciergeState: CarryConciergeState = {
  phase: "paused",
  detail: "Service is paused",
  detectionStreak: 0,
  targetPersonId: null
};

export function advanceCarryConcierge(
  state: CarryConciergeState,
  event: CarryConciergeEvent
): CarryConciergeState {
  switch (event.type) {
    case "arm":
    case "reset":
      return waitingState();
    case "disarm":
      return initialCarryConciergeState;
    case "person":
      return observePerson(state, event.person);
    case "accept":
      return state.phase === "offering"
        ? { ...state, phase: "loading", detail: "Place your items on the rover" }
        : state;
    case "loaded":
      return state.phase === "loading"
        ? { ...state, phase: "following", detail: "Looking for you" }
        : state;
    case "decline":
      return state.phase === "offering"
        ? { ...state, phase: "cooldown", detail: "No problem. I will keep waiting." }
        : state;
    case "offer_timeout":
      return state.phase === "offering"
        ? { ...state, phase: "cooldown", detail: "No reply. I will keep waiting." }
        : state;
    case "mission_progress":
      return missionProgress(state, event.progress);
    case "complete":
      return {
        ...state,
        phase: "complete",
        detail: "We have arrived",
        detectionStreak: 0
      };
    case "stop":
      return {
        ...state,
        phase: "stopped",
        detail: "Service stopped",
        detectionStreak: 0
      };
    case "error":
      return {
        ...state,
        phase: "error",
        detail: event.detail,
        detectionStreak: 0
      };
  }
}

function waitingState(): CarryConciergeState {
  return {
    phase: "waiting",
    detail: "Waiting for someone",
    detectionStreak: 0,
    targetPersonId: null
  };
}

function observePerson(
  state: CarryConciergeState,
  person: Readonly<PersonEvent>
): CarryConciergeState {
  if (state.phase === "cooldown" && person.status === "lost") return waitingState();
  if (!(["waiting", "noticing"] as CarryConciergePhase[]).includes(state.phase)) {
    if (["approaching", "loading", "following"].includes(state.phase)
      && person.status === "detected") {
      return { ...state, person };
    }
    return state;
  }

  if (person.status === "lost") return waitingState();

  const samePerson = state.targetPersonId === person.personId;
  const detectionStreak = samePerson ? state.detectionStreak + 1 : 1;
  if (detectionStreak >= REQUIRED_STABLE_DETECTIONS) {
    return {
      ...state,
      phase: "approaching",
      detail: "Coming closer so we can talk",
      detectionStreak,
      targetPersonId: person.personId,
      person
    };
  }

  return {
    ...state,
    phase: "noticing",
    detail: "Someone is approaching",
    detectionStreak,
    targetPersonId: person.personId,
    person
  };
}

function missionProgress(
  state: CarryConciergeState,
  progress: MissionProgress
): CarryConciergeState {
  if (state.phase === "approaching") {
    if (progress.phase === "arrived") {
      return {
        ...state,
        phase: "offering",
        detail: "Would you like help carrying something?",
        person: progress.person ?? state.person
      };
    }
    if (progress.phase === "lost") {
      return {
        ...state,
        phase: "lost",
        detail: progress.detail,
        detectionStreak: 0,
        person: progress.person
      };
    }
    return {
      ...state,
      detail: progress.detail,
      person: progress.person ?? state.person
    };
  }
  if (state.phase !== "following") return state;
  if (progress.phase === "lost") {
    return {
      ...state,
      phase: "lost",
      detail: progress.detail,
      detectionStreak: 0,
      person: progress.person
    };
  }
  if (progress.phase === "stopped" || progress.phase === "waiting") {
    return {
      ...state,
      phase: "stopped",
      detail: progress.detail,
      detectionStreak: 0,
      person: progress.person ?? state.person
    };
  }
  return {
    ...state,
    detail: progress.detail,
    person: progress.person ?? state.person
  };
}
