import type { Pose, ScenarioEventKind } from "./protocol";

export interface SimulatorFaults {
  command_latency_ms: number;
  state_latency_ms: number;
  drop_next_commands: number;
  pose_noise_m: number;
  yaw_noise_deg: number;
  stale_state_ms: number;
  battery_percent: number | null;
  encoder_fault: boolean;
  imu_fault: boolean;
  seed: number;
}

export interface SimulatorScenario {
  id: string;
  name: string;
  description: string;
  duration_ms: number;
  action_count: number;
}

export type FrontObstacleState = "CLEAR" | "BLOCKED" | "UNKNOWN";
export type PerceptionHealth = "healthy" | "degraded" | "unavailable";

export interface FrontObstacleSnapshot {
  state: FrontObstacleState;
  observed_state: FrontObstacleState;
  perception_health: PerceptionHealth;
  source: "manual" | "scenario" | "camera" | "sensor" | "replay" | null;
  observed_at: number | null;
  heartbeat_at: number | null;
  observation_age_ms: number | null;
  heartbeat_age_ms: number | null;
  stale_after_ms: number;
  stale: boolean;
  confidence: number | null;
  distance_m: number | null;
  lateral_m: number | null;
  latched: boolean;
  latched_at: number | null;
  cleared_at: number | null;
  clear_reason: string | null;
}

export interface SimulatorStatus {
  active_id: string | null;
  active_kind: "scenario" | "replay" | null;
  run_id: string | null;
  faults: SimulatorFaults;
  log_session_id: string;
  log_filename: string;
  front_obstacle: FrontObstacleSnapshot;
}

export interface StructuredLogEntry {
  seq: number;
  session_id: string;
  timestamp: number;
  elapsed_ms: number;
  category: string;
  name: string;
  data: Record<string, unknown>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body
      ? { "Content-Type": "application/json", ...init.headers }
      : init?.headers
  });
  const body = await response.json() as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail ?? `Simulator API returned ${response.status}`);
  return body;
}

export const simulatorApi = {
  placePose: (pose: Pose & { markers?: { id: number; x_m: number; y_m: number }[] }) => request<{ pose: Pose }>("/api/simulator/pose", {
    method: "PUT", body: JSON.stringify(pose)
  }),
  async scenarios(): Promise<readonly SimulatorScenario[]> {
    const response = await request<{ scenarios: SimulatorScenario[] }>("/api/simulator/scenarios");
    return response.scenarios;
  },
  status: () => request<SimulatorStatus>("/api/simulator/status"),
  runScenario: (id: string) => request<SimulatorStatus>(
    `/api/simulator/scenarios/${encodeURIComponent(id)}/run`,
    { method: "POST" }
  ),
  stopScenario: () => request<{ stopped: boolean; status: SimulatorStatus }>(
    "/api/simulator/scenarios/stop",
    { method: "POST" }
  ),
  injectEvent: (kind: ScenarioEventKind, payload: Record<string, unknown>) => request(
    "/api/simulator/events",
    { method: "POST", body: JSON.stringify({ kind, payload }) }
  ),
  setFaults: (faults: SimulatorFaults) => request<{ faults: SimulatorFaults }>(
    "/api/simulator/faults",
    { method: "PUT", body: JSON.stringify(faults) }
  ),
  clearFaults: () => request<{ faults: SimulatorFaults }>(
    "/api/simulator/faults",
    { method: "DELETE" }
  ),
  setFrontObstacle: (
    state: FrontObstacleState,
    perceptionHealth: PerceptionHealth
  ) => request<{ front_obstacle: FrontObstacleSnapshot }>(
    "/api/simulator/front-obstacle",
    {
      method: "PUT",
      body: JSON.stringify({
        state,
        perception_health: perceptionHealth,
        source: "manual",
        confidence: perceptionHealth === "healthy" ? 1 : null
      })
    }
  ),
  clearFrontObstacle: (reason: string) => request<{ front_obstacle: FrontObstacleSnapshot }>(
    "/api/simulator/front-obstacle/clear",
    { method: "POST", body: JSON.stringify({ reason }) }
  ),
  async logs(limit = 80): Promise<{
    session_id: string;
    filename: string;
    entries: StructuredLogEntry[];
  }> {
    return request(`/api/simulator/logs?limit=${limit}`);
  },
  clearLogs: () => request<{ session_id: string; cleared: boolean }>(
    "/api/simulator/logs",
    { method: "DELETE" }
  ),
  replayInputs: (speed = 10) => request<SimulatorStatus>(
    "/api/simulator/logs/replay",
    { method: "POST", body: JSON.stringify({ speed }) }
  )
};

export const nominalFaults: SimulatorFaults = {
  command_latency_ms: 0,
  state_latency_ms: 0,
  drop_next_commands: 0,
  pose_noise_m: 0,
  yaw_noise_deg: 0,
  stale_state_ms: 0,
  battery_percent: null,
  encoder_fault: false,
  imu_fault: false,
  seed: 2026
};
