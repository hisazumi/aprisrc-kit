import { useEffect, useRef, useState } from "react";

import type { Pose } from "../protocol";
import { simulatorApi } from "../simulatorApi";
import {
  projectVirtualPerson,
  type VirtualPersonProjection,
  type VirtualPersonTarget
} from "./virtualPerson";

const OBSERVATION_INTERVAL_MS = 450;

export function useVirtualPersonSimulation(
  pose: Pose | null,
  target: VirtualPersonTarget,
  enabled: boolean
): { projection: VirtualPersonProjection | null; error: string } {
  const poseRef = useRef(pose);
  const targetRef = useRef(target);
  const [projection, setProjection] = useState<VirtualPersonProjection | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    poseRef.current = pose;
  }, [pose]);

  useEffect(() => {
    targetRef.current = target;
  }, [target]);

  useEffect(() => {
    if (!enabled) {
      setProjection(null);
      return;
    }

    let disposed = false;
    let lastVisible = false;
    let timer: number | undefined;

    const emit = async () => {
      const currentPose = poseRef.current;
      if (!currentPose) return;
      const next = projectVirtualPerson(currentPose, targetRef.current);
      setProjection(next);
      try {
        if (next.visible) {
          await simulatorApi.injectEvent("person", {
            status: "detected",
            confidence: 0.95,
            person_id: "virtual-person",
            center_x: next.centerX,
            center_y: next.centerY,
            width: next.width,
            height: next.height,
            bearing_deg: next.bearingDeg
          });
          lastVisible = true;
        } else if (lastVisible) {
          await simulatorApi.injectEvent("person", {
            status: "lost",
            confidence: 0,
            person_id: "virtual-person"
          });
          lastVisible = false;
        }
        if (!disposed) setError("");
      } catch (cause) {
        if (!disposed) {
          setError(cause instanceof Error ? cause.message : "Virtual person update failed");
        }
      }
    };

    void emit();
    timer = window.setInterval(() => void emit(), OBSERVATION_INTERVAL_MS);
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearInterval(timer);
      if (lastVisible) {
        void simulatorApi.injectEvent("person", {
          status: "lost",
          confidence: 0,
          person_id: "virtual-person"
        }).catch(() => undefined);
      }
    };
  }, [enabled]);

  return { projection, error };
}
