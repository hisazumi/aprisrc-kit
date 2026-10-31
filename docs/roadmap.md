# Development roadmap

[日本語](roadmap.ja.md)

This is the canonical priority document for APRISRC Kit. It describes unfinished
outcomes and their completion criteria. Current capability belongs in
[Platform status](platform-status.md), design rationale in ADRs, and measured experiments in
hardware records. Completed implementation detail remains available in Git history instead of
occupying the main roadmap.

This roadmap covers the Kit, not APRISRC event deadlines, required tasks or judging criteria.
Participants create their own services using the Kit; see [Purpose and scope](positioning.md).

Last reviewed: 2026-10-31

Current focus: hand over editable Simulator samples so other developers can try and extend
services independently. Hardware-dependent validation remains open rather than blocking this handoff.

## Status definitions

- **Next**: the immediate implementation target
- **In progress**: a usable vertical slice exists, but completion criteria remain
- **Waiting**: ready to proceed when an external participant or environment is available
- **Hardware-dependent**: requires a physical rover or venue
- **Optional**: outside the core platform path
- **Completed**: summarized once under Completed foundation; detailed task lists are removed

## Near-term order

1. Use the [handoff guide](handoff.md) and Playground workshop to try, change and contribute
   services without hardware; record first-time setup and modification friction.
2. Run M7B with one first-time teacher when available, then expand to three to five people
   after removing any blocking friction.
3. Apply pilot findings to Mission API usability and the M5 setup/distribution path.
4. When hardware is available, verify the experimental live Playground greeting/following
   flow, complete the M7A Service App/UGV02 marker trials, and continue M6B qualification.
5. Defer production speech choices until the pilot demonstrates a concrete need beyond the
   current M8 browser and structured-intent path.

## M7: Reference service prototypes

Status: **In progress**

Person greeting, virtual-person approach/following, Carry assistant, target-loss handling,
cancellation, and E-stop flows are implemented. M7 is split so platform work can continue
without treating external evaluation as an engineering blocker.

### M7A: Marker-based Mobile Receptionist

Status: **In progress** (shared Service App and automated verification complete; interactive
Simulator and supervised UGV02 walkthroughs pending)

Goal: demonstrate a service that autonomously combines person perception, a structured
request, marker perception, bounded movement, and spoken feedback without bypassing the
platform safety boundary.

Reference flow:

1. Detect a visitor and greet them.
2. Accept an allowlisted request such as "Guide me to the entrance."
3. Search for the configured destination marker with bounded turns.
4. Align to and approach the marker in bounded steps.
5. Announce arrival and stop.
6. Stop on cancellation, stale/lost observations, blocked/unknown forward safety, or loss of
   control.

Deliverables:

- a registered mission using `onPerson`, `onMarker`, `move`, `turn`, `stop`, and `say`
- reusable marker-observation waiting/validation helpers where they remove real duplication
- a deterministic Simulator scenario covering person, intent, destination marker, and arrival
- one Service App screen that runs the same Mission against Simulator or UGV02 based only on
  the Local Server adapter
- tests for success, wrong marker, marker loss, cancellation, and blocked forward motion
- a short runnable demo guide describing service code versus platform-owned safety

Implemented now: the registered mission, three configured destinations, a deterministic
person/intent/marker scenario, a shared `/app?service=receptionist` flow with automatic
scenario launch or phone-camera handoff, supervised physical clearance, success and safety
tests, and the bilingual demo guide.

Exit criteria:

- the service contains no Simulator-specific motion calls or rover protocol knowledge
- the deterministic scenario reaches arrival and leaves zero commanded velocity
- every loss, cancellation, and unsafe-forward case stops through the normal Mission API
- the shared Service App completes the Simulator walkthrough without using Lab-only controls
- the same Mission completes a supervised UGV02 marker approach without source changes

### M7B: Independent developer feedback

Status: **Waiting** for independent trials

Try and change the Simulator samples, then report setup, editing and recovery friction.
Use [Contributing](../CONTRIBUTING.md). Individual evaluation records and internal pilot plans are not published here.

## M5: Event-ready local distribution

Status: **In progress**

Available now: truthful liveness/readiness, runtime status, doctor, typed redacted
configuration, one-command development startup, and local HTTPS/WSS guidance.

Remaining:

- serve the built PWA, API, and WebSocket from one FastAPI origin
- provide an offline venue setup and a connection URL/QR
- document service-worker update and cache recovery
- verify camera, microphone, installation, permissions, and updates on representative iOS and
  Android devices

Exit: a new computer and smartphone can be brought online and recovered from written
instructions without venue Internet.

## M6B: UGV02 hardware qualification

Status: **Hardware-dependent / In progress**

Already verified: firmware flashing, registration, heartbeat/telemetry, E-stop,
lease/watchdog, server-disconnect stop, bounded turn/reverse, and supervised phone following.

Remaining:

- production WSS and rover-scoped credential provisioning
- IMU/battery qualification and uncommanded RF-loss testing
- duplicate/max-duration tests and persistent idempotency
- measured p95 distance/angle error, maximum stop distance, and stop-time envelope
- requirements and qualification for forward-safety perception

Exit: configuration alone switches Simulator/UGV02, missions remain unchanged, every loss
path stops safely, and predeclared motion/safety limits pass.

## M8: Voice and structured intent

Status: **In progress; production provider work deferred**

Available now: browser speech recognition/synthesis, local keyword rules, optional OpenAI/Gemini
structured intent, allowlist validation, reserved stop handling, and mission dispatch. Model
output cannot contain motion parameters or transport commands.

Remaining, when justified by pilot evidence: select and measure production STT/TTS, test
device variability, and define latency/error budgets.

## M9: iron-X ROS 2 Humble bridge

Status: **Network service trial reported; latest configuration revalidation pending** (2026-10-31)

ROS telemetry, the command-expiry bridge, same-host Adapter and authenticated LAN
gateway/PC Adapter are implemented. Console floor trials and an operator-reported
iPhone following trial are recorded. The mission API is unchanged; `vy` remains zero.

Next: physically revalidate the stop-confirmation cancellation fix and 0.15 m/s
configuration; measure target-loss stopping and investigate observation gaps.
Then qualify perception/ownership handoff, Live Playground, network-loss recovery
and independent protection against bridge/OS/serial failure. Software recovery
tests are not physical fault qualification. LiDAR clearance remains unimplemented.
Start with [iron-X person following](hardware/ironx-follow.md).

## M10: LiDAR and advanced autonomy

Status: **Optional**

Potential work includes an RPLIDAR C1 or iron-X `/scan` adapter, recorded scans, operator
visualization, simple obstacle stop, and later mapping or path-planning experiments. Core
services must continue to work without LiDAR, and LiDAR-specific details must not enter
service missions.

## Completed foundation

The following milestones are complete and no longer carry detailed task lists here:

- **M0**: Simulator, Client protocol, single-owner control, speed/TTL limits, disconnect stop,
  E-stop, and the shared `RoverAdapter` boundary
- **M1**: smartphone camera path, HTTPS/WSS development, high-level motion, and separated
  Service App, Operator Console, and Development Lab views
- **M2**: public Mission API, mission registry, editable mission/config boundaries, starter,
  documentation, and tests
- **M3**: reproducible Simulator scenarios, fault injection, structured logs, replay, and
  safety regression tests
- **M4**: person/marker perception, pose estimation, marker correction, confidence, and
  target-loss handling

See [Platform status](platform-status.md) for the verified surface.
