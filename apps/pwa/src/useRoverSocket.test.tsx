import { StrictMode, useEffect } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRoverSocket } from "./useRoverSocket";

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
    this.onmessage?.({
      data: JSON.stringify({
        v: 1,
        type: "hello",
        client_id: "test",
        server_name: "test",
        capabilities: {
          lateral_motion: false,
          pose: true,
          imu: true,
          lidar: false,
          camera: false
        }
      })
    });
    this.onmessage?.({
      data: JSON.stringify({
        v: 1,
        type: "control",
        owner_client_id: null,
        is_owner: false,
        estop_latched: false
      })
    });
  }

  receive(message: unknown): void {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    queueMicrotask(() => this.onclose?.());
  }
}

function Harness() {
  const rover = useRoverSocket();
  return (
    <button
      disabled={rover.status !== "connected" || rover.control.ownerClientId !== null}
      onClick={rover.actions.acquire}
    >
      Acquire control
    </button>
  );
}

function MotionHarness({ onComplete }: { onComplete: () => void }) {
  const rover = useRoverSocket();
  return <button onClick={() => void rover.actions.move(0.4).then(onComplete)}>Move</button>;
}

function ServiceApiHarness({
  onPose,
  onRead,
  onStop
}: {
  onPose: (pose: { x: number; y: number; yaw: number }) => void;
  onRead: (pose: { x: number; y: number; yaw: number }) => void;
  onStop: () => void;
}) {
  const rover = useRoverSocket();
  useEffect(() => rover.serviceRover.onPose(onPose), [onPose, rover.serviceRover]);
  return (
    <>
      <button onClick={() => void rover.serviceRover.getPose().then(onRead)}>Read pose</button>
      <button onClick={() => void rover.serviceRover.stop("service requested").then(onStop)}>
        Stop service
      </button>
    </>
  );
}

function ScenarioEventHarness() {
  const rover = useRoverSocket();
  const event = rover.scenarioEvents[0];
  return <output>{event ? `${event.kind}:${event.source}` : "none"}</output>;
}

function PerceptionHarness({
  onPerson,
  onMarker
}: {
  onPerson: (event: { personId: string; status: string }) => void;
  onMarker: (event: { markerId: number; status: string }) => void;
}) {
  const rover = useRoverSocket();
  useEffect(() => rover.serviceRover.onPerson(onPerson), [onPerson, rover.serviceRover]);
  useEffect(() => rover.serviceRover.onMarker(onMarker), [onMarker, rover.serviceRover]);
  return (
    <button onClick={() => rover.actions.observe({
      kind: "person",
      status: "detected",
      confidence: 0.9,
      source: "recorded",
      payload: { person_id: "p1" }
    })}>
      Observe
    </button>
  );
}

function PathClearanceHarness() {
  const rover = useRoverSocket();
  return (
    <>
      <output>{rover.frontObstacle?.state ?? "none"}</output>
      <button onClick={() => rover.actions.setPathClearance(true)}>Path clear</button>
    </>
  );
}

describe("useRoverSocket", () => {
  const realWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(() => {
    globalThis.WebSocket = realWebSocket;
    vi.restoreAllMocks();
  });

  it("keeps the current socket when StrictMode closes the superseded socket", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <StrictMode>
          <Harness />
        </StrictMode>
      );
      await Promise.resolve();
    });

    expect(FakeWebSocket.instances).toHaveLength(2);
    const current = FakeWebSocket.instances[1];

    await act(async () => {
      current.open();
      await Promise.resolve();
    });

    expect(JSON.parse(current.sent[0] ?? "null")).toMatchObject({
      v: 1,
      type: "client_hello",
      client_kind: "service_app",
      app_version: "0.1.0"
    });

    const button = container.querySelector("button");
    expect(button?.disabled).toBe(false);

    await act(async () => button?.click());
    expect(current.sent.map((message) => JSON.parse(message))).toContainEqual({
      v: 1,
      type: "acquire_control"
    });

    await act(async () => root.unmount());
  });

  it("resolves a high-level motion when the server reports completion", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const onComplete = vi.fn();

    await act(async () => {
      root.render(<MotionHarness onComplete={onComplete} />);
      await Promise.resolve();
    });

    const socket = FakeWebSocket.instances[0];
    await act(async () => socket.open());
    await act(async () => container.querySelector("button")?.click());

    const motion = JSON.parse(socket.sent.at(-1) ?? "null");
    expect(motion).toMatchObject({
      v: 1,
      type: "move",
      distance_m: 0.4,
      speed_mps: 0.18
    });

    await act(async () => {
      socket.receive({
        v: 1,
        type: "motion",
        request_id: motion.request_id,
        motion: "move",
        status: "completed",
        detail: ""
      });
      await Promise.resolve();
    });

    expect(onComplete).toHaveBeenCalledOnce();
    await act(async () => root.unmount());
  });

  it("exposes pose observation, pose reads and stop through the service API", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const onPose = vi.fn();
    const onRead = vi.fn();
    const onStop = vi.fn();

    await act(async () => {
      root.render(<ServiceApiHarness onPose={onPose} onRead={onRead} onStop={onStop} />);
      await Promise.resolve();
    });

    const socket = FakeWebSocket.instances[0];
    await act(async () => socket.open());
    const pose = { x: 0.4, y: -0.2, yaw: 1.2 };
    await act(async () => {
      socket.receive({
        v: 1,
        type: "state",
        state: {
          timestamp: 1,
          connected: true,
          pose,
          velocity: { vx: 0, vy: 0, wz: 0 },
          battery_percent: 90,
          capabilities: {
            lateral_motion: false,
            pose: true,
            imu: true,
            lidar: false,
            camera: false
          },
          command_age_ms: null
        }
      });
      await Promise.resolve();
    });

    expect(onPose).toHaveBeenCalledWith(pose);

    const buttons = container.querySelectorAll("button");
    await act(async () => {
      buttons[0]?.click();
      buttons[1]?.click();
      await Promise.resolve();
    });

    expect(onRead).toHaveBeenCalledWith(pose);
    expect(onStop).toHaveBeenCalledOnce();
    expect(socket.sent.map((message) => JSON.parse(message))).toContainEqual({
      v: 1,
      type: "stop",
      reason: "service requested"
    });

    await act(async () => root.unmount());
  });

  it("exposes injected Simulator events without mixing them into rover state", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => {
      root.render(<ScenarioEventHarness />);
      await Promise.resolve();
    });
    const socket = FakeWebSocket.instances[0];
    await act(async () => socket.open());
    await act(async () => {
      socket.receive({
        v: 1,
        type: "scenario_event",
        event_id: "event-1",
        kind: "marker",
        payload: { markerId: 1 },
        source: "scenario",
        scenario_id: "perception-inputs"
      });
      await Promise.resolve();
    });

    expect(container.textContent).toBe("marker:scenario");
    await act(async () => root.unmount());
  });

  it("sends observations and exposes accepted person and marker events", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const onPerson = vi.fn();
    const onMarker = vi.fn();

    await act(async () => {
      root.render(<PerceptionHarness onPerson={onPerson} onMarker={onMarker} />);
      await Promise.resolve();
    });
    const socket = FakeWebSocket.instances[0];
    await act(async () => socket.open());
    await act(async () => container.querySelector("button")?.click());

    expect(JSON.parse(socket.sent.at(-1) ?? "null")).toMatchObject({
      v: 1,
      type: "perception_observation",
      kind: "person",
      source: "recorded",
      payload: { person_id: "p1" }
    });

    await act(async () => {
      socket.receive({
        v: 1,
        type: "perception_event",
        event_id: "person-1",
        kind: "person",
        status: "detected",
        confidence: 0.9,
        captured_at: 10,
        source: "camera",
        payload: { person_id: "p1", center_x: 0.5 },
        accepted: true,
        reason: ""
      });
      socket.receive({
        v: 1,
        type: "perception_event",
        event_id: "marker-1",
        kind: "marker",
        status: "detected",
        confidence: 0.9,
        captured_at: 11,
        source: "scenario",
        payload: {
          marker_id: 1,
          relative_x_m: 0.5,
          pose_correction: { applied: true, innovation_m: 0.2 }
        },
        accepted: true,
        reason: ""
      });
      await Promise.resolve();
    });

    expect(onPerson).toHaveBeenCalledWith(expect.objectContaining({
      personId: "p1",
      status: "detected"
    }));
    expect(onMarker).toHaveBeenCalledWith(expect.objectContaining({
      markerId: 1,
      poseCorrection: { applied: true, innovationM: 0.2 }
    }));
    await act(async () => root.unmount());
  });

  it("sends operator path clearance and exposes the authoritative state", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => {
      root.render(<PathClearanceHarness />);
      await Promise.resolve();
    });
    const socket = FakeWebSocket.instances[0];
    await act(async () => socket.open());
    await act(async () => container.querySelector("button")?.click());

    expect(JSON.parse(socket.sent.at(-1) ?? "null")).toEqual({
      v: 1,
      type: "path_clearance",
      confirmed: true
    });

    await act(async () => {
      socket.receive({
        v: 1,
        type: "front_obstacle",
        obstacle: {
          state: "CLEAR",
          observed_state: "CLEAR",
          perception_health: "healthy",
          source: "manual",
          stale: false,
          latched: false
        }
      });
      await Promise.resolve();
    });
    expect(container.querySelector("output")?.textContent).toBe("CLEAR");

    await act(async () => root.unmount());
  });
});
