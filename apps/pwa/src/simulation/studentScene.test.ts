import { describe, expect, it } from "vitest";
import { parseStudentScene, StudentSceneRunner, studentScenes } from "./studentScene";
import { projectVirtualPerson } from "./virtualPerson";

describe("student scene definitions and runner", () => {
  it("round-trips every preset and rejects invalid files", () => {
    for (const scene of studentScenes) expect(parseStudentScene(JSON.parse(JSON.stringify(scene)))).toEqual(scene);
    for (const invalid of [null, [], { ...studentScenes[0], version: 2 }, { ...studentScenes[0], person: { x: Infinity, y: 0 } },
      { ...studentScenes[0], rover: { x: 0, y: 0, yaw: 4 } }, { ...studentScenes[0], steps: [{ ...studentScenes[0].steps[0], points: [] }] },
      { ...studentScenes[0], steps: [{ ...studentScenes[0].steps[0], speedMps: 0 }] },
      { ...studentScenes[0], steps: [{ ...studentScenes[0].steps[0], trigger: { type: "delay", seconds: -1 } }] }]) {
      expect(() => parseStudentScene(invalid)).toThrow();
    }
  });
  it("waits for Next, walks at the requested speed and stops at the endpoint", () => {
    const run = new StudentSceneRunner(studentScenes[0], 0);
    expect(run.update(100)).toMatchObject({ phase: "waiting", manual: true, person: { x: 1.35, y: 0 } });
    run.next(100);
    expect(run.update(102).person.x).toBeCloseTo(1.55);
    run.next(102); // A second Next cannot restart an active walk.
    expect(run.update(107)).toMatchObject({ phase: "complete", person: { x: 2, y: 0 }, visible: true });
    expect(run.update(200).person).toEqual({ x: 2, y: 0 });
  });
  it("enters the camera field from outside and waits for the next manual action", () => {
    const scene = studentScenes[2], run = new StudentSceneRunner(scene, 10);
    expect(projectVirtualPerson(scene.rover, run.update(10).person).visible).toBe(false);
    expect(run.update(11).phase).toBe("waiting");
    expect(run.update(13).phase).toBe("walking");
    expect(projectVirtualPerson(scene.rover, run.update(25).person).visible).toBe(true);
    expect(run.update(25)).toMatchObject({ index: 1, manual: true });
  });
  it("supports waypoints, delays relative to completion, and disappearance", () => {
    const scene = parseStudentScene({ ...studentScenes[0], person: { x: 0, y: 0 }, steps: [
      { action: "walk", trigger: { type: "delay", seconds: 1 }, points: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }], speedMps: 0.5 },
      { action: "stand", trigger: { type: "delay", seconds: 2 }, points: [], speedMps: 0.1 },
      { action: "disappear", trigger: { type: "manual" }, points: [], speedMps: 0.1 }
    ] });
    const run = new StudentSceneRunner(scene, 0);
    expect(run.update(4).person).toEqual({ x: 1, y: 0.5 });
    expect(run.update(6)).toMatchObject({ index: 1, phase: "waiting", person: { x: 1, y: 1 } });
    expect(run.update(7)).toMatchObject({ index: 2, manual: true });
    expect(run.next(8)).toMatchObject({ visible: false, phase: "complete" });
  });
  it("restarts deterministically without carrying old position or time", () => {
    const oldRun = new StudentSceneRunner(studentScenes[0], 0);
    oldRun.next(0); oldRun.update(100);
    const fresh = new StudentSceneRunner(studentScenes[0], 100);
    expect(fresh.update(100)).toEqual(new StudentSceneRunner(studentScenes[0], 0).update(0));
  });
});
