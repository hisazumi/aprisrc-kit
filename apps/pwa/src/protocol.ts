export interface Pose {
  x: number;
  y: number;
  yaw: number;
}

export interface Velocity {
  vx: number;
  vy: number;
  wz: number;
}

export interface Capabilities {
  lateral_motion: boolean;
  pose: boolean;
  imu: boolean;
  lidar: boolean;
  camera: boolean;
}

export interface RoverState {
  timestamp: number;
  connected: boolean;
  pose: Pose;
  velocity: Velocity;
  battery_percent: number | null;
  capabilities: Capabilities;
  command_age_ms: number | null;
  pose_quality: PoseEstimateQuality;
}

export interface PoseEstimateQuality {
  frame_id: "odom" | "course";
  source: "encoder_imu" | "encoder_only" | "marker_corrected" | "unavailable";
  confidence: number;
  age_ms: number;
  encoder_status: "ok" | "missing" | "fault";
  imu_status: "ok" | "missing" | "fault";
  anomalies: string[];
  last_marker_id: number | null;
}

export type ScenarioEventKind = "person" | "marker" | "voice_intent";

export interface ScenarioInputEvent {
  eventId: string;
  kind: ScenarioEventKind;
  payload: Record<string, unknown>;
  source: PerceptionSource;
  scenarioId: string | null;
}

export type PerceptionSource = "camera" | "recorded" | "manual" | "scenario" | "replay";
export type PerceptionStatus = "detected" | "lost" | "rejected";

export interface PerceptionObservationInput {
  kind: "person" | "marker";
  status: "detected" | "lost";
  confidence: number;
  source: "camera" | "recorded";
  payload: Record<string, unknown>;
}

export interface FrontObstacleSnapshot {
  state: "CLEAR" | "BLOCKED" | "UNKNOWN";
  observed_state: "CLEAR" | "BLOCKED" | "UNKNOWN";
  perception_health: "healthy" | "degraded" | "unavailable";
  source: "manual" | "scenario" | "camera" | "sensor" | "replay" | null;
  stale: boolean;
  latched: boolean;
}

export type ClientKind =
  | "service_app"
  | "operator_console"
  | "development_lab"
  | "vehicle_perception"
  | "physicode_bridge";

export interface PersonEvent {
  eventId: string;
  status: "detected" | "lost";
  confidence: number;
  capturedAt: number;
  source: PerceptionSource;
  personId: string;
  centerX?: number;
  centerY?: number;
  width?: number;
  height?: number;
  bearingDeg?: number;
}

export interface MarkerEvent {
  eventId: string;
  status: "detected" | "lost";
  confidence: number;
  capturedAt: number;
  source: PerceptionSource;
  markerId: number;
  relativeXM?: number;
  relativeYM?: number;
  relativeYawRad?: number;
  poseCorrection?: {
    applied: boolean;
    reason?: string;
    innovationM?: number;
  };
}

export type ClientMessage =
  | {
      v: 1;
      type: "client_hello";
      client_kind: ClientKind;
      device_id: string;
      session_id: string;
      app_version: string;
      build_id: string;
    }
  | { v: 1; type: "acquire_control" }
  | { v: 1; type: "release_control" }
  | { v: 1; type: "drive"; vx: number; vy: number; wz: number; ttl_ms: number; seq: number }
  | { v: 1; type: "stop"; reason?: string }
  | {
      v: 1;
      type: "move";
      request_id: string;
      run_id?: string;
      effect_id?: string;
      distance_m: number;
      speed_mps: number;
    }
  | {
      v: 1;
      type: "turn";
      request_id: string;
      run_id?: string;
      effect_id?: string;
      angle_deg: number;
      speed_rad_s: number;
    }
  | { v: 1; type: "cancel_motion" }
  | { v: 1; type: "estop"; reason?: string }
  | { v: 1; type: "clear_estop" }
  | { v: 1; type: "reset_pose" }
  | { v: 1; type: "path_clearance"; confirmed: boolean }
  | {
      v: 1;
      type: "perception_observation";
      observation_id: string;
      kind: "person" | "marker";
      status: "detected" | "lost";
      confidence: number;
      captured_at: number;
      source: "camera" | "recorded";
      payload: Record<string, unknown>;
    };

export type ServerMessage =
  | {
      v: 1;
      type: "hello";
      client_id: string;
      server_name: string;
      server_version: string;
      build_id: string;
      instance_id: string;
      supported_protocol_versions: [1];
      capabilities: Capabilities;
    }
  | {
      v: 1;
      type: "control";
      owner_client_id: string | null;
      is_owner: boolean;
      estop_latched: boolean;
    }
  | { v: 1; type: "state"; state: RoverState }
  | {
      v: 1;
      type: "scenario_event";
      event_id: string;
      kind: ScenarioEventKind;
      payload: Record<string, unknown>;
      source: "manual" | "scenario" | "replay";
      scenario_id: string | null;
    }
  | {
      v: 1;
      type: "perception_event";
      event_id: string;
      kind: "person" | "marker";
      status: PerceptionStatus;
      confidence: number;
      captured_at: number;
      source: PerceptionSource;
      payload: Record<string, unknown>;
      accepted: boolean;
      reason: string;
    }
  | {
      v: 1;
      type: "motion";
      request_id: string;
      run_id?: string | null;
      effect_id?: string | null;
      motion: "move" | "turn";
      status: "started" | "completed" | "cancelled" | "failed";
      detail: string;
    }
  | {
      v: 1;
      type: "front_obstacle";
      request_id?: string | null;
      obstacle: FrontObstacleSnapshot;
    }
  | { v: 1; type: "event"; event: string; detail: string }
  | { v: 1; type: "error"; code: string; detail: string };

export function isServerMessage(value: unknown): value is ServerMessage {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return candidate.v === 1 && typeof candidate.type === "string";
}
