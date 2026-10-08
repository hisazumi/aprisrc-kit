import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { RoverState } from "../protocol";
import { MotionTrace } from "./MotionTrace";

const state: RoverState = {
  timestamp: 1,
  connected: true,
  pose: { x: 0, y: 0, yaw: 0 },
  velocity: { vx: 0, vy: 0, wz: 0 },
  battery_percent: null,
  capabilities: {
    lateral_motion: false,
    pose: true,
    imu: false,
    lidar: false,
    camera: false,
  },
  command_age_ms: null,
  pose_quality: {
    frame_id: "course",
    source: "encoder_only",
    confidence: 0.5,
    age_ms: 0,
    encoder_status: "ok",
    imu_status: "missing",
    anomalies: [],
    last_marker_id: null,
  },
};

describe("motion trace", () => {
  it("renders commanded and observed velocity plots", () => {
    const html = renderToStaticMarkup(
      <MotionTrace command={{ sampleId: 1, vx: 0, wz: 0.6 }} state={state} />,
    );

    expect(html).toContain("Command vs factory feedback");
    expect(html).toContain("Angular velocity (rad/s) over 12 seconds");
    expect(html).toContain("Linear velocity (m/s) over 12 seconds");
  });
});
