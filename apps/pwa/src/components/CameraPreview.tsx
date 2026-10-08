import { useCallback, useEffect, useRef, useState } from "react";

import { BrowserPerception, DetectionTracker } from "../perception/browserPerception";
import type { PerceptionObservationInput } from "../protocol";
import type { VirtualPersonProjection } from "../simulation/virtualPerson";

export type CameraFacing = "environment" | "user";
type CameraStatus = "idle" | "requesting" | "streaming" | "error";
type PerceptionStatus = "idle" | "loading" | "ready" | "error";

interface PersonOverlay {
  centerX: number;
  centerY: number;
  width: number;
  height: number;
  confidence: number;
}

interface CameraPreviewProps {
  onObservation?: (observation: PerceptionObservationInput) => boolean;
  virtualPerson?: VirtualPersonProjection | null;
  variant?: "developer" | "service";
  initialFacing?: CameraFacing;
  requestedFacing?: CameraFacing;
  requestedActive?: boolean;
  onPerceptionReadyChange?: (ready: boolean) => void;
}

function stopTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

function cameraErrorMessage(error: unknown): string {
  if (!(error instanceof DOMException)) {
    return "The camera could not be started.";
  }

  switch (error.name) {
    case "NotAllowedError":
      return "Camera permission was denied. Allow access in the browser settings and try again.";
    case "NotFoundError":
      return "No camera was found on this device.";
    case "NotReadableError":
      return "The camera is unavailable or already in use by another application.";
    case "SecurityError":
      return "Camera access requires a secure HTTPS connection.";
    default:
      return `The camera could not be started (${error.name}).`;
  }
}

export function CameraPreview({
  onObservation,
  virtualPerson,
  variant = "developer",
  initialFacing = "environment",
  requestedFacing,
  requestedActive,
  onPerceptionReadyChange
}: CameraPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recordedUrlRef = useRef<string | null>(null);
  const requestIdRef = useRef(0);
  const perceptionRef = useRef<BrowserPerception | null>(null);
  const trackerRef = useRef(new DetectionTracker());
  if (perceptionRef.current === null) perceptionRef.current = new BrowserPerception();
  const [facing, setFacing] = useState<CameraFacing>(initialFacing);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [inputSource, setInputSource] = useState<"camera" | "recorded">("camera");
  const [perceptionEnabled, setPerceptionEnabled] = useState(false);
  const [perceptionStatus, setPerceptionStatus] = useState<PerceptionStatus>("idle");
  const [personOverlay, setPersonOverlay] = useState<PersonOverlay | null>(null);
  const [videoAspectRatio, setVideoAspectRatio] = useState(16 / 9);
  const [lastDetection, setLastDetection] = useState("No detections yet");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onPerceptionReadyChange?.(inputSource === "camera" && status === "streaming"
      && perceptionEnabled && perceptionStatus === "ready");
  }, [inputSource, status, perceptionEnabled, perceptionStatus, onPerceptionReadyChange]);
  useEffect(() => () => onPerceptionReadyChange?.(false), [onPerceptionReadyChange]);

  const detachCurrentInput = useCallback(() => {
    stopTracks(streamRef.current);
    streamRef.current = null;
    if (recordedUrlRef.current) {
      URL.revokeObjectURL(recordedUrlRef.current);
      recordedUrlRef.current = null;
    }
    if (videoRef.current) {
      if (!videoRef.current.paused) videoRef.current.pause();
      videoRef.current.srcObject = null;
      videoRef.current.removeAttribute("src");
    }
    trackerRef.current.reset();
    setPerceptionEnabled(false);
    setPerceptionStatus("idle");
    setPersonOverlay(null);
    setVideoAspectRatio(16 / 9);
    setLastDetection("No detections yet");
  }, []);

  const startCamera = useCallback(async (nextFacing: CameraFacing = facing) => {
    const requestId = ++requestIdRef.current;
    detachCurrentInput();
    setError(null);
    setInputSource("camera");

    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("error");
      setError("Camera access is not supported by this browser or connection.");
      return;
    }

    setStatus("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: nextFacing },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      });

      if (requestId !== requestIdRef.current) {
        stopTracks(stream);
        return;
      }

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        void videoRef.current.play().catch(() => undefined);
      }
      setStatus("streaming");
      if (variant === "service"
        && (perceptionRef.current?.support.person || perceptionRef.current?.support.marker)) {
        setPerceptionStatus("loading");
        setPerceptionEnabled(true);
      }
    } catch (caught) {
      if (requestId !== requestIdRef.current) return;
      setStatus("error");
      setError(cameraErrorMessage(caught));
    }
  }, [detachCurrentInput, facing, variant]);

  const stopInput = useCallback(() => {
    requestIdRef.current += 1;
    detachCurrentInput();
    setStatus("idle");
    setError(null);
  }, [detachCurrentInput]);

  const loadRecordedVideo = useCallback(async (file: File) => {
    const requestId = ++requestIdRef.current;
    detachCurrentInput();
    setError(null);
    setInputSource("recorded");
    setStatus("requesting");
    try {
      const url = URL.createObjectURL(file);
      recordedUrlRef.current = url;
      const video = videoRef.current;
      if (!video) throw new Error("Video element is unavailable");
      video.src = url;
      video.loop = true;
      await video.play();
      if (requestId !== requestIdRef.current) return;
      setStatus("streaming");
    } catch (caught) {
      if (requestId !== requestIdRef.current) return;
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "The video could not be opened.");
    }
  }, [detachCurrentInput]);

  const switchCamera = useCallback(() => {
    const nextFacing = facing === "environment" ? "user" : "environment";
    const shouldRestart = status === "requesting" || status === "streaming";
    setFacing(nextFacing);
    if (shouldRestart) void startCamera(nextFacing);
  }, [facing, startCamera, status]);

  useEffect(() => {
    if (!requestedFacing || requestedFacing === facing) return;
    const shouldRestart = status === "requesting" || status === "streaming";
    setFacing(requestedFacing);
    if (shouldRestart) void startCamera(requestedFacing);
  }, [facing, requestedFacing, startCamera, status]);

  useEffect(() => {
    if (virtualPerson !== undefined || requestedActive === undefined) return;
    if (requestedActive) void startCamera(requestedFacing ?? facing);
    else stopInput();
  }, [requestedActive]);

  useEffect(() => () => {
    requestIdRef.current += 1;
    detachCurrentInput();
    perceptionRef.current?.close();
  }, [detachCurrentInput]);

  useEffect(() => {
    if (!perceptionEnabled || status !== "streaming") return;
    let disposed = false;
    let inFlight = false;
    const detect = async () => {
      const video = videoRef.current;
      const perception = perceptionRef.current;
      if (disposed || inFlight || !video || !perception || video.readyState < 2) return;
      inFlight = true;
      try {
        const detections = await perception.detect(
          video,
          video.videoWidth,
          video.videoHeight,
          inputSource
        );
        if (disposed) return;
        const observations = trackerRef.current.update(detections, performance.now());
        for (const observation of observations) {
          onObservation?.(observation);
          if (observation.kind === "person") {
            setPersonOverlay(personOverlayFromObservation(observation));
          }
        }
        setPerceptionStatus("ready");
        if (observations.length > 0) {
          const latest = observations.at(-1);
          setLastDetection(
            `${latest?.kind} ${latest?.status} · ${latest?.confidence.toFixed(2)}`
          );
        }
      } catch (cause) {
        if (disposed) return;
        setPerceptionStatus("error");
        setPerceptionEnabled(false);
        setPersonOverlay(null);
        setError(
          cause instanceof Error
            ? `Upper-body detection could not start: ${cause.message}`
            : "Upper-body detection could not start."
        );
      } finally {
        inFlight = false;
      }
    };
    void detect();
    const timer = window.setInterval(() => void detect(), 300);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [inputSource, onObservation, perceptionEnabled, status]);

  const cameraLabel = inputSource === "recorded"
    ? "Recorded video"
    : facing === "environment" ? "Rear camera" : "Front camera";
  const support = perceptionRef.current.support;
  const detectorLabel = [
    support.person && perceptionRef.current.personDetectorLabel,
    support.marker && "QR marker"
  ]
    .filter(Boolean)
    .join(" + ") || "not supported";
  const virtualMode = virtualPerson !== undefined;
  const selectedLabel = virtualMode ? "Virtual camera" : cameraLabel;
  const latestLabel = virtualMode
    ? virtualPerson?.visible ? "person detected · 0.95" : "person outside view"
    : lastDetection;
  const cameraView = (
    <div className="camera-viewport" style={{ aspectRatio: videoAspectRatio }}>
      <video
        ref={videoRef}
        muted
        playsInline
        aria-label="Camera preview"
        onLoadedMetadata={(event) => {
          const video = event.currentTarget;
          if (video.videoWidth > 0 && video.videoHeight > 0) {
            setVideoAspectRatio(video.videoWidth / video.videoHeight);
          }
        }}
      />
      {!virtualMode && status === "streaming" && personOverlay && (
        <CameraDetectionOverlay detection={personOverlay} />
      )}
      {virtualMode && <VirtualCameraView projection={virtualPerson} />}
      {status !== "streaming" && !virtualMode && (
        <div className="camera-placeholder">
          <span aria-hidden="true">◎</span>
          <strong>{status === "requesting" ? "Requesting camera…" : "Camera is off"}</strong>
          <small>{cameraLabel}</small>
        </div>
      )}
    </div>
  );

  if (variant === "service") {
    return (
      <section className="service-vision" aria-label="Smartphone vision">
        {cameraView}
        <div className="service-vision__controls">
          <div>
            <p className="section-label">SMARTPHONE VISION</p>
            <h2>
              {virtualMode
                ? "Scenario perception ready"
                : facing === "environment" && support.marker
                  ? "Looking for destination markers"
                  : !support.person
                    ? "Person detection unavailable"
                : perceptionStatus === "loading" ? "Preparing upper-body tracking"
                  : perceptionStatus === "error" ? "Detection unavailable"
                    : status === "streaming" ? "Looking for people" : "Vision is off"}
            </h2>
            <span>
              {virtualMode
                ? "The simulator supplies the same person and marker events consumed by the mission."
                : facing === "environment" && support.marker && status === "streaming"
                  ? lastDetection
                  : !support.person
                    ? "Use the Simulator to test the service."
                : perceptionStatus === "loading"
                  ? "Loading the on-device pose model…"
                  : status === "streaming" ? lastDetection : "Use the front camera on the rover."}
            </span>
          </div>
          {!virtualMode && <div className="service-vision__actions">
            {status === "streaming" || status === "requesting" ? (
              <button className="button button--quiet" onClick={stopInput}>Stop vision</button>
            ) : (
              <button
                className="button button--primary"
                disabled={!support.person && !support.marker}
                onClick={() => void startCamera()}
              >
                Start vision
              </button>
            )}
            <button
              className="button button--quiet"
              disabled={inputSource === "recorded"}
              onClick={switchCamera}
            >
              Use {facing === "environment" ? "front" : "rear"} camera
            </button>
          </div>}
          {!window.isSecureContext && (
            <p className="camera-warning">
              Camera access requires HTTPS when this page is opened from a phone.
            </p>
          )}
          {error && <p className="camera-error" role="alert">{error}</p>}
        </div>
      </section>
    );
  }

  return (
    <article className="panel panel--camera">
      <div className="panel__heading">
        <div>
          <p className="section-label">SMARTPHONE SENSOR</p>
          <h2>Camera preview</h2>
        </div>
        <span className={`camera-status camera-status--${virtualMode ? "streaming" : status}`}>
          {virtualMode ? "Simulation active" : status === "streaming" ? "Camera active" : status}
        </span>
      </div>

      <div className="camera-layout">
        {cameraView}

        <div className="camera-sidebar">
          <p>
            {virtualMode
              ? "This Lab view renders the same normalized person observation consumed by Follow me. The box position, size, and bearing are simulated camera measurements."
              : "Person and APRIS QR marker detection runs on this device when supported by the browser. Only validated observations are sent to the Local Server."}
          </p>
          {!virtualMode && <div className="camera-actions">
            {status === "streaming" || status === "requesting" ? (
              <button className="button button--quiet" onClick={stopInput}>
                Stop input
              </button>
            ) : (
              <button
                className="button button--primary"
                onClick={() => void startCamera()}
              >
                Start camera
              </button>
            )}
            <button
              className="button button--quiet"
              disabled={inputSource === "recorded"}
              onClick={switchCamera}
            >
              Use {facing === "environment" ? "front" : "rear"} camera
            </button>
            <label className="button button--quiet camera-file-button">
              Open recorded video
              <input
                type="file"
                accept="video/*"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void loadRecordedVideo(file);
                  event.target.value = "";
                }}
              />
            </label>
            <button
              className="button button--primary"
              disabled={status !== "streaming" || (!support.person && !support.marker)}
              onClick={() => setPerceptionEnabled((current) => {
                setPerceptionStatus(current ? "idle" : "loading");
                if (current) setPersonOverlay(null);
                return !current;
              })}
            >
              {perceptionEnabled ? "Stop perception" : "Start perception"}
            </button>
          </div>}
          <dl className="camera-facts">
            <div><dt>Selected</dt><dd>{selectedLabel}</dd></div>
            <div><dt>Audio</dt><dd>Disabled</dd></div>
            <div><dt>Transport</dt><dd>{virtualMode ? "In-memory" : "On-device only"}</dd></div>
            <div><dt>Detectors</dt><dd>{virtualMode ? "simulated person" : detectorLabel}</dd></div>
            <div><dt>Latest</dt><dd>{latestLabel}</dd></div>
          </dl>
          {!window.isSecureContext && (
            <p className="camera-warning">
              A phone connected by local IP needs HTTPS before the browser can grant camera access.
            </p>
          )}
          {error && <p className="camera-error" role="alert">{error}</p>}
        </div>
      </div>
    </article>
  );
}

function VirtualCameraView({
  projection
}: {
  projection: VirtualPersonProjection | null;
}) {
  const visible = projection?.visible === true;
  const boxStyle = visible ? {
    left: percent(projection.centerX - projection.width / 2),
    top: percent(projection.centerY - projection.height / 2),
    width: percent(projection.width),
    height: percent(projection.height)
  } : undefined;

  return (
    <div className="virtual-camera" aria-label="Virtual camera person detection">
      <div className="virtual-camera__horizon" />
      <div className="virtual-camera__centerline" />
      {visible && (
        <div className="virtual-camera__detection" style={boxStyle}>
          <div className="virtual-camera__label">PERSON 95%</div>
          <div className="virtual-camera__person" aria-hidden="true">
            <span className="virtual-camera__head" />
            <span className="virtual-camera__body" />
            <span className="virtual-camera__arm virtual-camera__arm--left" />
            <span className="virtual-camera__arm virtual-camera__arm--right" />
            <span className="virtual-camera__leg virtual-camera__leg--left" />
            <span className="virtual-camera__leg virtual-camera__leg--right" />
          </div>
        </div>
      )}
      <div className="virtual-camera__hud">
        <strong>VIRTUAL CAMERA</strong>
        <span>
          {visible && projection
            ? `${projection.distanceM.toFixed(2)} m · ${projection.bearingDeg.toFixed(1)}°`
            : projection ? "TARGET OUT OF VIEW" : "WAITING FOR POSE"}
        </span>
      </div>
    </div>
  );
}

function CameraDetectionOverlay({ detection }: { detection: PersonOverlay }) {
  return (
    <div
      className="camera-live-detection"
      aria-label="Upper body detected"
      style={{
        left: percent(detection.centerX - detection.width / 2),
        top: percent(detection.centerY - detection.height / 2),
        width: percent(detection.width),
        height: percent(detection.height)
      }}
    >
      <span>UPPER BODY {Math.round(detection.confidence * 100)}%</span>
    </div>
  );
}

function personOverlayFromObservation(
  observation: PerceptionObservationInput
): PersonOverlay | null {
  if (observation.status !== "detected") return null;
  const centerX = finiteNumber(observation.payload.center_x);
  const centerY = finiteNumber(observation.payload.center_y);
  const width = finiteNumber(observation.payload.width);
  const height = finiteNumber(observation.payload.height);
  if (centerX === null || centerY === null || width === null || height === null) return null;
  return { centerX, centerY, width, height, confidence: observation.confidence };
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function percent(value: number): string {
  return `${Number((value * 100).toFixed(3))}%`;
}
