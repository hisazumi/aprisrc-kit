import { useState } from "react";

import type { Pose } from "../protocol";
import { simulatorApi } from "../simulatorApi";
import {
  placeVirtualPerson,
  type VirtualPersonProjection,
  type VirtualPersonTarget
} from "../simulation/virtualPerson";

type Placement = "left" | "ahead" | "right";

interface VirtualPersonPanelProps {
  pose: Pose | null;
  enabled: boolean;
  walking: boolean;
  projection: VirtualPersonProjection | null;
  observationError: string;
  onTarget: (target: VirtualPersonTarget) => void;
  onEnabled: (enabled: boolean) => void;
  onWalking: (walking: boolean) => void;
}

const placements: Record<Placement, { forwardM: number; leftM: number; label: string }> = {
  left: { forwardM: 1.35, leftM: 0.3, label: "Left" },
  ahead: { forwardM: 1.35, leftM: 0, label: "Ahead" },
  right: { forwardM: 1.35, leftM: -0.3, label: "Right" }
};

export function VirtualPersonPanel({
  pose,
  enabled,
  walking,
  projection,
  observationError,
  onTarget,
  onEnabled,
  onWalking
}: VirtualPersonPanelProps) {
  const [placement, setPlacement] = useState<Placement>("left");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const start = async () => {
    if (!pose) {
      setError("Rover pose is not available yet.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const selected = placements[placement];
      onTarget(placeVirtualPerson(pose, selected.forwardM, selected.leftM));
      onWalking(false);
      const response = await simulatorApi.setFrontObstacle("CLEAR", "healthy");
      if (response.front_obstacle.latched) {
        await simulatorApi.clearFrontObstacle("virtual person demo area verified clear");
      }
      onEnabled(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start virtual scene");
    } finally {
      setBusy(false);
    }
  };

  const stop = () => {
    onWalking(false);
    onEnabled(false);
  };
  const displayError = observationError || error;

  return (
    <article className="panel panel--virtual-person">
      <div className="panel__heading">
        <div>
          <p className="section-label">VIRTUAL PERSON</p>
          <h2>Interaction scene</h2>
        </div>
        <span className={`owner-badge ${enabled ? "owner-badge--active" : ""}`}>
          {enabled ? (projection?.visible ? "visible" : "outside view") : "off"}
        </span>
      </div>

      <div className="virtual-person-layout">
        <div className="virtual-person-placement" role="group" aria-label="Person placement">
          {(Object.keys(placements) as Placement[]).map((id) => (
            <button
              key={id}
              className={placement === id ? "is-selected" : ""}
              disabled={busy || enabled}
              onClick={() => setPlacement(id)}
            >
              {placements[id].label}
            </button>
          ))}
        </div>
        <div className="virtual-person-readout" aria-live="polite">
          <div><span>distance</span><strong>{projection ? `${projection.distanceM.toFixed(2)} m` : "—"}</strong></div>
          <div><span>bearing</span><strong>{projection ? `${projection.bearingDeg.toFixed(1)}°` : "—"}</strong></div>
          <div><span>frame width</span><strong>{projection ? `${Math.round(projection.width * 100)}%` : "—"}</strong></div>
          <div><span>motion</span><strong>{walking ? "walking" : "standing"}</strong></div>
        </div>
        <div className="virtual-person-actions">
          {enabled ? (
            <>
              <button className="button button--primary" onClick={() => onWalking(!walking)}>
                {walking ? "Pause walking" : "Start walking"}
              </button>
              <button className="button button--quiet" onClick={stop}>Stop scene</button>
            </>
          ) : (
            <button className="button button--primary" disabled={busy || !pose} onClick={() => void start()}>
              Start scene
            </button>
          )}
        </div>
      </div>
      {displayError && <p className="scenario-error" role="alert">{displayError}</p>}
    </article>
  );
}
