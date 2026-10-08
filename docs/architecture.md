# Architecture and safety boundary

[日本語](architecture.ja.md)

APRISRC Kit separates service policy from perception, authorization and motor control.
Missions run in the controlling browser through the [Mission API](mission-api.md).
The phone/browser performs perception and sends structured observations, not camera video.
The local server validates observations, owns control authorization, imposes speed/expiry
limits and logs results. The device firmware performs motor-adjacent control and watchdog stops.

Browsers use the [Client protocol](protocol.md); physical rovers use the separate
[Rover protocol](rover-protocol.md) behind `RoverAdapter`. The device initiates its connection
to the server. Missions never send GPIO/PWM/wheel commands and never depend on Simulator APIs.

- Exactly one client owns movement; E-stop is available without ownership.
- Commands expire; disconnect, ownership loss, cancel and E-stop stop movement.
- Reconnection never resumes a mission automatically.
- Forward motion requires fresh healthy CLEAR; UNKNOWN is not traversable.
- Supervised path permission is explicit, leased and time-limited, not automatic obstacle sensing.
- Hardware-advertised motion limits cannot be raised by browser or server settings.
- Observation validation precedes service events/pose correction; odometry remains separate
  from course-frame corrections used for visualization.
- Replay emits simulated inputs, not drive commands.

Simulator and hardware adapters must preserve the same motion/result semantics and safety
checks. Hardware qualifications remain environment-specific; see [Platform status](platform-status.md).
Private design deliberations and experimental logs are not included in this public release.
