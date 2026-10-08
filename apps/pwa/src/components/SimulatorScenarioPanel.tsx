import { useCallback, useEffect, useMemo, useState } from "react";

import type { ScenarioInputEvent } from "../protocol";
import {
  nominalFaults,
  simulatorApi,
  type FrontObstacleState,
  type PerceptionHealth,
  type SimulatorFaults,
  type SimulatorScenario,
  type SimulatorStatus,
  type StructuredLogEntry
} from "../simulatorApi";

interface SimulatorScenarioPanelProps {
  events: readonly ScenarioInputEvent[];
}

const faultPresets: Record<string, { label: string; faults: SimulatorFaults }> = {
  latency: {
    label: "Command / state latency",
    faults: { ...nominalFaults, command_latency_ms: 250, state_latency_ms: 150 }
  },
  commandDrop: {
    label: "Drop next 3 commands",
    faults: { ...nominalFaults, drop_next_commands: 3 }
  },
  noisyPose: {
    label: "Noisy pose",
    faults: { ...nominalFaults, pose_noise_m: 0.05, yaw_noise_deg: 5 }
  },
  staleState: {
    label: "500 ms stale state",
    faults: { ...nominalFaults, stale_state_ms: 500 }
  },
  lowBattery: {
    label: "Low battery (12%)",
    faults: { ...nominalFaults, battery_percent: 12 }
  },
  sensors: {
    label: "Encoder + IMU fault",
    faults: { ...nominalFaults, encoder_fault: true, imu_fault: true }
  },
  mixed: {
    label: "Mixed deterministic faults",
    faults: {
      ...nominalFaults,
      command_latency_ms: 120,
      state_latency_ms: 80,
      drop_next_commands: 2,
      pose_noise_m: 0.03,
      yaw_noise_deg: 3,
      stale_state_ms: 250,
      battery_percent: 18,
      imu_fault: true
    }
  }
};

function activeFaultLabels(faults: SimulatorFaults | undefined): string[] {
  if (!faults) return [];
  const labels: string[] = [];
  if (faults.command_latency_ms) labels.push(`command +${faults.command_latency_ms} ms`);
  if (faults.state_latency_ms) labels.push(`state +${faults.state_latency_ms} ms`);
  if (faults.drop_next_commands) labels.push(`drop ${faults.drop_next_commands} command(s)`);
  if (faults.pose_noise_m) labels.push(`pose noise ${faults.pose_noise_m} m`);
  if (faults.yaw_noise_deg) labels.push(`yaw noise ${faults.yaw_noise_deg}°`);
  if (faults.stale_state_ms) labels.push(`stale ${faults.stale_state_ms} ms`);
  if (faults.battery_percent != null) labels.push(`battery ${faults.battery_percent}%`);
  if (faults.encoder_fault) labels.push("encoder fault");
  if (faults.imu_fault) labels.push("IMU fault");
  return labels;
}

export function SimulatorScenarioPanel({ events }: SimulatorScenarioPanelProps) {
  const [scenarios, setScenarios] = useState<readonly SimulatorScenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("mixed");
  const [obstacleState, setObstacleState] = useState<FrontObstacleState>("UNKNOWN");
  const [perceptionHealth, setPerceptionHealth] = useState<PerceptionHealth>("unavailable");
  const [status, setStatus] = useState<SimulatorStatus | null>(null);
  const [logs, setLogs] = useState<readonly StructuredLogEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [nextStatus, nextLogs] = await Promise.all([
      simulatorApi.status(),
      simulatorApi.logs()
    ]);
    setStatus(nextStatus);
    setLogs(nextLogs.entries);
  }, []);

  useEffect(() => {
    let disposed = false;
    void Promise.all([simulatorApi.scenarios(), simulatorApi.status(), simulatorApi.logs()])
      .then(([nextScenarios, nextStatus, nextLogs]) => {
        if (disposed) return;
        setScenarios(nextScenarios);
        setSelectedScenarioId((current) => current || nextScenarios[0]?.id || "");
        setStatus(nextStatus);
        setLogs(nextLogs.entries);
      })
      .catch((cause: unknown) => {
        if (!disposed) setError(cause instanceof Error ? cause.message : "Simulator API failed");
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!status?.active_id) return;
    const timer = window.setInterval(() => void refresh().catch(() => undefined), 500);
    return () => window.clearInterval(timer);
  }, [refresh, status?.active_id]);

  const perform = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await operation();
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Simulator action failed");
    } finally {
      setBusy(false);
    }
  };

  const selectedScenario = scenarios.find((scenario) => scenario.id === selectedScenarioId);
  const faultLabels = useMemo(() => activeFaultLabels(status?.faults), [status?.faults]);
  const visibleLogs = logs.slice(-10).reverse();

  return (
    <article className="panel panel--scenario">
      <div className="panel__heading">
        <div>
          <p className="section-label">SIMULATOR TOOLS</p>
          <h2>Reproducible scenarios</h2>
        </div>
        <span className={`owner-badge ${status?.active_id ? "owner-badge--active" : ""}`}>
          {status?.active_id ? `${status.active_kind}: ${status.active_id}` : "idle"}
        </span>
      </div>

      <p className="scenario-warning">
        Development-only controls. Faults affect the shared Simulator and are cleared when a
        scenario or replay ends.
      </p>

      <div className="scenario-layout">
        <section className="scenario-block">
          <h3>Front obstacle</h3>
          <p>
            Inject state and perception health separately. Forward motion requires a fresh,
            healthy CLEAR state.
          </p>
          <select
            aria-label="Front obstacle state"
            disabled={busy || Boolean(status?.active_id)}
            value={obstacleState}
            onChange={(event) => setObstacleState(event.target.value as FrontObstacleState)}
          >
            <option value="UNKNOWN">UNKNOWN</option>
            <option value="CLEAR">CLEAR</option>
            <option value="BLOCKED">BLOCKED</option>
          </select>
          <select
            aria-label="Perception health"
            disabled={busy || Boolean(status?.active_id)}
            value={perceptionHealth}
            onChange={(event) => setPerceptionHealth(event.target.value as PerceptionHealth)}
          >
            <option value="unavailable">unavailable</option>
            <option value="degraded">degraded</option>
            <option value="healthy">healthy</option>
          </select>
          <div className="scenario-actions">
            <button
              className="button button--primary"
              disabled={busy || Boolean(status?.active_id) || (
                obstacleState === "CLEAR" && perceptionHealth !== "healthy"
              )}
              onClick={() => void perform(() => simulatorApi.setFrontObstacle(
                obstacleState,
                perceptionHealth
              ))}
            >
              Apply state
            </button>
            <button
              className="button button--quiet"
              disabled={busy || Boolean(status?.active_id) || !status?.front_obstacle.latched}
              onClick={() => void perform(() => simulatorApi.clearFrontObstacle(
                "operator verified path in Development Lab"
              ))}
            >
              Clear latch
            </button>
          </div>
          <div className="scenario-faults">
            <span>effective {status?.front_obstacle.state ?? "UNKNOWN"}</span>
            <span>health {status?.front_obstacle.perception_health ?? "unavailable"}</span>
            <span>{status?.front_obstacle.latched ? "latched" : "not latched"}</span>
            <span>{status?.front_obstacle.stale ? "stale" : "fresh"}</span>
          </div>
        </section>

        <section className="scenario-block">
          <h3>Scenario file</h3>
          <select
            aria-label="Simulator scenario"
            disabled={busy || Boolean(status?.active_id)}
            value={selectedScenarioId}
            onChange={(event) => setSelectedScenarioId(event.target.value)}
          >
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>{scenario.name}</option>
            ))}
          </select>
          <p>{selectedScenario?.description ?? "Loading scenario files…"}</p>
          {selectedScenario && (
            <small>{selectedScenario.action_count} actions · {selectedScenario.duration_ms} ms</small>
          )}
          <div className="scenario-actions">
            <button
              className="button button--primary"
              disabled={busy || !selectedScenarioId || Boolean(status?.active_id)}
              onClick={() => void perform(() => simulatorApi.runScenario(selectedScenarioId))}
            >
              Run scenario
            </button>
            <button
              className="button button--quiet"
              disabled={busy || !status?.active_id}
              onClick={() => void perform(simulatorApi.stopScenario)}
            >
              Stop run
            </button>
          </div>
        </section>

        <section className="scenario-block">
          <h3>Manual input events</h3>
          <p>Inject the same event shape that perception and voice modules will publish.</p>
          <div className="scenario-button-grid">
            <button
              className="button button--quiet"
              disabled={busy || Boolean(status?.active_id)}
              onClick={() => void perform(() => simulatorApi.injectEvent(
                "person", {
                  status: "detected",
                  confidence: 0.95,
                  person_id: "manual-person",
                  center_x: 0.5,
                  center_y: 0.5,
                  width: 0.2,
                  height: 0.5
                }
              ))}
            >
              Person
            </button>
            <button
              className="button button--quiet"
              disabled={busy || Boolean(status?.active_id)}
              onClick={() => void perform(() => simulatorApi.injectEvent(
                "marker", {
                  status: "detected",
                  confidence: 0.92,
                  marker_id: 1,
                  relative_x_m: 0.6,
                  relative_y_m: 0
                }
              ))}
            >
              Marker 1
            </button>
            <button
              className="button button--quiet"
              disabled={busy || Boolean(status?.active_id)}
              onClick={() => void perform(() => simulatorApi.injectEvent(
                "voice_intent", { action: "wait_here" }
              ))}
            >
              Voice intent
            </button>
          </div>
          <ol className="scenario-event-list">
            {events.slice(0, 4).map((event) => (
              <li key={event.eventId}>
                <strong>{event.kind}</strong>
                <span>{event.source} · {JSON.stringify(event.payload)}</span>
              </li>
            ))}
            {events.length === 0 && <li className="event-list__empty">No injected events yet</li>}
          </ol>
        </section>

        <section className="scenario-block">
          <h3>Fault preset</h3>
          <select
            aria-label="Fault preset"
            disabled={busy || Boolean(status?.active_id)}
            value={selectedPreset}
            onChange={(event) => setSelectedPreset(event.target.value)}
          >
            {Object.entries(faultPresets).map(([id, preset]) => (
              <option key={id} value={id}>{preset.label}</option>
            ))}
          </select>
          <div className="scenario-actions">
            <button
              className="button button--primary"
              disabled={busy || Boolean(status?.active_id)}
              onClick={() => void perform(() => simulatorApi.setFaults(
                faultPresets[selectedPreset]?.faults ?? nominalFaults
              ))}
            >
              Apply faults
            </button>
            <button
              className="button button--quiet"
              disabled={busy || Boolean(status?.active_id)}
              onClick={() => void perform(simulatorApi.clearFaults)}
            >
              Clear faults
            </button>
          </div>
          <div className="scenario-faults">
            {faultLabels.length === 0 && <span>Nominal Simulator</span>}
            {faultLabels.map((label) => <span key={label}>{label}</span>)}
          </div>
        </section>

        <section className="scenario-block">
          <div className="scenario-block__heading">
            <h3>Structured log</h3>
            <small>{status?.log_filename ?? "Starting log…"}</small>
          </div>
          <div className="scenario-actions">
            <button
              className="button button--primary"
              disabled={busy || Boolean(status?.active_id)}
              onClick={() => void perform(() => simulatorApi.replayInputs(10))}
            >
              Replay inputs ×10
            </button>
            <button
              className="button button--quiet"
              disabled={busy || Boolean(status?.active_id)}
              onClick={() => void perform(simulatorApi.clearLogs)}
            >
              Clear view
            </button>
          </div>
          <ol className="scenario-log-list">
            {visibleLogs.map((entry) => (
              <li key={entry.seq}>
                <span>{(entry.elapsed_ms / 1000).toFixed(2)}s</span>
                <strong>{entry.category}</strong>
                <code>{entry.name}</code>
              </li>
            ))}
            {visibleLogs.length === 0 && <li className="event-list__empty">No log entries</li>}
          </ol>
        </section>
      </div>

      {error && <p className="scenario-error" role="alert">{error}</p>}
    </article>
  );
}
