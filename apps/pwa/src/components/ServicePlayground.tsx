import { useEffect, useMemo, useRef, useState } from "react";

import { serviceConfig, type CourseDestination } from "../config";
import courseSource from "../config/courseMarkers.ts?raw";
import { greetingStarterSettings } from "../config/greetingStarter";
import settingsSource from "../config/greetingStarter.ts?raw";
import { createGreetingMission } from "../missions/challengerStarter";
import missionSource from "../missions/challengerStarter.ts?raw";
import type { MissionProgress } from "../missions";
import { carryHelperMission } from "../missions/comeHere";
import followSource from "../missions/comeHere.ts?raw";
import { mobileReceptionistMission } from "../missions/mobileReceptionist";
import receptionistSource from "../missions/mobileReceptionist.ts?raw";
import type { Pose } from "../protocol";
import type { RoverAdapterType } from "../runtimeApi";
import { useVirtualPersonSimulation } from "../simulation/useVirtualPersonSimulation";
import { placeVirtualPerson, walkVirtualPerson, VIRTUAL_PERSON_WALK_DURATION_S } from "../simulation/virtualPerson";
import { simulatorApi } from "../simulatorApi";
import { useVirtualMarkerSimulation, type MarkerScene } from "../simulation/useVirtualMarkerSimulation";
import { speakEnglish } from "../speech";
import type { useRoverSocket } from "../useRoverSocket";
import { RoverMap } from "./RoverMap";
import { PlaygroundSceneEditor } from "./PlaygroundSceneEditor";
import { parseScene, scenePreset, SCENE_STORAGE_KEY } from "../simulation/playgroundScene";
import { HardwarePlaygroundInputs } from "./HardwarePlaygroundInputs";

type Props = { rover: ReturnType<typeof useRoverSocket>; adapterType: RoverAdapterType | null };
type Placement = "left" | "ahead" | "right" | "absent";
type Sample = "greeting" | "follow" | "receptionist";
type FollowDistance = "near" | "normal" | "far";

const runStart = missionSource.indexOf("  async run(");
const runEnd = missionSource.indexOf("\n  });", runStart);
const runSource = missionSource.slice(runStart, runEnd).split("\n");
const followStart = followSource.indexOf("export async function runFollowMe(");
const followEnd = followSource.indexOf("\nfunction arrivalWidth", followStart);
const followRunSource = followSource.slice(followStart, followEnd).split("\n");
const receptionistStart = receptionistSource.indexOf("export async function runMobileReceptionist(");
const receptionistEnd = receptionistSource.indexOf("\nfunction destinationMarker", receptionistStart);
const receptionistRunSource = receptionistSource.slice(receptionistStart, receptionistEnd).split("\n");
const destinations = serviceConfig.courseMarkers.filter((marker) => marker.destination !== "kitchen");

export function ServicePlayground({ rover, adapterType }: Props) {
  const [sample, setSample] = useState<Sample>(() => {
    const value = new URLSearchParams(window.location.search).get("sample");
    return value === "follow" || value === "receptionist" ? value : "greeting";
  });
  const [destination, setDestination] = useState<CourseDestination>("entrance");
  const [scene, setScene] = useState(() => scenePreset("front"));
  const [sceneNotice, setSceneNotice] = useState("");
  const [markerScene, setMarkerScene] = useState<MarkerScene>("destination");
  const [pathBlocked, setPathBlocked] = useState(false);
  const [settings, setSettings] = useState({ ...greetingStarterSettings });
  const [followDistance, setFollowDistance] = useState<FollowDistance>("normal");
  const [walking, setWalking] = useState(false);
  const [path, setPath] = useState<Pose[]>([]);
  const [placement, setPlacement] = useState<Placement>("absent");
  const [target, setTarget] = useState({ x: 1.35, y: 0 });
  const [active, setActive] = useState(false);
  const [hardwareReady, setHardwareReady] = useState(false);
  const [motionSteps, setMotionSteps] = useState<string[]>([]);
  const [startWhenOwned, setStartWhenOwned] = useState(false);
  const [progress, setProgress] = useState<MissionProgress>({ phase: "idle", detail: "Ready" });
  const [message, setMessage] = useState("");
  const [trace, setTrace] = useState<MissionProgress[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const sourceRef = useRef<HTMLPreElement | null>(null);
  const cancelMotionRef = useRef(rover.actions.cancelMotion);
  cancelMotionRef.current = rover.actions.cancelMotion;
  const pose = rover.state?.pose ?? null;
  const simulator = adapterType === "simulator";
  const hardware = adapterType === "websocket_rover" || adapterType === "ironx_network";
  const person = useVirtualPersonSimulation(pose, target, simulator && placement !== "absent");
  const sceneMarkers = destinations.map((marker) => ({ ...marker,
    xM: scene[marker.destination as "entrance" | "desk"].x,
    yM: scene[marker.destination as "entrance" | "desk"].y }));
  const destinationMarker = sceneMarkers.find((marker) => marker.destination === destination)!;
  const shownMarker = markerScene === "hidden" ? null : markerScene === "destination"
    ? destinationMarker : sceneMarkers.find((marker) => marker.id !== destinationMarker.id)!;
  const markerInput = useVirtualMarkerSimulation(pose, shownMarker,
    simulator && active && sample === "receptionist" && progress.phase !== "acquiring" && progress.phase !== "idle");
  const canStart = (simulator || (hardware && hardwareReady && sample !== "receptionist"))
    && rover.status === "connected" && !rover.control.estopLatched
    && (rover.control.isOwner || rover.control.ownerClientId === null);
  const liveService = useMemo(() => {
    const base = rover.serviceRover;
    const record = (text: string) => setMotionSteps((entries) => [...entries, `${new Date().toLocaleTimeString("en-US")} ${text}`].slice(-30));
    return { ...base,
      onPerson: (listener: Parameters<typeof base.onPerson>[0]) => base.onPerson((event) => {
        if (event.source === "camera") listener(event);
      }),
      onMarker: (listener: Parameters<typeof base.onMarker>[0]) => base.onMarker((event) => {
        if (event.source === "camera") listener(event);
      }),
      move: async (distance: number, speed?: number) => {
        record(`Move requested: ${distance} m`);
        try { await base.move(distance, speed); record("Move completed"); }
        catch (cause) { record("Move stopped or failed"); throw cause; }
      },
      turn: async (angle: number, speed?: number) => {
        record(`Turn requested: ${angle.toFixed(1)} deg`);
        try { await base.turn(angle, speed); record("Turn completed"); }
        catch (cause) { record("Turn stopped or failed"); throw cause; }
      },
      stop: async (reason?: string) => { record(`Stop: ${reason ?? "service"}`); await base.stop(reason); }
    };
  }, [rover.serviceRover]);

  useEffect(() => {
    if (!walking || !simulator || placement === "absent" || !pose) return;
    const origin = target;
    const heading = Math.atan2(target.y - pose.y, target.x - pose.x);
    const started = performance.now();
    const timer = window.setInterval(() => {
      const elapsed = (performance.now() - started) / 1000;
      setTarget(walkVirtualPerson(origin, heading, elapsed));
      if (elapsed >= VIRTUAL_PERSON_WALK_DURATION_S) setWalking(false);
    }, 50);
    return () => window.clearInterval(timer);
  }, [walking, simulator, placement]);

  useEffect(() => {
    if (!pose || !active) return;
    setPath((entries) => {
      const last = entries.at(-1);
      return last && Math.hypot(pose.x - last.x, pose.y - last.y) < .008
        ? entries : [...entries, pose].slice(-200);
    });
  }, [pose?.x, pose?.y, active]);

  useEffect(() => {
    if (!active || !simulator || sample === "greeting") return;
    let disposed = false;
    const refresh = async () => {
      try {
        await simulatorApi.setFrontObstacle(pathBlocked ? "BLOCKED" : "CLEAR", "healthy");
      } catch (cause) {
        if (!disposed) {
          stop();
          setProgress({ phase: "error", detail: cause instanceof Error ? cause.message : "Scene unavailable" });
        }
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [active, simulator, sample, pathBlocked]);

  const stop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStartWhenOwned(false);
    rover.actions.cancelMotion();
    setActive(false);
    setWalking(false);
    setProgress({ phase: "stopped", detail: "Service stopped" });
  };

  useEffect(() => () => {
    if (abortRef.current) {
      abortRef.current.abort();
      cancelMotionRef.current();
    }
  }, []);

  useEffect(() => {
    if (!active || (rover.status === "connected" && rover.control.isOwner
      && !rover.control.estopLatched && (simulator || (hardware && hardwareReady)))) return;
    stop();
  }, [active, rover.status, rover.control.isOwner, rover.control.estopLatched, simulator, hardware, hardwareReady]);

  const run = async () => {
    if (!canStart || !rover.control.isOwner || abortRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setActive(true);
    setMessage("");
    setTrace([]);
    setMotionSteps([]);
    setPath([]);
    setProgress({ phase: "idle", detail: hardware ? "Preparing live trial" : "Preparing the scene" });
    try {
      if (simulator && sample === "receptionist") {
        setMarkerScene(scene.hidden ? "hidden" : "destination");
        setPathBlocked(scene.blocked);
        await simulatorApi.placePose({ ...scene.origin,
          markers: sceneMarkers.map((marker) => ({ id: marker.id, x_m: marker.xM, y_m: marker.yM })) });
        controller.signal.throwIfAborted();
        setTarget(scene.visitor);
        setPlacement("ahead");
      }
      if (simulator && sample !== "greeting") {
        const blocked = sample === "receptionist" ? scene.blocked : pathBlocked;
        const prepared = await simulatorApi.setFrontObstacle(blocked ? "BLOCKED" : "CLEAR", "healthy");
        controller.signal.throwIfAborted();
        if (prepared.front_obstacle.latched && !blocked) {
          await simulatorApi.clearFrontObstacle("playground simulated follow area verified clear");
          controller.signal.throwIfAborted();
        }
        if (sample !== "receptionist" && placement === "absent" && pose) {
          setTarget(placeVirtualPerson(pose, 1.35, 0));
          setPlacement("ahead");
        }
      }
      const mission = sample === "receptionist" ? mobileReceptionistMission
        : sample === "follow" ? carryHelperMission : createGreetingMission(settings);
      await mission.run({
        rover: hardware ? liveService : rover.serviceRover,
        config: serviceConfig,
        signal: controller.signal,
        report: (next) => {
          if (controller.signal.aborted) return;
          setProgress(next);
          setTrace((entries) => entries.at(-1)?.detail === next.detail
            ? entries : [...entries, next].slice(-20));
        },
        say: (text) => {
          if (!controller.signal.aborted) { setMessage(text); speakEnglish(text); }
        }
      }, { intent: sample === "receptionist" ? "guide_visitor" : sample === "follow" ? "follow_person" : "greet_person", destination, followDistance });
    } catch (cause) {
      if (!controller.signal.aborted) {
        rover.actions.cancelMotion();
        const detail = cause instanceof Error ? cause.message : "Service failed";
        if (sample === "receptionist" && detail === "front_obstacle_blocked") {
          setMessage("The path is not clear. I am stopping.");
          setProgress({ phase: "waiting", detail: `Path to ${destinationMarker.label} is not clear` });
        } else setProgress({ phase: "error", detail });
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setActive(false);
        setWalking(false);
      }
    }
  };

  useEffect(() => {
    if (!startWhenOwned || !rover.control.isOwner) return;
    setStartWhenOwned(false);
    void run();
  }, [startWhenOwned, rover.control.isOwner]);

  const enter = (next: Placement) => {
    if (!simulator || !pose) return;
    setPlacement(next);
    setWalking(false);
    if (next !== "absent") {
      setTarget(placeVirtualPerson(pose, 1.35, next === "left" ? 0.3 : next === "right" ? -0.3 : 0));
    }
  };

  const highlighted = (line: string) => {
    if (sample === "receptionist") {
      if (progress.phase === "acquiring") return line.includes("waitForPerson");
      if (progress.phase === "waiting") return line.includes(progress.detail.startsWith("Path") ? "destination path is not clear" : "observations.next");
      if (progress.phase === "aligning") return line.includes(progress.detail.startsWith("Searching") ? "rover.turn(SEARCH_TURN_DEG" : "rover.turn(turnDeg");
      if (progress.phase === "approaching") return line.includes("rover.move(moveM");
      if (progress.phase === "arrived") return line.includes("destination marker reached");
      if (progress.phase === "lost") return line.includes("stopAfterFailure(rover, `destination");
      return false;
    }
    if (sample === "follow") {
      if (progress.phase === "acquiring") return line.includes("observations.next");
      if (progress.phase === "lost") return line.includes("rover.stop(\"person");
      if (progress.phase === "following") return progress.detail === "Following you"
        ? line.includes("rover.move(FOLLOW_MOVE_STEP_M") : line.includes("follow distance reached");
    }
    if (progress.phase === "waiting") return line.includes("waitForPerson");
    if (progress.phase === "aligning") return line.includes("rover.turn");
    if (progress.phase === "arrived") return line.includes("say(settings.greeting)");
    return false;
  };

  useEffect(() => {
    const code = sourceRef.current;
    const line = code?.querySelector<HTMLElement>(".is-executing");
    if (code && line) {
      code.scrollTop += line.getBoundingClientRect().top - code.getBoundingClientRect().top - 100;
    }
  }, [progress.phase, progress.detail, sample]);

  return (
    <section className="playground" aria-label="Service playground">
      <div className="playground-heading">
        <div className="playground-segments" role="tablist" aria-label="Service sample">
          {(["greeting", "follow", "receptionist"] as const).map((id) => <button key={id} role="tab"
            aria-selected={sample === id} disabled={active || startWhenOwned} onClick={() => {
              setSample(id); setMessage(""); setTrace([]); setWalking(false); setPath([]); setPathBlocked(false);
              setProgress({ phase: "idle", detail: "Ready" });
              const url = new URL(window.location.href); url.searchParams.set("sample", id);
              window.history.replaceState(null, "", url);
            }}>{id === "greeting" ? "Person greeting" : id === "follow" ? "Follow helper" : "Marker guide"}</button>)}
        </div>
        <div className="playground-actions">
          <a href="/lab">All Lab tools</a>
          <span className="playground-note">{simulator ? "Simulator" : hardware ? "Live rover · WebSocket" : "Adapter unavailable"}</span>
          <button className="button button--estop" disabled={rover.status !== "connected"}
            onClick={rover.actions.estop}>Emergency stop</button>
        </div>
      </div>
      {!simulator && !hardware && <p role="status">{adapterType === null ? "Checking connection..." : "Live trials require a WebSocket rover or iron-X network adapter."}</p>}
      {hardware && sample === "receptionist" && <p role="status">Physical marker guidance is not enabled in this MVP. Camera marker observations remain available.</p>}
      {rover.control.estopLatched && <div className="estop-banner">
        <strong>Emergency stop is active</strong>
        <button disabled={rover.status !== "connected" || !rover.control.isOwner} onClick={rover.actions.clearEstop}>Clear E-stop</button>
      </div>}
      {!rover.control.isOwner && rover.control.ownerClientId !== null && <p role="status">Another controller is using the rover.</p>}
      <div className="playground-grid">
        <div className="playground-experience">
          <section className="greeting-service" aria-label="Service experience">
            <span className="section-label">{sample === "receptionist" ? "RECEPTION DESK" : sample === "follow" ? "CARRY HELPER" : "GREETING SERVICE"}</span>
            <h3>{message || (sample === "receptionist" ? (active ? `Let me guide you to ${destinationMarker.label}.` : "Where would you like to go?") : sample === "follow" ? (active ? "I'll carry it. Lead the way." : "Need a hand carrying something?") : (active ? "I'm here to welcome you." : "Welcome"))}</h3>
            {sample === "receptionist" && <label className="playground-destination">Destination
              <select value={destination} disabled={active || startWhenOwned} onChange={(event) => setDestination(event.target.value as CourseDestination)}>
                {destinations.map((marker) => <option key={marker.id} value={marker.destination}>{marker.label}</option>)}
              </select>
            </label>}
            <p role="status">{progress.detail}</p>
            <div className="playground-actions">
              <button className="button button--primary" disabled={!canStart || active || startWhenOwned}
                onClick={() => {
                  if (rover.control.isOwner) void run();
                  else { setStartWhenOwned(true); rover.actions.acquire(); }
                }}>{sample === "receptionist" ? "Guide me" : sample === "follow" ? "Follow me" : "Start greeting"}</button>
              <button className="button button--quiet" disabled={!active && !startWhenOwned} onClick={stop}>Stop</button>
            </div>
          </section>
          {hardware && <HardwarePlaygroundInputs rover={rover} onReady={setHardwareReady} />}
          {simulator && <section className="playground-scene" aria-label="Try a situation">
            {sample === "receptionist" ? <>
              <h3>Destination marker</h3>
              <div className="playground-segments" role="group" aria-label="Marker visibility">
                {(["destination", "wrong", "hidden"] as const).map((scene) => <button key={scene} disabled={!simulator}
                  aria-pressed={markerScene === scene} onClick={() => setMarkerScene(scene)}>
                  {scene === "destination" ? "Correct marker" : scene === "wrong" ? "Other marker" : "Hide marker"}
                </button>)}
              </div>
              <label className="playground-obstacle"><input type="checkbox" checked={pathBlocked} disabled={!simulator}
                onChange={(event) => setPathBlocked(event.target.checked)} />Path blocked</label>
            </> : <>
            <h3>Visitor</h3>
            <div className="playground-segments" role="group" aria-label="Visitor location">
              {(["absent", "left", "ahead", "right"] as const).map((id) => (
                <button key={id} aria-pressed={placement === id} disabled={!simulator || !pose}
                  onClick={() => enter(id)}>{id === "absent" ? "Outside view" : id === "ahead" ? "In front" : id === "left" ? "On the left" : "On the right"}</button>
              ))}
            </div>
            </>}
            {sample === "follow" && <div className="playground-actions">
              <button className="button button--primary" disabled={!simulator || placement === "absent"}
                onClick={() => setWalking(!walking)}>{walking ? "Stand still" : "Walk ahead"}</button>
              <span className="playground-note">{placement === "absent" ? "Outside view" : walking ? "Walking" : "Standing"}</span>
            </div>}
            <RoverMap pose={sample === "receptionist" && progress.phase === "idle" ? scene.origin : pose} path={path}
              person={sample === "receptionist" ? scene.visitor : placement === "absent" ? null : target}
              focusTarget={sample === "receptionist" ? { x: destinationMarker.xM, y: destinationMarker.yM } : null}
              markers={sample === "receptionist" ? sceneMarkers.map((marker) => ({
                id: marker.id, label: marker.label, x: marker.xM, y: marker.yM,
                selected: marker.id === destinationMarker.id, visible: marker.id === shownMarker?.id
              })) : []} />
            {person.error && <p role="alert">{person.error}</p>}
            {sample === "receptionist" && markerInput.error && <p role="alert">{markerInput.error}</p>}
          </section>}
        </div>
        <div className="playground-development">
          {simulator && sample === "receptionist" && <PlaygroundSceneEditor scene={scene}
            disabled={active || startWhenOwned || !simulator}
            onChange={(next) => { setScene(next); setSceneNotice(""); setPath([]);
              setMarkerScene(next.hidden ? "hidden" : "destination"); setPathBlocked(next.blocked);
              setProgress({ phase: "idle", detail: "Ready" }); setMessage(""); }}
            onSave={() => { try { localStorage.setItem(SCENE_STORAGE_KEY, JSON.stringify(scene)); setSceneNotice("Scene saved in this browser"); }
              catch { setSceneNotice("Scene could not be saved"); } }}
            onLoad={() => { try { const saved = localStorage.getItem(SCENE_STORAGE_KEY);
              if (!saved) throw new Error("No saved scene");
              const next = parseScene(saved); setScene(next); setMarkerScene(next.hidden ? "hidden" : "destination");
              setPathBlocked(next.blocked); setPath([]); setMessage(""); setProgress({ phase: "idle", detail: "Ready" });
              setSceneNotice("Saved scene loaded");
            } catch (cause) { setSceneNotice(cause instanceof Error ? cause.message : "Scene could not be loaded"); } }}
            notice={sceneNotice} />}
          <section className="playground-settings">
            <h3>Preview settings</h3>
            <span className="playground-note">Browser preview only; reload restores file values.</span>
            {sample === "greeting" ? <><label>Greeting<input value={settings.greeting} disabled={active || startWhenOwned} maxLength={160}
              onChange={(event) => setSettings({ ...settings, greeting: event.target.value })} /></label>
            <label>Maximum turn: {settings.maxTurnDeg} degrees<input type="range" min="0" max="30" step="1"
              value={settings.maxTurnDeg} disabled={active || startWhenOwned}
              onChange={(event) => setSettings({ ...settings, maxTurnDeg: Number(event.target.value) })} /></label>
            <details><summary>Save defaults in config/greetingStarter.ts</summary><pre>{settingsSource}</pre></details></> : sample === "receptionist" ? <>
              <p>{destinationMarker.label} / marker {destinationMarker.id}</p>
              <details><summary>Destinations in config/courseMarkers.ts</summary><pre>{courseSource}</pre></details>
              <details><summary>Approach settings in missions/mobileReceptionist.ts</summary>
                <pre>{receptionistSource.slice(receptionistSource.indexOf("const DEFAULT_DESTINATION"), receptionistSource.indexOf("export const mobileReceptionistMission"))}</pre>
              </details>
            </> : <>
              <label>Following distance<select value={followDistance} disabled={active || startWhenOwned}
                onChange={(event) => setFollowDistance(event.target.value as FollowDistance)}>
                <option value="near">Near</option><option value="normal">Normal</option><option value="far">Far</option>
              </select></label>
              <details><summary>Distance defaults in missions/comeHere.ts</summary>
                <pre>{followSource.slice(followSource.indexOf("const FOLLOW_DISTANCE_WIDTHS"), followSource.indexOf("const CAMERA_FOLLOW_DISTANCE_WIDTHS"))}</pre>
              </details>
            </>}
          </section>
          <section className="playground-code" aria-label="Service implementation">
            <h3>{sample === "receptionist" ? "missions/mobileReceptionist.ts" : sample === "follow" ? "missions/comeHere.ts / runFollowMe" : "missions/challengerStarter.ts"}</h3>
            <pre ref={sourceRef} className="playground-source"><code>{(sample === "receptionist" ? receptionistRunSource : sample === "follow" ? followRunSource : runSource).map((line, i) => <span className={highlighted(line) ? "is-executing" : ""} key={i}>{line}{"\n"}</span>)}</code></pre>
          </section>
          <section className="playground-trace" aria-label="Service steps">
            <h3>This run</h3>
            <ol>{trace.map((entry, i) => <li key={i}>{entry.detail}</li>)}</ol>
            {hardware && <><h3>Motion requests and outcomes</h3><ol>{motionSteps.map((entry, i) => <li key={i}>{entry}</li>)}</ol></>}
          </section>
        </div>
      </div>
    </section>
  );
}
