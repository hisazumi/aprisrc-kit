import type { Pose } from "../protocol";

export const SCENE_STORAGE_KEY = "apris.marker-scene.v1";
export interface PlaygroundScene {
  origin: Pose;
  visitor: { x: number; y: number };
  entrance: { x: number; y: number };
  desk: { x: number; y: number };
  hidden: boolean;
  blocked: boolean;
}

export function scenePreset(kind: "front" | "behind" | "missing"): PlaygroundScene {
  return {
    origin: { x: -.8, y: -.15, yaw: kind === "behind" ? Math.PI : 0 },
    visitor: { x: kind === "behind" ? -2.15 : .55, y: -.15 },
    entrance: { x: 0, y: 0 }, desk: { x: 2, y: 0 },
    hidden: kind === "missing", blocked: false
  };
}

export function parseScene(value: string): PlaygroundScene {
  const scene = JSON.parse(value) as PlaygroundScene;
  const point = (p: { x: number; y: number } | undefined) => p && [p.x, p.y].every(
    (n) => typeof n === "number" && Number.isFinite(n) && Math.abs(n) <= 10);
  if (!scene || !point(scene.origin) || !point(scene.visitor) || !point(scene.entrance) || !point(scene.desk)
    || !Number.isFinite(scene.origin.yaw) || Math.abs(scene.origin.yaw) > Math.PI
    || typeof scene.hidden !== "boolean" || typeof scene.blocked !== "boolean") {
    throw new Error("Invalid saved scene");
  }
  return scene;
}
