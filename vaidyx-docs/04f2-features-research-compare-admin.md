# Features: Research, Comparison, Admin & Utilities

Frontend feature modules in `static/js/`. ES6 modules with cross-module
registration, localStorage persistence, and SSE streaming throughout.

---

## 1. Deep Research

Three files: `research/panel.js` (1260 lines), `research/jobs.js` (383),
`researchSynapse.js` (226).

### Panel (`research/panel.js`)

Side-panel UI with settings accordion (model/endpoint selector, round count
1-20, search-engine picker, category dropdown, depth/breadth sliders) and
scrollable job list with live progress cards.

- `init()` L210, `openPanel()` L236, `closePanel()` L328
- `_buildPanelHTML()` L345 -- full DOM construction
- `_renderJobs()` L663 -- diff-based re-render of job cards
- `_buildJobCard()` L888 -- card with progress bar, cancel/retry
- `_syncResearchRail()` L106 -- rail icon badge with running count

### Job Queue (`research/jobs.js`)

Lifecycle management: queue, launch, stream, cancel, retry, clear. Jobs persist
via library sync (2-minute debounce).

- Parallel: `startAllQueued()` L172 via `Promise.all`
- Sequential: `startAllQueuedSequential()` L179 -- waits for each to finish
- SSE: `_connectStream()` L302 via `EventSource`, `_pollFallback()` L334
- Library sync: `_syncLibrary()` L89 merges completed jobs from server
- Browser `Notification` on completion (L356)
- Dismissed jobs tracked in localStorage

### Synapse Visualization (`researchSynapse.js`)

Live SVG (520x220 viewBox) driven by SSE `research_progress` events. Central
query node, sub-question branches at angular slots, source leaves in concentric
arcs. `createResearchSynapse()` L23, `setPhase()` L172, `setRound()` L185,
`setSourceCount()` L199, `complete()` L212.

---

## 2. Model Comparison

Eight files under `compare/`: `index.js` (1541), `models.js` (105),
`panes.js` (818), `probe.js` (79), `scoreboard.js` (224), `selector.js`
(1336), `state.js` (59), `stream.js` (737), `vote.js` (255).

### Orchestrator (`compare/index.js`)

Four modes: **chat**, **agent**, **search**, **research**. Up to 8 models
side-by-side. `toggleMode()` enters/exits compare mode. `_executeCompare()`
runs parallel or sequential based on settings. Export: markdown, PDF (via
`html2pdf`), browser print. Eval prompts picker for structured evaluation.

### Blind Mode & Voting (`compare/vote.js`)

Hides model names during comparison. `buildVoteBar()` L42 renders vote buttons.
`handleVote()` L144 reveals names, highlights winner, triggers confetti.
`_saveVote()` L103 persists to localStorage + `/api/compare/vote`.

### Scoreboard (`compare/scoreboard.js`)

Modal with tabs per compare mode. Aggregates win% and cost per model.

### Model Selection (`compare/selector.js`)

Modal with blind/parallel/shuffle/save toggles. Searchable picker by type tabs.
Timeout config. Pre-probe with retry/swap for unreachable models.

### Streaming (`compare/stream.js`)

SSE to individual panes: text deltas, tool blocks, images, metrics. Throttled
markdown rendering. Live timer. Auto-grade via `_stampGradeBadge()`.

### Probe & State

`probe.js`: `_checkUnprobed()` probes models via `/api/probe-selected`, skips
image-only models. `state.js`: shared mutable object (`isActive`, `_streaming`,
`_blindMode`, `_selectedModels`, `_paneSessionIds`, `_compareMode`).

---

## 3. Admin Panel

`admin.js` (3144 lines). Entry: `initAll()` L3102, `refreshAll()` L3116,
`open()` L3133.

### User Management

`loadUsers()` fetches `/api/auth/users`. Per-user: privileges (agent, browser,
bash, documents, research, images, memory), rate limits, model allowlists,
admin toggle, rename, delete. Signup enable/disable.

### Endpoint Management

**Local**: model panels with search/all/none/refresh. **API**: provider picker
with logos (OpenAI, Anthropic, Google, Mistral, Groq, xAI, DeepSeek, Cohere,
Together, OpenRouter, GitHub Copilot, ChatGPT). Device auth flows via
`PROVIDER_DEVICE_FLOWS`. `_normalizeBaseUrl()` for URL cleanup. Network
scanning via `/api/discover`. Ollama quickstart.

### MCP Server Management

16 presets: Gmail, Email (IMAP/SMTP), CalDAV, Google Calendar, Google Drive,
GitHub, Slack, Notion, Linear, Brave Search, Playwright, Filesystem, Memory,
Postgres, Todoist. Per-server tool enable/disable.

### Built-in Tools

`TOOL_META` with 30+ tools in 8 categories: Code, Search, Documents, Media,
Knowledge, Multi-Agent, Sessions, System. Per-tool and per-category toggles.

### Webhooks & API Tokens

Webhooks: CRUD with event filtering, test endpoint, signed secrets, last-status
tracking. Tokens: scoped permissions (`todos:read/write`,
`documents:read/write`, `email:read/draft/send`, `calendar:read/write`,
`memory:read/write`, `cookbook:read/launch`), revoke, rename.

### Features, CalDAV, Backup, Danger Zone, Logs

- Feature toggles: web_search, deep_research, memory, document_editor, rag,
  sensitive_filter, gallery
- CalDAV: URL/user/password with save/test
- Backup: export/import JSON
- Danger zone: per-category wipe (chats, memory, skills, notes, tasks,
  documents, gallery, calendar) with double-confirm
- Terminal logs: level/search filtering, auto-refresh, limit select

---

## 4. Skills

`skills.js` (1968 lines). SKILL.md files with YAML frontmatter.

- `loadSkills()` (default export) -- fetches `/api/skills`, renders list
- `renderSkillsList()` L624 -- library-style cards with expand/collapse
- `addSkill()`, `importSkillFromUrl()` -- create via POST
- Built-in capabilities: read-only cards with edit/revert-to-default

### Duplicate Detection & Confidence

`_duplicateMeta()` groups skills by similarity with keep/remove pills.
`_confColor()` maps confidence to color codes; `_confMax` filter.

### Audit System

- `_testSkill()` L1143 -- sandbox agent + AI evaluator (teacher model)
- `_renderTestVerdict()` -- pass/needs_work/fail/inconclusive with summary
- `_auditAllSkills()` L1425 -- batch audit with progress panel and cancel
- `_bulkDeleteNonPassing()` -- removes duplicates/trivial/irrelevant/failed

### Select Mode

`_enterSelectMode()` for bulk delete, approve, or audit operations.

---

## 5. Group Chat

`group.js` (1017 lines). Multi-model conversations, up to 8 models.

- `showModelPicker()` -- searchable overlay with character assignment step
- `startGroup()` L592 -- parent session + hidden per-model sessions with
  system prompts including group etiquette
- **Parallel** (`_sendParallel`): `Promise.allSettled`, then
  `_syncAllResponses` cross-injects
- **Round-robin** (`_sendRoundRobin`): Fisher-Yates shuffle each turn,
  sequential with cross-injection after each response
- `_streamToHolder()` -- SSE with text/tool/image events, markdown rendering
- `_saveState()`/`_restoreState()` via localStorage `GROUP_STATE_KEY`

---

## 6. RAG

`rag.js` (178 lines). Document management for retrieval-augmented generation.

- `init()` L12 -- drag-and-drop zone + file input
- `loadPersonalDocs()` L26 -- list from `/api/personal` with file size
- `uploadRagFiles()` L108 -- multipart FormData upload
- Per-document delete via `/api/personal` DELETE

---

## 7. Voice

### Recording & STT (`voiceRecorder.js`, 284 lines)

`MediaRecorder` API. Four providers: **disabled** (file attachment), **browser**
(Web Speech API), **local** (Whisper at `/api/stt/transcribe`), **endpoint**
(API STT). `startRecording()` L151, `stopRecording()` L249,
`refreshSttProvider()` L29, `startBrowserSTT()` L75,
`transcribeOnServer()` L111.

### TTS (`tts-ai.js`, 522 lines)

`AITTSManager` class. Server synthesis via `/api/tts/synthesize` with
client-side `Map` cache. Browser via `SpeechSynthesisUtterance`. Playback
speed control. Sequential audio queue. **Streaming TTS**:
`streamingUpdate()` L351 splits by sentence boundaries for low-latency
playback. `addAITTSButton()` L459 attaches speaker icon to messages.

---

## 8. Code Runner

`codeRunner.js` (404 lines). Four execution environments:

| Language | Engine | Timeout |
|----------|--------|---------|
| Python | Pyodide v0.27.5 (CDN) | 10s |
| JavaScript | Sandboxed iframe + postMessage | 10s |
| HTML | Popup window (800x600) | -- |
| Bash/Python (server) | `/api/shell/exec` base64 | -- |

`run()` L381 dispatches by language. `runPython()` L187, `runJavaScript()`
L244, `runServer()` L311, `runHTML()` L360.

---

## 9. Search

### Provider Management (`search.js`, 53 lines)

`init()` L11 fetches from `/api/auth/settings`. `getCurrentProvider()` L26.
Providers: SearXNG, Brave, DuckDuckGo, Google, Tavily, Serper.

### Command Palette (`search-chat.js`, 224 lines)

Ctrl+K shortcut (`init()` L198). Debounced query to `/api/search`, results
grouped by session with highlight. Arrow key + Enter navigation.

---

## 10. Presets

`presets.js` (1151 lines).

### Built-in Characters

| Name | Style | Temp |
|------|-------|------|
| Socrates | Socratic questioning | 0.9 |
| Razor | Minimal words | 0.4 |
| Nietzsche | Nietzschean analysis | 1.2 |
| Spark | Playful assistant | 1.0 |
| Vaidyx | Strategic counsel | 1.0 |

### User Templates & Inject Mode

CRUD via `/api/presets/templates`. Character config: name, system prompt,
temperature/max-tokens sliders. AI prompt expansion via `/api/presets/expand`.
Inject mode: prefix/suffix wrapping for tuned chats without persona.

### Persistent Chats

Favorited sessions locked to character via `vaidyx-char-sessions` localStorage.
`onSessionSwitch()` L1071 restores character from mapping.

Key: `init()` L79, `loadPresets()` L501, `saveCustomPreset()` L746,
`getCharacterName()` L929, `deactivateCharacter()` L956.

---

## 11. Widgets

### Censor (`censor.js`, 357 lines)

Pattern-based sensitive info detection: emails, API keys (`sk-`, `ghp_`,
`glpat-`, `xox*-`, `npm_`, `AKIA`), Bearer tokens, key=value credentials,
SSH/PEM keys, hex hashes (32+), JWTs, internal IPs. `_contextCensor()` finds
labels then censors adjacent values. `MutationObserver` for streaming content.
Click-to-reveal toggle. `init()` L44, `censorElement()` L334.

### Emoji Picker (`emojiPicker.js`, 314 lines)

Monochrome SVG icons in groups (Faces, Checks, Arrows, Math, Currency). U+FE0E
(VS15) for text presentation. Supports textarea and contenteditable.
`createEmojiButton()` L119, `_insertEmoji()` L273.

### Color Picker (`colorPicker.js`, 454 lines)

HSV picker with drag handles. EyeDropper API, hex input, harmony suggestions
(complement, analogous, split-complement, tone shift). Recent colors in
localStorage (max 12). `attachColorPicker()` L400, `buildPopover()` L98.

### Emoji Shortcodes (`emojiShortcodes.js`)

`:shortcode:` to Unicode conversion (GitHub/Slack style). Used by markdown
renderer before SVG pass.

---

## 12. Key Functions Reference

| File | Function | Line | Purpose |
|------|----------|------|---------|
| research/panel.js | `init()` | 210 | Initialize research panel |
| research/panel.js | `_buildPanelHTML()` | 345 | Build panel DOM |
| research/panel.js | `_renderJobs()` | 663 | Re-render job list |
| research/jobs.js | `_launchJob()` | 272 | POST to /api/research/start |
| research/jobs.js | `_connectStream()` | 302 | SSE EventSource connection |
| researchSynapse.js | `createResearchSynapse()` | 23 | Build SVG visualization |
| compare/vote.js | `handleVote()` | 144 | Process vote, reveal names |
| compare/stream.js | `_stampGradeBadge()` | -- | Auto-grade eval responses |
| admin.js | `initAll()` | 3102 | Initialize all admin sections |
| admin.js | `open()` | 3133 | Open admin panel |
| skills.js | `renderSkillsList()` | 624 | Library-style skill cards |
| skills.js | `_testSkill()` | 1143 | Sandbox audit single skill |
| skills.js | `_auditAllSkills()` | 1425 | Batch audit with progress |
| group.js | `startGroup()` | 592 | Create multi-model session |
| group.js | `sendMessage()` | 708 | Dispatch to all models |
| voiceRecorder.js | `startRecording()` | 151 | Begin audio capture |
| tts-ai.js | `streamingUpdate()` | 351 | Sentence-level streaming TTS |
| codeRunner.js | `run()` | 381 | Language dispatcher |
| censor.js | `init()` | 44 | Initialize censor system |
| presets.js | `onSessionSwitch()` | 1071 | Restore character on switch |
| colorPicker.js | `attachColorPicker()` | 400 | Wrap native color input |
