# Try, change, and hand over APRISRC Kit

[日本語](handoff.ja.md)

APRISRC Kit supports participants developing services for APRISRC, the robot challenge
associated with the APRIS conference. You create the service; the Kit provides shared
development functions and reference samples. See [Purpose and scope](positioning.md).

Start here when someone sends you this repository. No rover is needed to try or change a
service. Local development tools are required; this is not
yet a packaged, offline-ready app. Hardware trials assume one computer/server and one rover.

## Choose a path

| You want to | Start with | Done when |
| --- | --- | --- |
| Try without hardware | [Playground hands-on](demos/playground-workshop.md), 20-30 minutes | You run the three samples and compare one change |
| Make a service | [Participant quickstart](challenger-quickstart.md), 30-45 minutes | Your mission and tests work without runtime or firmware changes |
| Try a provisioned UGV02 | [UGV02 self-test](hardware/ugv02-self-test.md) | Raised-wheel greeting turns toward you and stops |
| Prepare an unconfigured UGV02 | [Firmware provisioning](hardware/ugv02-websocket-firmware.md), then self-test | Firmware, LAN, ID/token, HTTPS and stopped telemetry agree |
| Inspect live code and observations | [Live rover playground](demos/hardware-playground.md) | You record a supervised greeting/following trial; this UI is not physically verified yet |
| Use another phone or rover | [Hardware assumptions and porting](hardware/service-hardware-porting.md) | It satisfies the same observation, motion and safety contracts |

Start in the Simulator even if you own a rover. The desktop workshop needs no camera,
microphone, LLM API key, printed marker, ROS 2 or LiDAR. Use a feature branch for changes and
stop running services before source edits. Simulator success does not qualify hardware.

## Evidence and limits

| Surface | Status |
| --- | --- |
| Simulator Playground | Shared greeting, carry and marker services, manual inputs, scenarios and read-only definition source; no source-line highlighting; virtual observations are not camera recognition |
| UGV02 firmware and older service flow | Bounded turn/reverse, lease/disconnect stop and supervised phone following observed on the reference unit |
| Live Playground | Mocked-input tests and disconnected desktop/mobile UI checks; actual camera/rover trial still required |
| Physical marker guidance | Not demonstrated; disabled in Live Playground. The legacy URL is also an alias, not an alternate hardware path |

[Platform status](platform-status.md) defines current capabilities; the firmware guide records
measured hardware history. No path promises unattended autonomy, general obstacle avoidance,
or a qualified stopping distance. Supervised permission is a person's path check, not a sensor.

## Change a service

Find behavior in Implementation, then edit `apps/pwa/src/missions/myService.ts`.
Shared services use `service/catalog.ts`; lower-level missions use `missions/index.ts`.
Scene settings do not write source; export/import JSON to retain and share environments.
Follow the quickstart and the public API.

Missions execute in the owning browser tab. The server validates observations and authorizes
motion; firmware controls motors and its watchdog. Keep the browser foreground and awake
during supervised trials. Do not put GPIO, PWM, transport calls or safety bypasses in missions.
Hardware and sensor changes belong at the documented adapter/client boundary.

After changes run `npm test`, `npm run typecheck`, and `npm run build`. Server changes also
need the root README's Ruff/pytest checks. In a PR describe changed behavior and tested
environments; mocks are not physical verification. The [roadmap](roadmap.md) identifies
hardware-dependent work separately from contributions possible without a robot.

## Hand over or report a problem

Include these in a private trial note or a credential-redacted issue:

- Git commit/branch, firmware version, adapter and sample URL
- Phone/browser, mounting/camera direction, and raised wheels versus floor
- Completed setup steps and last working guide/step
- Scene/preset or physical layout, one code/config change, expected versus observed behavior
- Visible status/error, screenshot, and `apris-doctor --json` output where relevant
- Stop method, whether you observed the wheels stop, and remaining unverified behavior

Share rover ID and connection details privately; provision the recipient's development token
locally. Never commit tokens, Wi-Fi passwords, `.env`, `apris_rover_secrets.h`, CA private keys
or private flash backups. A LAN change may need firmware server-host configuration and
certificate regeneration. Do not assume another computer can use the previous owner's IP/CA.

For unexpected motion, use E-stop and physical power removal if necessary. Do not repeat a
failed floor trial until the cause is understood. Missing or zero telemetry alone is not proof
that wheels stopped. Use the [Operations runbook](operations/runbook.md) for process recovery;
historical experiments are references, not setup instructions.

## Current editing and permission model

Start with [My service](demos/student-service.md): edit `missions/myService.ts`.
The selector uses `service/catalog.ts`, separately from the generic mission registry.
Implementation is read-only with no execution highlighting. Scenes use JSON import/export,
not the old browser-local Save scene/Load scene controls.
Physical use requires separate 30-second manual clearance; starting does not extend it.
Follow the [current hardware controls](demos/hardware-playground.md).
