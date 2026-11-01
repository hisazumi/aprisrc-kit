# Windows setup

[日本語](windows-setup.ja.md)

## First start (PowerShell)

Windows is the default participant setup. Use Edge or Chrome on the PC; WSL and
Safari are not required. For macOS/Linux, open the collapsed alternative in the
[participant quickstart](challenger-quickstart.md).

Install Git, Node.js 22.12+ or 24+ (including npm), and [uv](https://docs.astral.sh/uv/getting-started/installation/).

### Install Node.js and npm

For a new setup, use the official Windows installer for **Node.js 24.x**.
npm is included; do not install it separately. See the
[npm installation guide](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm/).

1. Open the [Node.js download page](https://nodejs.org/en/download) and select
   version **24.x**, **Windows**, and **Windows Installer (.msi)** for your PC's architecture.
2. Run the installer, keeping the npm and PATH options enabled. If your managed PC
   requires administrator approval, ask its administrator rather than bypassing restrictions.
3. Close and reopen PowerShell. If using the VS Code terminal, restart VS Code too.
4. Check both commands:

```powershell
node --version
npm.cmd --version
```

The first should report `v24.x.x`; the second should print an npm version number.
If both already work with a supported Node.js version, no reinstall is needed.
If either command is not found, first reopen the terminal, then check that the
installation completed and PATH was enabled. Do not change PowerShell's execution policy;
this guide uses `npm.cmd` to avoid the `npm.ps1` restriction.

### Install uv

uv installs the project's Python version and dependencies. You do not need to
install Python separately before installing uv this way.
In PowerShell, use the WinGet command from the
[official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/#winget):

```powershell
winget install --id=astral-sh.uv -e
```

After installation, close and reopen PowerShell (restart VS Code if using its
terminal), then check:

```powershell
uv --version
```

A version number confirms that uv is available. If it already works, skip installation.
If `winget` is unavailable, consult the official guide for another installation method
or ask your PC administrator. Do not bypass institutional installation restrictions.
If `uv` is still not found after reopening the terminal, check whether installation
completed and its executable directory was added to PATH.

Continue below: `uv python install 3.12` installs Python, while `uv sync` prepares
this project's dependencies.

### Start the simulator

Run these commands from the repository root, the folder containing `package.json`:

```powershell
uv python install 3.12
npm.cmd ci
uv sync --directory apps/server --no-dev
$env:APRIS_ADAPTER="simulator"
$env:APRIS_DISABLE_HTTPS="1"
$env:APRIS_SERVER_URL="http://127.0.0.1:8000"
npm.cmd run dev
```

The tracked `.python-version` files select Python 3.12 at the repository root and
in `apps/server`. You do not need to replace the system Python or prepare Rust
just to try the simulator. Compatible prebuilt dependency packages normally avoid
local compilation; package mirrors or custom installation settings can affect this.
The package's minimum Python metadata is not a promise that every newer Python
version has prebuilt dependencies on Windows. Use the pinned version.

Open `http://localhost:5173/playground?service=my-service` (use the port Vite prints if 5173 is busy).
Confirm both `[pwa]` and `[server]` startup messages. A page loading is not proof
that the backend has started. `http://127.0.0.1:8000/api/status` should return JSON.
Stop the development processes with Ctrl+C. These settings are for the desktop
simulator, not a smartphone camera or physical robot; those require their own setup.

PowerShell uses `$env:NAME="value"`, not Bash's `NAME=value command` syntax.
`npm.cmd` avoids the `npm.ps1` execution-policy error without changing that policy.
Environment variables apply to this PowerShell session; set them again in a new terminal.

## Troubleshooting

| Symptom | Next check |
| --- | --- |
| `npm.ps1` is blocked | Use `npm.cmd`; do not relax PowerShell execution policy. |
| `[vite] ws proxy error ... ECONNREFUSED` | Read the first `[server]` error. Check `/api/status` on port 8000. The frontend may be running while Python dependency setup has failed. |
| `watchfiles`, `maturin`, or Rust build failure | See **Python dependency builds fail** below to check the active Python version and first error. |
| Package download timeout | Set `$env:UV_HTTP_TIMEOUT="300"`, then retry `uv sync --directory apps/server --no-dev`. Do not clear caches as the first step; that forces more downloads. |
| Backend responds at `127.0.0.1` but Vite cannot connect | Set `$env:APRIS_SERVER_URL="http://127.0.0.1:8000"` and restart Vite. Check for an old override pointing at another server. |
| Port 8000 is in use | Stop the previous APRIS server before starting another. Do not terminate unrelated processes. |

To isolate backend startup, run `npm.cmd run dev:server`. Wait for
`Application startup complete` and verify `/api/status`. **Stop it with Ctrl+C
before running `npm.cmd run dev`**, which starts its own backend.

### Python dependency builds fail

**Symptom:** Startup reports a `watchfiles`, `maturin`, or Rust build error and
the `[server]` process does not start. The page may still load while Vite reports
`ECONNREFUSED`.

**Check:** An existing virtual environment created with another Python version
(for example, 3.15) may lack compatible prebuilt dependencies. From the repository
root, check the existing interpreter directly:

```powershell
apps/server/.venv/Scripts/python.exe --version
```

If `.venv` does not exist, return to the first-start steps. If the version is not
3.12, recreate only the project's environment below. Do not replace the system
Python. Skip this procedure when startup already works.

**Fix:** Stop all APRIS development terminals first. From the repository root:

```powershell
uv python install 3.12
if (Test-Path apps/server/.venv) {
    $backup = ".venv-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Rename-Item -Path apps/server/.venv -NewName $backup
}
uv sync --directory apps/server --python 3.12 --no-dev
uv run --directory apps/server --no-dev python --version
```

Check that the last command reports `Python 3.12.x`, then use the first-start
environment settings and `npm.cmd run dev`. The renamed environment is only a
backup, not a relocatable environment to run. Do not commit it or share it.

If builds still fail with 3.12, the Python version may not be the cause.
Inspect the first full `[server]` error and package-index, mirror, and installation
settings. Identify the failing dependency before installing Rust or repeatedly
recreating the same environment.

## Tests and development tools

Normal `npm.cmd run dev` uses `uv run --no-dev`, so a simulator trial does not
automatically install pytest or ruff. To run checks, install the development group:

```powershell
uv sync --directory apps/server --dev
uv run --directory apps/server pytest
uv run --directory apps/server ruff check src tests
npm.cmd test
npm.cmd run typecheck
```

These PowerShell steps have been checked against the scripts and uv's options,
but have not been executed on a Windows machine as part of this change.
