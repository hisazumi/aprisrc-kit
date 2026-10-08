# Perception and pose estimation

[日本語](perception-and-pose.ja.md)

APRIS converts on-phone perception and rover sensor data into shared service events and pose.
Detector output never becomes a motor command directly; it always passes Local Server
validation and the mission boundary.

## Data flow

```text
live camera / recorded video
        | on-device detector
        v
perception_observation
        | timestamp / confidence / payload validation
        v
perception_event ---> onPerson() / onMarker()
        |
        +-- known marker ---> course-frame pose correction

wheel encoders + IMU ---> odom pose ---> course-frame pose
```

Perception observations do not require control ownership and do not authorize motion.

## Browser detection

Use **Camera preview** in the Service App or Development Lab. Video remains in the PWA; only
structured observations are sent over WebSocket.

- MediaPipe Pose Landmarker Lite tracks shoulder midpoint and width. Legs and face are not
  required; shoulder width can synthesize an upper-body box when the waist is outside frame.
- `BarcodeDetector` recognizes QR values formatted as `APRIS:MARKER:<id>`.
- The pinned pose model and WASM load after **Start vision** and run on-device.
- Browser support for `BarcodeDetector` is checked at runtime; person perception continues
  when barcode detection is unavailable.
- Recorded video uses the same detector path as the live camera.

The MVP tracks at most one person. Missing shoulder visibility/presence suppresses detections;
1.2 seconds without a valid observation emits one explicit `lost` event. The overlay shows the
same normalized box sent to APRIS.

Marker range and bearing currently assume a 160 mm marker and 60-degree horizontal camera
field of view. QR alone does not provide full 3D pose, so correction normally updates position
while retaining odometry yaw. A future AprilTag/ArUco detector can provide the same
`relative_x_m`, `relative_y_m`, and optional `relative_yaw_rad` fields.

## Observation validation

Example browser message:

```json
{
  "v": 1,
  "type": "perception_observation",
  "observation_id": "perception-...",
  "kind": "marker",
  "status": "detected",
  "confidence": 0.9,
  "captured_at": 1786000000.0,
  "source": "camera",
  "payload": {
    "marker_id": 1,
    "relative_x_m": 0.7,
    "relative_y_m": 0.1
  }
}
```

The Local Server rejects:

- duplicate observation IDs
- observations older than 2.5 seconds or more than 0.5 seconds in the future
- confidence below 0.50 for people or 0.65 for markers
- invalid normalized person boxes or non-finite marker positions
- unknown marker IDs or ranges outside 0.08-5.0 m
- pose corrections exceeding 3.0 m or 90 degrees from current pose

Rejected input produces an operator event but never reaches `onPerson()` / `onMarker()` or
changes pose.

## Service event API

```ts
const stopPeople = rover.onPerson((event) => {
  if (event.status === "lost") void rover.stop("person lost")
})

const stopMarkers = rover.onMarker((event) => {
  console.log(event.markerId, event.poseCorrection?.applied)
})
```

Detected targets are emitted at up to approximately 1.7 Hz. `lost` does not itself start or
stop a mission; a following mission must explicitly call `stop()`.

## Odometry and pose correction

`WheelImuOdometry` integrates cumulative encoder ticks with IMU yaw rate. The Simulator uses:

- wheel radius: 0.0475 m
- track width: 0.225 m
- encoder resolution: 1320 ticks/revolution
- IMU yaw weight: 0.70

`PoseFusion` maintains an SE(2) transform from odometry to course coordinates. Known marker
poses live in `apps/server/config/course-markers.json`. Marker corrections are confidence
weighted, while relative `move` and `turn` completion continues to use uncorrected odometry so
a correction cannot skip a motion threshold.

`state.pose_quality` reports frame, source, confidence, encoder/IMU health, anomalies, and the
last correction marker. Both sensor faults may make pose unavailable, but server safety, TTL,
and stop behavior remain active.

## Current limitations

- First person detection downloads roughly 6 MB of model/WASM assets; offline self-hosting is open.
- Shoulder width is a distance proxy and requires device/camera calibration.
- Occluded shoulders, extreme side poses, or leaving frame cause target loss.
- Barcode Detection API support varies by browser.
- QR range is an uncalibrated estimate until camera intrinsics and marker size are configured.
- Server and service marker maps must use the same IDs and coordinates.
- Physical encoder/IMU units, signs, rates, and fault thresholds still require qualification.
