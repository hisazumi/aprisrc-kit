import { describe, expect, it, vi } from "vitest";

import { BrowserPerception, DetectionTracker, parseMarkerId } from "./browserPerception";
import type { UpperBodyDetector } from "./mediaPipeUpperBody";

describe("browser perception", () => {
  it("turns upper-body and QR detections into normalized observations", async () => {
    const personDetector: UpperBodyDetector = {
      label: "test upper body",
      detect: vi.fn().mockResolvedValue([{
        confidence: 0.88,
        box: { x: 0.4, y: 0.1, width: 0.2, height: 0.6 }
      }]),
      close: vi.fn()
    };
    class BarcodeDetector {
      detect = vi.fn().mockResolvedValue([
        { rawValue: "APRIS:MARKER:7", boundingBox: { x: 440, y: 180, width: 120, height: 120 } }
      ]);
    }
    const perception = new BrowserPerception({
      globals: { BarcodeDetector },
      personDetector
    });
    const detections = await perception.detect({} as CanvasImageSource, 1000, 600, "recorded");

    expect(perception.support).toEqual({ person: true, marker: true });
    expect(perception.personDetectorLabel).toBe("test upper body");
    expect(detections[0]?.observation).toMatchObject({
      kind: "person",
      source: "recorded",
      confidence: 0.88,
      payload: { center_x: 0.5, center_y: 0.4, width: 0.2 }
    });
    expect(detections[1]?.observation).toMatchObject({
      kind: "marker",
      payload: { marker_id: 7, relative_y_m: 0 }
    });
    perception.close();
    expect(personDetector.close).toHaveBeenCalledOnce();
  });

  it("emits one explicit lost event after the target timeout", () => {
    const tracker = new DetectionTracker();
    const detection = {
      key: "person:0",
      observation: {
        kind: "person" as const,
        status: "detected" as const,
        confidence: 0.9,
        source: "camera" as const,
        payload: { person_id: "p1" }
      }
    };

    expect(tracker.update([detection], 0)).toHaveLength(1);
    expect(tracker.update([], 1000)).toHaveLength(0);
    expect(tracker.update([], 1300)).toEqual([{
      kind: "person",
      status: "lost",
      confidence: 0,
      source: "camera",
      payload: { person_id: "p1" }
    }]);
    expect(tracker.update([], 2600)).toHaveLength(0);
  });

  it("accepts only explicit numeric APRIS marker values", () => {
    expect(parseMarkerId("APRIS:MARKER:12")).toBe(12);
    expect(parseMarkerId("marker 3")).toBe(3);
    expect(parseMarkerId("https://example.com")).toBeNull();
  });
});
