import { StudentServicePanel } from "./components/StudentServicePanel";
import { studentCarry } from "./missions/studentCarry";
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
import { AutonomousCarryService } from "./components/AutonomousCarryService";
import { HumanInteractionPanel } from "./components/HumanInteractionPanel";
import { MobileReceptionistService } from "./components/MobileReceptionistService";
import { Joystick } from "./components/Joystick";
import { MissionPanel } from "./components/MissionPanel";
import { MotionTrace, type CommandedVelocity } from "./components/MotionTrace";
import { RoverMap } from "./components/RoverMap";
import { SimulatorScenarioPanel } from "./components/SimulatorScenarioPanel";
import { VirtualPersonPanel } from "./components/VirtualPersonPanel";
import { ServicePlayground } from "./components/ServicePlayground";
import { serviceConfig } from "./config";
import { missionRegistry } from "./missions";
import type { Pose } from "./protocol";
import { runtimeApi, type RoverAdapterType } from "./runtimeApi";
import {
  VIRTUAL_PERSON_WALK_DURATION_S,
  projectVirtualPerson,
  walkVirtualPerson,
  type VirtualPersonTarget
} from "./simulation/virtualPerson";
import { useVirtualPersonSimulation } from "./simulation/useVirtualPersonSimulation";
import { useRoverSocket } from "./useRoverSocket";

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
  const playground = view === "lab" && serviceMode !== "student";
  const studentLab = view === "lab" && serviceMode === "student";
  const content = viewContent[view];
  const [adapterType, setAdapterType] = useState<RoverAdapterType | null>(null);
  const rover = useRoverSocket(selectFollowProfile(adapterType, import.meta.env.VITE_IRONX_CONTINUOUS_FOLLOW));
  const [serviceRunning, setServiceRunning] = useState(false);
  useEffect(() => {
    const canonical = viewUrl(view, serviceMode, window.location.search);
    if (window.location.pathname + window.location.search !== canonical) {
      window.history.replaceState(null, "", canonical + window.location.hash);
    }
  }, [view, serviceMode]);
  const [receptionistCameraFacing, setReceptionistCameraFacing] = useState<
    "user" | "environment"
  >("user");
  const [receptionistVisionActive, setReceptionistVisionActive] = useState(false);
  const [path, setPath] = useState<Pose[]>([]);
  const [manualCommand, setManualCommand] = useState<CommandedVelocity>({
    sampleId: 0,
    vx: 0,
    wz: 0,
  });
  const [virtualPersonEnabled, setVirtualPersonEnabled] = useState(false);
  const [virtualPersonWalking, setVirtualPersonWalking] = useState(false);
  const [virtualPersonTarget, setVirtualPersonTarget] = useState<VirtualPersonTarget>({
    x: 1.35,
    y: 0.3
  });
  const [studentScene, setStudentScene] = useState(() => structuredClone(studentScenes[0]));
  const sceneRun = useStudentScene();
  const [studentRunning, setStudentRunning] = useState(false);
  const [testMode, setTestMode] = useState<"manual" | "scenario">("manual");
  const [testSpeech, setTestSpeech] = useState<{ id: number; text: string }>();
  const studentSimulator = studentLab && adapterType === "simulator";
  const pose = rover.state?.pose ?? null;
  const manualPerson = useManualPerson(pose, studentSimulator && testMode === "manual" && rover.status === "connected");
  const observedPerson = studentSimulator ? testMode === "manual" ? manualPerson.person : sceneRun.frame?.person ?? studentScene.person : virtualPersonTarget;
  const personEnabled = studentSimulator ? testMode === "manual" ? rover.control.isOwner : sceneRun.active && sceneRun.frame?.visible === true : virtualPersonEnabled;
  const studentRunningChanged = useCallback((running: boolean) => {
    setStudentRunning(running);
    if (!running) { sceneRun.stop(); manualPerson.stop(); }
  }, [sceneRun.stop, manualPerson.stop]);
  const virtualPerson = useVirtualPersonSimulation(
    pose,
    observedPerson,
    view === "lab" && !playground && personEnabled
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

  useEffect(() => {
    if (!virtualPersonEnabled || !virtualPersonWalking || !pose) return;
    const origin = virtualPersonTarget;
    const headingRad = Math.atan2(origin.y - pose.y, origin.x - pose.x);
    const startedAt = performance.now();
    const timer = window.setInterval(() => {
      const elapsedS = (performance.now() - startedAt) / 1000;
      setVirtualPersonTarget(walkVirtualPerson(origin, headingRad, elapsedS));
      if (elapsedS >= VIRTUAL_PERSON_WALK_DURATION_S) setVirtualPersonWalking(false);
    }, 50);
    return () => window.clearInterval(timer);
  }, [virtualPersonEnabled, virtualPersonWalking]);

  const driveDisabled =
    rover.status !== "connected" || !rover.control.isOwner || rover.control.estopLatched;
  const carryMission = missionRegistry.find((mission) => mission.id === "carry-helper");
  const approachMission = missionRegistry.find((mission) => mission.id === "come-here");
  const receptionistMission = missionRegistry.find(
    (mission) => mission.id === "mobile-receptionist"
  );

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

  const receptionistVision = (
    <CameraPreview
      onObservation={rover.actions.observe}
      variant="service"
      initialFacing="user"
      requestedFacing={receptionistCameraFacing}
      requestedActive={receptionistVisionActive}
      virtualPerson={adapterType === "simulator" ? null : undefined}
    />
  );

  const mobileReceptionistService = (
    <MobileReceptionistService
      onRunningChange={setServiceRunning}
      connected={rover.status === "connected"}
      isOwner={rover.control.isOwner}
      controlAvailable={rover.control.isOwner || rover.control.ownerClientId === null}
      estopLatched={rover.control.estopLatched}
      adapterType={adapterType}
      rover={rover.serviceRover}
      mission={receptionistMission}
      config={serviceConfig}
      onAcquireControl={rover.actions.acquire}
      onReleaseControl={rover.actions.release}
      onCancelMotion={rover.actions.cancelMotion}
      onEmergencyStop={rover.actions.estop}
      onPathClearanceChange={rover.actions.setPathClearance}
      onCameraFacingChange={setReceptionistCameraFacing}
      onVisionActiveChange={setReceptionistVisionActive}
    />
  );

  const studentServicePanel = (
    <StudentServicePanel
      service={studentCarry}
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
            const response = await simulatorApi.setFrontObstacle("CLEAR", "healthy");
            signal.throwIfAborted();
            if (response.front_obstacle.latched) throw new Error("Clear the obstacle latch in Advanced controls before restarting.");
            signal.addEventListener("abort", manualPerson.stop, { once: true });
            return;
          }
          const definition = parseStudentScene(studentScene);
          sceneRun.stop();
          await simulatorApi.placePose(definition.rover);
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

  const autonomousCarryService = (
    <AutonomousCarryService
      onRunningChange={setServiceRunning}
      connected={rover.status === "connected"}
      isOwner={rover.control.isOwner}
      controlAvailable={rover.control.isOwner || rover.control.ownerClientId === null}
      estopLatched={rover.control.estopLatched}
      batteryPercent={rover.state?.battery_percent ?? null}
      frontObstacle={rover.frontObstacle}
      rover={rover.serviceRover}
      approachMission={approachMission}
      mission={carryMission}
      config={serviceConfig}
      onAcquireControl={rover.actions.acquire}
      onReleaseControl={rover.actions.release}
      onCancelMotion={rover.actions.cancelMotion}
      onEmergencyStop={rover.actions.estop}
      onPathClearanceChange={rover.actions.setPathClearance}
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
              disabled={studentRunning || serviceRunning}
              onChange={event => window.location.assign(viewUrl(view,
                event.target.value as import("./navigation").ServiceMode, window.location.search))}>
              <option value="student">{studentCarry.title}</option>
              <option value="carry">Carry helper</option>
              <option value="receptionist">Mobile receptionist</option>
              <option value="greeting">Person greeting</option>
            </select>
            <nav className="view-nav" aria-label="PWA views">
              {([["app", "Service"], ["lab", "Playground"], ["console", "Console"]] as const).map(([target, label]) =>
                <a key={target} href={viewUrl(target, serviceMode, window.location.search)}
                  aria-current={view === target ? "page" : undefined}
                  aria-disabled={studentRunning || serviceRunning || undefined}
                  onClick={event => { if (studentRunning || serviceRunning) event.preventDefault(); }}>{label}</a>)}
            </nav>
          </div>
          {(studentRunning || serviceRunning) && <span role="status">Stop the service to switch.</span>}
          <div className={`connection connection--${rover.status}`}>
            <span className="connection__dot" />
            {connectionText}
          </div>
        </div>
      </header>

      {view !== "app" && !playground && !studentLab && (
        <section className="hero-note">
          <p>{content.description}</p>
          <span>Client {rover.clientId ?? "—"}</span>
        </section>
      )}

      {view === "app" && (
        <section className="service-app">
          {serviceMode === "student" ? (
            <>{studentServicePanel}{serviceVision}</>
          ) : serviceMode === "carry" ? (
            <>{autonomousCarryService}{serviceVision}</>
          ) : serviceMode === "greeting" ? (
            <ServicePlayground rover={rover} adapterType={adapterType} sample="greeting" serviceOnly onRunningChange={setServiceRunning} />
          ) : (
            <>{mobileReceptionistService}{receptionistVision}</>
          )}
        </section>
      )}

      {view === "console" && (
        <>
          <section className="dashboard">{simulatorPanel}{manualControlPanel}</section>
          <MotionTrace command={manualCommand} state={rover.state} />
          {diagnostics}
        </>
      )}

      {playground && <ServicePlayground rover={rover} adapterType={adapterType}
        sample={serviceMode === "carry" ? "follow" : serviceMode === "receptionist" ? "receptionist" : "greeting"}
        onRunningChange={setServiceRunning} />}

      {view === "lab" && !playground && (
        <>
          {!studentLab && <a className="playground-link" href="/lab?sample=student">Try student service</a>}
          {!studentLab && <a className="playground-link" href="/lab?sample=greeting">Open greeting playground</a>}
          {studentSimulator && <div className="scene-toolbar" role="tablist" aria-label="Test mode">
            <button role="tab" aria-selected={testMode === "manual"} disabled={studentRunning} onClick={() => setTestMode("manual")}>Manual test</button>
            <button role="tab" aria-selected={testMode === "scenario"} disabled={studentRunning} onClick={() => setTestMode("scenario")}>Scenario runner</button>
          </div>}
          {studentSimulator && testMode === "scenario" && <StudentScenePanel scene={studentScene} onChange={setStudentScene} />}
          {studentLab && <>{estopBanner}<section className="dashboard">{studentServicePanel}{simulatorPanel}</section></>}
          {!studentLab && <section className="dashboard">{simulatorPanel}{manualControlPanel}</section>}
          {!studentSimulator && <section className="virtual-person-section">
            <VirtualPersonPanel
              pose={pose}
              enabled={virtualPersonEnabled}
              projection={virtualPerson.projection}
              walking={virtualPersonWalking}
              observationError={virtualPerson.error}
              onTarget={setVirtualPersonTarget}
              onEnabled={(enabled) => {
                setVirtualPersonEnabled(enabled);
                if (!enabled) setVirtualPersonWalking(false);
              }}
              onWalking={setVirtualPersonWalking}
            />
          </section>}
          {!studentLab && <section className="autonomous-service-section">{autonomousCarryService}</section>}
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
