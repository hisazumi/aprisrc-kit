import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CourseDestination, ServiceConfig } from "../config";
import type { MissionDefinition, MissionProgress, ServiceRover } from "../missions";
import type { RoverAdapterType } from "../runtimeApi";
import { simulatorApi } from "../simulatorApi";
import { speakEnglish } from "../speech";

type ReceptionistStatus = "idle" | "starting" | "running" | "completed" | "error";
type CameraFacing = "user" | "environment";

interface MobileReceptionistServiceProps {
  connected: boolean;
  isOwner: boolean;
  controlAvailable: boolean;
  estopLatched: boolean;
  adapterType: RoverAdapterType | null;
  rover: ServiceRover;
  mission: MissionDefinition | undefined;
  config: ServiceConfig;
  onAcquireControl: () => void;
  onReleaseControl: () => void;
  onCancelMotion: () => boolean;
  onEmergencyStop: () => void;
  onPathClearanceChange?: (confirmed: boolean) => boolean;
  onCameraFacingChange?: (facing: CameraFacing) => void;
  onVisionActiveChange?: (active: boolean) => void;
  runScenario?: (id: string) => Promise<unknown>;
  stopScenario?: () => Promise<unknown>;
  speak?: (text: string) => void;
}

const SUPERVISED_MOTION_MS = 30_000;
const PATH_CLEARANCE_HEARTBEAT_MS = 400;
const RECEPTIONIST_SCENARIO_ID = "mobile-receptionist";
const ignorePathClearance = () => false;

export function MobileReceptionistService({
  connected,
  isOwner,
  controlAvailable,
  estopLatched,
  adapterType,
  rover,
  mission,
  config,
  onAcquireControl,
  onReleaseControl,
  onCancelMotion,
  onEmergencyStop,
  onPathClearanceChange = ignorePathClearance,
  onCameraFacingChange,
  onVisionActiveChange,
  runScenario = simulatorApi.runScenario,
  stopScenario = simulatorApi.stopScenario,
  speak = speakEnglish
}: MobileReceptionistServiceProps) {
  const [status, setStatus] = useState<ReceptionistStatus>("idle");
  const [destination, setDestination] = useState<CourseDestination>("entrance");
  const [progress, setProgress] = useState<MissionProgress>({
    phase: "idle",
    detail: "Ready to greet a visitor"
  });
  const [error, setError] = useState("");
  const [startWhenOwned, setStartWhenOwned] = useState(false);
  const [pathClearUntilMs, setPathClearUntilMs] = useState<number | null>(null);
  const [clockMs, setClockMs] = useState(() => Date.now());
  const abortRef = useRef<AbortController | null>(null);
  const simulatorMode = adapterType === "simulator";
  const active = status === "starting" || status === "running";

  const pathClearSeconds = pathClearUntilMs === null
    ? 0
    : Math.max(0, Math.ceil((pathClearUntilMs - clockMs) / 1000));

  const statusNote = useMemo(() => {
    if (!connected) return "Connecting to the Local Server";
    if (adapterType === null) return "Checking the rover adapter";
    if (estopLatched) return "Emergency stop is active";
    if (simulatorMode) return "Simulator connected";
    if (isOwner) return "UGV02 service control active";
    if (!controlAvailable) return "Another controller is using the rover";
    return "UGV02 ready";
  }, [adapterType, connected, controlAvailable, estopLatched, isOwner, simulatorMode]);

  useEffect(() => {
    if (pathClearUntilMs === null) return;
    onPathClearanceChange(true);
    const heartbeat = window.setInterval(
      () => onPathClearanceChange(true),
      PATH_CLEARANCE_HEARTBEAT_MS
    );
    const clock = window.setInterval(() => setClockMs(Date.now()), 250);
    const expiry = window.setTimeout(
      () => setPathClearUntilMs(null),
      Math.max(0, pathClearUntilMs - Date.now())
    );
    return () => {
      window.clearInterval(heartbeat);
      window.clearInterval(clock);
      window.clearTimeout(expiry);
      onPathClearanceChange(false);
    };
  }, [onPathClearanceChange, pathClearUntilMs]);

  useEffect(() => {
    if (pathClearUntilMs !== null && (!active || simulatorMode || !isOwner || estopLatched)) {
      setPathClearUntilMs(null);
    }
  }, [active, estopLatched, isOwner, pathClearUntilMs, simulatorMode]);

  const stopService = useCallback(async (releaseControl: boolean) => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStartWhenOwned(false);
    setPathClearUntilMs(null);
    onCancelMotion();
    if (simulatorMode) await stopScenario().catch(() => undefined);
    setStatus("idle");
    setProgress({ phase: "idle", detail: "Ready to greet a visitor" });
    onCameraFacingChange?.("user");
    onVisionActiveChange?.(false);
    if (releaseControl && isOwner) onReleaseControl();
  }, [isOwner, onCameraFacingChange, onCancelMotion, onReleaseControl, onVisionActiveChange, simulatorMode, stopScenario]);

  useEffect(() => () => {
    abortRef.current?.abort();
    onPathClearanceChange(false);
    onVisionActiveChange?.(false);
  }, [onPathClearanceChange, onVisionActiveChange]);

  useEffect(() => {
    if (!estopLatched || !active) return;
    abortRef.current?.abort();
    abortRef.current = null;
    setStatus("error");
    setError("Emergency stop is active");
    setProgress({ phase: "error", detail: "Service stopped by emergency stop" });
    onVisionActiveChange?.(false);
  }, [active, estopLatched, onVisionActiveChange]);

  const runMission = useCallback(async () => {
    if (!mission || abortRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("running");
    setError("");
    onCameraFacingChange?.("user");
    if (!simulatorMode) onVisionActiveChange?.(true);

    const missionPromise = mission.run({
      rover,
      config,
      signal: controller.signal,
      report: (nextProgress) => {
        setProgress(nextProgress);
        if (["waiting", "aligning", "approaching"].includes(nextProgress.phase)) {
          onCameraFacingChange?.("environment");
        }
      },
      say: speak
    }, {
      intent: "guide_visitor",
      destination,
      followDistance: "normal"
    });

    try {
      if (simulatorMode) {
        try {
          await runScenario(RECEPTIONIST_SCENARIO_ID);
        } catch (cause) {
          controller.abort();
          await missionPromise.catch(() => undefined);
          throw cause;
        }
      }
      await missionPromise;
      if (!controller.signal.aborted) {
        setStatus("completed");
        onVisionActiveChange?.(false);
      }
    } catch (cause) {
      controller.abort();
      onCancelMotion();
      const detail = cause instanceof Error ? cause.message : "Receptionist service failed";
      setError(detail);
      setProgress({ phase: "error", detail });
      setStatus("error");
      onVisionActiveChange?.(false);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [config, destination, mission, onCameraFacingChange, onCancelMotion, onVisionActiveChange, rover, runScenario, simulatorMode, speak]);

  useEffect(() => {
    if (!startWhenOwned || !isOwner) return;
    setStartWhenOwned(false);
    void runMission();
  }, [isOwner, runMission, startWhenOwned]);

  const startService = () => {
    if (!connected || adapterType === null || estopLatched || !controlAvailable || !mission) return;
    setStatus("starting");
    setProgress({ phase: "acquiring", detail: "Acquiring rover control" });
    if (isOwner) void runMission();
    else {
      setStartWhenOwned(true);
      onAcquireControl();
    }
  };

  const authorizePath = () => {
    if (!active || simulatorMode || !isOwner || estopLatched) return;
    const now = Date.now();
    setClockMs(now);
    setPathClearUntilMs(now + SUPERVISED_MOTION_MS);
  };

  return (
    <section className={`receptionist-service receptionist-service--${progress.phase}`}>
      <div className="receptionist-service__statusbar">
        <div>
          <span className={`carry-service__signal ${connected ? "is-online" : ""}`} />
          <strong>{statusNote}</strong>
        </div>
        <span>{adapterType ?? "detecting"}</span>
      </div>

      <div className="receptionist-service__body">
        <div>
          <p className="section-label">MOBILE RECEPTIONIST</p>
          <h2>{progress.phase === "arrived" ? "Destination reached" : progress.detail}</h2>
          <p className="receptionist-service__summary">
            {simulatorMode
              ? "Run the complete visitor-to-destination flow with deterministic simulated observations."
              : "The phone confirms a visitor, switches to the rear camera, and guides the rover toward a destination QR marker."}
          </p>
        </div>

        <label className="receptionist-service__destination">
          <span>Destination</span>
          <select
            value={destination}
            disabled={active || simulatorMode}
            onChange={(event) => setDestination(event.target.value as CourseDestination)}
          >
            {config.courseMarkers.map((marker) => (
              <option key={marker.destination} value={marker.destination}>
                {marker.label} · marker {marker.id}
              </option>
            ))}
          </select>
          {simulatorMode && <small>The reference scenario uses Entrance marker 1.</small>}
        </label>

        {!simulatorMode && active && (
          <div className="path-clearance">
            <button
              className={`button path-clearance__button ${pathClearSeconds > 0 ? "is-authorized" : ""}`}
              disabled={!isOwner || estopLatched}
              onClick={pathClearSeconds > 0 ? () => setPathClearUntilMs(null) : authorizePath}
            >
              {pathClearSeconds > 0
                ? `Movement enabled · ${pathClearSeconds} s`
                : "Allow movement for 30 s"}
            </button>
            <span>Confirm that the floor ahead is clear. Tap again to revoke.</span>
          </div>
        )}

        {error && <p className="receptionist-service__error" role="alert">{error}</p>}

        <div className="receptionist-service__actions">
          {!active && status !== "completed" ? (
            <button
              className="button button--primary"
              disabled={!connected || adapterType === null || estopLatched || !controlAvailable || !mission}
              onClick={startService}
            >
              {simulatorMode ? "Run simulated service" : "Start receptionist"}
            </button>
          ) : status === "completed" ? (
            <button className="button button--primary" onClick={startService}>Run again</button>
          ) : (
            <button className="button button--stop" onClick={() => void stopService(false)}>
              Stop service
            </button>
          )}
          <button
            className="button button--estop"
            disabled={!connected}
            onClick={onEmergencyStop}
          >
            Emergency stop
          </button>
          {isOwner && !active && (
            <button className="button button--quiet" onClick={() => void stopService(true)}>
              Release control
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
