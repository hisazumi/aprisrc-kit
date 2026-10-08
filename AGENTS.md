# Repository guidance

- Keep hardware-specific protocols behind the Rover Adapter interface.
- Never allow a browser client or mission to send motor-controller commands directly.
- Preserve command TTL, speed limiting, control ownership, disconnect stop, and emergency stop behavior.
- Use SI units and the coordinate convention documented in `docs/protocol.md`.
- Simulator behavior and real adapters must satisfy the same safety tests.
- Do not make ROS 2, LiDAR, or a physical rover mandatory for local development.
- Keep service-specific behavior and settings in `apps/pwa/src/missions/` and `apps/pwa/src/config/`; missions may use only the high-level API.
- Preserve the view boundary: `/app` is service-facing, `/console` is operational, and `/lab` is development-only.
- Keep reproducible Simulator inputs in `apps/server/scenarios/`; Simulator fault controls must not become requirements of a physical `RoverAdapter`.
- Log replay may re-emit scenario inputs and fault settings, but must never replay drive or motor commands.
- Treat camera recognition as untrusted observation input: validate timestamp, confidence, payload, marker identity, and pose innovation before publishing service events or correcting pose.
- Keep local odometry separate from course-frame correction so map observations cannot skip relative `move` / `turn` completion checks.
