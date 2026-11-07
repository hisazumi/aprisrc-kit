# Next platform: shared map and localization contract

[日本語](map-localization.ja.md)

Status: design proposal, 2026-11-07; not an implemented API.
This refines [requirements F01–F04/F11 and Q01/Q04/Q06/Q08](requirements.md)
and the [architecture](architecture.md). Inventory baseline:
`next-platform` commit `39c6d92c98cd29404b17e1f26f9892f17f2a29f2`.

## 1. Decision and scope

Share the venue map and correct robot-provided odometry with sparse known markers.
Students select named places and registered routes; the platform owns transforms,
localization quality and motion control. **Implement map loading/validation and
pose contract types/tests first**, then the estimator, then registered-route motion.

A shared map does not eliminate per-robot calibration. Wheel geometry/encoders,
camera intrinsics/extrinsics, body dimensions and stopping performance belong in
robot/sensor profiles. A map plus odometry cannot determine arbitrary initial
absolute position and heading by itself.

## 2. Existing implementation

| Component | Reuse | Gap |
| --- | --- | --- |
| `odometry.py`, `WheelImuOdometry` | Local encoder/IMU pose | Epoch/time contract and distance/rotation-dependent error assessment; current confidence is heuristic |
| `perception.py`, `PoseFusion` | Planar odom-to-course transform, known ID/range/position and yaw innovation rejection | Unlocalized state, map identity, capture-time odometry association, quality degradation |
| `runtime.py` | Relative move/turn use adapter-local pose; published pose is corrected separately | Versioned localization snapshot and route quality gate |
| `course-markers.json`, `courseMarkers.ts` | Marker/place examples | Duplicated server/PWA data; no map version, size, independent places/routes |
| `browserPerception.ts` | Marker observation path | Fixed 16 cm size and image-width range approximation; no calibrated 6DoF pose or heading |
| `mobileReceptionist.ts` | Visible destination-marker approach, stop on loss | Not sparse-marker map navigation |
| Existing perception/runtime/Simulator tests | Correction, rejected input and relative-motion regressions | M1–M4 contract/integration coverage below |

PoseFusion currently labels even its initial identity transform as course pose.
Old corrections produce an anomaly but high odometry confidence can still look
like good global localization. Freshness is checked, but correction uses odometry
retrieved at reception, not capture time. These are not sufficient route admission
criteria. The existing code is a useful starting point, not a qualified navigator.

## 3. Responsibilities and frames

| Component | Responsibility |
| --- | --- |
| Map loader | Validate schema, references, finite values and identity; publish an immutable snapshot |
| Robot/sensor profile | Odometry source, camera calibration/transforms, capabilities and operating limits |
| Observation normalizer | Validate clock/frame/calibration/marker identity; transform into body coordinates |
| Localization | Associate odometry history and observations; supply map-to-odom and quality |
| Route capability | Evaluate registered routes against pose; request motion through the shared authority |
| Motion authority | Preserve single ownership, TTL, guards, front state and stop evidence |

`T_A_B` transforms coordinates from B into A:
`T_map_base(t) = T_map_odom(t) × T_odom_base(t)`.
Base is the robot control reference, odom is continuous local motion, map is the
fixed venue frame. Use SI, right-handed axes, body +x forward/+y left and positive
yaw counter-clockwise. Survey the map origin and +x direction. Explicitly transform
camera optical coordinates using calibration rather than treating them as body axes.

Corrections change only T_map_odom. Never overwrite local odometry or skip relative
move/turn progress. Relative goals use one odomEpoch. An odometry reset/restart
changes that epoch, invalidates transforms/history, and interrupts active motion
with stop handling. Require re-localization and a new explicit start.

## 4. Proposed Map v1

Start with a single planar floor, named places and directed registered routes.
Places and markers are independent: destinations need not carry a marker.
Reverse travel requires a separately registered route.

```json
{
  "schemaVersion": 1,
  "mapId": "apris-demo-room",
  "revision": "1",
  "frameId": "map",
  "units": { "length": "m", "angle": "rad" },
  "markers": [
    { "family": "example-square", "id": 1, "sizeM": 0.16,
      "pose": { "xM": 0.0, "yM": 0.0, "zM": 0.8,
        "rollRad": 0.0, "pitchRad": 0.0, "yawRad": 0.0 } }
  ],
  "places": [
    { "id": "start", "label": "Start", "pose": { "xM": 0.0, "yM": 0.0, "yawRad": 0.0 } },
    { "id": "desk", "label": "Desk", "pose": { "xM": 2.0, "yM": 0.0, "yawRad": 0.0 } }
  ],
  "routes": [
    { "id": "start-to-desk", "from": "start", "to": "desk",
      "via": [ { "xM": 1.0, "yM": 0.0 } ] }
  ],
  "initialPoseCandidates": [ { "id": "start-placement", "placeId": "start" } ]
}
```

This illustrates the format, not a surveyed venue, detector configuration or motion
permission. Deployment must choose a supported marker family. Marker poses describe
the marker center in 3D; rotation is `Rz(yaw) Ry(pitch) Rx(roll)`. Normalize the marker's
native axes in its detector profile. Even planar localization must account for
camera mounting and marker height/tilt.

M1 rejects unknown fields, unsupported schema versions, duplicate IDs/(family,id),
nonfinite values, nonpositive size, missing fields and dangling references; it checks
route order. Geometry is the polyline from→via→to; empty via means a straight segment,
not implicit path planning. Bound file size, collection sizes, ID lengths and spatial
range in the loader profile. Validate completely before atomic activation. Failed
loads preserve the previous map; do not partially load or guess unknown versions.

Bind `mapId + revision + contentDigest` to each run, together with robot/calibration/
quality profile versions. The digest is SHA-256 of the loaded UTF-8 bytes: formatting
changes also change the digest. Reject a different digest under an already known
ID/revision. Reject changes during any active run/motion. Require stop evidence,
old-run termination and explicit operator activation, then re-localize. Supply the
active server snapshot to UI rather than duplicating configuration.

Walls, exclusion zones and traversable width are subsequent F01 extensions: M1 alone
does not complete F01. Before M3 route execution, add corridor validation including
body width and stopping margin. Do not silently execute a map containing unsupported
geometry. Initial pose candidates describe placement instructions, not evidence of
the current pose.

## 5. Localization and observation contract

These are new internal semantics; do not reinterpret existing state fields.

| Information | Required meaning |
| --- | --- |
| Scope | robotId, controlEpoch, odomEpoch, localizationEpoch, map ID/revision/digest and profile versions |
| Time | clockId/clockEpoch, sampleTime, receivedTime, monotonic sequence; no subtraction across unrelated clocks |
| odomPose | Uncorrected T_odom_base, freshness and sensor health |
| mapPose / mapFromOdom | Estimate and transform at the same sampleTime; null before localization |
| quality | unlocalized / tracking / degraded / lost; reasons, estimated error, last correction, distance and rotation since correction |
| Provenance | real / simulated / synthetic, estimator/calibration versions; Simulator truth stays in the test comparison path |

Error indicators use metres/radians with an identified evaluation method, profile
version and applicability. Do not call heuristic indicators statistical covariance
or guaranteed bounds. Unknown indicators are null and insufficient, never zero or
confidence=1. Tracking alone is not a motion grant: check route-specific accuracy
and freshness as well.

Observations carry sourceId/sessionEpoch/sequence/observationId, capture time/clock,
map identity, calibration version, marker family/id, frameId, relative pose, quality
and provenance. Accept corrections only when clock conversion error is acceptable
and bounded same-epoch odometry history brackets the capture timestamp. Interpolate;
do not extrapolate or relabel stale input as current. Initially reject observations
older than the last accepted capture time; sophisticated out-of-order fusion is later.
Compute map-to-odom at capture time and apply that transform to current odometry.

For a body-normalized marker pose:
`T_map_base(capture) = T_map_marker × inverse(T_base_marker(capture))`.
Apply 3D transforms before projecting observations compatible with the planar model.
Validate timestamp, duplicates, finite data, calibration, known marker identity,
range, planar consistency, position and heading innovations. Log rejection reasons.
Rejected input never renews lastCorrection or validity. Existing 2.5 s/3 m/90 degree
thresholds are not automatically adopted as route operating limits.

## 6. Initialization and sparse observations

Start unlocalized. Establish the initial transform through either:

- Operator-confirmed placement and heading at a named initial candidate, with an
  uncertainty assessment from the calibrated profile.
- Sufficient known-marker pose evidence for position and heading. Reject ambiguous
  solutions or require additional observations.

One position-only marker observation cannot uniquely determine arbitrary initial
position and heading. The existing browser approximation is not sufficient proof
of initial localization. Initialization uses separate checks, not innovation against
an arbitrary zero pose. Reject implausibly large tracking corrections. Re-localizing
from lost requires stopping and explicit action; it never resumes an interrupted route.

Marker absence alone does not immediately mean lost. Grow estimated error with time,
distance, accumulated rotation and odometry quality. Continue dead reckoning while
inside the measured route profile. Degraded indicates reduced quality and permits
continuation only when explicitly allowed by that profile. Interrupt motion if required
accuracy/freshness is exceeded; report lost or the quality failure reason. Later
observations can restore localization quality but cannot revive an old operation.

## 7. Registered-route integration (M3 onward)

Expose high-level capabilities such as `goTo(placeId)` and `followRoute(routeId)`.
Initially goTo selects a route only when a confirmed starting place and destination
have one registered route; ambiguous cases require routeId. Never drive directly
from an off-route pose to the start without a registered connection. Reject unsupported
capability, unknown place, map mismatch, missing localization or inadequate quality
before admission.

Execution binds to existing run/activity/operation and motion ownership. Reassess
pose between short bounded move/turn segments and recompute as needed. Large corrections
or route deviation require stopping and reassessment; never skip route progress into
success. Python must monitor quality during route motion even if the runner omits
its checks. Connect this to the existing authority rather than creating another
command owner.

Arrival requires the same map/epoch, position and (when required) heading tolerances,
sufficient quality and stop evidence. Handover completion is a separate business
condition. Maps/routes/markers never replace front CLEAR or operator permission.
This does not add generic obstacle avoidance, SLAM, arbitrary path planning or
physical stopping guarantees.

## 8. Implementation order and acceptance

Write contract tests before implementing each slice. Preserve motion-protection and
service-scenario regressions.

| Stage | Deliverable | Acceptance |
| --- | --- | --- |
| M1: next change | Python map loader, versioned snapshot, pose/observation contracts, example map, validation profile | Reject invalid/duplicate/dangling/oversized/unknown-version data, same-version different digest, and active-run replacement; retain old map on failure; uninitialized mapPose=null |
| M2 | Shared localization, injected clock, bounded odometry history, explicit initialization and quality model | Different initial poses; translated/rotated frames; ±π; capture delay; clock error, missing history, old epochs, out-of-order input; marker loss/reacquisition; implausible corrections; unchanged odometry |
| M3 | Registered-route capability, corridor/quality checks, existing authority integration | Same map with different robot profiles; correction cannot prematurely complete relative motion; quality loss, unconfirmed stop, guard/lease/front UNKNOWN, cancellation without auto-resume |
| M4 | Inputs under `apps/server/scenarios/`, traces, operator display/procedure | Repeat sparse-marker travel, drift correction, loss/stop, re-localization, map/odom reset and stale-observation rejection; record estimates separately from truth |

Fix synthetic expected errors and tolerances before M2/M3 tests and exercise just
below/at/above boundaries. Measure physical marker spacing, observation latency,
accuracy and stopping margin separately into deployment profiles. Portability means
shared contracts and calibration procedures, not equal accuracy on every robot.

## 9. Migration and current change

Keep the old marker JSON as an explicit conversion input. Operators must supply
missing size/family/calibration instead of enabling route motion through silent
defaults. Preserve existing course display and marker-approach services as legacy
paths distinct from new map-pose semantics. Host guideTo stays unsupported until M3.

This change is documentation only. The boundaries allow M1–M4 evaluation with the
lightweight Simulator before selecting ROS/Hakoniwa/Godot/MuJoCo. Rich 3D simulation
and improved perception providers can subsequently implement the same contracts.
