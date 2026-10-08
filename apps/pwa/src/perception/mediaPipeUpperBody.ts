export interface PosePoint {
  x: number;
  y: number;
  visibility?: number;
  presence?: number;
}

export interface UpperBodyDetection {
  confidence: number;
  box: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export interface UpperBodyDetector {
  readonly label: string;
  detect(source: CanvasImageSource, timestampMs: number): Promise<UpperBodyDetection[]>;
  close(): void;
}

interface PoseLandmarkerLike {
  detectForVideo(source: CanvasImageSource, timestampMs: number): {
    landmarks: PosePoint[][];
  };
  close(): void;
}

type PoseLandmarkerLoader = () => Promise<PoseLandmarkerLike>;

const LEFT_SHOULDER = 11;
const RIGHT_SHOULDER = 12;
const LEFT_HIP = 23;
const RIGHT_HIP = 24;
const NOSE = 0;
const MIN_SHOULDER_VISIBILITY = 0.5;
const MIN_SHOULDER_SPAN = 0.025;

const WASM_BASE_URL =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

export class MediaPipeUpperBodyDetector implements UpperBodyDetector {
  readonly label = "upper-body pose";
  private detectorPromise: Promise<PoseLandmarkerLike> | null = null;
  private detector: PoseLandmarkerLike | null = null;
  private lastTimestampMs = 0;

  constructor(private readonly loadDetector: PoseLandmarkerLoader = loadMediaPipePoseLandmarker) {}

  async detect(
    source: CanvasImageSource,
    timestampMs: number
  ): Promise<UpperBodyDetection[]> {
    const detector = await this.getDetector();
    const monotonicTimestamp = Math.max(timestampMs, this.lastTimestampMs + 1);
    this.lastTimestampMs = monotonicTimestamp;
    return detector
      .detectForVideo(source, monotonicTimestamp)
      .landmarks
      .map(upperBodyFromLandmarks)
      .filter((detection): detection is UpperBodyDetection => detection !== null);
  }

  close(): void {
    this.detector?.close();
    this.detector = null;
    this.detectorPromise = null;
  }

  private async getDetector(): Promise<PoseLandmarkerLike> {
    if (!this.detectorPromise) {
      this.detectorPromise = this.loadDetector().then((detector) => {
        this.detector = detector;
        return detector;
      });
    }
    return this.detectorPromise;
  }
}

export function upperBodyFromLandmarks(
  landmarks: readonly PosePoint[]
): UpperBodyDetection | null {
  const leftShoulder = landmarks[LEFT_SHOULDER];
  const rightShoulder = landmarks[RIGHT_SHOULDER];
  if (!isVisible(leftShoulder) || !isVisible(rightShoulder)) return null;

  const shoulderSpan = Math.hypot(
    leftShoulder.x - rightShoulder.x,
    leftShoulder.y - rightShoulder.y
  );
  if (shoulderSpan < MIN_SHOULDER_SPAN) return null;

  const shoulderCenter = midpoint(leftShoulder, rightShoulder);
  const nose = landmarks[NOSE];
  const leftHip = landmarks[LEFT_HIP];
  const rightHip = landmarks[RIGHT_HIP];
  const hipsVisible = isVisible(leftHip, 0.35) && isVisible(rightHip, 0.35);
  const horizontalMargin = shoulderSpan * 0.3;
  const left = clamp(Math.min(leftShoulder.x, rightShoulder.x) - horizontalMargin);
  const right = clamp(Math.max(leftShoulder.x, rightShoulder.x) + horizontalMargin);
  const top = clamp(
    isVisible(nose, 0.3)
      ? nose.y - shoulderSpan * 0.35
      : shoulderCenter.y - shoulderSpan * 0.9
  );
  const bottom = clamp(
    hipsVisible
      ? Math.max(leftHip.y, rightHip.y) + shoulderSpan * 0.25
      : shoulderCenter.y + shoulderSpan * 1.75
  );
  if (right <= left || bottom <= top) return null;

  return {
    confidence: clamp((visibility(leftShoulder) + visibility(rightShoulder)) / 2),
    box: {
      x: left,
      y: top,
      width: right - left,
      height: bottom - top
    }
  };
}

async function loadMediaPipePoseLandmarker(): Promise<PoseLandmarkerLike> {
  const { FilesetResolver, PoseLandmarker } = await import("@mediapipe/tasks-vision");
  const vision = await FilesetResolver.forVisionTasks(WASM_BASE_URL);
  return PoseLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: MODEL_URL,
      delegate: "CPU"
    },
    runningMode: "VIDEO",
    numPoses: 1,
    minPoseDetectionConfidence: 0.55,
    minPosePresenceConfidence: 0.55,
    minTrackingConfidence: 0.55,
    outputSegmentationMasks: false
  }) as Promise<PoseLandmarkerLike>;
}

function isVisible(point: PosePoint | undefined, threshold = MIN_SHOULDER_VISIBILITY): point is PosePoint {
  return point !== undefined
    && visibility(point) >= threshold
    && (point.presence ?? 1) >= threshold;
}

function visibility(point: PosePoint): number {
  return point.visibility ?? 1;
}

function midpoint(first: PosePoint, second: PosePoint): PosePoint {
  return {
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2
  };
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}
