import { expect, it } from "vitest";
import { moveManualPerson, placeManualPerson } from "./manualPerson";
import { projectVirtualPerson } from "./virtualPerson";

it("places a person inside and outside the live rover field, regardless of rover heading", () => {
  for (const yaw of [0, Math.PI / 2, -Math.PI]) {
    const pose = { x: 2, y: -1, yaw };
    expect(projectVirtualPerson(pose, placeManualPerson(pose, "enter")).visible).toBe(true);
    expect(projectVirtualPerson(pose, placeManualPerson(pose, "leave")).visible).toBe(false);
    expect(placeManualPerson(pose, "reset")).toEqual(placeManualPerson(pose, "enter"));
  }
});
it("moves relative to the rover, stops on demand, and bounds delayed ticks", () => {
  const pose = { x: 0, y: 0, yaw: 0 }, person = { x: 1.35, y: 0 };
  expect(moveManualPerson(person, pose, "away", 0.1, .1).x).toBeCloseTo(1.36);
  expect(moveManualPerson(person, pose, "closer", 0.1, .1).x).toBeCloseTo(1.34);
  expect(moveManualPerson(person, pose, "left", 0.1, .1).y).toBeGreaterThan(0);
  expect(moveManualPerson(person, pose, "right", 0.1, .1).y).toBeLessThan(0);
  expect(moveManualPerson(person, pose, "still", 0.1, .1)).toEqual(person);
  expect(moveManualPerson(person, pose, "away", 0.1, 10).x).toBeCloseTo(1.36);
  expect(moveManualPerson({ x: .4, y: 0 }, pose, "closer", .1, .1)).toEqual({ x: .4, y: 0 });
});
