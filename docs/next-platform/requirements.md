# Next platform: requirements draft

[日本語](requirements.ja.md)

Status: discussion draft, 2026-11-05. These are proposed requirements for the next
APRISRC Kit, not delivered capabilities, challenge rules, or a technology selection.
Review the scope before deriving the architecture.

## 1. Purpose and scope

Enable participants to design, implement and evaluate services combining movement,
perception and interaction without repeatedly building localization, device transport
and integration infrastructure themselves.

Start with coarse requirements, then design responsibilities, interfaces, variability
and deployment. Validate uncertain design choices with small end-to-end prototypes.
Do not assume a rewrite of existing components.

The initial domain is supervised indoor service prototyping on a prepared map and
registered routes. A prototype may use human loading, unloading and confirmation.
The three reference scenarios below are coverage examples, not prescribed student
solutions or an exhaustive statement of future service needs.

## 2. Users and responsibilities

| Role | Responsibility |
| --- | --- |
| Participant developer | Select the problem, service policy, destinations, recognition conditions, interaction and evaluation |
| Service user / staff | Request a service, receive notifications, confirm handover or task completion |
| Instructor / operator | Prepare the environment and hardware, supervise trials, manage access and recover failures |
| Platform maintainer | Supply reusable capabilities, adapters, runtime contracts, distribution and diagnostics |

Students own service decisions; the platform supplies mechanisms and reusable defaults.
For example, the platform reports a bottle observation; the service decides whether it
represents a cleaning task. Runtime motion protections cannot be overridden by service policy.

## 3. Reference scenarios

### S1: Patrol and report

1. An operator starts a configured patrol.
2. The rover visits registered locations while object observations are monitored.
3. A service-selected condition creates a report with an image, observation time and
   location context, such as a room and patrol point.
4. Staff receive the report on another screen and acknowledge or complete the task.
5. Patrol continues or pauses according to the service policy.

Initially support one known object category. Exact object world coordinates are not
required. Repeated detections must not silently create unlimited duplicate tasks.
Missing/stale observations, uncertain position, notification failure and cancellation
must have visible outcomes. Actual cleaning is outside this scenario.

### S2: Delivery and handover

1. A user requests delivery between named locations.
2. A person loads the item and confirms readiness.
3. The rover follows a registered route to the destination.
4. The recipient confirms receipt; the service completes the job and returns or waits.

Distinguish arrival from successful handover. A missing confirmation must not be
reported as successful delivery. New requests may be accepted while a job is running,
but the initial service may execute deliveries sequentially. Robotic manipulation is
not required.

### S3: Guidance with companion awareness

1. A visitor selects a destination.
2. The rover leads along a registered route while checking whether the visitor is following.
3. It waits when the visitor falls behind and resumes only under an explicit policy.
4. It announces arrival or reports that guidance was interrupted.

Leading and following are different capabilities. Companion checking may initially
use explicit confirmation; automatic visual checking is a replaceable option.
Loss of the companion must not be treated as successful guidance.

## 4. Functional requirements

Priority: **Core** is required for the initial reference scope; **Extension** is a
later capability. Core does not mean every implementation variant is required.

| ID | Priority | Requirement | Acceptance evidence |
| --- | --- | --- | --- |
| F01 | Core | Load a shared map with named places, routes, initial pose and known marker poses/sizes; represent walls and prohibited regions where relevant to the selected model | A saved environment is reused for a simulated and physical trial; coordinate conventions are documented |
| F02 | Core | Provide pose and localization quality, using odometry between sparse known-marker observations in the reference configuration | Measure drift, correction and unavailable/unreliable pose behavior on a declared route |
| F03 | Core | Move to named destinations via registered routes, patrol and return; report arrival, failure and cancellation distinctly | S1 and S2 run without service-specific wheel commands or timed-turn tuning |
| F04 | Core | Supply validated person, marker and selected object observations, including source, time and confidence/quality where available | Synthetic, recorded or live inputs use the same documented observation contract; invalid/stale inputs are distinguishable |
| F05 | Core | Combine sequences with concurrent activities and directed events, with defined task lifetimes | Patrol monitoring and S3 waiting behavior work; ending a service ends its subordinate activities |
| F06 | Core | Define long-running operation start, progress where meaningful, completion, failure and cancellation | Cancelling motion distinguishes request acceptance from confirmed stop; late results cannot restart a cancelled operation |
| F07 | Core | Support editable service-facing requests, confirmations and notifications across roles/screens | S2 handover and S1 staff notification work without exposing operator controls to service users |
| F08 | Core | Provide job identity and state mechanisms; allow service-defined transitions and duplicate handling | Repeated observations and repeated acknowledgements follow an explicit policy; interruption is not recorded as success |
| F09 | Core | Run the same service logic against compatible simulated and physical capabilities | Switching the supported backend requires configuration/adapters, not a simulation-only service rewrite |
| F10 | Core | Support saved initial conditions, simulated time, pause/resume/reset and fault scenarios | Repeat a trial under declared inputs and timing; label uncontrolled sources of variability |
| F11 | Core | Expose active behavior, observations, waiting conditions, target, stop/failure reason and relevant timing | A developer can explain why a reference service is waiting or stopped |
| F12 | Extension | Support free path planning, advanced autonomy and additional sensing | Evaluate separately after registered-route services work |

A map is not a planner; localization is not obstacle avoidance. Wall graphics are not
evidence of collision or sensing behavior. Specify those semantics for each simulator.
Object detection does not automatically provide distance or persistent identity.

For F08, restart persistence and job retention duration remain open. The initial scope
requires an explicit interrupted state and recovery policy, not a general workflow database.

## 5. Quality and operational requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| Q01 | Preserve ownership, command expiry, speed limits, disconnect stop and emergency stop; identify actual target and prevent automatic motion resumption after recovery | Unknown/reconnected targets, competing commands and interruption are tested; physical stopping is measured separately |
| Q02 | Deliver a versioned, reproducible environment with simple start, stop, reset and recovery | An independent user brings up and recovers the supported configuration on a clean representative PC using the supplied instructions |
| Q03 | Define execution lifetime independently of incidental browser state | Closing/backgrounding a UI, phone sleep and reconnect are tested against the documented execution policy; reconnection cannot silently duplicate a mission |
| Q04 | Keep sensor, robot and middleware details behind capability contracts | A second service reuses capabilities without protocol knowledge; unsupported capabilities are reported explicitly |
| Q05 | Keep participant code and results recoverable across environment replacement | An environment update/recovery exercise retains the student's work |
| Q06 | Distinguish measured facts, simulation truth, estimates and synthetic observations | Trial records show input sources and configuration; simulated success is not described as physical qualification |
| Q07 | Support local venue operation for the initial reference scenarios without a mandatory cloud service | After provisioning, run the reference configuration without Internet; document any optional online features |
| Q08 | Make performance and precision limits explicit and observable | Establish and measure route accuracy, stopping, observation age, response latency and resource budgets before acceptance |
| Q09 | Provide useful diagnostics without exposing credentials or unnecessary captured data | Diagnostic output is redacted; image/report access and retention are defined for the reference service |

Real hardware watchdogs use real monotonic time. Simulation timers use an explicitly
defined clock; pause/reset must not weaken physical protections. Replay must never
re-emit historical motor commands onto physical hardware.

Quantitative acceptance thresholds are intentionally not invented here. Before qualification,
choose supported PC/robot profiles, route geometry and operating limits, then set thresholds
and measure them. A single successful demo is insufficient evidence of repeatability.

## 6. Responsibility boundary and variability

| Concern | Platform provides | Participant selects / implements |
| --- | --- | --- |
| Movement | Localization, route execution, progress and stopping contracts | Destinations, patrol order and actions on arrival |
| Perception | Input adapters, validated observations and replaceable recognizers | Target categories, service conditions and response |
| Interaction | Request/confirmation/notification mechanisms and UI examples | Roles, wording, screen flow and completion criteria |
| Execution | Concurrent activity lifetime, event delivery and operation control | Service sequencing, event reactions and business recovery policy |
| Jobs | Identity, state and duplicate-handling mechanisms | Meaning of states and allowed business transitions |
| Trials | Inputs, simulator adapters, diagnostics and repeatable scenarios | Expected outcomes, experiments and evaluation of user value |

Instructor configuration covers the venue map, marker placement, camera calibration,
robot profile and operating limits. These should not be rediscovered by every team.

Variation points include robot, recognition provider/input, localization/movement method,
completion confirmation, UI/notification endpoint, execution host, middleware and simulator.
Implement one representative configuration first. Identify required capabilities and
fallback behavior explicitly; do not promise every combination or silently substitute
physical capabilities with simulated ones.

## 7. Constraints and candidate architecture directions

These directions are inputs to architecture evaluation, not additional functional requirements:

- Treat odometry as a prerequisite for the reference physical platform; assess its
  accuracy and camera/marker calibration effort.
- Prefer a service runner outside the browser; define behavior on UI loss and process failure.
- Prefer a prepared Linux execution environment. For Windows, evaluate distributing a
  complete WSL2 environment with simulation and control inside the same Linux environment.
  WSL setup, host GPU compatibility and restoration still need validation.
- Trial one prepared team computer before fleet procurement. Raspberry Pi is a candidate;
  do not assume it can host all perception workloads.
- Evaluate ROS 2 for reusable robotics integration; mailbox semantics alone do not require it.
- Evaluate Godot/MuJoCo, with or without Hakoniwa, for richer simulation. Test image
  acquisition and control integration early; defer detailed scenery.
- Retain a lightweight local development/test path. ROS 2, LiDAR and physical hardware
  must not become mandatory for all local development.
- Preserve the service-facing, operator and development view separation.

Student notation, event transport, process boundaries, exact APIs and the choice of
ROS 2/Hakoniwa are architecture decisions still to be made. Define behavior before syntax.

## 8. Initial scope and deferred work

First prove a small S1 flow with one object category and registered routes, then use S2
and S3 to test that the interfaces are not cleaning-specific. Prototype uncertain
deployment, graphics and camera paths while designing the architecture.

Defer autonomous cleaning/manipulation, outdoor navigation, arbitrary SLAM/path planning,
multi-robot fleet optimization, a dedicated state-machine editor, numerous backend
variants and photorealistic environments. Retain extension boundaries where justified.

The Kit does not prescribe competition tasks, evaluation rules or unattended operation.

## 9. Questions to resolve before architecture acceptance

1. Do S1–S3 cover the intended service range? Which behavior is missing?
2. What route accuracy, marker spacing, stopping envelope and observation age are needed
   for the selected venue and robot?
3. Which operations continue or stop on UI disconnection, and which require an operator
   to explicitly restart?
4. What event ordering, queue bounds, duplicate handling and overload behavior are needed?
5. What job state survives process/environment restart, and where are reports retained?
6. What is the minimum supported PC/phone configuration, and what deployment work remains
   for instructors and participants?
7. What simulated physics, sensing and image fidelity is necessary for the intended tests?

The next deliverable is an architecture proposal tracing these requirement IDs to
responsibilities, interfaces, deployment and verification. It should identify reused
components, gaps and small experiments; it should not begin by selecting all technologies.

## 10. Basis and related documents

This draft synthesizes the 2026 retrospective and subsequent design discussion. Reference
scenarios are generalized requirements examples, not assessments of individual participants.
The existing implementation and validation limits must be checked separately.

- [Purpose and scope](../positioning.md)
- [Current platform status](../platform-status.md)
- [Existing roadmap](../roadmap.md)
- [Existing architecture](../architecture.md)
- [Repository guidance](../../AGENTS.md)

This draft does not rewrite the current roadmap or claim that these requirements are
already implemented.
