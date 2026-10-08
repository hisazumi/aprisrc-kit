import type { Pose } from "../protocol";

export interface VirtualPersonTarget {
  x: number;
  y: number;
}

export interface VirtualPersonProjection {
  visible: boolean;
  distanceM: number;
  bearingDeg: number;
  centerX: number;
  centerY: number;
  width: number;
  height: number;
}

export const VIRTUAL_PERSON_WALK_DURATION_S = 12;

const HORIZONTAL_FOV_RAD = (70 * Math.PI) / 180;
const MAX_VISIBLE_DISTANCE_M = 4;
const PERSON_WIDTH_M = 0.48;
const PERSON_ASPECT_RATIO = 2.35;
const WALK_DISTANCE_M = 0.66;
const WALK_SWAY_M = 0.12;

export function projectVirtualPerson(
  pose: Readonly<Pose>,
  target: Readonly<VirtualPersonTarget>
): VirtualPersonProjection {
  const dx = target.x - pose.x;
  const dy = target.y - pose.y;
  const distanceM = Math.hypot(dx, dy);
  const bearingRad = normalizeAngle(Math.atan2(dy, dx) - pose.yaw);
  const focalWidth = 1 / (2 * Math.tan(HORIZONTAL_FOV_RAD / 2));
  const width = clamp(PERSON_WIDTH_M * focalWidth / Math.max(distanceM, 0.2), 0.04, 0.9);
  const height = clamp(width * PERSON_ASPECT_RATIO, 0.08, 0.96);
  const centerX = clamp(0.5 - bearingRad / HORIZONTAL_FOV_RAD, 0, 1);
  const visible = distanceM <= MAX_VISIBLE_DISTANCE_M
    && Math.abs(bearingRad) <= HORIZONTAL_FOV_RAD / 2;

  return {
    visible,
    distanceM,
    bearingDeg: (bearingRad * 180) / Math.PI,
    centerX,
    centerY: 0.5,
    width,
    height
  };
}

export function placeVirtualPerson(
  pose: Readonly<Pose>,
  forwardM: number,
  leftM: number
): VirtualPersonTarget {
  const cosine = Math.cos(pose.yaw);
  const sine = Math.sin(pose.yaw);
  return {
    x: pose.x + cosine * forwardM - sine * leftM,
    y: pose.y + sine * forwardM + cosine * leftM
  };
}

export function walkVirtualPerson(
  origin: Readonly<VirtualPersonTarget>,
  headingRad: number,
  elapsedS: number
): VirtualPersonTarget {
  const progress = clamp(elapsedS / VIRTUAL_PERSON_WALK_DURATION_S, 0, 1);
  const forwardM = WALK_DISTANCE_M * progress;
  const leftM = WALK_SWAY_M * Math.sin(progress * Math.PI * 2);
  const cosine = Math.cos(headingRad);
  const sine = Math.sin(headingRad);
  return {
    x: origin.x + cosine * forwardM - sine * leftM,
    y: origin.y + sine * forwardM + cosine * leftM
  };
}

function normalizeAngle(angle: number): number {
  return Math.atan2(Math.sin(angle), Math.cos(angle));
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
