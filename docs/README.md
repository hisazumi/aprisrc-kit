# Documentation index

[日本語](README.ja.md)

APRISRC Kit documentation is organized by audience and task. New users normally
need only **Start here**. [Platform status](platform-status.md) is authoritative for current
capabilities, [Development roadmap](roadmap.md) for priorities, and
[Operations runbook](operations/runbook.md) for startup and recovery.

## Start here

To extend a service, follow [Add a voice-triggered action](adding-actions.md).

Using a web chat or coding assistant? Start with [AI-assisted development](ai-assisted-development.md),
then attach the [AI context memo](ai-service-context.md) with current source files.

For text/voice intent interpretation settings, see [Assistant providers](assistant-providers.md).

Read [Purpose and scope](positioning.md) for the distinction between the APRIS conference,
APRISRC challenge, Kit and participant-created services. Samples are development starting
points; these guides do not define event rules or judging criteria.

| Goal | Document |
| --- | --- |
| Start on Windows or recover from Python/backend setup errors | [Windows setup](windows-setup.md) |
| Choose a trial, service-development, or hardware handoff path | [Try, change, and hand over APRISRC Kit](handoff.md) |
| Run the MVP and compare a small service change | [Playground hands-on](demos/playground-workshop.md) |
| Try a service and connect its behavior to code | [Service playground](demos/service-playground.md) |
| Run the person-following and interaction demo | [Human interaction demo](demos/human-interaction.md) |
| Build a small person-responsive service | [Participant quickstart](challenger-quickstart.md) |
| Understand the mission API and safety boundary | [Mission API and service templates](mission-api.md) |
| Run the same starter on a supported UGV02 | [UGV02 self-test](hardware/ugv02-self-test.md) |
| Try iron-X following, then recover from a stop (experimental) | [iron-X person following](hardware/ironx-follow.md) |
| Connect a student's Kit server to iron-X over the LAN (experimental) | [iron-X network setup](hardware/ironx-network.md) |
| Check current capabilities and limitations | [Platform status](platform-status.md) |


See [Initial public release](release-scope.md) for distribution scope and [Contributing](../CONTRIBUTING.md) for changes.

## Reference

| Goal | Document |
| --- | --- |
| Understand `/app`, `/console`, and `/lab` | [PWA views](pwa-views.md) |
| Understand the shared safety and responsibility boundaries | [Architecture](architecture.md) |
| Inspect experimental live Playground inputs and safety gates | [Live rover playground](demos/hardware-playground.md) |
| Connect a smartphone over HTTPS | [Local HTTPS and smartphone setup](local-https.md) |
| Test with reproducible inputs and faults | [Simulator scenarios, fault injection, and logs](simulator-scenarios.md) |
| Understand person/marker perception and pose | [Perception and pose estimation](perception-and-pose.md) |
| Run the marker-based reception and guidance service | [Mobile Receptionist demo](demos/mobile-receptionist.md) |
| Understand the Carry assistant state machine | [Autonomous carry service](demos/autonomous-carry-service.md) |
| Replace the reference phone or rover | [Service hardware assumptions and porting](hardware/service-hardware-porting.md) |

## Maintainer and operations

These documents are for platform, firmware, and integration maintenance. Service authors do
not normally need them.

| Goal | Document |
| --- | --- |
| Start, stop, diagnose, collect logs, and recover | [Operations runbook](operations/runbook.md) |
| Maintain same-host iron-X console operation | [iron-X console setup](hardware/ironx-quickstart.md) |
| Manage priorities and long-term scope | [Development roadmap](roadmap.md) |
| Inspect the browser/server message schema | [Client protocol](protocol.md) |
| Inspect the server/rover motion contract | [APRIS Rover WebSocket protocol](rover-protocol.md) |
| Build, flash, and qualify APRIS firmware | [UGV02 APRIS WebSocket firmware](hardware/ugv02-websocket-firmware.md) |

## Documentation language

- The default `.md` path is the English canonical document.
- A Japanese translation, when available, uses `.ja.md` and is linked at the top.
- Update the English document first when behavior or priorities change, then synchronize the
  Japanese translation.
