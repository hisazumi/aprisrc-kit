import { describe, expect, it } from "vitest";

import {
  placeVirtualPerson,
  projectVirtualPerson,
  VIRTUAL_PERSON_WALK_DURATION_S,
  walkVirtualPerson
} from "./virtualPerson";

describe("projectVirtualPerson", () => {
  it("projects a person ahead into the center of the camera", () => {
    const projection = projectVirtualPerson(
      { x: 0, y: 0, yaw: 0 },
      { x: 1.5, y: 0 }
    );

    expect(projection.visible).toBe(true);
    expect(projection.centerX).toBeCloseTo(0.5);
    expect(projection.bearingDeg).toBeCloseTo(0);
    expect(projection.width).toBeGreaterThan(0.1);
  });

  it("uses positive bearing and the left side of the image for a person to the left", () => {
    const projection = projectVirtualPerson(
      { x: 0, y: 0, yaw: 0 },
      { x: 1.4, y: 0.4 }
    );

    expect(projection.visible).toBe(true);
    expect(projection.bearingDeg).toBeGreaterThan(0);
    expect(projection.centerX).toBeLessThan(0.5);
  });

  it("marks a person outside the camera field of view as lost", () => {
    const projection = projectVirtualPerson(
      { x: 0, y: 0, yaw: 0 },
      { x: 0, y: 1 }
    );

    expect(projection.visible).toBe(false);
  });

  it("grows the apparent person width as the rover approaches", () => {
    const far = projectVirtualPerson({ x: 0, y: 0, yaw: 0 }, { x: 2, y: 0 });
    const near = projectVirtualPerson({ x: 1, y: 0, yaw: 0 }, { x: 2, y: 0 });

    expect(near.width).toBeGreaterThan(far.width);
  });
});

describe("placeVirtualPerson", () => {
  it("places a target in rover-relative coordinates", () => {
    const target = placeVirtualPerson(
      { x: 2, y: 3, yaw: Math.PI / 2 },
      1.5,
      0.4
    );

    expect(target.x).toBeCloseTo(1.6);
    expect(target.y).toBeCloseTo(4.5);
  });
});

describe("walkVirtualPerson", () => {
  it("moves forward on a gentle route and ends centered on its heading", () => {
    const origin = { x: 1, y: 2 };
    const midway = walkVirtualPerson(origin, 0, VIRTUAL_PERSON_WALK_DURATION_S / 4);
    const end = walkVirtualPerson(origin, 0, VIRTUAL_PERSON_WALK_DURATION_S);

    expect(midway.x).toBeGreaterThan(origin.x);
    expect(midway.y).toBeGreaterThan(origin.y);
    expect(end.x).toBeCloseTo(1.66);
    expect(end.y).toBeCloseTo(origin.y);
  });

  it("rotates the route into the selected heading", () => {
    const end = walkVirtualPerson(
      { x: 0, y: 0 },
      Math.PI / 2,
      VIRTUAL_PERSON_WALK_DURATION_S
    );

    expect(end.x).toBeCloseTo(0);
    expect(end.y).toBeCloseTo(0.66);
  });
});
