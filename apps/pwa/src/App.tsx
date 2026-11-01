import { StudentServicePanel } from "./components/StudentServicePanel";
import { simulatorApi } from "./simulatorApi";
import { StudentScenePanel, StudentSceneExecution } from "./components/StudentScenePanel";
import { parseStudentScene, studentScenes } from "./simulation/studentScene";
import { useStudentScene } from "./simulation/useStudentScene";
import { useManualPerson } from "./simulation/useManualPerson";
import { ManualPersonPanel } from "./components/ManualPersonPanel";
import { useCallback, useEffect, useMemo, useState } from "react";
import { selectFollowProfile } from "./missions/followProfile";
import { ManualPathClearance } from "./components/ManualPathClearance";

import { CameraPreview } from "./components/CameraPreview";
import { HumanInteractionPanel } from "./components/HumanInteractionPanel";
import { Joystick } from "./components/Joystick";
import { MissionPanel } from "./components/MissionPanel";
import { MotionTrace, type CommandedVelocity } from "./components/MotionTrace";
import { RoverMap } from "./components/RoverMap";
import { SimulatorScenarioPanel } from "./components/SimulatorScenarioPanel";
import { serviceConfig } from "./config";
import { missionRegistry } from "./missions";
import type { Pose } from "./protocol";
import { runtimeApi, type RoverAdapterType } from "./runtimeApi";
import { projectVirtualPerson } from "./simulation/virtualPerson";
import { useVirtualPersonSimulation } from "./simulation/useVirtualPersonSimulation";
import { useRoverSocket } from "./useRoverSocket";
import { serviceCatalog } from "./service/catalog";
import { useVirtualMarkerSimulation } from "./simulation/useVirtualMarkerSimulation";

import { viewForPathname, serviceModeForSearch, viewUrl, type PwaView } from "./navigation";
export { viewForPathname, serviceModeForSearch } from "./navigation";

const viewContent: Record<PwaView, { eyebrow: string; title: string; description: string }> = {
  app: {
    eyebrow: "APRIS 2026 · SERVICE APP",
    title: "Rover Service",
    description: "Prototype the smartphone experience with camera input and high-level rover missions."
  },
  console: {
    eyebrow: "APRIS 2026 · OPERATOR CONSOLE",
    title: "Rover Console",
    description: "Observe the rover, take manual control, and inspect safety state without editing service UI."
  },
  lab: {
    eyebrow: "APRIS 2026 · PLAYGROUND",
    title: "Rover Playground",
    description: "Use the service UI and Simulator tools together while developing without hardware."
  }
};

const formatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});

function number(value: number | undefined): string {
  return formatter.format(value ?? 0);
}

export function App() {
  const view = viewForPathname(window.location.pathname);
  const serviceMode = serviceModeForSearch(window.location.search);
  const studentLab = view === "lab";
  const selectedService = serviceCatalog[serviceMode];
  const content = viewContent[view];
  const [adapterType, setAdapterType] = useState<RoverAdapterType | null>(null);
  const rover = useRoverSocket(selectFollowProfile(adapterType, import.meta.env.VITE_IRONX_CONTINUOUS_FOLLOW));
  useEffect(() => {
    const canonical = viewUrl(view, serviceMode, window.location.search);
    if (window.location.pathname + window.location.search !== canonical) {
      window.history.replaceState(null, "", canonical + window.location.hash);
    }
  }, [view, serviceMode]);
  const [path, setPath] = useState<Pose[]>([]);
  const [manualCommand, setManualCommand] = useState<CommandedVelocity>({
    sampleId: 0,
    vx: 0,
    wz: 0,
  });
  const [studentScene, setStudentScene] = useState(() => structuredClone(studentScenes[0]));
  const sceneRun = useStudentScene();
  const [studentRunning, setStudentRunning] = useState(false);
  const [testMode, setTestMode] = useState<"manual" | "scenario">("manual");
  const [testSpeech, setTestSpeech] = useState<{ id: number; text: string }>();
  const studentSimulator = studentLab && adapterType === "simulator";
  const pose = rover.state?.pose ?? null;
  const [markersVisible, setMarkersVisible] = useState(false);
  const [markerReady, setMarkerReady] = useState(false);
  const [markers, setMarkers] = useState(() => serviceConfig.courseMarkers.filter(m => m.destination !== "kitchen")
    .map((m, i) => ({ ...m, xM: 1.8 + i * .7, yM: i ? -.6 : .6 })));
  const markerEnabled = studentSimulator && markerReady && rover.control.isOwner;
  const entranceInput = useVirtualMarkerSimulation(pose, markersVisible ? markers[0] : null, markerEnabled);
  const deskInput = useVirtualMarkerSimulation(pose, markersVisible ? markers[1] : null, markerEnabled);
  const manualPerson = useManualPerson(pose, studentSimulator && testMode === "manual" && rover.status === "connected");
  const observedPerson = testMode === "manual" ? manualPerson.person : sceneRun.frame?.person ?? studentScene.person;
  const personEnabled = studentSimulator && rover.control.isOwner && (testMode === "manual" || sceneRun.active && sceneRun.frame?.visible === true);
  const studentRunningChanged = useCallback((running: boolean) => {
    setStudentRunning(running);
    if (!running) { sceneRun.stop(); manualPerson.stop(); setMarkerReady(false); }
  }, [sceneRun.stop, manualPerson.stop]);
  const virtualPerson = useVirtualPersonSimulation(
    pose,
    observedPerson,
    view === "lab" && personEnabled
  );

  useEffect(() => {
    document.title = `${content.title} · APRIS`;
  }, [content.title]);

  useEffect(() => {
    if (rover.status !== "connected") {
      setAdapterType(null);
      return;
    }
    let disposed = false;
    void runtimeApi.status()
      .then((status) => {
        if (!disposed) setAdapterType(status.adapter.type);
      })
      .catch(() => {
        if (!disposed) setAdapterType(null);
      });
    return () => {
      disposed = true;
    };
  }, [rover.status]);

  useEffect(() => {
    if (!pose) return;
    setPath((current) => {
      const last = current.at(-1);
      if (last && Math.hypot(pose.x - last.x, pose.y - last.y) < 0.008) return current;
      return [...current, pose].slice(-700);
    });
  }, [pose?.x, pose?.y, pose?.yaw]);

  const driveDisabled =
    rover.status !== "connected" || !rover.control.isOwner || rover.control.estopLatched;

  const driveManually = useCallback((vx: number, wz: number) => {
    setManualCommand((current) => ({ sampleId: current.sampleId + 1, vx, wz }));
    rover.actions.drive(vx, wz);
  }, [rover.actions.drive]);

  const stopManualDrive = useCallback(() => {
    setManualCommand((current) => ({ sampleId: current.sampleId + 1, vx: 0, wz: 0 }));
    rover.actions.stop("joystick released");
  }, [rover.actions.stop]);

  const connectionText = useMemo(() => {
    if (rover.status === "connecting") return "Connecting";
    if (rover.status === "connected") return "Local Server online";
    return "Reconnecting";
  }, [rover.status]);

  const controlActions = (
    <div className="control-actions">
      {!rover.control.isOwner ? (
        <button
          className="button button--primary"
          disabled={rover.status !== "connected" || rover.control.ownerClientId !== null}
          onClick={rover.actions.acquire}
        >
          Acquire control
        </button>
      ) : (
        <button className="button button--quiet" onClick={rover.actions.release}>
          Release control
        </button>
      )}
      <button
        className="button button--estop"
        disabled={rover.status !== "connected"}
        onClick={rover.actions.estop}
      >
        Emergency stop
      </button>
    </div>
  );

  const estopBanner = rover.control.estopLatched ? (
    <div className="estop-banner">
      <strong>Emergency stop latched</strong>
      <span>Motion commands are blocked.</span>
      <button disabled={!rover.control.isOwner} onClick={rover.actions.clearEstop}>
        Clear E-stop
      </button>
    </div>
  ) : null;

  const simulatorPanel = (
    <article className="panel panel--map">
      <div className="panel__heading">
        <div>
          <p className="section-label">LIVE STATE</p>
          <h2>Rover field</h2>
        </div>
        <button
          className="button button--quiet"
          disabled={!rover.control.isOwner || (studentSimulator && studentRunning)}
          onClick={() => {
            rover.actions.resetPose();
            setPath([]);
          }}
        >
          Reset pose
        </button>
      </div>
      <RoverMap
        pose={pose}
        path={path}
        person={view === "lab" && (personEnabled || (studentSimulator && !sceneRun.active)) ? observedPerson : null}
        markers={studentSimulator ? markers.map(m => ({
          id: m.id, label: m.label, x: m.xM, y: m.yM, selected: false, visible: markersVisible
        })) : []}
      />
      <div className="telemetry">
        <div><span>x</span><strong>{number(pose?.x)} m</strong></div>
        <div><span>y</span><strong>{number(pose?.y)} m</strong></div>
        <div><span>yaw</span><strong>{number(pose ? (pose.yaw * 180) / Math.PI : 0)}°</strong></div>
        <div><span>linear</span><strong>{number(rover.state?.velocity.vx)} m/s</strong></div>
        <div><span>angular</span><strong>{number(rover.state?.velocity.wz)} rad/s</strong></div>
        <div><span>battery</span><strong>{number(rover.state?.battery_percent ?? 0)}%</strong></div>
      </div>
      <div className="pose-quality">
        <span>
          Pose {rover.state?.pose_quality.source ?? "unavailable"} · {number(
            (rover.state?.pose_quality.confidence ?? 0) * 100
          )}% confidence
        </span>
        {(rover.state?.pose_quality.anomalies ?? []).map((anomaly) => (
          <strong key={anomaly}>{anomaly}</strong>
        ))}
      </div>
    </article>
  );

  const manualControlPanel = (
    <article className="panel panel--control">
      <div className="panel__heading">
        <div>
          <p className="section-label">MANUAL CONTROL</p>
          <h2>Dead-man joystick</h2>
        </div>
        <span className={`owner-badge ${rover.control.isOwner ? "owner-badge--active" : ""}`}>
          {rover.control.isOwner ? "You have control" : "Observer"}
        </span>
      </div>
      {controlActions}
      {estopBanner}
      {view === "console" && <ManualPathClearance
        eligible={rover.status === "connected" && rover.control.isOwner
          && !rover.control.estopLatched && rover.state?.connected === true}
        blocked={rover.frontObstacle?.state === "BLOCKED"}
        onChange={rover.actions.setPathClearance}
      />}
      <Joystick
        disabled={driveDisabled}
        onDrive={driveManually}
        onStop={stopManualDrive}
      />
      <p className="joystick-help">
        Hold to drive. Releasing the pointer sends stop; missing commands expire after 500 ms.
      </p>
    </article>
  );

  const cameraPanel = (
    <section className="camera-section">
      <CameraPreview
        onObservation={rover.actions.observe}
        virtualPerson={view === "lab" && personEnabled
          ? virtualPerson.projection
          : undefined}
      />
    </section>
  );

  const serviceVision = (
    <CameraPreview
      onObservation={rover.actions.observe}
      variant="service"
      initialFacing="user"
    />
  );

  const studentServicePanel = (
    <StudentServicePanel
      service={selectedService.definition}
      blockedReason={selectedService.simulatorOnly && adapterType !== null && adapterType !== "simulator"
        ? "Live marker guidance is not enabled in this shared MVP. Use the simulator for this service." : undefined}
      rover={rover.serviceRover}
      config={serviceConfig}
      eligible={rover.status === "connected" && rover.control.isOwner && !rover.control.estopLatched}
      acquire={rover.actions.acquire}
      cancel={rover.actions.cancelMotion}
      emergencyStop={rover.actions.estop}
      clearance={rover.actions.setPathClearance}
      onRunningChange={studentRunningChanged}
      speech={studentSimulator && testMode === "manual" ? testSpeech : undefined}
      execution={studentSimulator && testMode === "manual" ? <ManualPersonPanel
        enabled={rover.status === "connected" && !!pose} visible={pose ? projectVirtualPerson(pose, manualPerson.person).visible : false}
        motion={manualPerson.motion} speed={manualPerson.speed} onMotion={manualPerson.setMotion}
        onPlace={manualPerson.place} onSpeed={manualPerson.setSpeed}
        onSay={text => setTestSpeech(previous => ({ id: (previous?.id ?? 0) + 1, text }))}
      /> : studentSimulator && sceneRun.definition && sceneRun.frame ?
        <StudentSceneExecution scene={sceneRun.definition} frame={sceneRun.frame} active={sceneRun.active} onNext={sceneRun.next} /> : undefined}
      simulator={studentLab && adapterType === "simulator" ? {
        name: testMode === "scenario" ? studentScene.name : undefined,
        startLabel: testMode === "manual" ? (studentRunning ? "Restart service" : "Start service") : undefined,
        available: rover.status === "connected" && !!pose && !rover.control.estopLatched
          && (rover.control.isOwner || rover.control.ownerClientId === null),
        unavailableReason: rover.status !== "connected" ? "Waiting for the server connection."
          : rover.control.estopLatched ? "Emergency stop is active. Release it in Advanced controls before starting."
          : !pose ? "Waiting for the rover position."
          : !rover.control.isOwner && rover.control.ownerClientId !== null
            ? "Another tab or client has control. Release control there, or close that tab and wait for control to become available."
            : undefined,
        prepare: async (signal) => {
          const status = await runtimeApi.status();
          signal.throwIfAborted();
          if (status.adapter.type !== "simulator" || !pose) throw new Error("Simulator is not available");
          if (testMode === "manual") {
            sceneRun.stop();
            await simulatorApi.placePose({ ...pose, markers: markers.map(m => ({ id: m.id, x_m: m.xM, y_m: m.yM })) });
            signal.throwIfAborted();
            setMarkerReady(true);
            const response = await simulatorApi.setFrontObstacle("CLEAR", "healthy");
            signal.throwIfAborted();
            if (response.front_obstacle.latched) throw new Error("Clear the obstacle latch in Advanced controls before restarting.");
            signal.addEventListener("abort", manualPerson.stop, { once: true });
            return;
          }
          const definition = parseStudentScene(studentScene);
          sceneRun.stop();
          await simulatorApi.placePose({ ...definition.rover,
            markers: markers.map(m => ({ id: m.id, x_m: m.xM, y_m: m.yM })) });
          signal.throwIfAborted();
          setMarkerReady(true);
          setPath([]);
          signal.throwIfAborted();
          const response = await simulatorApi.setFrontObstacle("CLEAR", "healthy");
          signal.throwIfAborted();
          if (response.front_obstacle.latched) throw new Error("Clear the obstacle latch in Advanced controls before restarting.");
          signal.addEventListener("abort", sceneRun.stop, { once: true });
          sceneRun.start(definition);
        }
      } : undefined}
    />
  );

  const missionPanel = (
    <section className="mission-section">
      <MissionPanel
        disabled={driveDisabled}
        rover={rover.serviceRover}
        missions={missionRegistry}
        config={serviceConfig}
        defaultMissionId={serviceConfig.team.defaultMissionId}
        cancelMotion={rover.actions.cancelMotion}
      />
    </section>
  );

  const interactionPanel = (
    <section className="interaction-section">
      <HumanInteractionPanel
        disabled={driveDisabled}
        rover={rover.serviceRover}
        missions={missionRegistry}
        config={serviceConfig}
        cancelMotion={rover.actions.cancelMotion}
      />
    </section>
  );

  const diagnostics = (
    <section className="lower-grid">
      <article className="panel">
        <p className="section-label">SAFETY STATUS</p>
        <div className="safety-grid">
          <div><span>Control owner</span><strong>{rover.control.ownerClientId ?? "none"}</strong></div>
          <div>
            <span>Command age</span>
            <strong>
              {rover.state?.command_age_ms == null
                ? "—"
                : `${number(rover.state.command_age_ms)} ms`}
            </strong>
          </div>
          <div><span>Linear limit</span><strong>0.30 m/s</strong></div>
          <div><span>Angular limit</span><strong>1.20 rad/s</strong></div>
        </div>
      </article>
      <article className="panel">
        <p className="section-label">RECENT EVENTS</p>
        <ol className="event-list">
          {rover.events.length === 0 && <li className="event-list__empty">No events yet</li>}
          {rover.events.map((event) => (
            <li key={event.id} className={`event event--${event.level}`}>{event.text}</li>
          ))}
        </ol>
      </article>
    </section>
  );

  const implementationPanel = <section className="shared-source" aria-label="Service implementation">
    <h2>Implementation</h2><p><code>apps/pwa/src/{selectedService.file}</code></p>
    <pre><code>{selectedService.source}</code></pre>
  </section>;

  return (
    <main data-view={view}>
      <header className="topbar">
        <div>
          <p className="eyebrow">{content.eyebrow}</p>
          <h1>{content.title}</h1>
        </div>
        <div className="topbar__aside">
          <div className="service-navigation">
            <select aria-label="Selected service" value={serviceMode}
              disabled={studentRunning}
              onChange={event => window.location.assign(viewUrl(view,
                event.target.value as import("./navigation").ServiceMode, window.location.search))}>
              {(Object.entries(serviceCatalog) as [import("./navigation").ServiceMode, typeof selectedService][])
                .map(([id, entry]) => <option key={id} value={id}>{entry.definition.title}</option>)}
            </select>
            <nav className="view-nav" aria-label="PWA views">
              {([["app", "Service"], ["lab", "Playground"], ["console", "Console"]] as const).map(([target, label]) =>
                <a key={target} href={viewUrl(target, serviceMode, window.location.search)}
                  aria-current={view === target ? "page" : undefined}
                  aria-disabled={studentRunning || undefined}
                  onClick={event => { if (studentRunning) event.preventDefault(); }}>{label}</a>)}
            </nav>
          </div>
          {studentRunning && <span role="status">Stop the service to switch.</span>}
          <div className={`connection connection--${rover.status}`}>
            <span className="connection__dot" />
            {connectionText}
          </div>
        </div>
      </header>

      {view === "console" && (
        <section className="hero-note">
          <p>{content.description}</p>
          <span>Client {rover.clientId ?? "—"}</span>
        </section>
      )}

      {view === "app" && (
        <section className="service-app">
          {estopBanner}{studentServicePanel}{serviceVision}
        </section>
      )}

      {view === "console" && (
        <>
          <section className="dashboard">{simulatorPanel}{manualControlPanel}</section>
          <MotionTrace command={manualCommand} state={rover.state} />
          {diagnostics}
        </>
      )}

      {view === "lab" && (
        <>
          {studentSimulator && <div className="scene-toolbar" role="tablist" aria-label="Test mode">
            <button role="tab" aria-selected={testMode === "manual"} disabled={studentRunning} onClick={() => setTestMode("manual")}>Manual test</button>
            <button role="tab" aria-selected={testMode === "scenario"} disabled={studentRunning} onClick={() => setTestMode("scenario")}>Scenario runner</button>
          </div>}
          {studentSimulator && testMode === "scenario" && <StudentScenePanel scene={studentScene} onChange={setStudentScene} />}
          {studentLab && <>{estopBanner}<section className="dashboard">{studentServicePanel}{simulatorPanel}</section>
            {implementationPanel}
            {studentSimulator && <section className="shared-environment" aria-label="Test markers">
              <h2>Test markers</h2>
              <label><input type="checkbox" checked={markersVisible} onChange={e => setMarkersVisible(e.target.checked)} />Markers visible</label>
              {markers.map((marker, index) => <fieldset key={marker.id} disabled={studentRunning}>
                <legend>{marker.label}</legend>
                {(["xM", "yM"] as const).map(axis => <label key={axis}>{axis === "xM" ? "x (m)" : "y (m)"}
                  <input type="number" aria-label={`${marker.label} ${axis}`} value={marker[axis]} min={-10} max={10} step={.1}
                    onChange={e => { const value = e.target.valueAsNumber;
                      if (Number.isFinite(value) && Math.abs(value) <= 10) setMarkers(current => current.map((m, i) => i === index ? { ...m, [axis]: value } : m));
                    }} /></label>)}
              </fieldset>)}
              {(entranceInput.error || deskInput.error) && <p role="alert">{entranceInput.error || deskInput.error}</p>}
            </section>}
            {!studentSimulator && serviceVision}
          </>}
          <details open={studentLab ? undefined : true}>
          <summary>Advanced controls</summary>
          {studentLab && manualControlPanel}
          <section className="simulator-tools">
            <SimulatorScenarioPanel events={rover.scenarioEvents} />
          </section>
          {cameraPanel}
          {interactionPanel}
          {missionPanel}
          {diagnostics}
          </details>
        </>
      )}
    </main>
  );
}
