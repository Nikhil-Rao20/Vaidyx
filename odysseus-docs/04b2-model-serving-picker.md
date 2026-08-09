# 04b2 - Model Serving and Picker UI

Deep-dive into the model serving pipeline, running-task management, model picker
dropdown, model list rendering, sorting, provider identification, and OAuth
device-flow authentication across six frontend modules.

---

## 1. Model Serving (`cookbookServe.js` -- 4305 lines)

The Serve tab lets users configure and launch a local or remote model server
from a cached (already-downloaded) model.

### 1.1 Cached Model Scanning

Models on disk are discovered via `_fetchCachedModels()` (line 4111), which
calls `GET /api/model/cached` with optional `host`, `ssh_port`, `platform`, and
`model_dir` query params. Results are cached in `localStorage` under key
`cookbook_cached_models_scan_v3_ltx_video` with a 6-hour TTL (line 50). A
signature-based cache prevents redundant network scans; stale entries for
downloads that are no longer active are evicted automatically (lines 98-114).

### 1.2 Backend Detection and Warnings

Each model's format (AWQ/GPTQ/FP8 safetensors vs GGUF) determines which
serving backend is compatible:

- **AWQ/GPTQ/FP8** requires vLLM or SGLang on CUDA/ROCm GPUs.
- **GGUF** requires llama.cpp or Ollama.
- **MLX** for Apple Silicon unified memory.
- **Diffusers** for image generation models.

`_serveBackendWarning()` (line 196) produces user-facing error messages when
an incompatible backend is selected. `_backendChoicesForTarget()` (line 749)
returns the list of backends available for the current platform (macOS Metal
gets MLX first; Linux/CUDA gets vLLM first; Windows gets llama.cpp only).

### 1.3 Context Window Estimation

Three estimators compute how many tokens the hardware can serve:

| Function | Line | Backend | Strategy |
|---|---|---|---|
| `_estimateVllmContextFit` | 454 | vLLM/SGLang | Per-GPU VRAM budget minus model shard minus overhead; KV-cache bytes per token scaled by active param count and MoE detection |
| `_estimateLlamaContextFit` | 541 | llama.cpp | Supports CPU mode, GPU mode, and unified-memory mode; queries hardware-fit profiles first; falls back to VRAM/RAM arithmetic |
| `_estimateMlxContextFit` | 655 | MLX | Uses Apple unified memory pool; conservative KV estimate for unified architecture |

All three respect `_modelContextMaxForServe()` (line 440) which reads the
model's trained context length from metadata fields (`context_length`,
`max_position_embeddings`, `n_ctx_train`, etc.).

### 1.4 Serve Panel and Command Building

When a user clicks a cached model card, `_rerenderCachedModels()` (line 1100)
expands an inline serve panel with fields for:

- Backend selector (vLLM / SGLang / llama.cpp / Ollama / MLX / Diffusers)
- Tensor parallelism (TP), GPU IDs, GPU memory utilization
- Data type, KV cache dtype, context length
- GGUF file selector (for multi-GGUF repos)
- Model path, served model name, venv path
- LoRA/adapter module selector
- Port (auto-incremented via `_nextServeLaunchPort`, line 77)

The panel reads/writes per-model state from `localStorage` key
`cookbook-serve-state` in a `{ _byRepo: { <repo>: {...} }, _lastUsed: {...} }`
schema (lines 1394-1401).

### 1.5 Serve Favorites

Users can pin models to the top of the Serve tab list. Favorites are stored in
`localStorage` key `cookbook-serve-favorite-models` as a JSON array. Functions:
`_loadServeFavorites()` (line 129), `_saveServeFavorites()` (line 138),
`_toggleServeFavorite()` (line 171).

### 1.6 Runtime Readiness Probe

`_fetchServeRuntimePackage()` (line 816) calls
`GET /api/cookbook/packages?host=...&model_hint=...` to check whether the
selected backend (vLLM, SGLang, etc.) is installed on the target server before
launch.

### 1.7 Init

`initServe(shared)` (line 4240) receives shared state and functions from the
parent cookbook module (env state, SSH helpers, backend detectors, preset
loaders, etc.).

---

## 2. Running Models (`cookbookRunning.js` -- 4433 lines)

The Running tab tracks all active downloads and serve tasks, displaying live
status, output, and controls.

### 2.1 Task CRUD

Tasks (downloads and serves) are stored in `localStorage` key `cookbook-tasks`.

| Function | Line | Purpose |
|---|---|---|
| `_loadTasks()` | 781 | Load and normalize tasks from storage |
| `_saveTasks(tasks)` | 908 | Save tasks and trigger server sync |
| `_addTask(sessionId, name, type, payload)` | 913 | Create a new task, switch to Running tab, start background monitor |
| `_updateTask(sessionId, updates)` | 952 | Patch a task in-place |
| `_removeTask(sessionId)` | 981 | Delete a task with tombstone to prevent sync resurrection |

Tombstones (key `cookbook-removed-tasks`) prevent the server from re-merging
deleted tasks during cross-device sync. They expire after 24 hours (line 839).

### 2.2 Serve Phase Detection

`_parseServePhase(snapshot)` (line 437) is a regex-based state machine that
parses tmux output to determine the current phase of a serve task:

- `building llama.cpp N%` -- compiling from source
- `cloning llama.cpp` -- git clone in progress
- `configuring llama.cpp` -- CMake configuration
- `downloading N%` / `loading N%` -- weight loading
- `warming up` -- GPU KV cache allocation
- `initializing` -- post-load setup
- `ready` -- `Application startup complete` or HTTP access log detected
- `N tok/s` -- live throughput from vLLM/SGLang metrics

### 2.3 Launching a Serve Task

`_launchServeTask(shortName, repo, cmd, fields, hostOverride, targetMeta)`
(line 1910):

1. If replacing an existing task, graceful-kills the old one via `/api/shell/exec`.
2. Detects port conflicts with running serves on the same host.
3. Builds env activation prefix (venv or conda).
4. Runs GPU preflight check via `_confirmGpuPreflight()`.
5. POSTs to `/api/model/serve` with repo, command, host, SSH port, env prefix,
   HF token, GPU IDs.
6. Creates a task via `_addTask()` and refreshes the model picker.

### 2.4 Download Queue

Downloads run one-at-a-time per server host. `_processQueue()` (line 661)
dequeues the next `queued` download for each idle host.
`_startQueuedDownload(task)` (line 677) POSTs to `/api/model/download` and
transitions the task to `running`.

### 2.5 tmux Session Management

All serve/download processes run inside tmux sessions. Key functions:

| Function | Line | Purpose |
|---|---|---|
| `_tmuxCmd(task, args)` | 1009 | Build a tmux command (local or SSH-wrapped) |
| `_tmuxGracefulKill(task)` | 1068 | Send C-c then kill-session after 2s |
| `_tmuxForceKill(task)` | 1084 | SIGKILL pane PIDs then kill-session |
| `_tmuxIsAliveCheck(task)` | 1110 | Print ALIVE/DEAD for escalation logic |

Windows uses PowerShell equivalents via `_winSessionCmd()` (line 1020) with
PID files in `$env:TEMP\odysseus-sessions`.

### 2.6 Endpoint Auto-Registration

When a serve becomes ready, the background monitor:
1. Fetches existing endpoints via `GET /api/model-endpoints`.
2. Creates a new endpoint via `POST /api/model-endpoints` with the base URL,
   pinned model name, and container scope.
3. On stop, optionally removes the endpoint via `DELETE /api/model-endpoints/{id}`.

### 2.7 Background Monitor

`_startBackgroundMonitor()` (line 4040) polls every 10 seconds
(`BG_MONITOR_INTERVAL_MS`). It calls `/api/cookbook/tasks/status` (line 4139)
for batch status, probes individual endpoints via
`/api/model-endpoints/{id}/probe`, and runs `_selfHealStaleTasks()` (line 3969)
to detect and fix stalled downloads or orphaned serves.

### 2.8 Cross-Device State Sync

`_syncToServer()` (line 1325) debounces (400ms) and POSTs the full state
(tasks, tombstones, presets, env, serve-state, favorites) to
`POST /api/cookbook/state`. `_syncFromServer()` (line 1388) fetches via
`GET /api/cookbook/state` and merges server tasks with local tasks, respecting
tombstones.

### 2.9 Auto-Save Working Configs

`_autoSaveWorkingConfig(task)` (line 1288) saves a serve configuration as a
preset the moment its endpoint registers successfully. It deduplicates by
exact command string and caps at 5 presets per model.

### 2.10 Crash Diagnosis

`_terminalServeDiagnosis(task, outputText)` (line 224) produces structured
error messages with fix actions:
- AWQ on local backend --> "Find GGUF download" + "Edit serve"
- AWQ without accelerator --> same
- Generic failure --> `_diagnose(output)` from `cookbook-diagnosis.js`

`_buildCrashReport(task, outputText)` (line 304) generates a markdown crash
report with redacted secrets for bug filing.

### 2.11 Init

`initRunning(shared)` (line 4397) receives shared cookbook state. Also exports
`_retryDownload`, `_nextAvailablePort`, `_processQueue`, `_taskPort`
(line 4433).

---

## 3. Model Picker (`modelPicker.js` -- 958 lines)

The chatbox model-selection dropdown that lets users switch models mid-session.

### 3.1 Initialization

`initModelPicker(deps)` (line 192) receives dependency functions:
- `getCurrentSessionId()`, `getSessions()` -- session state
- `getPendingChat()`, `setPendingChat()` -- deferred model pick before first message
- `createDirectChat()` -- create a new chat session

### 3.2 Model Population

`_getAllModels()` (line 275) reads from `window.modelsModule.getCachedItems()`,
deduplicates (local by model ID, API by endpoint+model), marks stale/offline
endpoints, and returns a sorted array via `sortModelObjects()`.

### 3.3 Browse vs Search Mode

- **Browse mode** (no query): Shows Favorites section, then Recent (last 5,
  auto-tracked), then provider-grouped collapsible sections for large catalogs
  (>12 models). Small catalogs list all models flat.
- **Search mode**: Flat filtered list matching model ID, display name, endpoint
  name, or provider name.

Provider grouping uses `_PROVIDER_NAMES` (line 373, ~80 entries) and
`_PROVIDER_ALIAS` (line 403) to map model ID prefixes to display names.

### 3.4 Model Selection (`_pick`)

`_pick(m)` (line 644):
1. Pushes to Recent history (`_pushRecent`).
2. Dispatches `odysseus:model-picked` custom event.
3. If no session exists: sets pending chat or calls `createDirectChat()`.
4. If session exists: PATCHes `/api/session/{id}` with new model/endpoint.
5. Updates the picker label and shows a toast.

### 3.5 Default Model Resolution

`_ensureDefaultPendingChat()` (line 127) fetches `GET /api/default-chat` for
the admin-configured default. Falls back to the first available model if no
default is configured. Caches the result in both `window.__odysseusDefaultChat`
and `localStorage` key `odysseus-default-chat-cache`.

### 3.6 Local Endpoint Health Probe

`_refreshLocalProbe()` (line 262) calls `GET /api/model-endpoints/probe-local`
with a 5-second TTL cache. Dead local endpoints are dimmed in the picker with
a tooltip showing the error reason.

### 3.7 Picker Label Update

`updateModelPicker()` (line 855) is called after session changes, model
switches, and picker refreshes. It resolves the active model from session,
pending-chat, or cached default, and renders the provider logo + model name.

---

## 4. Model List (`models.js` -- 642 lines)

The sidebar "Models" section that shows all available models grouped by
category and endpoint.

### 4.1 Data Fetching

`refreshModels(force, opts)` (line 167) fetches `GET /api/models` (with
`?refresh=true` on forced refresh or `?background=false` otherwise). Uses a
30-second client-side cache (`_FETCH_CACHE_TTL`). Deduplicates in-flight
requests via `_fetchInflight`. Items are stored in `_cachedItems`.

### 4.2 Rendering Structure

Models are grouped by category (`local` / `api`) and endpoint name. Each
endpoint group is collapsible (state in `localStorage` key
`odysseus-models-collapsed`). Only the first 5 models per endpoint are shown;
the rest behind a "Show N more" button.

### 4.3 Favorites and Usage Tracking

- **Favorites** (`odysseus-model-favorites`): Toggle via star icon; favorited
  models appear in a dedicated top section.
- **Usage** (`odysseus-model-usage`): Tracks `count` and `last` timestamp per
  model ID. Used by sort modes.
- **Sort modes** (`odysseus-model-sort`): `alpha`, `last-used`, `most-used`,
  or default (favorited order / drag order).

### 4.4 Drag Reorder

Uses `dragSortModule` for drag-and-drop within flat lists or group containers.
Saved order stored in `localStorage` key `models-order`.

### 4.5 Search

A search input appears when there are 10+ total models. Searches across all
cached items (including hidden overflow and extra models) by model ID and
display name.

### 4.6 Provider Dropdown

`refreshProviders()` (line 600) fetches `GET /api/providers`, finds the OpenAI
provider entry, and populates a `<select>` with sorted model IDs.

---

## 5. Sorting (`modelSort.js` -- 33 lines)

Three exported functions for consistent alphabetical sorting:

| Function | Purpose |
|---|---|
| `sortModelIds(models)` | Sort an array of model ID strings; strips org prefix for comparison, uses locale-aware numeric sort |
| `compareModelObjects(a, b)` | Compare two model objects by display/name/id |
| `sortModelObjects(models)` | Sort an array of model objects |

`_sortText(value)` extracts the part after the last `/` for comparison so
`meta-llama/Llama-3.1-8B` sorts by `Llama-3.1-8B`.

---

## 6. Providers (`providers.js` -- 186 lines)

### 6.1 Logo Matching

`providerLogo(modelId)` (line 93) tests the model ID against an ordered array
of `[regex, svgString]` pairs (the `_PROVIDERS` array, lines 5-90). Supports
Ollama, OpenAI, GitHub/Copilot, OpenRouter, Anthropic/Claude, Google/Gemini,
Meta/Llama, Mistral, Qwen, DeepSeek, xAI/Grok, Cohere, Perplexity,
Nous/Hermes, Microsoft/Phi, Zhipu/GLM, MiniMax, Kimi/Moonshot, NVIDIA.

### 6.2 Endpoint Labels

`providerLabel(endpointUrl)` (line 130) maps endpoint URLs to friendly names
using the `_ENDPOINT_LABELS` array (lines 107-123). Loopback and LAN addresses
return `"Local"`. Unknown hosts return the bare hostname with `api.` stripped.

### 6.3 URL-Based Logo

`providerLogoFromUrl(url)` (line 163) tests host, port, and path against the
same `_PROVIDERS` regex catalog so loopback servers (e.g., Ollama on
`localhost:11434`) still get logos by port number.

---

## 7. Device Flow (`providerDeviceFlow.js` -- 128 lines)

### 7.1 Supported Providers

`PROVIDER_DEVICE_FLOWS` (line 3) defines two OAuth device-flow providers:

| Provider | Start URL | Poll URL |
|---|---|---|
| `copilot` (GitHub Copilot) | `/api/copilot/device/start` | `/api/copilot/device/poll` |
| `chatgpt-subscription` | `/api/chatgpt-subscription/device/start` | `/api/chatgpt-subscription/device/poll` |

### 7.2 Flow Execution

`runProviderDeviceFlow(provider, options)` (line 73):
1. POSTs to the provider's `startUrl` to get a `poll_id` and `verification_uri`.
2. Opens the auth URL in a new browser window.
3. Enters a polling loop, POSTing `poll_id` to `pollUrl` at the server-specified
   interval (minimum 2 seconds).
4. Returns `{ status: 'authorized', endpoint }` on success,
   `{ status: 'failed', error }` on denial, or `{ status: 'expired' }` on
   timeout (default 900 seconds).

Callbacks: `onStart`, `onWaiting`, `onPoll` for UI updates during the flow.

---

## 8. Model Match Key (`model/matchKey.js` -- 19 lines)

`matchModelKey(name, keys)` (line 10) returns the longest key that is a
substring of the lowercased model name. This prevents `gpt-4o-mini` from
matching the shorter `gpt-4o` key (which would apply wrong pricing/context).

---

## 9. API Endpoints Summary

| Endpoint | Method | Module | Purpose |
|---|---|---|---|
| `/api/models` | GET | models.js | List all model endpoints and their models |
| `/api/providers` | GET | models.js | List API providers (OpenAI, etc.) |
| `/api/default-chat` | GET | modelPicker.js | Admin-configured default model |
| `/api/session/{id}` | PATCH | modelPicker.js | Update session model/endpoint |
| `/api/model-endpoints/probe-local` | GET | modelPicker.js | Probe local endpoint health |
| `/api/model/cached` | GET | cookbookServe.js | Scan cached models on disk |
| `/api/cookbook/packages` | GET | cookbookServe.js | Check runtime package readiness |
| `/api/hwfit/profiles` | GET | cookbookServe.js | Hardware-fit context profiles |
| `/api/cookbook/gpus` | GET | cookbookServe.js | GPU inventory query |
| `/api/cookbook/kill-pid` | POST | cookbookServe.js | Kill a specific process by PID |
| `/api/model/serve` | POST | cookbookRunning.js | Launch a model serve in tmux |
| `/api/model/download` | POST | cookbookRunning.js | Start/retry a model download |
| `/api/shell/exec` | POST | cookbookRunning.js | Execute shell commands (tmux ops) |
| `/api/model-endpoints` | GET/POST/DELETE | cookbookRunning.js | CRUD for model endpoints |
| `/api/model-endpoints/{id}/probe` | GET | cookbookRunning.js | Probe specific endpoint |
| `/api/cookbook/state` | GET/POST | cookbookRunning.js | Cross-device state sync |
| `/api/cookbook/tasks/status` | GET | cookbookRunning.js | Batch task status poll |
| `/api/copilot/device/start` | POST | providerDeviceFlow.js | Start GitHub Copilot OAuth |
| `/api/copilot/device/poll` | POST | providerDeviceFlow.js | Poll Copilot OAuth status |
| `/api/chatgpt-subscription/device/start` | POST | providerDeviceFlow.js | Start ChatGPT OAuth |
| `/api/chatgpt-subscription/device/poll` | POST | providerDeviceFlow.js | Poll ChatGPT OAuth status |

---

## 10. User Workflow: Download to Serving

1. **Search/Download**: User finds a model in the Cookbook Search tab and clicks
   download. A task is created via `_addTask()` and queued. `_processQueue()`
   launches it via `POST /api/model/download`.

2. **Monitor Download**: The Running tab polls tmux output via
   `/api/shell/exec` with `tmux capture-pane`. `_parseServePhase()` extracts
   download percentage. The background monitor auto-retries stalled downloads
   (up to 2 times via `_DL_MAX_AUTO_RETRY`).

3. **Scan Cache**: When the download completes, `_fetchCachedModels()` re-scans
   `GET /api/model/cached` and the model appears in the Serve tab.

4. **Configure Serve**: User clicks the model card to expand the serve panel.
   Backend is auto-detected (`_detectBackend`). Context length is estimated
   based on hardware. Port is auto-incremented to avoid conflicts.

5. **Launch**: User clicks "Launch". `_buildServeCmd()` assembles the shell
   command. `_launchServeTask()` POSTs to `/api/model/serve`, creating a tmux
   session. A task card appears in the Running tab.

6. **Readiness**: The background monitor watches for `Application startup
   complete` or HTTP access logs. On ready, it auto-registers a model endpoint
   via `POST /api/model-endpoints` and auto-saves the working config as a
   preset.

7. **Chat**: The model picker refreshes via `refreshModels(force)`. The new
   endpoint appears in the picker dropdown. User selects it and starts
   chatting. The session is PATCHed with the new model via
   `PATCH /api/session/{id}`.

8. **Stop**: User clicks Stop on the Running tab card. The graceful-kill sends
   C-c to tmux, waits 2 seconds, then kills the session. If the process
   survives, force-kill escalates to SIGKILL. The endpoint is optionally
   removed via `DELETE /api/model-endpoints/{id}`.
