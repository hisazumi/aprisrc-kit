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

The default development path is **Windows + PowerShell**, with Edge or Chrome on the PC.
Install Git, Node.js 22.12+ or 24+ (including npm), and uv. The commands below install
Python 3.12. WSL, macOS, and Safari are not required for a simulator trial.
See [Windows setup and troubleshooting](docs/windows-setup.md) for details.

```powershell
git clone https://github.com/hisazumi/aprisrc-kit.git
cd aprisrc-kit
```

```powershell
uv python install 3.12
npm.cmd ci
uv sync --directory apps/server --no-dev
$env:APRIS_ADAPTER="simulator"
$env:APRIS_DISABLE_HTTPS="1"
$env:APRIS_SERVER_URL="http://127.0.0.1:8000"
npm.cmd run dev
```

<details>
<summary>macOS / Linux alternative (Bash or zsh)</summary>

```bash
uv python install 3.12
npm ci
uv sync --directory apps/server --no-dev
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 APRIS_SERVER_URL=http://127.0.0.1:8000 npm run dev
```

For checks below, replace `npm.cmd` with `npm`.

</details>

This starts the backend on port 8000 and the UI on port 5173. It explicitly selects
Simulator and desktop HTTP, even if certificates already exist. Use the startup output
if the UI chooses another port.

- [My service Playground](http://localhost:5173/playground?service=my-service): start here
- [Service](http://localhost:5173/service?service=my-service): the selected service's user view
- [Console](http://localhost:5173/console?service=my-service): operation and monitoring

Check that `http://127.0.0.1:8000/api/status` returns JSON as well: a loaded page alone
does not prove the Python server started. Stop with Ctrl+C. See [PWA views](docs/pwa-views.md).

Only proceed to [HTTPS setup](docs/local-https.md) when using a phone camera.
A Windows PC can be paired with an iPhone; Safari refers to the phone browser, not a
requirement to use a Mac. The browser sends structured observations, not camera video.

After changes, run these checks in PowerShell:

```powershell
uv sync --directory apps/server --dev
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
uv run --directory apps/server ruff check src tests
uv run --directory apps/server pytest
```

For browser changes, also check the relevant Service, Playground and Console views.
Windows is the default documentation path; this edit does not add Windows-machine
test evidence. Use the [documentation index](docs/README.md) for configuration and maintenance.

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

### Student service template

Edit the service flow in `apps/pwa/src/missions/myService.ts`, then run `/playground?service=my-service` with the Simulator or `/service?service=my-service` with camera observations. See [the quick start](docs/demos/student-service.md) ([日本語](docs/demos/student-service.ja.md)) for setup, UI input, safety boundaries, and limitations.
