import { useCallback, useEffect, useState } from "react";

import type { MarkerEvent, PersonEvent } from "../protocol";
import type { useRoverSocket } from "../useRoverSocket";
import { CameraPreview } from "./CameraPreview";
import { MotionTrace } from "./MotionTrace";

interface Props {
  rover: ReturnType<typeof useRoverSocket>;
  onReady: (ready: boolean) => void;
}

export function HardwarePlaygroundInputs({ rover, onReady }: Props) {
  const [visionReady, setVisionReady] = useState(false);
  const [person, setPerson] = useState<PersonEvent | null>(null);
  const [marker, setMarker] = useState<MarkerEvent | null>(null);
  const [clock, setClock] = useState(Date.now());
  const [armedUntil, setArmedUntil] = useState(0);
  const connected = rover.status === "connected" && rover.state?.connected === true;
  const personFresh = person?.status === "detected" && clock - person.capturedAt * 1000 < 1800;
  const telemetryFresh = !!rover.state && clock - rover.state.timestamp * 1000 < 2000;
  const eligible = connected && telemetryFresh && visionReady && !!personFresh
    && rover.control.isOwner && !rover.control.estopLatched;
  const ready = eligible && personFresh && armedUntil > clock && rover.frontObstacle?.state === "CLEAR";
  const observe = useCallback((input: Parameters<typeof rover.actions.observe>[0]) => {
    return input.source === "camera" && rover.actions.observe(input);
  }, [rover.actions.observe]);

  useEffect(() => rover.serviceRover.onPerson((event) => {
    if (event.source === "camera") setPerson(event);
  }), [rover.serviceRover]);
  useEffect(() => rover.serviceRover.onMarker((event) => {
    if (event.source === "camera") setMarker(event);
  }), [rover.serviceRover]);
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { onReady(!!ready); }, [ready, onReady]);
  useEffect(() => {
    if (!eligible || rover.frontObstacle?.state === "BLOCKED") setArmedUntil(0);
  }, [eligible, rover.frontObstacle?.state]);
  useEffect(() => {
    if (!eligible || armedUntil <= clock) return;
    rover.actions.setPathClearance(true);
    const timer = window.setInterval(() => rover.actions.setPathClearance(true), 300);
    return () => {
      window.clearInterval(timer);
      rover.actions.setPathClearance(false);
    };
    // Clock updates must not restart the clearance heartbeat.
  }, [eligible, armedUntil, armedUntil > clock, rover.actions.setPathClearance]);

  const value = (n: number | undefined) => n === undefined ? "—" : n.toFixed(2);
  return <section className="hardware-playground" aria-label="Live rover inputs">
    <h3>Live rover · supervised trial</h3>
    <CameraPreview variant="service" initialFacing="user" onObservation={observe}
      onPerceptionReadyChange={setVisionReady} />
    <div className="playground-actions">
      {!rover.control.isOwner && <button className="button button--quiet"
        disabled={!connected || rover.control.ownerClientId !== null} onClick={rover.actions.acquire}>Acquire control</button>}
      <button className="button button--primary" disabled={!eligible}
        onClick={() => { setClock(Date.now()); setArmedUntil(Date.now() + 30_000); }}>
        {armedUntil > clock ? `Renew clear-path confirmation · ${Math.ceil((armedUntil - clock) / 1000)} s` : "Confirm clear path · 30 s"}
      </button>
      <button className="button button--quiet" disabled={armedUntil <= clock} onClick={() => setArmedUntil(0)}>Disable motion</button>
    </div>
    <p role="status">{!connected ? "Waiting for rover connection" : !telemetryFresh ? "Rover feedback is stale"
      : !visionReady ? "Start live camera perception" : !rover.control.isOwner ? "Acquire control before a trial"
        : rover.control.estopLatched ? "Emergency stop is active" : !personFresh ? "Waiting for a fresh camera person observation"
          : armedUntil <= clock ? "Clear-path confirmation required" : rover.frontObstacle?.state !== "CLEAR"
            ? "Waiting for authoritative front safety CLEAR" : "Ready for an explicit service start"}</p>
    <dl className="hardware-observations">
      <div><dt>Person · accepted camera event</dt><dd>{person ? `${person.status} · confidence ${value(person.confidence)} · age ${Math.max(0, clock - person.capturedAt * 1000).toFixed(0)} ms` : "None"}</dd></div>
      <div><dt>Bearing / image width</dt><dd>{value(person?.bearingDeg)} deg / {value(person?.width)}</dd></div>
      <div><dt>Marker · accepted camera event</dt><dd>{marker ? `ID ${marker.markerId} · ${marker.status} · age ${Math.max(0, clock - marker.capturedAt * 1000).toFixed(0)} ms` : "None"}</dd></div>
      <div><dt>Marker relative x / y</dt><dd>{value(marker?.relativeXM)} / {value(marker?.relativeYM)} m</dd></div>
      <div><dt>Front safety</dt><dd>{rover.frontObstacle?.state ?? "UNKNOWN"}{rover.frontObstacle?.latched ? " · latched" : ""}</dd></div>
      <div><dt>Pose estimate x / y / yaw</dt><dd>{connected ? `${value(rover.state?.pose.x)} / ${value(rover.state?.pose.y)} m / ${value(rover.state?.pose.yaw)} rad${telemetryFresh ? "" : " · stale"}` : "Unavailable"}</dd></div>
    </dl>
    <details><summary>Server observations and decisions</summary>
      <pre>{JSON.stringify(rover.scenarioEvents?.slice(0, 6) ?? [], null, 2)}</pre>
    </details>
    {!connected && <p role="status">No connected-rover telemetry</p>}
    <MotionTrace state={connected ? rover.state : null} />
  </section>;
}
