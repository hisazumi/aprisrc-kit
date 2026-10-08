import { useEffect, useRef, useState } from "react";

import type { CourseMarker } from "../config";
import type { Pose } from "../protocol";
import { simulatorApi } from "../simulatorApi";
import { projectVirtualPerson } from "./virtualPerson";

export type MarkerScene = "destination" | "wrong" | "hidden";

export function relativeMarkerPosition(pose: Pose, marker: CourseMarker) {
  const dx = marker.xM - pose.x;
  const dy = marker.yM - pose.y;
  return {
    x: Math.cos(pose.yaw) * dx + Math.sin(pose.yaw) * dy,
    y: -Math.sin(pose.yaw) * dx + Math.cos(pose.yaw) * dy
  };
}

export function useVirtualMarkerSimulation(pose: Pose | null, marker: CourseMarker | null, enabled: boolean) {
  const current = useRef({ pose, marker });
  current.current = { pose, marker };
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let visibleId: number | null = null;
    let timer: number | undefined;
    const emit = async () => {
      try {
        const { pose: position, marker: target } = current.current;
        const visible = position && target && projectVirtualPerson(position, { x: target.xM, y: target.yM }).visible;
        if (visibleId !== null && (!visible || target?.id !== visibleId)) {
          await simulatorApi.injectEvent("marker", { status: "lost", confidence: 0, marker_id: visibleId });
          visibleId = null;
        }
        if (disposed) return;
        if (visible && position && target) {
          const relative = relativeMarkerPosition(position, target);
          await simulatorApi.injectEvent("marker", {
            status: "detected", confidence: .96, marker_id: target.id,
            relative_x_m: relative.x, relative_y_m: relative.y
          });
          visibleId = target.id;
        }
        if (!disposed) setError("");
      } catch (cause) {
        if (!disposed) setError(cause instanceof Error ? cause.message : "Marker scene unavailable");
      } finally {
        if (!disposed) timer = window.setTimeout(() => void emit(), 450);
      }
    };
    void emit();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      if (visibleId !== null) {
        void simulatorApi.injectEvent("marker", { status: "lost", confidence: 0, marker_id: visibleId }).catch(() => undefined);
      }
    };
  }, [enabled]);
  return { error };
}
