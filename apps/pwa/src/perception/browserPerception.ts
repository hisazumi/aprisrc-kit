import type { PerceptionObservationInput } from "../protocol";
import {
  MediaPipeUpperBodyDetector,
  type UpperBodyDetector
} from "./mediaPipeUpperBody";

interface DetectionBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface BarcodeDetectorResult {
  rawValue: string;
  boundingBox: DetectionBox;
}

interface BarcodeDetectorInstance {
  detect(source: CanvasImageSource): Promise<BarcodeDetectorResult[]>;
}

interface DetectorGlobals {
  BarcodeDetector?: new (options?: { formats?: string[] }) => BarcodeDetectorInstance;
}

interface BrowserPerceptionOptions {
  globals?: DetectorGlobals;
  personDetector?: UpperBodyDetector | null;
}

export interface DetectionSupport {
  person: boolean;
  marker: boolean;
}

export interface FrameDetection {
  key: string;
  observation: PerceptionObservationInput;
}

export class BrowserPerception {
  readonly support: DetectionSupport;
  readonly personDetectorLabel: string;
  private readonly personDetector: UpperBodyDetector | null;
  private readonly barcodeDetector: BarcodeDetectorInstance | null;

  constructor(options: BrowserPerceptionOptions = {}) {
    const globals = options.globals ?? globalThis as DetectorGlobals;
    this.personDetector = options.personDetector === undefined
      ? new MediaPipeUpperBodyDetector()
      : options.personDetector;
    this.barcodeDetector = globals.BarcodeDetector
      ? new globals.BarcodeDetector({ formats: ["qr_code"] })
      : null;
    this.support = {
      person: this.personDetector !== null,
      marker: this.barcodeDetector !== null
    };
    this.personDetectorLabel = this.personDetector?.label ?? "not supported";
  }

  async detect(
    source: CanvasImageSource,
    width: number,
    height: number,
    inputSource: "camera" | "recorded"
  ): Promise<FrameDetection[]> {
    if (width <= 0 || height <= 0) return [];
    const [people, barcodes] = await Promise.all([
      this.personDetector?.detect(source, performance.now()) ?? [],
      this.barcodeDetector?.detect(source).catch(() => []) ?? []
    ]);
    const focalPx = width / (2 * Math.tan(Math.PI / 6));
    const detections: FrameDetection[] = people.map((person, index) => {
      const box = person.box;
      const pixelBox = {
        x: box.x * width,
        y: box.y * height,
        width: box.width * width,
        height: box.height * height
      };
      return {
        key: `person:${index}`,
        observation: {
          kind: "person",
          status: "detected",
          confidence: person.confidence,
          source: inputSource,
          payload: {
            person_id: `camera-person-${index + 1}`,
            center_x: box.x + box.width / 2,
            center_y: box.y + box.height / 2,
            width: box.width,
            height: box.height,
            bearing_deg: bearingDegrees(pixelBox, width, focalPx)
          }
        }
      };
    });

    for (const barcode of barcodes) {
      const markerId = parseMarkerId(barcode.rawValue);
      if (markerId === null || barcode.boundingBox.width <= 0) continue;
      const bearingRad = bearingRadians(barcode.boundingBox, width, focalPx);
      const markerSizeM = 0.16;
      const rangeM = markerSizeM * focalPx / barcode.boundingBox.width;
      detections.push({
        key: `marker:${markerId}`,
        observation: {
          kind: "marker",
          status: "detected",
          confidence: 0.90,
          source: inputSource,
          payload: {
            marker_id: markerId,
            relative_x_m: rangeM * Math.cos(bearingRad),
            relative_y_m: rangeM * Math.sin(bearingRad)
          }
        }
      });
    }
    return detections;
  }

  close(): void {
    this.personDetector?.close();
  }
}

interface TrackState {
  lastSeenMs: number;
  lastEmittedMs: number;
  observation: PerceptionObservationInput;
  lost: boolean;
}

export class DetectionTracker {
  private readonly tracks = new Map<string, TrackState>();

  update(detections: readonly FrameDetection[], nowMs: number): PerceptionObservationInput[] {
    const output: PerceptionObservationInput[] = [];
    const present = new Set(detections.map((detection) => detection.key));
    for (const detection of detections) {
      const current = this.tracks.get(detection.key);
      if (!current || current.lost || nowMs - current.lastEmittedMs >= 600) {
        output.push(detection.observation);
      }
      this.tracks.set(detection.key, {
        lastSeenMs: nowMs,
        lastEmittedMs: output.at(-1) === detection.observation
          ? nowMs
          : current?.lastEmittedMs ?? nowMs,
        observation: detection.observation,
        lost: false
      });
    }

    for (const [key, track] of this.tracks) {
      if (present.has(key) || track.lost || nowMs - track.lastSeenMs < 1200) continue;
      output.push(lostObservation(track.observation));
      this.tracks.set(key, { ...track, lost: true, lastEmittedMs: nowMs });
    }
    return output;
  }

  reset(): void {
    this.tracks.clear();
  }
}

export function parseMarkerId(rawValue: string): number | null {
  const match = rawValue.trim().match(/^(?:APRIS[:\s-]*)?(?:MARKER[:\s-]*)?(\d+)$/i);
  if (!match) return null;
  const markerId = Number(match[1]);
  return Number.isSafeInteger(markerId) ? markerId : null;
}

function normalizedBox(box: DetectionBox, width: number, height: number): DetectionBox {
  return {
    x: clamp(box.x / width),
    y: clamp(box.y / height),
    width: clamp(box.width / width),
    height: clamp(box.height / height)
  };
}

function bearingRadians(box: DetectionBox, width: number, focalPx: number): number {
  const centerX = box.x + box.width / 2;
  return Math.atan((width / 2 - centerX) / focalPx);
}

function bearingDegrees(box: DetectionBox, width: number, focalPx: number): number {
  return bearingRadians(box, width, focalPx) * 180 / Math.PI;
}

function lostObservation(observation: PerceptionObservationInput): PerceptionObservationInput {
  const idKey = observation.kind === "person" ? "person_id" : "marker_id";
  return {
    kind: observation.kind,
    status: "lost",
    confidence: 0,
    source: observation.source,
    payload: { [idKey]: observation.payload[idKey] }
  };
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}
