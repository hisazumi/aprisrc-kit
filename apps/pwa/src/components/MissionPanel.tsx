import { useRef, useState } from "react";

import type { ServiceConfig } from "../config";
import type { MissionDefinition, ServiceRover } from "../missions";
import { speakEnglish } from "../speech";

interface MissionPanelProps {
  disabled: boolean;
  rover: ServiceRover;
  missions: readonly MissionDefinition[];
  config: ServiceConfig;
  defaultMissionId: string;
  cancelMotion: () => boolean;
}

type MissionStatus = "idle" | "running" | "cancelling" | "completed" | "error";

function initialMissionId(missions: readonly MissionDefinition[], defaultMissionId: string): string {
  return missions.some((mission) => mission.id === defaultMissionId)
    ? defaultMissionId
    : (missions[0]?.id ?? "");
}

export function MissionPanel({
  disabled,
  rover,
  missions,
  config,
  defaultMissionId,
  cancelMotion
}: MissionPanelProps) {
  const [selectedMissionId, setSelectedMissionId] = useState(
    () => initialMissionId(missions, defaultMissionId)
  );
  const [status, setStatus] = useState<MissionStatus>("idle");
  const [detail, setDetail] = useState("Choose a mission and acquire control to run it.");
  const cancelRequestedRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const selectedMission = missions.find((mission) => mission.id === selectedMissionId)
    ?? missions[0];

  const run = async () => {
    if (!selectedMission) return;
    cancelRequestedRef.current = false;
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setStatus("running");
    setDetail(selectedMission.runningDetail);
    try {
      await selectedMission.run({
        rover,
        config,
        signal: abortController.signal,
        report: (progress) => setDetail(progress.detail),
        say: speakEnglish
      });
      setStatus("completed");
      setDetail(`${selectedMission.title} completed.`);
    } catch (error) {
      if (cancelRequestedRef.current || abortController.signal.aborted) {
        setStatus("idle");
        setDetail("Mission cancelled. Rover stopped.");
      } else {
        setStatus("error");
        setDetail(error instanceof Error ? error.message : "Mission failed.");
      }
    } finally {
      if (abortControllerRef.current === abortController) abortControllerRef.current = null;
    }
  };

  const cancel = () => {
    cancelRequestedRef.current = true;
    abortControllerRef.current?.abort();
    setStatus("cancelling");
    setDetail("Stopping the active motion…");
    if (!cancelMotion()) {
      setStatus("error");
      setDetail("Local Server is not connected.");
    }
  };

  const selectMission = (id: string) => {
    setSelectedMissionId(id);
    setStatus("idle");
    setDetail("Ready to run the selected mission.");
  };

  const active = status === "running" || status === "cancelling";

  return (
    <article className="panel panel--mission">
      <div className="panel__heading">
        <div>
          <p className="section-label">SERVICE MISSIONS</p>
          <h2>{selectedMission?.title ?? "No missions registered"}</h2>
        </div>
        <span className={`mission-status mission-status--${status}`}>{status}</span>
      </div>

      <div className="mission-layout">
        <div>
          <label className="mission-selector">
            <span>Mission</span>
            <select
              aria-label="Mission"
              disabled={active || missions.length === 0}
              value={selectedMission?.id ?? ""}
              onChange={(event) => selectMission(event.target.value)}
            >
              {missions.map((mission) => (
                <option key={mission.id} value={mission.id}>{mission.title}</option>
              ))}
            </select>
          </label>
          <p className="mission-description">
            {selectedMission?.description ?? "Add a mission definition to missions/index.ts."}
          </p>
          {selectedMission && (
            <pre className="mission-code"><code>{selectedMission.script.join("\n")}</code></pre>
          )}
        </div>
        <div className="mission-controls">
          <p className={`mission-detail mission-detail--${status}`} role="status">{detail}</p>
          {active ? (
            <button className="button button--estop" disabled={status === "cancelling"} onClick={cancel}>
              Cancel mission
            </button>
          ) : (
            <button
              className="button button--primary"
              disabled={disabled || !selectedMission}
              onClick={() => void run()}
            >
              Run selected mission
            </button>
          )}
          {disabled && !active && (
            <small>Acquire control and clear the E-stop before running a mission.</small>
          )}
          <small>{config.team.serviceName} · {missions.length} mission(s) registered</small>
        </div>
      </div>
    </article>
  );
}
