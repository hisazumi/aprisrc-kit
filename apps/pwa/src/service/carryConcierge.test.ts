import { describe, expect, it } from "vitest";

import type { PersonEvent } from "../protocol";
import {
  advanceCarryConcierge,
  initialCarryConciergeState,
  REQUIRED_STABLE_DETECTIONS
} from "./carryConcierge";

function person(
  personId = "person-1",
  status: PersonEvent["status"] = "detected",
  width = 0.2
): PersonEvent {
  return {
    eventId: `${personId}-${status}`,
    status,
    confidence: status === "detected" ? 0.95 : 0,
    capturedAt: 1,
    source: "camera",
    personId,
    centerX: status === "detected" ? 0.5 : undefined,
    centerY: status === "detected" ? 0.5 : undefined,
    width: status === "detected" ? width : undefined,
    height: status === "detected" ? 0.5 : undefined,
    bearingDeg: status === "detected" ? 0 : undefined
  };
}

function armed() {
  return advanceCarryConcierge(initialCarryConciergeState, { type: "arm" });
}

describe("carry concierge service state", () => {
  it("waits while a person is outside the frame, then approaches after stable entry", () => {
    let state = armed();
    state = advanceCarryConcierge(state, { type: "person", person: person("outside", "lost") });
    expect(state.phase).toBe("waiting");

    for (let index = 0; index < REQUIRED_STABLE_DETECTIONS - 1; index += 1) {
      state = advanceCarryConcierge(state, { type: "person", person: person("entrant") });
      expect(state.phase).toBe("noticing");
    }
    state = advanceCarryConcierge(state, { type: "person", person: person("entrant") });

    expect(state.phase).toBe("approaching");
    expect(state.targetPersonId).toBe("entrant");
  });

  it("offers only after the approach mission reaches the person", () => {
    let state = armed();
    for (let index = 0; index < REQUIRED_STABLE_DETECTIONS; index += 1) {
      state = advanceCarryConcierge(state, { type: "person", person: person() });
    }

    state = advanceCarryConcierge(state, {
      type: "mission_progress",
      progress: { phase: "approaching", detail: "Coming closer", person: person() }
    });
    expect(state).toMatchObject({ phase: "approaching", detail: "Coming closer" });

    state = advanceCarryConcierge(state, {
      type: "mission_progress",
      progress: { phase: "arrived", detail: "I am here", person: person("person-1", "detected", 0.4) }
    });
    expect(state).toMatchObject({
      phase: "offering",
      detail: "Would you like help carrying something?"
    });
  });

  it("reports target loss instead of offering when the approach loses the person", () => {
    let state = armed();
    for (let index = 0; index < REQUIRED_STABLE_DETECTIONS; index += 1) {
      state = advanceCarryConcierge(state, { type: "person", person: person() });
    }

    state = advanceCarryConcierge(state, {
      type: "mission_progress",
      progress: { phase: "lost", detail: "I lost sight of you" }
    });

    expect(state).toMatchObject({ phase: "lost", detail: "I lost sight of you" });
  });

  it("does not approach a passerby that disappears before detection is stable", () => {
    let state = armed();
    state = advanceCarryConcierge(state, { type: "person", person: person("passerby") });
    state = advanceCarryConcierge(state, { type: "person", person: person("passerby") });
    state = advanceCarryConcierge(state, {
      type: "person",
      person: person("passerby", "lost")
    });

    expect(state.phase).toBe("waiting");
    expect(state.targetPersonId).toBeNull();
  });

  it("restarts the stability count when a different person enters", () => {
    let state = armed();
    state = advanceCarryConcierge(state, { type: "person", person: person("first") });
    state = advanceCarryConcierge(state, { type: "person", person: person("first") });
    state = advanceCarryConcierge(state, { type: "person", person: person("second") });

    expect(state.phase).toBe("noticing");
    expect(state.detectionStreak).toBe(1);
    expect(state.targetPersonId).toBe("second");
  });

  it("enters cooldown when the offer is declined or receives no reply", () => {
    let state = armed();
    for (let index = 0; index < REQUIRED_STABLE_DETECTIONS; index += 1) {
      state = advanceCarryConcierge(state, { type: "person", person: person() });
    }
    state = advanceCarryConcierge(state, {
      type: "mission_progress",
      progress: { phase: "arrived", detail: "I am here", person: person() }
    });

    expect(advanceCarryConcierge(state, { type: "decline" }).phase).toBe("cooldown");
    expect(advanceCarryConcierge(state, { type: "offer_timeout" }).phase).toBe("cooldown");
  });

  it("waits for loading confirmation before following and reports target loss", () => {
    let state = armed();
    for (let index = 0; index < REQUIRED_STABLE_DETECTIONS; index += 1) {
      state = advanceCarryConcierge(state, { type: "person", person: person() });
    }
    state = advanceCarryConcierge(state, {
      type: "mission_progress",
      progress: { phase: "arrived", detail: "I am here", person: person() }
    });
    state = advanceCarryConcierge(state, { type: "accept" });
    expect(state.phase).toBe("loading");
    state = advanceCarryConcierge(state, { type: "loaded" });
    expect(state.phase).toBe("following");
    state = advanceCarryConcierge(state, {
      type: "mission_progress",
      progress: { phase: "following", detail: "Following you", person: person() }
    });
    state = advanceCarryConcierge(state, {
      type: "mission_progress",
      progress: { phase: "lost", detail: "I lost sight of you" }
    });

    expect(state.phase).toBe("lost");
    expect(state.detail).toBe("I lost sight of you");
  });

  it("lets an explicit stop preempt following", () => {
    const following = {
      ...armed(),
      phase: "following" as const,
      detail: "Following you"
    };

    expect(advanceCarryConcierge(following, { type: "stop" })).toMatchObject({
      phase: "stopped",
      detail: "Service stopped"
    });
  });
});
