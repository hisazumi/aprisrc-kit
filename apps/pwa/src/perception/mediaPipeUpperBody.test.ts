import { describe, expect, it, vi } from "vitest";

import {
  MediaPipeUpperBodyDetector,
  type PosePoint,
  upperBodyFromLandmarks
} from "./mediaPipeUpperBody";

function upperBodyPose(): PosePoint[] {
  const landmarks = Array.from({ length: 33 }, () => ({
    x: 0.5,
    y: 0.5,
    visibility: 0
  }));
  landmarks[0] = { x: 0.5, y: 0.2, visibility: 0.9 };
  landmarks[11] = { x: 0.4, y: 0.36, visibility: 0.9 };
  landmarks[12] = { x: 0.6, y: 0.36, visibility: 0.8 };
  landmarks[23] = { x: 0.43, y: 0.72, visibility: 0.8 };
  landmarks[24] = { x: 0.57, y: 0.72, visibility: 0.8 };
  return landmarks;
}

describe("upperBodyFromLandmarks", () => {
  it("builds a tracking box from shoulders without requiring legs", () => {
    const detection = upperBodyFromLandmarks(upperBodyPose());

    expect(detection?.confidence).toBeCloseTo(0.85);
    expect(detection?.box.x).toBeCloseTo(0.34);
    expect(detection?.box.width).toBeCloseTo(0.32);
    expect(detection?.box.y).toBeCloseTo(0.13);
    expect(detection?.box.height).toBeCloseTo(0.64);
  });

  it("uses a shoulder-based torso estimate when the hips are outside the frame", () => {
    const landmarks = upperBodyPose();
    landmarks[23] = { x: 0.43, y: 1.1, visibility: 0.1 };
    landmarks[24] = { x: 0.57, y: 1.1, visibility: 0.1 };

    const detection = upperBodyFromLandmarks(landmarks);

    expect(detection).not.toBeNull();
    expect(detection?.box.height).toBeCloseTo(0.58);
  });

  it("rejects a pose when either shoulder is unreliable", () => {
    const landmarks = upperBodyPose();
    landmarks[12] = { x: 0.6, y: 0.36, visibility: 0.2 };

    expect(upperBodyFromLandmarks(landmarks)).toBeNull();
  });
});

describe("MediaPipeUpperBodyDetector", () => {
  it("loads lazily and keeps video timestamps monotonic", async () => {
    const close = vi.fn();
    const detectForVideo = vi.fn((_: CanvasImageSource, __: number) => ({
      landmarks: [upperBodyPose()]
    }));
    const load = vi.fn(async () => ({ detectForVideo, close }));
    const detector = new MediaPipeUpperBodyDetector(load);

    await detector.detect({} as CanvasImageSource, 20);
    await detector.detect({} as CanvasImageSource, 20);

    expect(load).toHaveBeenCalledOnce();
    expect(detectForVideo.mock.calls.map((call) => call[1])).toEqual([20, 21]);
    detector.close();
    expect(close).toHaveBeenCalledOnce();
  });
});
