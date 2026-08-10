# 08 - Deployment & Infrastructure

This document covers every deployment method, container configuration, GPU passthrough setup, platform-specific launcher, systemd service, networking, environment variables, and licensing for the Vaidyx codebase.

---

## 1. Deployment Overview

Vaidyx supports five distinct deployment methods:

| Method | Platform | Entry Point | GPU Access |
|---|---|---|---|
| Docker Compose (CPU) | Any Docker host | `docker-compose.yml` | None |
| Docker Compose (NVIDIA GPU) | Linux with NVIDIA GPU | `docker-compose.gpu-nvidia.yml` or overlay `docker/gpu.nvidia.yml` | NVIDIA CUDA |
| Docker Compose (AMD GPU) | Linux with AMD GPU | `docker-compose.gpu-amd.yml` or overlay `docker/gpu.amd.yml` | AMD ROCm |
| Native macOS | macOS (Apple Silicon / Intel) | `start-macos.sh` or `build-macos-app.sh` | Metal (native only) |
| Native Windows | Windows 10/11 | `launch-windows.ps1` or portable `build-windows-portable.ps1` | NVIDIA CUDA (native) |
| Native Linux (systemd) | Linux | `install-service.sh` + `vaidyx-ui.service` | Direct hardware access |

The core application is a FastAPI app (`app.py`) served by uvicorn. All deployment methods ultimately run:

```
uvicorn app:app --host <bind> --port <port>
```

The Docker stack additionally provisions three companion services: SearXNG (web search), ChromaDB (vector database), and ntfy (push notifications).

---

## 2. Docker Deployment

### 2.1 Dockerfile

**File:** `/Dockerfile` (114 lines)

The image uses a two-stage build on `python:3.14-slim`.

**Stage 1 -- `realesrgan-wheels`** (lines 6-10):
- Base: `python:3.14-slim`
- Runs `docker/build-realesrgan-wheels.sh` to build patched wheels for `basicsr==1.4.2`, `gfpgan==1.3.8`, `facexlib==0.3.0`
- These packages use a `locals()['__version__']` pattern that breaks on Python 3.13+ (PEP 667); the script patches `get_version()` to use an explicit namespace dict

**Stage 2 -- final image** (lines 12-114):
- Base: `python:3.14-slim`
- System packages installed (line 23-38):
  - `build-essential`, `cmake` -- for building llama.cpp inside the container
  - `curl`, `git` -- general tooling
  - `nodejs`, `npm` -- provides `npx` for the Browser MCP server
  - `chromium` -- browser binary for the MCP server
  - `tmux` -- Cookbook background downloads/serves
  - `openssh-client` -- Cookbook remote server operations
  - `gosu` -- privilege dropping without extra shell layers
  - `libgl1`, `libglib2.0-0t64`, `libxcb1` -- runtime shared libs for opencv-python (cv2)
  - `libmagic1` -- content-based MIME sniffing for `src/upload_handler.py`
- Docker CLI client installed (lines 59-70): static binary from `download.docker.com`, version controlled by `DOCKER_CLI_VERSION` build arg (default `29.6.2`), supports `amd64` and `arm64`
- Python dependencies installed (lines 77-79): `requirements.txt` always; `requirements-optional.txt` only when build arg `INSTALL_OPTIONAL=true`
- `python-magic==0.4.27` installed separately (line 84) because it depends on `libmagic1` system lib
- Patched Real-ESRGAN wheels copied from stage 1 and installed with `--no-deps` (lines 91-93)
- Application code copied with `COPY . .` (line 96)
- Data directories created: `data`, `logs`, `services/cache/search` (line 99)
- Entrypoint: `/usr/local/bin/entrypoint.sh` (line 112)
- Default command: `uvicorn app:app --host 0.0.0.0 --port 7000` (line 113)
- Exposed port: `7000` (line 110)

**Build args:**

| Arg | Default | Purpose |
|---|---|---|
| `DOCKER_CLI_VERSION` | `29.6.2` | Docker CLI static binary version |
| `INSTALL_OPTIONAL` | `false` | Install `requirements-optional.txt` (includes AGPL packages like PyMuPDF) |

### 2.2 Docker Entrypoint

**File:** `/docker/entrypoint.sh` (147 lines)

The entrypoint implements the standard PUID/PGID pattern to avoid the root-owned bind-mount problem. It:

1. **Creates user/group** (lines 22-27): Creates an `vaidyx` group at `PGID` and user at `PUID` (both default to `1000`) unless they already exist
2. **Docker socket plumbing** (lines 36-48): When `VAIDYX_ENABLE_HOST_DOCKER=true` and `/var/run/docker.sock` is present, adds the app user to the Docker socket's group for host Docker access
3. **Ownership repair** (lines 50-101): Repairs ownership of `/app` (excluding mount points) and each bind-mounted directory (`/app/data`, `/app/logs`, `/app/.ssh`, `/app/.cache/huggingface`, `/app/.local`) -- with a safety check to skip broad mount roots like `/`, `/home`, `/srv`
4. **CUDA_HOME auto-detection** (lines 118-126): Scans pip-installed NVIDIA wheel paths (`nvidia/cu13`, `nvidia/cu12`, `nvidia/cuda_nvcc`) for an `nvcc` binary and exports `CUDA_HOME` if found
5. **FlashInfer JIT sampler disabled** (line 132): Sets `VLLM_USE_FLASHINFER_SAMPLER=0` unconditionally to prevent vLLM startup crashes when nvcc headers are missing
6. **PATH extension** (line 136): Prepends `/app/.local/bin` for Cookbook-installed Python CLIs (vLLM, etc.)
7. **First-time setup** (line 141): Runs `setup.py` as the app user (idempotent, failure non-fatal)
8. **Privilege drop** (line 146): Uses `gosu` to exec the command as the app user, ensuring signals (SIGTERM from `docker stop`) reach uvicorn directly

### 2.3 Real-ESRGAN Wheel Builder

**File:** `/docker/build-realesrgan-wheels.sh` (70 lines)

This script:
- Downloads sdist tarballs for `basicsr==1.4.2`, `gfpgan==1.3.8`, `facexlib==0.3.0` via PyPI JSON API (avoids `pip download` which triggers the same version-read bug)
- Patches all three `setup.py` files to replace the broken `exec()` + `locals()['__version__']` pattern with an explicit `_ver_ns = {}` namespace dict
- Builds wheels with `pip wheel --no-deps` into the output directory (default `/wheels`)
- Asserts exactly 3 files were patched

### 2.4 Docker Compose -- CPU (Base)

**File:** `/docker-compose.yml` (158 lines)

Four services are defined:

#### Service: `vaidyx` (lines 2-82)
- Built from local Dockerfile
- Port mapping: `${APP_BIND:-127.0.0.1}:${APP_PORT:-7000}:7000`
- Volumes:
  - `${APP_DATA_DIR:-./data}:/app/data:z` -- persistent application data
  - `${APP_LOGS_DIR:-./logs}:/app/logs:z` -- log files
  - `${APP_DATA_DIR:-./data}/ssh:/app/.ssh:z` -- SSH identity for Cookbook remote servers
  - `${APP_DATA_DIR:-./data}/huggingface:/app/.cache/huggingface:z` -- HuggingFace model cache
  - `${APP_DATA_DIR:-./data}/local:/app/.local:z` -- pip-installed CLIs (vLLM, llama-cpp-python)
- Extra host: `host.docker.internal:host-gateway` -- allows reaching host services (e.g., Ollama at port 11434)
- Depends on: `searxng` (healthy), `chromadb` (started)
- Restart policy: `unless-stopped`

#### Service: `chromadb` (lines 84-92)
- Image: `docker.io/chromadb/chroma:latest`
- Port mapping: `${CHROMADB_BIND:-127.0.0.1}:8100:8000`
- Volume: `chromadb-data:/chroma/chroma` (named volume)
- Telemetry disabled: `ANONYMIZED_TELEMETRY=FALSE`

#### Service: `searxng` (lines 94-142)
- Image: `docker.io/searxng/searxng:2026.5.31-7159b8aed` (pinned -- not `:latest`; version `2026.6.2` is known to crash with `KeyError: 'default_doi_resolver'`, issue #1414)
- Custom entrypoint (lines 102-113): On first boot or when settings contain the template placeholder `__SEARXNG_SECRET__`, generates a random secret key (or uses `SEARXNG_SECRET` env var) and renders the settings template
- Port mapping: `127.0.0.1:8080:8080` (hardcoded loopback, not configurable)
- Volumes:
  - `searxng-data:/etc/searxng` -- persisted settings
  - `./config/searxng/settings.yml:/tmp/searxng-settings.yml.template:ro,z` -- template
- Linux capabilities: drops ALL, adds `CHOWN`, `SETGID`, `SETUID`, `DAC_OVERRIDE`
- Healthcheck: Python urllib request to `http://localhost:8080/` every 5s, 6s timeout, 20 retries, 10s start period

#### Service: `ntfy` (lines 144-153)
- Image: `docker.io/binwiederhier/ntfy`
- Command: `serve`
- Port mapping: `${NTFY_BIND:-127.0.0.1}:8091:80`
- Volume: `ntfy-cache:/var/cache/ntfy`

#### Named Volumes (lines 155-158)
- `searxng-data`
- `chromadb-data`
- `ntfy-cache`

### 2.5 GPU Compose Overlays

There are two approaches to enabling GPU support:

**Approach A -- COMPOSE_FILE overlay** (recommended for CLI users):
Set in `.env`:
```
COMPOSE_FILE=docker-compose.yml:docker/gpu.nvidia.yml
```

**Approach B -- Standalone compose file** (for UI-based stack managers like Portainer/Coolify/Dockhand):
Use `docker-compose.gpu-nvidia.yml` or `docker-compose.gpu-amd.yml` directly. These are self-contained files equivalent to the base + overlay combined.

#### NVIDIA GPU Overlay

**File:** `/docker/gpu.nvidia.yml` (35 lines)

Adds to the `vaidyx` service:
```yaml
environment:
  - NVIDIA_VISIBLE_DEVICES=all
  - NVIDIA_DRIVER_CAPABILITIES=compute,utility
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

**Prerequisites:**
- NVIDIA Container Toolkit on the host
- Installation varies by distro:
  - Arch: `sudo pacman -S nvidia-container-toolkit`
  - Debian: `sudo apt install nvidia-container-toolkit`
  - Fedora: `sudo dnf install nvidia-container-toolkit`
- Post-install:
  ```
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
  ```
- Verify: `docker info | grep -i nvidia`

**File:** `/docker-compose.gpu-nvidia.yml` (181 lines) -- standalone equivalent with all services included.

#### AMD ROCm GPU Overlay

**File:** `/docker/gpu.amd.yml` (20 lines)

Adds to the `vaidyx` service:
```yaml
devices:
  - /dev/kfd
  - /dev/dri
group_add:
  - video
  - ${RENDER_GID:-render}
```

**Prerequisites:**
- ROCm drivers on the host (`/dev/kfd` and `/dev/dri` device nodes)
- Host user running Docker must be in `video` and `render` groups
- Set `RENDER_GID` in `.env` to the numeric render group ID:
  ```
  RENDER_GID=$(getent group render | cut -d: -f3)
  ```

**.env configuration:**
```
COMPOSE_FILE=docker-compose.yml:docker/gpu.amd.yml
RENDER_GID=<numeric render group id>
```

**File:** `/docker-compose.gpu-amd.yml` (178 lines) -- standalone equivalent with all services included.

### 2.6 Host Docker Access Overlay

**File:** `/docker/host-docker.yml` (13 lines)

This is a high-trust overlay that mounts the host Docker socket into the container for Cookbook-driven Docker management:

```yaml
services:
  vaidyx:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    group_add: ["${DOCKER_GID:-963}"]
    environment:
      - VAIDYX_ENABLE_HOST_DOCKER=true
```

**Usage:**
```
COMPOSE_FILE=docker-compose.yml:docker/host-docker.yml
DOCKER_GID=<numeric host Docker group id>
```

**Security note:** Raw socket access grants broad control over the host Docker daemon. Enable only when local Docker-daemon management from Cookbook is required.

### 2.7 GPU Diagnostic Scripts

**File:** `/scripts/check-docker-gpu.sh` (616 lines) -- NVIDIA GPU diagnostic and optional setup helper.

Modes:
- **Default (no flags):** Read-only diagnostic -- checks host `nvidia-smi`, Docker daemon status, and GPU passthrough via `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`
- `--print-install-commands`: Shows OS-specific install commands (detects Ubuntu/Debian, Fedora/RHEL, Arch, OpenSUSE)
- `--install-nvidia-toolkit`: Interactive installer for Ubuntu/Debian only (adds NVIDIA apt repo, installs toolkit, configures Docker runtime, optionally restarts Docker)
- `--enable-nvidia-overlay`: Writes `COMPOSE_FILE=docker-compose.yml:docker/gpu.nvidia.yml` to `.env` (gated on successful passthrough test)
- `--yes`: Skip confirmation prompts for automated/CI use
- Detects WSL2 snap Docker incompatibility and provides specific guidance

**File:** `/scripts/check-docker-amd-gpu.sh` (206 lines) -- AMD/ROCm read-only diagnostic.

Checks:
- Host `/dev/kfd` and `/dev/dri/renderD*` device nodes
- Host `render` and `video` group GIDs
- Host `rocminfo` availability (optional)
- Docker passthrough test using `alpine:3.20` (configurable via `VAIDYX_AMD_TEST_IMAGE`)
- Prints suggested `.env` values on completion

---

## 3. macOS Deployment

### 3.1 Quick Start Script

**File:** `/start-macos.sh` (267 lines)

One-command native launcher for macOS. Designed so a user can run it without knowing about venvs, pip, or uvicorn. All steps are idempotent -- safe to re-run.

**Why native instead of Docker:** Docker on macOS runs a Linux VM with no access to the Metal GPU. Running natively lets Cookbook detect and use the Mac's GPU.

**Startup sequence:**

1. **Load `.env`** (lines 23-31): Sources `.env` file if present; existing shell variables take priority
2. **Port configuration** (lines 35-36):
   - Default port: `7860` (not 7000, because macOS AirPlay Receiver holds port 7000)
   - Overrides: `VAIDYX_PORT` > `APP_PORT` > `7860`
   - Bind: `VAIDYX_HOST` > `APP_BIND` > `127.0.0.1`
3. **Port conflict detection** (lines 48-52): Fails fast if the port is already in use
4. **Homebrew check** (lines 56-63): Required; directs user to install if missing
5. **Python discovery** (lines 73-84):
   - On Apple Silicon (`arm64`): Only looks under `/opt/homebrew/bin` for arm64 interpreters (python3.13, 3.12, 3.11). A universal2 or x86 Python from `/usr/local` would produce wrong-architecture compiled extensions
   - On Intel: Uses whatever Python 3.11+ is on PATH
6. **System dependencies via Homebrew** (lines 100-122):
   - `tmux` -- Cookbook background operations
   - `llama.cpp` -- prebuilt Metal-enabled llama-server (no compile step)
   - `apfel` -- Apple Foundation model server
   - `python@3.11` -- only if no suitable Python was found
   - Failed installs warn but do not abort (non-fatal)
7. **Virtual environment** (lines 133-149):
   - Creates `venv/` in the repo directory
   - Tracks requirements hash in `venv/.requirements_hash` to skip reinstalls when unchanged
   - Removes conflicting `chromadb-client` package if present
8. **First-run setup** (line 164): Runs `setup.py` (creates data dirs, DB, admin user)
9. **Apfel server** (lines 171-184): On Apple Silicon, starts the Apfel OpenAI-compatible server on port `11435` in the background
10. **ChromaDB** (lines 189-213): Starts a local ChromaDB server on `127.0.0.1:${CHROMADB_PORT:-8100}` unless one is already running or `CHROMADB_HOST` points to a remote host
11. **Browser auto-open** (lines 234-252): Background poller waits up to 90 seconds for the server, then opens the URL. Suppressed with `VAIDYX_NO_OPEN=1`
12. **Tailscale URL** (lines 223-228): If bound to `0.0.0.0` and Tailscale is installed, prints the Tailscale IPv4 URL
13. **Server launch** (line 266): `uvicorn app:app --host $HOST --port $PORT`
14. **Cleanup** (line 257): Kills background poller, Apfel, and ChromaDB on exit

### 3.2 macOS App Builder

**File:** `/build-macos-app.sh` (174 lines)

Produces:
- `dist/Vaidyx.app` -- double-click launcher
- `dist/Vaidyx.dmg` -- drag-to-Applications disk image

This is a launcher wrapper, not a bundled application. It drives the venv in the repo; the install path is baked in at build time.

**App structure:**
```
dist/Vaidyx.app/
  Contents/
    Info.plist          -- Bundle identifier: com.vaidyx.launcher, min macOS 11.0
    MacOS/Vaidyx      -- Bash launcher script
    Resources/
      vaidyx.icns     -- Icon (center-cropped from docs/vaidyx.jpg)
```

**Launcher behavior** (embedded script, lines 70-147):
- Checks for `venv/bin/uvicorn`; shows a GUI error dialog if the venv is not set up
- If the server is already running, just opens the browser
- Starts uvicorn in the background (with `arch -arm64` on Apple Silicon)
- Opens the UI in a chrome-less app window using Chromium-based browsers (Google Chrome, Microsoft Edge, Brave, Chromium), falling back to the default browser
- Traps TERM/INT to stop the server on app quit
- Waits up to 120 seconds for server readiness (first run downloads an embedding model)
- Default port: `${VAIDYX_PORT:-7860}`

**DMG creation** (lines 157-164): Uses `hdiutil create` with UDZO format and an Applications symlink for drag-to-install.

---

## 4. Windows Deployment

### 4.1 Native Windows Launcher

**File:** `/launch-windows.ps1` (170 lines)

One-command setup and launch script. Requires PowerShell 5.1+.

**Usage:**
```powershell
powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1
powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1 -Port 7000 -BindHost 127.0.0.1
```

**Parameters:**

| Parameter | Default | Purpose |
|---|---|---|
| `-Port` | `7000` | Server port |
| `-BindHost` | `127.0.0.1` | Bind address (use `0.0.0.0` for LAN access) |

**Startup sequence:**

1. **Python discovery** (lines 66-117): Tries the `py` launcher with `-3.13`, `-3.12`, `-3.11` flags first, then falls back to `python` on PATH. Requires Python 3.11+. Detects and avoids Windows Store stub (`WindowsApps\python.exe`)
2. **Virtual environment** (lines 123-130): Creates `venv\` if missing using `python -m venv venv`
3. **Dependencies** (lines 133-136): Runs `pip install -r requirements.txt`
4. **First-time setup** (lines 139-141): Runs `setup.py` (creates data dirs, DB, admin user, prints admin password on first run)
5. **Git Bash check** (lines 144-150): Warns if Git Bash is not found (needed for full Cookbook/agent-shell parity). Searches `ProgramFiles`, `ProgramW6432`, `ProgramFiles(x86)`, `LocalAppData`, and common paths
6. **CUDA path detection** (lines 153-163): Scans `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA` for the newest CUDA toolkit with a `bin` directory and sets `CUDA_PATH`
7. **Server launch** (line 169): `python -m uvicorn app:app --host $BindHost --port $Port`

### 4.2 Portable Windows Build

**File:** `/build-windows-portable.ps1` (72 lines)

Builds a self-contained portable Windows distribution using PyInstaller.

**Usage:**
```powershell
powershell -ExecutionPolicy Bypass -File .\build-windows-portable.ps1
```

**Output layout:**
```
dist\Vaidyx\
  Vaidyx.exe            -- PyInstaller-frozen launcher
  static\...              -- Static web assets
  scripts\...             -- Helper scripts
  mcp_servers\...         -- MCP server definitions
  services\hwfit\data\... -- Hardware fitness data
  config\...              -- Configuration files
  .env.example            -- Environment template
```

**Build process:**
1. Finds Python (checks `.venv\Scripts\python.exe`, then `py`, then `python` on PATH)
2. Installs build dependencies: `requirements.txt`, `pyinstaller`, `pystray`, `Pillow`
3. Runs PyInstaller with `--onedir --noconsole --icon=static/icon.ico --name Vaidyx`
4. Bundles data via `--add-data` for `static`, `scripts`, `mcp_servers`, `services/hwfit/data`, `config`, `.env.example`
5. Entry point: `launcher.py`

### 4.3 Windows Launcher (launcher.py)

**File:** `/launcher.py` (143 lines)

Dedicated entrypoint for the frozen PyInstaller bundle. Handles:

- **NullWriter** (lines 18-25): Suppresses console stream crashes in windowed GUI mode
- **Splash screen** (lines 36-66): When running frozen (`sys.frozen`), immediately shows a tkinter splash with branding (dark theme, `#1a1c23` background, `#e06c75` accent)
- **System tray icon** (lines 69-109): Creates a pystray icon with "Open Vaidyx" and "Exit" menu items, using a programmatically generated sailing boat icon in brand colors
- **Browser auto-open** (lines 112-124): Waits 3.5 seconds, destroys splash, opens default browser
- **Server** (lines 127-142): Reads `APP_BIND` (default `127.0.0.1`) and `APP_PORT` (default `7000`) from environment, runs `uvicorn.run(app, ...)`

### 4.4 Windows Update Script

**File:** `/update_windows.bat` (59 lines)

Batch script for updating a Docker-based Windows deployment:

1. Verifies `git`, `docker`, and `docker compose` are available
2. Pulls latest code: `git pull --ff-only`
3. Rebuilds and restarts: `docker compose up -d --build`
4. Cleans up: `docker image prune -f`

---

## 5. Linux Deployment (systemd)

### 5.1 Service Unit File

**File:** `/vaidyx-ui.service` (17 lines)

```ini
[Unit]
Description=Vaidyx UI
After=network.target

[Service]
Type=simple
User=YOURUSER
WorkingDirectory=/home/YOURUSER/vaidyx-ui
ExecStart=/home/YOURUSER/vaidyx-ui/venv/bin/uvicorn app:app --port 7000 --host 0.0.0.0
Restart=always
RestartSec=3
EnvironmentFile=-/home/YOURUSER/vaidyx-ui/.env

[Install]
WantedBy=multi-user.target
```

**Key details:**
- `User`, `WorkingDirectory`, and `ExecStart` paths must be edited before installation
- `EnvironmentFile=-` (dash prefix) means the `.env` file is optional; absence does not prevent the service from starting
- Binds to `0.0.0.0:7000` by default (all interfaces)
- Restarts on any failure after 3 seconds

### 5.2 Service Installer

**File:** `/install-service.sh` (20 lines)

```bash
sudo cp vaidyx-ui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vaidyx-ui
sudo systemctl start vaidyx-ui
sudo systemctl status vaidyx-ui
```

Must edit the service file first with the correct username and paths.

---

## 6. GPU Support

### 6.1 NVIDIA GPU Configuration

**Enable via COMPOSE_FILE overlay:**
```
# In .env:
COMPOSE_FILE=docker-compose.yml:docker/gpu.nvidia.yml
```

**Or use the standalone file:**
```bash
docker compose -f docker-compose.gpu-nvidia.yml up -d --build
```

**Or use the diagnostic script for assisted setup:**
```bash
# Read-only diagnostic:
scripts/check-docker-gpu.sh

# Full automated setup (Ubuntu/Debian):
scripts/check-docker-gpu.sh --install-nvidia-toolkit --enable-nvidia-overlay --yes
```

**What the overlay does:**
- Sets `NVIDIA_VISIBLE_DEVICES=all` and `NVIDIA_DRIVER_CAPABILITIES=compute,utility`
- Reserves all NVIDIA GPUs via the Docker `deploy.resources.reservations.devices` mechanism

**Important:** The slim Vaidyx image does not bundle CUDA userspace or inference engines. After enabling GPU passthrough, install vLLM / llama-cpp-python / SGLang via Cookbook (Dependencies tab) or pip inside the container.

**Entrypoint CUDA handling:**
- Auto-detects pip-installed `nvcc` in `/app/.local/lib/python*/site-packages/nvidia/{cu13,cu12,cuda_nvcc}/bin/nvcc` and sets `CUDA_HOME`
- Disables FlashInfer JIT sampler (`VLLM_USE_FLASHINFER_SAMPLER=0`) to prevent vLLM startup crashes

### 6.2 AMD ROCm GPU Configuration

**Enable via COMPOSE_FILE overlay:**
```
# In .env:
COMPOSE_FILE=docker-compose.yml:docker/gpu.amd.yml
RENDER_GID=<numeric render group id from: getent group render | cut -d: -f3>
```

**Or use the standalone file:**
```bash
RENDER_GID=$(getent group render | cut -d: -f3) \
  docker compose -f docker-compose.gpu-amd.yml up -d --build
```

**What the overlay does:**
- Passes `/dev/kfd` and `/dev/dri` device nodes to the container
- Adds the container user to `video` and `${RENDER_GID:-render}` groups

**Prerequisites:**
- ROCm drivers installed on the host
- Host user running Docker in `video` and `render` groups

**Diagnostic:**
```bash
scripts/check-docker-amd-gpu.sh
```

### 6.3 macOS GPU (Metal)

macOS GPU support is available only in native (non-Docker) deployments. Docker on macOS runs a Linux VM with no Metal access. The `start-macos.sh` script installs `llama.cpp` via Homebrew, which provides a Metal-enabled `llama-server` binary. On Apple Silicon, the Apfel server is also started on port `11435`.

### 6.4 Windows GPU (CUDA)

The `launch-windows.ps1` script auto-detects the NVIDIA CUDA Toolkit at `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA` and sets `CUDA_PATH` to the newest version with a `bin` directory.

---

## 7. SearXNG Configuration

**File:** `/config/searxng/settings.yml` (10 lines)

```yaml
use_default_settings: true

server:
  secret_key: "__SEARXNG_SECRET__"

search:
  formats:
    - html
    - json
```

This file serves as a template. The compose entrypoint (lines 102-113 of `docker-compose.yml`) processes it on first boot:

1. Checks if `/etc/searxng/settings.yml` is empty, contains the template placeholder `__SEARXNG_SECRET__`, or an old marker string `vaidyx-local-searxng-json-2026-05-30`
2. If so, generates a random secret (or uses `SEARXNG_SECRET` env var): `python -c 'import secrets; print(secrets.token_urlsafe(48))'`
3. Substitutes `__SEARXNG_SECRET__` with the generated secret via `sed`
4. Writes the rendered settings to `/etc/searxng/settings.yml` (persisted in the `searxng-data` named volume)
5. Then execs the official SearXNG entrypoint

**Key configuration:**
- `use_default_settings: true` -- inherits all default SearXNG engine configurations
- JSON format enabled -- required for Vaidyx to query SearXNG programmatically
- HTML format enabled -- allows direct browser access to the SearXNG UI at `http://localhost:8080`

The `vaidyx` service connects to SearXNG at `http://searxng:8080` (Docker internal network).

---

## 8. Licensing

Four third-party license files are maintained in `/licenses/`:

| File | License | Component | Used In |
|---|---|---|---|
| `DeepResearch-Apache-2.0.txt` | Apache 2.0 | DeepResearch | Research functionality |
| `llmfit-MIT-LICENSE.txt` | MIT | llmfit (Alex Jones, 2026) | `services/hwfit/`, `routes/cookbook_*.py`, `routes/hwfit_routes.py`, `static/js/cookbook*.js`, `scripts/vaidyx-cookbook` |
| `opencode-MIT-LICENSE.txt` | MIT | opencode (2025, originally opencode-ai/opencode) | Agent-loop / tool-execution patterns and UI concepts |
| `OpenDyslexic-OFL.txt` | SIL Open Font License 1.1 | OpenDyslexic font (Abbie Gonzalez) | Accessibility font bundled in the UI |

**Note on optional dependencies:** The default Docker image stays MIT-core. Optional extras (e.g., PyMuPDF which is AGPL) are installed only when `INSTALL_OPTIONAL=true` is set as a build arg, per the Dockerfile comment on line 75.

---

## 9. Environment Variables

### 9.1 LLM / AI Provider Configuration

| Variable | Default | Description |
|---|---|---|
| `LLM_HOST` | `localhost` | Primary LLM host |
| `LLM_HOSTS` | (empty) | Additional LLM hosts |
| `OPENAI_API_KEY` | (empty) | OpenAI API key |
| `OLLAMA_BASE_URL` | (empty) | Ollama server URL |
| `RESEARCH_LLM_ENDPOINT` | (empty) | Research-specific LLM endpoint |
| `HF_TOKEN` | (empty) | HuggingFace token |
| `HUGGING_FACE_HUB_TOKEN` | (empty) | HuggingFace Hub token (alternate) |

### 9.2 Search Provider API Keys

| Variable | Default | Description |
|---|---|---|
| `DATA_BRAVE_API_KEY` | (empty) | Brave Search API key |
| `GOOGLE_API_KEY` | (empty) | Google API key |
| `GOOGLE_PSE_CX` | (empty) | Google Programmable Search Engine CX |
| `TAVILY_API_KEY` | (empty) | Tavily search API key |
| `SERPER_API_KEY` | (empty) | Serper search API key |

### 9.3 Google OAuth

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | (empty) | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | (empty) | Google OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | (empty) | Google OAuth redirect URI |

### 9.4 Embedding Configuration

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_URL` | (empty) | External embedding API URL |
| `EMBEDDING_MODEL` | (empty) | Embedding model name |
| `EMBEDDING_API_KEY` | (empty) | Embedding API key |
| `FASTEMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local FastEmbed model |
| `FASTEMBED_CACHE_PATH` | (empty) | FastEmbed model cache path |

### 9.5 Infrastructure Services

| Variable | Default | Description |
|---|---|---|
| `SEARXNG_INSTANCE` | `http://searxng:8080` | SearXNG URL (hardcoded in compose) |
| `SEARXNG_BASE_URL` | `http://localhost:8080/` | SearXNG public base URL |
| `SEARXNG_SECRET` | (auto-generated) | SearXNG secret key |
| `CHROMADB_HOST` | `chromadb` | ChromaDB hostname (Docker) / `localhost` (native) |
| `CHROMADB_PORT` | `8000` | ChromaDB port (internal) |
| `DATABASE_URL` | `sqlite:///./data/app.db` | Primary database URL |
| `NTFY_BASE_URL` | `http://localhost:8091` | ntfy notification server URL |

### 9.6 Authentication & Security

| Variable | Default | Description |
|---|---|---|
| `AUTH_ENABLED` | `true` | Enable authentication |
| `LOCALHOST_BYPASS` | `false` | Allow unauthenticated localhost access |
| `VAIDYX_ADMIN_USER` | `admin` | Admin username |
| `VAIDYX_ADMIN_PASSWORD` | (empty) | Admin password (generated on first run if empty) |
| `ALLOWED_ORIGINS` | `http://localhost,http://127.0.0.1` | CORS allowed origins |
| `SECURE_COOKIES` | `false` | Use secure (HTTPS-only) cookies |

### 9.7 Upload Size Limits

| Variable | Default | Description |
|---|---|---|
| `VAIDYX_CHAT_UPLOAD_MAX_BYTES` | `10485760` (10 MB) | Chat file upload limit |
| `VAIDYX_GALLERY_UPLOAD_MAX_BYTES` | `104857600` (100 MB) | Gallery upload limit |
| `VAIDYX_GALLERY_TRANSFORM_UPLOAD_MAX_BYTES` | `26214400` (25 MB) | Gallery transform upload limit |
| `VAIDYX_MEMORY_IMPORT_MAX_BYTES` | `10485760` (10 MB) | Memory import limit |
| `VAIDYX_PERSONAL_UPLOAD_MAX_BYTES` | `26214400` (25 MB) | Personal file upload limit |
| `VAIDYX_EMAIL_COMPOSE_UPLOAD_MAX_BYTES` | `26214400` (25 MB) | Email attachment limit |
| `VAIDYX_STT_MAX_AUDIO_BYTES` | `26214400` (25 MB) | Speech-to-text audio limit |
| `VAIDYX_ICS_MAX_BYTES` | `10485760` (10 MB) | Calendar ICS import limit |
| `VAIDYX_TTS_CACHE_MAX_BYTES` | (unset) | TTS cache size limit |

### 9.8 Application Behavior

| Variable | Default | Description |
|---|---|---|
| `CLEANUP_INTERVAL_HOURS` | `24` | Cleanup task interval in hours |
| `VAIDYX_INPROCESS_POLLERS` | `1` | Number of in-process pollers |
| `VAIDYX_INPROCESS_TASKS` | `1` | Number of in-process tasks |
| `VAIDYX_SCRIPT_HOST` | `localhost` | Script execution host |

### 9.9 Container / Deployment Variables

| Variable | Default | Description |
|---|---|---|
| `PUID` | `1000` | User ID the container drops to |
| `PGID` | `1000` | Group ID the container drops to |
| `APP_BIND` | `127.0.0.1` | Bind address for the app |
| `APP_PORT` | `7000` | App port (Docker); `7860` (macOS native) |
| `APP_DATA_DIR` | `./data` | Data directory path |
| `APP_LOGS_DIR` | `./logs` | Logs directory path |
| `CHROMADB_BIND` | `127.0.0.1` | ChromaDB bind address |
| `NTFY_BIND` | `127.0.0.1` | ntfy bind address |
| `VAIDYX_ENABLE_HOST_DOCKER` | (unset) | Enable host Docker socket access |
| `DOCKER_GID` | `963` | Host Docker group ID (for socket overlay) |
| `DOCKER_SOCK` | `/var/run/docker.sock` | Docker socket path |

### 9.10 GPU-Specific Variables

| Variable | Default | Description |
|---|---|---|
| `NVIDIA_VISIBLE_DEVICES` | `all` | NVIDIA devices to expose |
| `NVIDIA_DRIVER_CAPABILITIES` | `compute,utility` | NVIDIA driver capabilities |
| `RENDER_GID` | `render` | AMD render group GID |
| `CUDA_HOME` | (auto-detected) | CUDA toolkit path (set by entrypoint) |
| `CUDA_PATH` | (auto-detected) | CUDA path (set by Windows launcher) |
| `VLLM_USE_FLASHINFER_SAMPLER` | `0` | Disable FlashInfer JIT sampler |

### 9.11 macOS-Specific Variables

| Variable | Default | Description |
|---|---|---|
| `VAIDYX_PORT` | `7860` | macOS app port (overrides `APP_PORT`) |
| `VAIDYX_HOST` | `127.0.0.1` | macOS bind host (overrides `APP_BIND`) |
| `VAIDYX_NO_OPEN` | (unset) | Suppress auto-opening browser |
| `VAIDYX_SKIP_RUN_HINT` | (unset) | Suppress setup.py run hint |

---

## 10. Network / Port Configuration

### 10.1 Port Map

| Service | Internal Port | Default External Mapping | Configurable Via |
|---|---|---|---|
| Vaidyx (app) | 7000 | `${APP_BIND:-127.0.0.1}:${APP_PORT:-7000}` | `APP_BIND`, `APP_PORT` |
| ChromaDB | 8000 | `${CHROMADB_BIND:-127.0.0.1}:8100` | `CHROMADB_BIND` |
| SearXNG | 8080 | `127.0.0.1:8080` (hardcoded) | Not configurable |
| ntfy | 80 | `${NTFY_BIND:-127.0.0.1}:8091` | `NTFY_BIND`, `NTFY_BASE_URL` |
| Apfel (macOS native) | 11435 | `127.0.0.1:11435` | Not configurable |
| ChromaDB (macOS native) | 8100 | `127.0.0.1:${CHROMADB_PORT:-8100}` | `CHROMADB_PORT` |

**macOS native note:** The default app port on macOS is `7860`, not `7000`, because macOS AirPlay Receiver occupies port 7000.

### 10.2 Bind Address Semantics

- `127.0.0.1` (default): Accessible only from the local machine
- `0.0.0.0`: Accessible from the local network (LAN/Tailscale)
- All external-facing ports default to `127.0.0.1` for security

### 10.3 Docker Internal Networking

Within the Docker Compose stack, services communicate using Docker DNS:
- Vaidyx reaches SearXNG at `http://searxng:8080`
- Vaidyx reaches ChromaDB at `chromadb:8000`
- The `host.docker.internal:host-gateway` extra-host mapping allows reaching services on the Docker host (e.g., Ollama at `http://host.docker.internal:11434`)

### 10.4 Service Dependencies

```
vaidyx
  |-- depends_on: searxng (condition: service_healthy)
  |-- depends_on: chromadb (condition: service_started)
```

The `vaidyx` container will not start until:
- SearXNG passes its healthcheck (Python urllib request to `http://localhost:8080/`, up to 20 retries at 5-second intervals with 10-second start period)
- ChromaDB has started (no healthcheck required, just container start)

### 10.5 Volume Persistence

**Docker named volumes:**
- `searxng-data` -- SearXNG configuration at `/etc/searxng`
- `chromadb-data` -- ChromaDB vector data at `/chroma/chroma`
- `ntfy-cache` -- ntfy notification cache at `/var/cache/ntfy`

**Bind-mounted volumes (Vaidyx container):**

| Container Path | Host Default | Purpose |
|---|---|---|
| `/app/data` | `./data` | Application data, SQLite DB, preferences |
| `/app/logs` | `./logs` | Application logs |
| `/app/.ssh` | `./data/ssh` | SSH keys for Cookbook remote servers |
| `/app/.cache/huggingface` | `./data/huggingface` | HuggingFace model cache |
| `/app/.local` | `./data/local` | pip-installed CLIs (vLLM, llama-cpp-python) |

All bind mounts use the `:z` SELinux relabeling suffix for compatibility with SELinux-enabled hosts.

---

## Appendix: Quick-Start Commands

### Docker (CPU)
```bash
docker compose up -d --build
# App at http://localhost:7000
```

### Docker (NVIDIA GPU)
```bash
# Option A: overlay
echo 'COMPOSE_FILE=docker-compose.yml:docker/gpu.nvidia.yml' >> .env
docker compose up -d --build

# Option B: standalone
docker compose -f docker-compose.gpu-nvidia.yml up -d --build

# Option C: assisted setup
scripts/check-docker-gpu.sh --install-nvidia-toolkit --enable-nvidia-overlay --yes
docker compose up -d --build
```

### Docker (AMD GPU)
```bash
echo "COMPOSE_FILE=docker-compose.yml:docker/gpu.amd.yml" >> .env
echo "RENDER_GID=$(getent group render | cut -d: -f3)" >> .env
docker compose up -d --build
```

### macOS Native
```bash
./start-macos.sh
# App at http://127.0.0.1:7860
```

### macOS App
```bash
./build-macos-app.sh
open dist/Vaidyx.app
```

### Windows Native
```powershell
powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1
# App at http://127.0.0.1:7000
```

### Windows Portable Build
```powershell
powershell -ExecutionPolicy Bypass -File .\build-windows-portable.ps1
# Run: dist\Vaidyx\Vaidyx.exe
```

### Linux systemd
```bash
# Edit vaidyx-ui.service with your username and paths
./install-service.sh
# App at http://0.0.0.0:7000
```
