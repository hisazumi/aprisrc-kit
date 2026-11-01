# APRISRC Kit: purpose and scope

[日本語](positioning.ja.md)

**APRISRC Kit** is a service prototyping kit for the APRIS Robot Challenge, called
**APRISRC**. It helps participants build services that combine robot movement with
perception and interaction, rather than start by implementing device drivers and transport.

## Names and roles

| Name | Meaning in these documents |
| --- | --- |
| APRIS | The conference, not the name of this software |
| APRISRC | The robot challenge associated with APRIS |
| APRISRC Kit | This development kit: software, Simulator, samples, tests and guides |
| Participant service | The experience and behavior a participant designs using the Kit |

These documents describe the Kit's implementation and use. They are not challenge rules,
judging criteria, or a statement that this is an official or mandatory challenge platform.
Event-specific requirements and its formal status must be specified separately by the organizers.

## Participants create the service

Participants choose who the service helps, in what situation, what the robot should do,
how people interact with it, and how success or failure should be handled. They implement
those decisions in mission code, configuration and, when needed, service-facing UI.

The Kit provides reusable perception/interaction inputs, a high-level motion API, a Simulator,
reference hardware connectivity, runtime safety checks and development views. The server
and firmware retain control ownership, command expiry, motion limits and stop mechanisms;
participants must not bypass these protections to make a service work.

Greeting, following, carrying and marker guidance are **reference samples**, not prescribed
challenge solutions or evidence that a team's service is complete. They make API use,
changes and failure handling concrete. Change or replace the service policy; do not treat
matching a sample as the challenge objective. API examples also do not replace a complete
service-facing interaction design.

## Simulator and hardware

The Simulator is a place to run and change the same high-level service logic with repeatable
virtual observations. It is not a separate Simulator-only application target or a guarantee
of real camera recognition, movement accuracy or safe stopping distance.

The current physical reference is a UGV02 and a mounted smartphone connected through a
local server. This is the Kit's tested reference configuration, not a claim that APRISRC
requires this hardware. Another robot or sensor needs the documented adapter/client contracts
and its own validation. See [hardware assumptions and porting](hardware/service-hardware-porting.md).

See [Platform status](platform-status.md) for evidence and limits: earlier UGV02 supervised
following has been observed, the new live Playground is not physically verified, and
physical marker guidance remains unverified. None of these paths claims unattended autonomy
or general obstacle avoidance.

## Read or change the Kit

Start with [Try, change, and hand over APRISRC Kit](handoff.md), then the workshop or
participant quickstart. `/service` is service-facing, `/playground` is for development and source/observation
inspection, and `/console` is for operation. Each service may need its own user experience.
The [roadmap](roadmap.md) tracks Kit development, not event deadlines or competition tasks.

English documents are canonical; Japanese translations are linked at the top.
The software was previously called **APRIS Rover Platform**. That name remains in historical
records. This public repository/root package is `aprisrc-kit`. Server/PWA package names,
`APRIS_*` settings, protocol names, certificate labels and firmware identifiers remain
technical compatibility names. In particular, **APRIS Rover WebSocket protocol** still names
the server/device contract, not the conference or the entire Kit.

This public distribution includes current code/guides, not private development history.
See [Release scope](release-scope.md), [Licensing](../LICENSING.md) and [Contributing](../CONTRIBUTING.md).
Licenses define reuse permissions; the Kit name alone does not determine them.
