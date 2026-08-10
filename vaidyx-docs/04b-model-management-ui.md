# 04b - Model Management UI (Cookbook System)

## 1. Cookbook Overview

The Cookbook is Vaidyx's model management system -- a browser-based UI for discovering, downloading, serving, and troubleshooting LLM and image-generation models across local and remote servers. It is implemented as a modular JavaScript system under `static/js/`.

### Architecture

The system is split into focused sub-modules imported by a central orchestrator:

| File | Lines | Role |
|------|-------|------|
| `cookbook.js` | 3677 | Main orchestrator: env state, server management, backend detection, command builders, tab wiring, presets, dependencies UI |
| `cookbookDownload.js` | 668 | Download sub-module: SSE streaming, model download via tmux, command building for HF/Ollama pulls |
| `cookbook-hwfit.js` | 2826 | Hardware fitness: "What Fits?" scan, GPU toggle rendering, model list rendering, expand panels, sort/filter |
| `cookbook-diagnosis.js` | 1079 | Error pattern matching (40+ patterns), diagnosis UI with one-click fixes |
| `cookbookSchedule.js` | 386 | Scheduled serve tasks with calendar integration |
| `cookbookPorts.js` | 19 | Pure port helpers: extract port from commands, find next free port |
| `cookbookProgressSignal.js` | 29 | Liveness signal for download watchdog (byte counter or output-tail fingerprint) |
| `cookbook-deps-recipes.js` | 189 | Per-backend install recipes (pip/docker commands) for the Dependencies tab |

Additional sub-modules imported but not in scope: `cookbookRunning.js` (task lifecycle), `cookbookServe.js` (cached model serving).

### Global State

The central state object `_envState` (cookbook.js, line 84) holds:
- `env` / `envPath`: Python environment type (venv/conda/none) and path
- `hfToken`: HuggingFace token for gated models
- `gpus`: CUDA_VISIBLE_DEVICES pin
- `remoteHost` / `remoteServerKey`: active SSH target
- `servers[]`: configured server list with name, host, port, env, color, modelDirs, platform
- `platform` / `hostPlatform`: OS detection (linux/windows/termux/darwin)

State persists to `localStorage` under keys `cookbook-last-state`, `cookbook-presets`, and `cookbook-serve-state`, with server-side sync via `cookbook_state.json`.

---

## 2. Model Discovery and Browsing

### Search Tab (What Fits?)

The Search tab is powered by `cookbook-hwfit.js`. It probes the target server's hardware, then fetches a ranked model list from the backend.

**Filter controls:**
- **Server selector** (`#hwfit-server-select`): picks local or any configured remote server
- **Use-case dropdown** (`#hwfit-usecase`): filters by purpose (e.g., `image_gen`)
- **Search input** (`#hwfit-search`): free-text search against model names
- **Quant filter** (`#hwfit-quant`): quantization type (Q4_K_M, AWQ-4bit, FP8, etc.)
- **Engine filter** (`#hwfit-engine`): backend filter (vllm/sglang/llamacpp/ollama/diffusers)
- **Context slider** (`#hwfit-context`): target context window (8k/16k/32k/50k/131k/Max)
- **GPU toggle buttons**: RAM-only, 1 GPU, 2 GPU, 4 GPU, 8 GPU (pool-aware for heterogeneous boxes)

**Column headers** (sortable, click to toggle direction):
Fit | Model (latest) | VRAM | Param | Quant | Ctx | Speed | Score | Mode

**Fit levels:** `perfect`, `good`, `marginal`, `too_tight`, `no_fit` -- color-coded green/yellow/orange/red.

**Scan caching** (hwfit.js, lines 340-523): Results are cached in `localStorage` under `hwfit_scan_cache_v1` with a 6-hour TTL and max 12 entries. A stale-while-revalidate pattern shows cached data instantly on reload while fetching fresh data in the background.

**Manual hardware simulation** (hwfit.js, lines 376-462): Users can override detected hardware with simulated GPU count, VRAM, RAM, and backend to answer "what if I had different hardware?"

**Ollama library merge** (hwfit.js, lines 584-665): Ollama library models are fetched from `/api/cookbook/ollama/library`, converted to hwfit row format with estimated VRAM needs (0.6 GB per billion params at Q4_K_M), and merged into the main list for unified filtering.

### Row Expansion

Clicking a model row calls `_expandModelRow()` (hwfit.js, line 1608), rendering an inline action panel with:
- **Download** button -- triggers `_runModelDownload()`
- **Run** button -- download + launch with smart defaults (auto TP, context, GPU mem)
- **Configure** button -- opens the full serve configuration panel
- HuggingFace link to the source repository

---

## 3. Model Downloading

### Download Flow (`cookbookDownload.js`)

Downloads are managed through a dedicated tmux-backed endpoint. The flow:

1. User clicks Download (from Search row panel or Download card input)
2. `_runModelDownload()` (line 468) resolves the target server, repo, and include pattern
3. Duplicate detection: checks for already-running or queued downloads of the same repo on the same host
4. Zombie revival: probes tmux sessions for "done" tasks that are actually still alive
5. Queue management: if another download is active on the target host, the new one is queued
6. POST to `/api/model/download` with payload containing repo_id, backend, include pattern, HF token, remote host, SSH port, download directory
7. Task is registered via `_addTask()` for the Running tab

**Command building** (`_buildDownloadCmd`, line 124): Generates either:
- `ollama pull <tag>` for Ollama models
- A Python script using `huggingface_hub.snapshot_download()` with a custom tqdm replacement that emits machine-parseable `FILE <name> [####] 75% 1.81/2.49GB 45.2MB/s` progress lines

**GGUF handling** (lines 60-96): For llama.cpp models, resolves GGUF sources from `model.gguf_sources[]`, builds include patterns like `*Q4_K_M*.gguf`, and extracts quant labels from filenames.

**SSE streaming** (`_runPanelCmd`, line 362): Streams command output via `/api/shell/stream` with real-time progress parsing. Progress lines are detected by regex and update in-place (replacing the previous progress line for the same file). Diagnosis runs on every output chunk.

**Progress signal** (`cookbookProgressSignal.js`): The watchdog uses `computeProgressSignal()` to detect stalled downloads. During file transfer, the byte counter is the signal. During pip dependency resolution or CUDA compilation (no byte counter), the output tail fingerprint serves as the liveness signal.

---

## 4. Hardware Fitness

### Hardware Detection

`_hwfitFetch()` (hwfit.js, line 667) is the main fetch function. It:
1. Builds query params from all filter controls and manual hardware overrides
2. Calls `/api/hwfit/models` (or `/api/hwfit/image-models` for image mode) with params including host, ssh_port, gpu_count, gpu_group, quant, ctx, search, use_case, manual hardware overrides
3. Renders hardware chips and GPU toggle buttons from the `system` object in the response
4. Sorts models client-side by the active column (fit, newest, vram, params, speed, score, context)
5. Merges Ollama library rows

### Hardware Chip Display

`_hwfitRenderHw()` (hwfit.js, line 1055) renders clickable hardware chips showing:
- GPU name(s) with heterogeneous pool support (e.g., "1x RTX 4090 + 1x RTX 3060")
- VRAM total
- RAM (available / total)
- CPU cores
- Backend (cuda/rocm/metal/vulkan)
- Manual hardware indicator

Each chip is toggleable (click to dim = exclude from ranking, X to fully remove).

### GPU Pool Toggle

`_renderGpuToggles()` (hwfit.js, line 211) renders RAM / GPU / multi-GPU buttons. On heterogeneous boxes, a pool dropdown lets users select which GPU group to serve from. Valid TP counts are powers of two up to the pool size.

### Backend Detection

`_detectBackend()` (cookbook.js, line 495) determines the serving engine:
- Ollama tags -> `ollama`
- Image models -> `diffusers` or `mlx_image`
- MLX models -> `mlx`
- AWQ/GPTQ/FP8/NVFP4 -> `vllm`
- GGUF files -> `llamacpp`
- Windows -> `llamacpp`
- Apple Silicon -> `mlx`
- ROCm/AMD -> `sglang`
- Default (unquantized/BF16) -> `vllm`

---

## 5. Diagnosis

### Error Pattern Matching (`cookbook-diagnosis.js`)

The `ERROR_PATTERNS` array (line 264) contains 40+ patterns, each with:
- `pattern` (regex) or `match` (function) for detection
- `message`: user-facing diagnosis
- `suggestion`: recommended action
- `fixes[]`: array of one-click fix buttons with label and action callback

**Key error categories and their fixes:**

| Category | Example Pattern | Fixes |
|----------|----------------|-------|
| Missing tools | `tmux not found` | Open Dependencies, copy install command |
| Port conflicts | `Port already serving` | Edit serve, check port |
| GPU OOM | `CUDA out of memory` | Retry with higher TP, lower context, enforce eager |
| KV cache | `No available memory for cache blocks` | Retry with gpu_mem 0.95, context 2048, TP=8 |
| Missing backends | `No module named vllm/sglang` | Open Dependencies, copy install |
| Gated models | `403 Forbidden`, `gated repo` | Request HF access, check token |
| NCCL errors | `ncclSystemError` | Set TP=1, enable enforce eager |
| Build failures | `cmake not found` | Open Dependencies, copy apt/pacman/dnf install |
| Disk full | `No space left on device` | Check HF cache size |

**Auto-fix actions** include: `_serveAutoRetry` (append flag), `_serveAutoRetryReplace` (replace flag value), `_serveAutoRetryRemove` (remove flag), `_serveAutoFix` (prepend env var). These kill the current task and relaunch with the modified command.

**Quick commands** (`_runQuickCmd`, line 1044): Executes a one-shot shell command via `/api/shell/exec` with SSH wrapping for remote targets, displaying output inline in the diagnosis panel.

### Diagnosis UI

`_showDiagnosis()` (line 898) renders a diagnosis card below the output with:
- Message and suggestion text
- Copy bundle button (generates a markdown troubleshooting report with task metadata, diagnosis, command, and captured output)
- Dismiss button
- Inline fix buttons with icons matched to action type (retry, copy, edit, install, kill, switch)

---

## 6. Scheduling (`cookbookSchedule.js`)

The scheduling module creates `ScheduledTask` entries with `action=cookbook_serve`.

**UI flow:**
1. User clicks the schedule arrow button next to a serve panel's Launch button
2. `openForm()` (line 165) renders an inline form with start time, end time, and day-of-week chips
3. Day chips default to weekdays (Mon-Fri); clicking toggles them
4. Optional "Create event in calendar" toggle mirrors the task to a CalDAV calendar

**Schedule creation** (line 194):
- Converts local wall-clock time to UTC
- Builds schedule type: `daily` (all 7 days), `weekly` (single day), or `cron` (custom day set)
- POSTs to `/api/tasks` with `task_type: "action"`, `action: "cookbook_serve"`, `trigger_type: "schedule"`
- Prompt payload includes preset name, repo_id, host, and end_after_min (duration)

**Calendar mirroring** (lines 290-360): When enabled, creates/finds a "Cookbook" calendar via `/api/calendar/calendars`, creates a recurring event via `/api/calendar/events` with `rrule`, and patches the task with `cookbook_event_uid` for cascading deletes.

---

## 7. Dependencies and Recipes

### Dependencies Tab

`_fetchDependencies()` (cookbook.js, line 1071) fetches `/api/cookbook/packages` with optional host, ssh_port, venv, platform, and backend params. Renders packages grouped by category (System, Tools, LLM, Image) with install/update/reinstall buttons.

### Install Recipes (`cookbook-deps-recipes.js`)

The `_RECIPES` array defines per-backend install commands with pip and docker variants:

| Backend | Label | Pip Command | Docker Command |
|---------|-------|-------------|----------------|
| `vllm` | Any vLLM model | `uv pip install -U vllm --torch-backend auto` | `docker pull vllm/vllm-openai:latest` |
| `sglang` | Any SGLang model | `uv pip install -U "sglang[all]" --torch-backend auto` | `docker pull lmsysorg/sglang:latest` |
| `mlx_lm` | Any MLX model | `python -m pip install -U mlx-lm` | -- |
| `llama_cpp` | Any GGUF model | `CMAKE_ARGS="-DGGML_CUDA=on" uv pip install -U "llama-cpp-python[server]"` | `docker pull ghcr.io/ggml-org/llama.cpp:server-cuda` |
| `diffusers` | Any Diffusers model | `python -m pip install -U "diffusers[torch]" torchvision accelerate scipy python-multipart` | -- |
| `mflux` | MLX image models | `python -m pip install -U mflux fastapi uvicorn python-multipart` | -- |

Recipe selection uses `pickRecipe(backend, modelId)` -- specific model patterns match first, then the generic fallback for that backend.

`RECIPE_BACKENDS` (line 170) lists all backends that get an expandable recipe panel in the Dependencies UI.

---

## 8. API Calls

### Hardware and Models
| Method | Endpoint | Used In | Purpose |
|--------|----------|---------|---------|
| GET | `/api/hwfit/models` | hwfit.js `_hwfitFetch` | Ranked model list with hardware fitness |
| GET | `/api/hwfit/image-models` | hwfit.js `_hwfitFetch` | Image model list with fitness |
| GET | `/api/model/cached` | hwfit.js `_hwfitFetch` | List downloaded model repo IDs |
| GET | `/api/cookbook/ollama/library` | hwfit.js `_ensureOllamaLib` | Ollama model library |

### Downloads and Serving
| Method | Endpoint | Used In | Purpose |
|--------|----------|---------|---------|
| POST | `/api/model/download` | cookbookDownload.js `_runModelDownload` | Start tmux-backed model download |
| POST | `/api/model/serve` | cookbook.js `_installDep`, recipe run | Launch serve/install task via tmux |
| POST | `/api/shell/stream` | cookbookDownload.js `_runPanelCmd` | SSE streaming command execution |
| POST | `/api/shell/exec` | diagnosis, zombie probe, quick cmd | One-shot command execution |

### Dependencies
| Method | Endpoint | Used In | Purpose |
|--------|----------|---------|---------|
| GET | `/api/cookbook/packages` | cookbook.js `_fetchDependencies` | List packages with install status |
| POST | `/api/cookbook/install-system-deps` | cookbook.js sysdeps handler | Install OS packages (tmux, cmake) |
| POST | `/api/cookbook/rebuild-engine` | cookbook.js `_rebuildLlamaCpp` | Clear cached llama-server build |

### Scheduling and Calendar
| Method | Endpoint | Used In | Purpose |
|--------|----------|---------|---------|
| POST | `/api/tasks` | cookbookSchedule.js | Create scheduled serve task |
| PUT | `/api/tasks/{id}` | cookbookSchedule.js | Update task with calendar event UID |
| GET | `/api/calendar/calendars` | cookbookSchedule.js | List calendars |
| POST | `/api/calendar/calendars` | cookbookSchedule.js | Create "Cookbook" calendar |
| POST | `/api/calendar/events` | cookbookSchedule.js | Create recurring calendar event |

---

## 9. Key Functions

### cookbook.js
| Function | Line | Purpose |
|----------|------|---------|
| `_detectBackend()` | 495 | Route model to serving engine (vllm/sglang/llamacpp/ollama/mlx/diffusers) |
| `_buildServeCmd()` | 672 | Build full serve command with all flags for any backend |
| `_buildEnvPrefix()` | 612 | Build venv/conda activation + env var prefix |
| `_detectReasoningParser()` | 430 | Map model name to vLLM reasoning parser slug |
| `_detectToolParser()` | 471 | Map model name to vLLM tool-call parser |
| `_detectModelOptimizations()` | 342 | Detect MoE/speculative/KV-cache optimizations per model family |
| `_sshCmd()` | 293 | Wrap command in SSH for remote execution |
| `_fetchDependencies()` | 1071 | Fetch and render the Dependencies tab |
| `_wireTabEvents()` | 1974 | Wire tab switching, swipe navigation, server selectors |
| `_applyServerSelection()` | 1897 | Apply server dropdown change to global state |
| `_serverKey()` | 129 | Generate stable per-profile key for server dropdown values |

### cookbook-hwfit.js
| Function | Line | Purpose |
|----------|------|---------|
| `_hwfitFetch()` | 667 | Main fetch: query backend, merge Ollama, cache, render |
| `_hwfitRenderList()` | 1331 | Render the sortable model grid with fit colors and badges |
| `_hwfitRenderHw()` | 1055 | Render hardware chips (GPU, VRAM, RAM, cores, backend) |
| `_renderGpuToggles()` | 211 | Render RAM/GPU pool toggle buttons |
| `_expandModelRow()` | 1608 | Expand inline action panel (Download/Run/Configure) |
| `_resetGpuToggleState()` | 176 | Reset GPU toggle state for server switch |
| `_ensureBackendInstalled()` | 103 | Pre-launch check: is the backend pip package installed? |

### cookbookDownload.js
| Function | Line | Purpose |
|----------|------|---------|
| `_runModelDownload()` | 468 | Full download flow: dedup, zombie check, queue, POST |
| `_runPanelCmd()` | 362 | SSE streaming command runner with progress parsing |
| `_buildDownloadCmd()` | 124 | Build download command (ollama pull or HF snapshot_download) |
| `_wirePanelEvents()` | 229 | Wire download/stop/copy/save buttons on a panel |

### cookbook-diagnosis.js
| Function | Line | Purpose |
|----------|------|---------|
| `_diagnose()` | 869 | Match output text against ERROR_PATTERNS, return first hit |
| `_showDiagnosis()` | 898 | Render diagnosis card with message, suggestion, fix buttons |
| `_clearDiagnosis()` | 1036 | Remove diagnosis card from panel |
| `_runQuickCmd()` | 1044 | Execute one-shot command with SSH wrapping |
| `openCookbookDependencies()` | 71 | Deep-link into Dependencies tab with auto-expand |

### cookbookSchedule.js
| Function | Line | Purpose |
|----------|------|---------|
| `openForm()` | 165 | Render inline schedule form |
| `wireForm()` | 189 | Wire day chips, save handler with UTC conversion and calendar mirroring |
| `readPanelConfig()` | 89 | Extract model identity from the nearest serve panel |

### cookbook-deps-recipes.js
| Function | Line | Purpose |
|----------|------|---------|
| `pickRecipe()` | 182 | Find best recipe for a backend + model id |
| `recipesForBackend()` | 175 | All recipe entries for a given backend |
| `recipeCommands()` | 161 | Get command array for a recipe + variant (pip/docker) |

### cookbookPorts.js
| Function | Line | Purpose |
|----------|------|---------|
| `portOf()` | 6 | Extract --port value from a serve command string |
| `nextFreePort()` | 14 | Find lowest free port not in a used-ports set |

### cookbookProgressSignal.js
| Function | Line | Purpose |
|----------|------|---------|
| `computeProgressSignal()` | 23 | Compute liveness signal from byte counter or output tail |
