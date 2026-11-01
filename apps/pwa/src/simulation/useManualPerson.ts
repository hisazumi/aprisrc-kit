import { useCallback, useEffect, useRef, useState } from "react";
import type { Pose } from "../protocol";
import { moveManualPerson, placeManualPerson, type PersonMotion } from "./manualPerson";

export function useManualPerson(pose: Pose | null, enabled: boolean) {
  const [person, setPerson] = useState({ x: 1.35, y: 0 });
  const [motion, setMotion] = useState<PersonMotion>("still");
  const [speed, setSpeed] = useState(0.1);
  const currentPose = useRef(pose); currentPose.current = pose;
  const initialized = useRef(false);
  const stop = useCallback(() => setMotion("still"), []);
  useEffect(() => {
    if (enabled && pose && !initialized.current) {
      initialized.current = true; setPerson(placeManualPerson(pose, "reset"));
    }
  }, [enabled, pose]);
  useEffect(() => {
    if (!enabled) { stop(); return; }
    const hide = () => { if (document.hidden) stop(); };
    document.addEventListener("visibilitychange", hide);
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now(), dt = (now - previous) / 1000; previous = now;
      const p = currentPose.current;
      if (p && !document.hidden) setPerson(value => moveManualPerson(value, p, motion, speed, dt));
    }, 50);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", hide); };
  }, [enabled, motion, speed, stop]);
  const place = (action: "enter" | "leave" | "reset") => {
    if (!enabled || !currentPose.current) return;
    stop(); setPerson(placeManualPerson(currentPose.current, action));
  };
  return { person, motion, speed, setSpeed, setMotion, stop, place };
}
