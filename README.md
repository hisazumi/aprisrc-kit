# APRISRC Kit

[日本語](README.ja.md)

**A service prototyping kit for the APRIS Robot Challenge (APRISRC).**

APRIS is the conference; APRISRC is its robot challenge; APRISRC Kit is this software and
development kit. Participants design their own services combining smartphone perception
and interaction with robot movement. The Kit supplies shared APIs, a Simulator, reference
hardware connectivity, samples and guides so they can focus on service behavior.

Greeting, following, carrying and marker guidance are starting examples, not prescribed
challenge solutions. Start in the Simulator, then validate supported high-level missions
on hardware. See [Purpose and scope](docs/positioning.md) for responsibilities and terminology.
This README does not define challenge rules, judging criteria or official/mandatory status.

## Start here

| Goal | Guide |
| --- | --- |
| Choose a trial, development, or hardware handoff path | [Try, change, and hand over APRISRC Kit](docs/handoff.md) |
| Try the MVP and make two small improvements (20-30 min) | [Playground hands-on](docs/demos/playground-workshop.md) |
| Try and change greeting, following, and marker-guidance services | [Service playground](docs/demos/service-playground.md) |
| Run an implemented demo | [Human interaction demo](docs/demos/human-interaction.md) |
| Build a service for the first time | [Participant quickstart](docs/challenger-quickstart.md) |
| Write service code with a web chat or coding assistant | [AI-assisted development](docs/ai-assisted-development.md) |
| Understand the mission API and safety boundary | [Mission API](docs/mission-api.md) |
| Test on the supported UGV02 | [UGV02 self-test](docs/hardware/ugv02-self-test.md) |
| Try supervised iron-X following with a PC and iPhone | [iron-X person following](docs/hardware/ironx-follow.md) |
| Find development and maintenance material | [Documentation index](docs/README.md) |

See [Platform status](docs/platform-status.md) for implemented capabilities, verified hardware,
and current limitations.

## What works today

- Person reaction, approach, following, and carry-service flows in the Simulator
- In-browser person, upper-body, and APRIS marker perception
- Text and supported-browser speech mapped to allowlisted high-level intents
- Server-owned control, speed limits, command TTL, disconnect stop, and E-stop
- UGV02 bounded turn/reverse and supervised person following using APRIS development firmware

The default adapter is the Simulator. Physical-rover support uses development firmware and a
private LAN; it does not claim unattended autonomy or general obstacle avoidance.

```text
Smartphone / Browser PWA
        │ WebSocket
        ▼
FastAPI Local Server
  control ownership / safety / logs
        │ Rover Adapter
        ▼
Simulator or supported rover adapter
```

## Repository layout

```text
apps/pwa/               React + TypeScript + Vite PWA
apps/server/            FastAPI Local Server and Simulator
apps/server/scenarios/  Reproducible Simulator input and fault scenarios
apps/server/config/     Local Server course marker configuration
packages/protocol/      Versioned JSON message schema
firmware/                UGV02 firmware sources and profiles
docs/                    Guides, reference, operations, and design records
```

## Development

Requirements: Node.js 22.x (22.12+) or 24+, npm, Python 3.11 or later, and `uv`.

```bash
git clone https://github.com/hisazumi/aprisrc-kit.git
cd aprisrc-kit
npm install
uv sync --directory apps/server --dev
npm run dev
```

`npm run dev` starts the FastAPI server at `http://localhost:8000` and the Vite development server at `http://localhost:5173`. The PWA development server proxies `/ws` and `/api` to FastAPI. If development certificates are present in `.certs/`, Vite automatically switches to `https://localhost:5173` and the WebSocket connection also uses WSS.

- `https://localhost:5173/app`: Service App for smartphones
- `https://localhost:5173/console`: Operator Console for PCs
- `https://localhost:5173/lab`: Integrated interface for Simulator development

Visiting `/` also displays the Service App. See [PWA views](docs/pwa-views.md) for the role of each view.

Cameras are available on the PC through `localhost`, but HTTPS is required when a smartphone connects to the PC's local IP address. See [Local HTTPS and smartphone setup](docs/local-https.md) for setup instructions. Video is not sent to the server; only structured observations recognized in the PWA are transmitted.

After making changes, run the following standard checks:

```bash
npm run typecheck
npm test
npm run build
uv run --directory apps/server ruff check src tests
uv run --directory apps/server pytest
```

Commit only after all checks pass. For browser-related changes, also open and verify `/app`, `/console`, and `/lab` as appropriate.

Use the [documentation index](docs/README.md) for adapter configuration, factory-firmware
diagnostics, protocols, and design records.

## Coordinate convention

- `x`: forward
- `y`: left
- `yaw`: counter-clockwise positive
- distance and velocity: metres and metres per second
- angles and angular velocity: radians and radians per second

## Scope

The supported physical reference is a Waveshare UGV02 running APRIS development firmware.
Experimental iron-X ROS 2 Humble integration supports a PC-hosted Kit over the LAN.
An operator has reported successful iPhone-based following; the latest stop-confirmation
fix and 0.15 m/s configuration still need physical revalidation. Start with
[iron-X person following](docs/hardware/ironx-follow.md). Broader qualification and LiDAR-based autonomy remain future work
tracked in the [Development roadmap](docs/roadmap.md).

## Distribution and contributions

This public repository is the code-development home. See [Initial public release](docs/release-scope.md) and [Contributing](CONTRIBUTING.md).
Original Kit code/docs use [MIT](LICENSE); vendored firmware retains its GPL terms. See [Licensing and attribution](LICENSING.md).
