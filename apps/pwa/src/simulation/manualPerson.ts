import type { Pose } from "../protocol";
import { placeVirtualPerson, type VirtualPersonTarget } from "./virtualPerson";

export type PersonMotion = "still" | "away" | "closer" | "left" | "right";
export function placeManualPerson(pose: Pose, action: "enter" | "leave" | "reset"): VirtualPersonTarget {
  return placeVirtualPerson(pose, action === "leave" ? 0 : 1.35, action === "leave" ? 1.35 : 0);
}
export function moveManualPerson(person: VirtualPersonTarget, pose: Pose, motion: PersonMotion, speed: number, dt: number): VirtualPersonTarget {
  if (motion === "still") return person;
  const distance = Math.hypot(person.x - pose.x, person.y - pose.y);
  const bearing = distance > 0.01 ? Math.atan2(person.y - pose.y, person.x - pose.x) : pose.yaw;
  const heading = motion === "away" ? bearing : motion === "closer" ? bearing + Math.PI
    : pose.yaw + (motion === "left" ? Math.PI / 2 : -Math.PI / 2);
  const step = Math.min(Math.max(dt, 0), 0.1) * Math.min(Math.max(speed, 0.01), 0.5);
  if ((motion === "closer" && distance <= 0.45) || (motion === "away" && distance >= 4.5)) return person;
  const next = { x: person.x + Math.cos(heading) * step, y: person.y + Math.sin(heading) * step };
  if (Math.hypot(next.x - pose.x, next.y - pose.y) > 4.55) return person;
  return next;
}
