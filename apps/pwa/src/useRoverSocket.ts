import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  MarkerListener,
  PersonListener,
  PoseListener,
  ServiceRover
} from "./missions/api";
import type {
  ClientKind,
  ClientMessage,
  FrontObstacleSnapshot,
  MarkerEvent,
  PerceptionObservationInput,
  PersonEvent,
  RoverState,
  ScenarioInputEvent
} from "./protocol";
import { isServerMessage } from "./protocol";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

interface ControlState {
  ownerClientId: string | null;
  isOwner: boolean;
  estopLatched: boolean;
}

export interface RoverEvent {
  id: number;
  level: "info" | "error";
  text: string;
}

interface PendingMotion {
  resolve: () => void;
  reject: (error: Error) => void;
  timeoutId: number;
}

function websocketUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

const DEVICE_ID_STORAGE_KEY = "apris-device-id";

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `web-${Date.now()}-${Math.random()}`;
}

function deviceId(): string {
  try {
    const existing = window.localStorage.getItem(DEVICE_ID_STORAGE_KEY);
    if (existing) return existing;
    const created = newId();
    window.localStorage.setItem(DEVICE_ID_STORAGE_KEY, created);
    return created;
  } catch {
    return newId();
  }
}

function clientKind(): ClientKind {
  if (window.location.pathname.startsWith("/console")) return "operator_console";
  if (window.location.pathname.startsWith("/lab")) return "development_lab";
  return "service_app";
}

export function useRoverSocket(continuousFollowing = false) {
  const socketRef = useRef<WebSocket | null>(null);
  const sequenceRef = useRef(0);
  const motionSequenceRef = useRef(0);
  const eventIdRef = useRef(0);
  const pendingMotionsRef = useRef(new Map<string, PendingMotion>());
  const stateRef = useRef<RoverState | null>(null);
  const frontObstacleRef = useRef<FrontObstacleSnapshot | null>(null);
  const poseListenersRef = useRef(new Set<PoseListener>());
  const personListenersRef = useRef(new Set<PersonListener>());
  const markerListenersRef = useRef(new Set<MarkerListener>());
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [clientId, setClientId] = useState<string | null>(null);
  const [control, setControl] = useState<ControlState>({
    ownerClientId: null,
    isOwner: false,
    estopLatched: false
  });
  const [state, setState] = useState<RoverState | null>(null);
  const [frontObstacle, setFrontObstacle] = useState<FrontObstacleSnapshot | null>(null);
  const [events, setEvents] = useState<RoverEvent[]>([]);
  const [scenarioEvents, setScenarioEvents] = useState<ScenarioInputEvent[]>([]);

  const addEvent = useCallback((level: RoverEvent["level"], text: string) => {
    const event = { id: ++eventIdRef.current, level, text };
    setEvents((current) => [event, ...current].slice(0, 8));
  }, []);

  const rejectPendingMotions = useCallback((reason: string) => {
    for (const pending of pendingMotionsRef.current.values()) {
      window.clearTimeout(pending.timeoutId);
      pending.reject(new Error(reason));
    }
    pendingMotionsRef.current.clear();
  }, []);

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: number | undefined;
    let activeSocket: WebSocket | null = null;

    const connect = () => {
      setStatus("connecting");
      const socket = new WebSocket(websocketUrl());
      activeSocket = socket;
      socketRef.current = socket;

      socket.onopen = () => {
        if (disposed || socketRef.current !== socket) return;
        const registration: ClientMessage = {
          v: 1,
          type: "client_hello",
          client_kind: clientKind(),
          device_id: deviceId(),
          session_id: newId(),
          app_version: "0.1.0",
          build_id: import.meta.env.VITE_BUILD_ID ?? import.meta.env.MODE
        };
        socket.send(JSON.stringify(registration));
        setStatus("connected");
        addEvent("info", "Connected to Local Server");
      };

      socket.onmessage = (event) => {
        if (disposed || socketRef.current !== socket) return;
        let parsed: unknown;
        try {
          parsed = JSON.parse(String(event.data));
        } catch {
          addEvent("error", "Server sent invalid JSON");
          return;
        }
        if (!isServerMessage(parsed)) {
          addEvent("error", "Server sent an unknown message");
          return;
        }
        switch (parsed.type) {
          case "hello":
            setClientId(parsed.client_id);
            break;
          case "control":
            setControl({
              ownerClientId: parsed.owner_client_id,
              isOwner: parsed.is_owner,
              estopLatched: parsed.estop_latched
            });
            break;
          case "state": {
            stateRef.current = parsed.state;
            setState(parsed.state);
            const pose = { ...parsed.state.pose };
            for (const listener of poseListenersRef.current) {
              try {
                listener(pose);
              } catch {
                poseListenersRef.current.delete(listener);
                addEvent("error", "A failed mission pose listener was removed");
              }
            }
            break;
          }
          case "scenario_event":
            setScenarioEvents((current) => [{
              eventId: parsed.event_id,
              kind: parsed.kind,
              payload: parsed.payload,
              source: parsed.source,
              scenarioId: parsed.scenario_id
            }, ...current].slice(0, 20));
            addEvent("info", `scenario_${parsed.kind}: ${parsed.source}`);
            break;
          case "perception_event": {
            setScenarioEvents((current) => [{
              eventId: parsed.event_id,
              kind: parsed.kind,
              payload: {
                status: parsed.status,
                confidence: parsed.confidence,
                accepted: parsed.accepted,
                reason: parsed.reason,
                ...parsed.payload
              },
              source: parsed.source,
              scenarioId: null
            }, ...current].slice(0, 20));
            if (!parsed.accepted || parsed.status === "rejected") {
              addEvent("error", `${parsed.kind} observation rejected: ${parsed.reason}`);
              break;
            }
            if (parsed.kind === "person") {
              const person: PersonEvent = {
                eventId: parsed.event_id,
                status: parsed.status,
                confidence: parsed.confidence,
                capturedAt: parsed.captured_at,
                source: parsed.source,
                personId: String(parsed.payload.person_id ?? "person"),
                centerX: numberOrUndefined(parsed.payload.center_x),
                centerY: numberOrUndefined(parsed.payload.center_y),
                width: numberOrUndefined(parsed.payload.width),
                height: numberOrUndefined(parsed.payload.height),
                bearingDeg: numberOrUndefined(parsed.payload.bearing_deg)
              };
              notifyListeners(personListenersRef.current, person, addEvent, "person");
            } else {
              const correction = recordOrUndefined(parsed.payload.pose_correction);
              const marker: MarkerEvent = {
                eventId: parsed.event_id,
                status: parsed.status,
                confidence: parsed.confidence,
                capturedAt: parsed.captured_at,
                source: parsed.source,
                markerId: Number(parsed.payload.marker_id),
                relativeXM: numberOrUndefined(parsed.payload.relative_x_m),
                relativeYM: numberOrUndefined(parsed.payload.relative_y_m),
                relativeYawRad: numberOrUndefined(parsed.payload.relative_yaw_rad),
                poseCorrection: correction ? {
                  applied: Boolean(correction.applied),
                  reason: stringOrUndefined(correction.reason),
                  innovationM: numberOrUndefined(correction.innovation_m)
                } : undefined
              };
              notifyListeners(markerListenersRef.current, marker, addEvent, "marker");
            }
            addEvent("info", `${parsed.kind}_${parsed.status}: ${parsed.source}`);
            break;
          }
          case "motion": {
            const pending = pendingMotionsRef.current.get(parsed.request_id);
            if (!pending || parsed.status === "started") break;
            window.clearTimeout(pending.timeoutId);
            pendingMotionsRef.current.delete(parsed.request_id);
            if (parsed.status === "completed") {
              pending.resolve();
            } else {
              pending.reject(new Error(parsed.detail || `Motion ${parsed.status}`));
            }
            break;
          }
          case "front_obstacle":
            frontObstacleRef.current = parsed.obstacle;
            setFrontObstacle(parsed.obstacle);
            break;
          case "event":
            addEvent("info", parsed.detail ? `${parsed.event}: ${parsed.detail}` : parsed.event);
            break;
          case "error":
            addEvent("error", `${parsed.code}: ${parsed.detail}`);
            break;
        }
      };

      socket.onclose = () => {
        if (socketRef.current !== socket) return;
        socketRef.current = null;
        setStatus("disconnected");
        frontObstacleRef.current = null;
        setFrontObstacle(null);
        rejectPendingMotions("Local Server disconnected during motion");
        setControl((current) => ({ ...current, isOwner: false, ownerClientId: null }));
        if (!disposed) reconnectTimer = window.setTimeout(connect, 1200);
      };

      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
      activeSocket?.close();
      rejectPendingMotions("Rover connection closed");
      if (socketRef.current === activeSocket) socketRef.current = null;
    };
  }, [addEvent, rejectPendingMotions]);

  const send = useCallback((message: ClientMessage) => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(message));
    return true;
  }, []);

  const drive = useCallback(
    (vx: number, wz: number) =>
      send({
        v: 1,
        type: "drive",
        vx,
        vy: 0,
        wz,
        ttl_ms: 500,
        seq: ++sequenceRef.current
      }),
    [send]
  );

  const startMotion = useCallback((
    message: Extract<ClientMessage, { type: "move" | "turn" }>
  ) => new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      pendingMotionsRef.current.delete(message.request_id);
      reject(new Error("Motion response timed out"));
    }, 120_000);
    pendingMotionsRef.current.set(message.request_id, { resolve, reject, timeoutId });
    if (!send(message)) {
      window.clearTimeout(timeoutId);
      pendingMotionsRef.current.delete(message.request_id);
      reject(new Error("Local Server is not connected"));
    }
  }), [send]);

  const nextMotionId = useCallback(() => {
    motionSequenceRef.current += 1;
    return `motion-${Date.now().toString(36)}-${motionSequenceRef.current}`;
  }, []);

  const move = useCallback((distanceM: number, speedMps = 0.18) => startMotion({
    v: 1,
    type: "move",
    request_id: nextMotionId(),
    distance_m: distanceM,
    speed_mps: speedMps
  }), [nextMotionId, startMotion]);

  const turn = useCallback((angleDeg: number, speedRadS = 0.70) => startMotion({
    v: 1,
    type: "turn",
    request_id: nextMotionId(),
    angle_deg: angleDeg,
    speed_rad_s: speedRadS
  }), [nextMotionId, startMotion]);

  const stop = useCallback(
    (reason = "operator") => send({ v: 1, type: "stop", reason }),
    [send]
  );

  const missionStop = useCallback(async (reason = "mission") => {
    if (!stop(reason)) throw new Error("Local Server is not connected");
  }, [stop]);

  const getPose = useCallback(async () => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      throw new Error("Local Server is not connected");
    }
    const pose = stateRef.current?.pose;
    if (!pose) throw new Error("Rover pose is not available yet");
    return { ...pose };
  }, []);

  const onPose = useCallback((listener: PoseListener) => {
    poseListenersRef.current.add(listener);
    const pose = stateRef.current?.pose;
    if (pose) {
      try {
        listener({ ...pose });
      } catch {
        poseListenersRef.current.delete(listener);
        addEvent("error", "A failed mission pose listener was removed");
      }
    }
    return () => poseListenersRef.current.delete(listener);
  }, [addEvent]);

  const onPerson = useCallback((listener: PersonListener) => {
    personListenersRef.current.add(listener);
    return () => personListenersRef.current.delete(listener);
  }, []);

  const onMarker = useCallback((listener: MarkerListener) => {
    markerListenersRef.current.add(listener);
    return () => markerListenersRef.current.delete(listener);
  }, []);

  const observe = useCallback((observation: PerceptionObservationInput) => send({
    v: 1,
    type: "perception_observation",
    observation_id: perceptionObservationId(),
    captured_at: Date.now() / 1000,
    ...observation
  }), [send]);

  const setPathClearance = useCallback((confirmed: boolean) => send({
    v: 1,
    type: "path_clearance",
    confirmed
  }), [send]);

  const serviceRover = useMemo<ServiceRover>(() => ({
    continuousFollowMaxSpeed: continuousFollowing ? 0.25 : undefined,
    continuousFollowDistanceGain: continuousFollowing ? 0.8 : undefined,
    setVelocity: continuousFollowing ? async (vx, wz) => {
      if (!Number.isFinite(vx) || !Number.isFinite(wz) || !drive(vx, wz)) {
        throw new Error("Continuous command could not be sent");
      }
    } : undefined,
    move,
    turn,
    stop: missionStop,
    getPose,
    onPose,
    onPerson,
    onMarker,
    getFrontObstacle: () => frontObstacleRef.current
  }), [continuousFollowing, drive, getPose, missionStop, move, onMarker, onPerson, onPose, turn]);

  return {
    status,
    clientId,
    control,
    state,
    frontObstacle,
    events,
    scenarioEvents,
    serviceRover,
    actions: {
      acquire: () => send({ v: 1, type: "acquire_control" }),
      release: () => send({ v: 1, type: "release_control" }),
      drive,
      move,
      turn,
      cancelMotion: () => send({ v: 1, type: "cancel_motion" }),
      stop,
      estop: () => send({ v: 1, type: "estop", reason: "PWA emergency stop" }),
      clearEstop: () => send({ v: 1, type: "clear_estop" }),
      resetPose: () => send({ v: 1, type: "reset_pose" }),
      setPathClearance,
      observe
    }
  };
}

function numberOrUndefined(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function recordOrUndefined(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : undefined;
}

function notifyListeners<T>(
  listeners: Set<(event: T) => void>,
  event: T,
  addEvent: (level: RoverEvent["level"], text: string) => void,
  kind: string
): void {
  for (const listener of listeners) {
    try {
      listener(event);
    } catch {
      listeners.delete(listener);
      addEvent("error", `A failed mission ${kind} listener was removed`);
    }
  }
}

let perceptionSequence = 0;

function perceptionObservationId(): string {
  perceptionSequence += 1;
  return `perception-${Date.now().toString(36)}-${perceptionSequence}`;
}
