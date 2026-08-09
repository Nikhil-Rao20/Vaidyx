# Odysseus Codebase Documentation — Master Index

> **Generated**: August 2026 · **Source**: Every file in the repository was read and analyzed by code  
> **Total**: 29 documents · 14,000+ lines of documentation · Covers 1,302 source files

This documentation set was created by exhaustive source-code reading — not from existing docs.
It serves as the knowledge base for understanding and modifying the Odysseus platform.

---

## How to Use This Index

| If you want to…                            | Start here                                                          |
|--------------------------------------------|---------------------------------------------------------------------|
| Understand the overall architecture        | [01 — Core Architecture](#01--core-architecture)                    |
| Find a specific API endpoint               | [02 — API Routes](#02--api-routes)                                  |
| Understand a backend service               | [03 — Backend Services](#03--backend-services)                      |
| Work on the frontend UI                    | [04 — Frontend UI](#04--frontend-ui-overview) and sub-docs          |
| Modify the AI/agent system                 | [05 — AI Agent System](#05--ai-agent-system)                        |
| Work with MCP servers                      | [06 — MCP Servers](#06--mcp-servers)                                |
| Add integrations or companion features     | [07 — Integrations & Companion](#07--integrations--companion)       |
| Deploy or package the app                  | [08 — Deployment & Infrastructure](#08--deployment--infrastructure)  |
| Modify native Swift/MLX code               | [09 — Swift Native](#09--swift-native)                              |
| Run or write tests                         | [10 — Tests, Scripts & Specs](#10--tests-scripts--specs)            |

---

## 01 — Core Architecture
**File**: [01-core-architecture.md](01-core-architecture.md)

App entry point (`app.py`, 1282 lines), launcher, setup. All `core/` modules: database layer
(24 SQLAlchemy models, FTS5 search, 35+ migrations), auth system (bcrypt, sessions, TOTP 2FA,
11 privilege keys), middleware (CSP with nonces, CORS, GZip), platform compatibility utilities.

---

## 02 — API Routes
**File**: [02-api-routes.md](02-api-routes.md)

Master table of all **140+ endpoints** with HTTP method, URL, handler function, line numbers,
parameters, and auth requirements. Covers 14 route modules: admin_wipe, cleanup, compare,
contacts, document (23 endpoints), gallery (33 endpoints), history, memory, note, research
(15 endpoints), search, vault, webhook.

---

## 03 — Backend Services
**File**: [03-backend-services.md](03-backend-services.md)

All **11 services**: DocsService/RAG with ChromaDB, face recognition (stub), hardware fitness
(GPU detection, bandwidth tables, model scoring), memory service (LLM extraction, skills system),
research (8-round deep researcher), search (6 providers with SSRF protection), shell (async
subprocess), STT (faster-whisper), TTS (Kokoro-82M), YouTube.

---

## 04 — Frontend UI (Overview)
**File**: [04-frontend-ui.md](04-frontend-ui.md)

High-level map of the **115,000+ line** frontend. Vanilla JavaScript ES modules (no framework),
module loading patterns, state management architecture. All 120+ JS files mapped with line
ranges and responsibilities. Gateway to the 13 detailed sub-documents below.

### 04a — Chat & Streaming System
**File**: [04a-chat-streaming-system.md](04a-chat-streaming-system.md)

`chat.js` (6,007 lines), `chatRenderer.js` (2,811 lines). Message flow: `handleChatSubmit`
10-step pipeline, SSE streaming with 16+ event types, 30+ chat API endpoints, message
rendering, tool call display.

### 04a2 — Slash Commands & Markdown
**File**: [04a2-slash-commands-markdown.md](04a2-slash-commands-markdown.md)

`slashCommands.js` (6,520 lines): all commands by group (13 chat, 5 toggle, 4 memory, 3 RAG,
24 flat, 11 tours, 11 easter eggs), autocomplete scoring algorithm, markdown rendering
(18-step pipeline with XSS defense).

### 04b — Model Management UI (Cookbook)
**File**: [04b-model-management-ui.md](04b-model-management-ui.md)

Model browsing with filters, download flow with SSE progress, hardware fitness display,
diagnosis (40+ error patterns), scheduling with CalDAV, dependency recipes.

### 04b2 — Model Serving & Picker
**File**: [04b2-model-serving-picker.md](04b2-model-serving-picker.md)

`cookbookServe.js` (4,305 lines), `cookbookRunning.js` (4,433 lines). Serve phase detection
via regex state machine, model picker with 80+ provider groups, device flow OAuth, 21 API
endpoints.

### 04c — Image Editor Core
**File**: [04c-image-editor-core.md](04c-image-editor-core.md)

Editor state (60+ properties in 15 slices), canvas coordinate system, layer system with
drag-sort, history/undo panel, keyboard shortcuts, clipboard/import.

### 04c2 — Image Editor Tools
**File**: [04c2-image-editor-tools.md](04c2-image-editor-tools.md)

All editor tools: stroke pipeline, clone, lasso, magic wand, flood fill, move, crop,
transform (drag/handles/session), blur filters (Gaussian/zoom/motion), edge feather,
adjustment popup, histogram, pixel pass engine, mask utilities.

### 04c3 — Image Editor AI Wire
**File**: [04c3-image-editor-ai-wire.md](04c3-image-editor-ai-wire.md)

AI inpainting (`runInpaint` with mask dilation), background removal (edge-cleanup tuner),
AI model dropdown, `applyImageTool` factory, harmonize/upscale/style transfer, 6 build
modules, 7 wire modules, `galleryEditor.js` integration (4,386 lines).

### 04d — Document System
**File**: [04d-document-system.md](04d-document-system.md)

`document.js` (11,200 lines): 30+ subsystems, 8 editing modes, auto-save, PDF
forms/annotations, version history, streaming, document library with 4 tabs.

### 04d2 — Email System
**File**: [04d2-email-system.md](04d2-email-system.md)

`emailLibrary.js` (8,504 lines): multi-account IMAP, SWR caching, body rendering pipeline,
inbox with swipe-to-archive, reply recipients, 7-strategy signature folding, canvas
drawing-pad signatures, 35+ API endpoints.

### 04e — Settings & Sessions
**File**: [04e-settings-sessions.md](04e-settings-sessions.md)

`settings.js` (5,822 lines): 18 setting categories across 6 tabs, session management with
deferred materialization, service worker (3-tier caching), storage wrapper with 18 key constants.

### 04e2 — UI Layout & Windowing
**File**: [04e2-ui-layout-windowing.md](04e2-ui-layout-windowing.md)

Sidebar (3-state), modal manager with dock chips, 16 built-in themes + custom themes,
window drag/resize/tile, workspace browser, keyboard shortcuts, accessibility (ARIA),
tour system.

### 04f — Gallery, Notes & Calendar
**File**: [04f-features-gallery-notes-calendar.md](04f-features-gallery-notes-calendar.md)

Gallery (albums, AI auto-tagging, concurrent upload), notes (Keep-style with reminders),
calendar (4 views, CalDAV sync, NLP quick-add), tasks (3 types, 17+ built-in actions),
memory (7 categories, tidy/audit).

### 04f2 — Research, Compare & Admin
**File**: [04f2-features-research-compare-admin.md](04f2-features-research-compare-admin.md)

Deep research panel (SSE + polling, synapse SVG), model comparison (4 modes, blind voting),
admin panel (users, endpoints, MCP presets, tools, webhooks, API tokens), skills system,
group chat, RAG, voice I/O, code runner, search, presets, widgets (censor, emoji, color picker).

### 04g — HTML Structure
**File**: [04g-html-structure.md](04g-html-structure.md)

`index.html` structure, template elements, modal hierarchy, accessibility attributes,
meta tags, asset loading order.

### 04g2 — CSS Architecture
**File**: [04g2-css-architecture.md](04g2-css-architecture.md)

41,132-line stylesheet: CSS custom properties theming system, responsive breakpoints,
animation library, component styling patterns, dark/light mode handling.

---

## 05 — AI Agent System
**File**: [05-ai-agent-system.md](05-ai-agent-system.md)

Core agent loop architecture, conversation flow (12 steps), tool registration and execution
pipeline, SSE streaming protocol.

### 05 — AI Agent Tools
**File**: [05-ai-agent-tools.md](05-ai-agent-tools.md)

12 tool categories: subprocess, filesystem, document, web, interaction, session, model,
coding, background jobs, admin, domain, AI tools. Complete tool registry with parameters.

### 05b — Model Capabilities & Search
**File**: [05b-model-capabilities-search.md](05b-model-capabilities-search.md)

7 model capability readers (OpenAI, OpenRouter, Google, Ollama, LM Studio, llama.cpp, generic),
6 search providers, MCP manager (3 transports, 5 built-in servers), constants.

---

## 06 — MCP Servers
**File**: [06-mcp-servers.md](06-mcp-servers.md)

4 Python + 1 NPX browser MCP servers exposing 19 tools total. `email_server.py` (2,921 lines,
15 tools), `memory_server.py` (1 multi-action tool), `rag_server.py` (1 tool),
`image_gen_server.py` (1 tool). Integration via `builtin_mcp.py` and `mcp_manager.py`.

---

## 07 — Integrations & Companion
**File**: [07-integrations-companion.md](07-integrations-companion.md)

Claude integration (skill bundle, 19-command CLI helper), Codex integration (marketplace
registration), 28 server-side routes, companion mobile app system (QR pairing, LAN discovery,
28 endpoints).

---

## 08 — Deployment & Infrastructure
**File**: [08-deployment-infrastructure.md](08-deployment-infrastructure.md)

Dockerfile (2-stage), 4 compose files, GPU support (NVIDIA/AMD/Metal), macOS app bundle + DMG,
Windows portable + launcher, Linux systemd, 50+ environment variables, install/update scripts.

---

## 09 — Swift Native
**File**: [09-swift-native.md](09-swift-native.md)

`Package.swift` (swift-tools-version 6.2), `OdysseusMLXColorize` (DDColor, float16 Metal),
`OdysseusMLXInpaint` (LaMa/MI-GAN), Python integration via subprocess.

---

## 10 — Tests, Scripts & Specs
**File**: [10-tests-scripts-specs.md](10-tests-scripts-specs.md)

Test framework (`conftest`, taxonomy, focused runner), 28 CLI test files, streaming JS tests,
20+ `odysseus-*` CLI scripts, shell completion, demo email scripts, 12 standalone utilities.

---

## Quick Stats

| Metric                     | Value          |
|----------------------------|----------------|
| Total source files         | 1,302          |
| Python backend (app.py)    | 1,282 lines    |
| Frontend JavaScript        | 115,000+ lines |
| CSS stylesheet             | 41,132 lines   |
| Database models            | 24             |
| API endpoints              | 140+           |
| Backend services           | 11             |
| MCP tools                  | 19             |
| AI agent tool categories   | 12             |
| Documentation files        | 29             |
| Documentation lines        | 14,000+        |
