# Development roadmap

[日本語](roadmap.ja.md)

This is the canonical priority document for APRISRC Kit. It describes unfinished
outcomes and their completion criteria. Current capability belongs in
[Platform status](platform-status.md), design rationale in ADRs, and measured experiments in
hardware records. Completed implementation detail remains available in Git history instead of
occupying the main roadmap.

This roadmap covers the Kit, not APRISRC event deadlines, required tasks or judging criteria.
Participants create their own services using the Kit; see [Purpose and scope](positioning.md).

Last reviewed: 2026-11-03

Current focus: post-challenge safety, setup/recovery, and a repeatable development environment.
Physical qualification and next-fleet selection remain open.

## Status definitions

- **Next**: the immediate implementation target
- **In progress**: a usable vertical slice exists, but completion criteria remain
- **Waiting**: ready to proceed when an external participant or environment is available
- **Hardware-dependent**: requires a physical rover or venue
- **Optional**: outside the core platform path
- **Completed**: summarized once under Completed foundation; detailed task lists are removed

## Post-challenge priorities

These are proposed priorities after the 2026-11-03 challenge, not release commitments.
They supersede the previous pilot-first order. Detailed milestone contracts remain below.

### Lessons and evidence

- Students tried services in the Simulator and on shared iron-X robots. This is useful
  field feedback, not a completed independent usability or hardware qualification study.
- An operator reported a robot falling from a desk while charging after remote operation
  was mistaken for simulation. Bilingual floor/raised-wheel precautions are documented;
  a warning alone does not resolve target confusion.
- Startup complexity, repeated clear-path confirmation, and unclear E-stop recovery caused
  friction. A phone interaction required repeated presses; browser versus network causes
  have not been isolated.
- Network command delays, ownership/nonce expiry, and a robot-side control-loop fault were
  observed during development/trials. Treat these as separate failure modes, not all "Wi-Fi".
- A startup race was fixed on one robot and reboot startup checked. Telemetry after a
  subsequent clock synchronization remains unverified: NTP was not responding.
- Presentation feedback adds needs for simulation time, rooms, custom phone UI, coordinate
  navigation, optional 3D, and more recognition categories. These are requests, not shipped features.

### P0: Make physical operation unmistakable

- [ ] Display the verified actual adapter and robot address/identity in Service, Playground,
  and Console, including beside motion-enabling controls; show unknown targets explicitly.
  Never expose tokens. A virtual field must not imply Simulator mode.
- [ ] Provide a concise pre-motion check: floor placement, secure raised wheels for non-driving
  tests, clear area, charging cable disconnected for driving, and an operator ready to stop.
- [ ] Distinguish ordinary E-stop, control ownership conflicts, and restart-required faults
  such as `control_loop_delayed_restart_required` / `stop_unconfirmed`.
  Show pending/success/failure and student versus instructor recovery actions.
- [ ] Review repeated clear-path confirmation without silently treating unknown/blocked
  space as clear. Recovery must not automatically resume motion.

Exit: a first-time user identifies the target and correct recovery action without guessing;
automated tests cover unknown/reconnected targets and no automatic motion resumption.

### P1: Make setup and everyday use reproducible

- [ ] Prepare a fixed next-event release with a tested compatibility table covering
  PC/PWA, firmware, robot bridges, and supported phone/browser environments.
  Reconcile current guides and platform status with verified changes; label old
  private-fork plans and historical trials so they cannot be mistaken for setup instructions.
- [ ] Refine Windows installation from reported failures: OpenSSL prerequisite,
  `spawnSync openssl ENOENT`, WinGet, executable-path/`OPENSSL` checks, and certificate retry.
  Separate PC-only simulation from phone HTTPS setup; installation advice still needs
  fresh-Windows verification.
- [ ] Reduce startup steps and clearly label Simulator versus hardware launch paths.
  Document credentials, phone URL, duplicate-server/control-owner checks, and shutdown.
- [ ] Qualify robot boot order, E-stopped autostart, fresh telemetry, and clock changes;
  do not mark a system ready solely because its processes are running.
- [ ] Reproduce phone interaction delays and measure click-to-acknowledgement separately
  from browser rendering and robot/network response time.
- [ ] Export a credential-redacted diagnostic bundle with target identity, component
  versions, stop reason, and recent command/observation latency. Make it usable without
  SSH; test that tokens, keys, passwords, and private configuration are excluded.
- [ ] Make shared-robot handoff explicit: identifiable robot, availability/owner status,
  control release, and instructions for conflicting tabs or a wrong target.
  Keep this useful even when most teams have their own robot.

Exit: another teacher/student starts, connects, stops, and recovers using the bilingual
instructions on a fresh Windows PC without developer intervention.

### P2: Handle jitter and trial one onboard UGV02 setup

- [ ] Decide where student service code executes. Missions currently run in the owning
  browser; test tab closure, backgrounding, phone sleep, disconnection, and recovery.
  Moving only the server onboard does not make browser-owned service execution local.
  Compare a documented foreground-only contract with an onboard runner using the same API;
  require explicit restart after interruption rather than automatic motion resumption.
- [ ] Reproduce bursty delay, loss, duplicates, reordering, and reconnection in simulation;
  distinguish ownership expiry, stale commands, stale observations, and local loop stalls.
  Compare command cadence/latest-command handling and recovery using latency/stop logs.
- [ ] Define speed-dependent slowdown/stop limits and qualify measured stop times/distances.
  Simulation and operator supervision do not substitute for physical fault testing.
- [ ] Prototype one UGV02 with an onboard computer (Raspberry Pi is a candidate, not selected).
  Compare phone recognition over a robot-local connection with onboard camera recognition;
  simply moving the server does not remove a remote perception/control dependency.
- [ ] Retain PC development/Simulator use; choose power, mounting, compute, and cost only
  after the one-robot trial. Aim for one kit per team. Borrowed shared iron-X remains a
  valid option, not the assumed next-event fleet.

Exit: repeatable jitter tests and one physical prototype demonstrate usable following and
bounded stopping before fleet procurement or relaxed limits.

### P3: Make Simulator environments editable and repeatable

- [ ] Provide a staged test path: virtual observations + Simulator, real camera +
  Simulator, then supervised hardware. Expose which observations are real versus
  simulated so recognition errors can be isolated from motion/transport errors.
- [ ] Add explicit simulation time, pause/resume, reset, and controllable time progression.
  Decide which mission timers, observations, and motion use that clock; keep real hardware
  watchdogs on real monotonic time. Rendering speed must not change trial outcomes.
- [ ] Add a top-down field/room editor for walls, obstacles, rover, people, and markers,
  with initial-layout save/load. Keep editing separate from scenario execution.
- [ ] Define collision, room bounds, and occlusion semantics before calling rooms a tested
  environment; visual walls alone are not simulated sensing or physical safety.
- [ ] Explore an optional 3D environment after the 2D model is useful, reusing the same
  service API and scene definitions rather than creating simulation-only services.

Exit: save a room and initial state, replay the same trial with reproducible timing,
and edit without ever sending physical motion commands. 3D is optional, not a core dependency.

### P4: Broaden what students can build

- [ ] Visualize current behavior, received observations, waiting conditions, and stop
  reasons alongside editable service code. Validate that students can relate one code
  change to behavior; source-line highlighting is optional, not a prerequisite.
- [ ] Document a minimal "go to coordinates" example, coordinate frame/units, localization
  assumptions, cancellation, arrival stop, and failure behavior. First check the existing
  Mission API; separate relative motion from navigation/path planning. Do not present
  straight-line movement as obstacle-avoiding navigation.
- [ ] Provide a minimal editable user-facing phone app template using the same mission API;
  separate service-specific buttons/status from operator and development controls.
  Test whether a student can change the screen and behavior together.
- [ ] Support more recognition categories, for example a bottle triggering speech.
  Define validated object observations, confidence/freshness/loss behavior and Simulator
  inputs. Detection is not distance estimation or identity tracking.
- [ ] Improve editable samples and use first-time feedback to assess API affordances;
  finish marker-guidance hardware work only when required by the selected service.

Exit: an independent student changes a phone UI and service behavior, tests it in the
Simulator, and can explain what remains to validate on hardware.

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

Implemented now: the registered mission and configured destinations, deterministic scenario
support, success/safety tests, and bilingual guides. The shared Playground at
`/playground?service=receptionist` uses manual person/marker inputs or the scenario runner;
the UI offers Entrance and Desk. Markers visible defaults off. The old dedicated screen's
automatic scenario launch and camera handoff are not the current workflow. Physical marker
guidance is disabled in Service and Playground; the hardware exit criterion remains open.

Exit criteria:

- the service contains no Simulator-specific motion calls or rover protocol knowledge
- the deterministic scenario reaches arrival and leaves zero commanded velocity
- every loss, cancellation, and unsafe-forward case stops through the normal Mission API
- the shared Service App completes the Simulator walkthrough without using Lab-only controls
- the same Mission completes a supervised UGV02 marker approach without source changes

### M7B: Independent developer feedback

Status: **In progress** — challenge feedback received; structured follow-up pending

Try and change the Simulator samples, then report setup, editing and recovery friction.
Use [Contributing](../CONTRIBUTING.md). Individual evaluation records and internal pilot plans are not published here.

Challenge feedback is consolidated under P0–P4 above; M7B now collects follow-up
validation rather than waiting for the first independent trial.

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

Stop-recovery UI and instructions are tracked under P0; jitter and boot/clock
qualification under P1–P2. The dated milestone evidence above is not a current fleet health check.

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
