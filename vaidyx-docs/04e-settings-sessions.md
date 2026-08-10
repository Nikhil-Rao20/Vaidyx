# 04e -- Settings, Sessions, and App Bootstrap

Reference for the initialization pipeline, settings panel, session management,
storage layer, platform detection, and service worker.

Source files (all under `static/`):

| File | Lines | Role |
|------|-------|------|
| `js/init.js` | 421 | Early bootstrap, sidebar setup, mobile fixes |
| `app.js` | ~4615 | Main orchestrator, wires all modules |
| `js/settings.js` | 5822 | Settings modal (AI, Search, Appearance, etc.) |
| `js/sessions.js` | 3670 | Session CRUD, sidebar list, archive/library |
| `js/storage.js` | 125 | localStorage wrapper with key constants |
| `js/platform.js` | 47 | AltGr/Mac detection |
| `sw.js` | 144 | PWA service worker, caching strategies |

---

## 1. App Initialization

### init.js -- Early Bootstrap (loaded before app.js)

1. **Composer guard** (L6-33) -- Marks `window.__vaidyxComposerUserEdited` on
   first user input. Prevents the system from overwriting text the user typed
   during startup.

2. **User-switch wipe** (L43-91) -- Fetches `/api/auth/status`; if the logged-in
   user differs from the cached `vaidyx-auth-user` key, wipes all localStorage
   and sessionStorage. Defense-in-depth against cross-account data leakage.
   Also applies per-user privilege gates (hides documents, research, agent,
   memory UI elements when `privileges.can_use_*` is false).

3. **Sidebar section collapse** (L97-119) -- Reads `sidebar-collapsed` from
   Storage. Defaults `sessions-section` to collapsed. A MutationObserver on the
   sessions section clears the notification dot when expanded.

4. **CSS variable sync** (L125-182) -- Publishes `--icon-rail-w` and
   `--sidebar-w` via ResizeObserver + MutationObserver so fullscreen panels can
   reserve space. Updates on resize, class flip, and sidebar toggle.

5. **Composer clearance** (L186-214) -- Sets `--composer-clearance` CSS var so
   minimized tool chips float above the chat input bar.

6. **Resizable sidebar** (L218-353) -- Drag-to-resize with min 200px, max 700px,
   collapse threshold 150px. Persists width to `sidebar-width` Storage key. Rail
   handle expands sidebar from icon-rail state.

7. **Mobile viewport fix** (L357-397) -- Scrolls chat to bottom when virtual
   keyboard opens. Fades welcome screen on input focus (touch devices only).

8. **Welcome animation gate** (L408-421) -- Delays splash entrance animations
   until fonts are ready (+ double-rAF). Hard fallback at 1200ms.

### app.js -- Main Orchestrator

- Imports all 30+ modules and exposes key ones on `window` (themeModule,
  sessionModule, uiModule, adminModule, cookbookModule).
- **Global 401 interceptor** (L189-196) -- Wraps `window.fetch` to redirect
  to `/login` on any 401 response (except auth endpoints themselves).
- **Foreground heartbeat** (L123-154) -- Sends `POST /api/activity/heartbeat`
  every 15s (or on focus/pointer/key), using `sendBeacon` with fetch fallback.
- **Default chat cache** (L207-227) -- Fetches `/api/default-chat` at load,
  caches in localStorage as `vaidyx-default-chat-cache`.
- **Feature visibility** (L1486-1531) -- Fetches `/api/auth/features` and
  `/api/auth/settings` to hide admin-disabled features (web search, research,
  document editor, gallery, TTS).
- **Event listeners** (L268+) -- Wires chat form, file attachments, paste
  handler, message count observer, scroll/auto-scroll, export menu (copy, PDF,
  save-to-docs, compact, delete, rename), tool buttons (compare, research,
  cookbook, documents, gallery, tasks, calendar, notes), modal dismiss stack,
  session sort/tidy, and keyboard shortcut routing.
- **URL routing** (L1157-1218) -- Maps paths `/notes`, `/calendar`, `/cookbook`,
  `/email`, `/memory`, `/gallery`, `/tasks`, `/library` to tool openers.

### PWA Manifest

`app.js` registers `sw.js`. The manifest is served from `index.html` as a
standard web app manifest link.

---

## 2. Settings System

### Architecture

The settings modal (`#settings-modal`) is a draggable, dockable window with
tab navigation. Lazy-initialized on first open via `initAll()` (L2319).

**Public API:** `open(tab?)`, `close()` -- exported from `settings.js`.

### Tabs and Setting Categories

| Tab | Init Function | Line | What It Configures |
|-----|--------------|------|--------------------|
| **AI** | `initDefaultChat()` | 444 | Default chat model + endpoint + fallback chain |
| | `initUtilityModel()` | 578 | Utility/summarization model (falls back to chat) |
| | `initTeacherModel()` | 649 | SOTA escalation model for agent failures |
| | `initImageSettings()` | 744 | Image generation model + endpoint |
| | `initVisionSettings()` | 807 | Vision/multimodal model + fallback chain |
| | `initTtsSettings()` | 887 | TTS provider, voice, speed, endpoint |
| | `initSttSettings()` | 1046 | Speech-to-text model + endpoint |
| | `initResearchSettings()` | 1510 | Deep research model selection |
| | `initAgentSettings()` | 1675 | Agent loop config (max iterations, tools) |
| **Search** | `initSearchSettings()` | 1157 | Search provider, API keys, result count, fallback |
| | `initResearchSearchSettings()` | 1622 | Research-specific search provider |
| **Appearance** | `initAppearance()` | 1732 | UI element visibility toggles, privacy blur |
| **Shortcuts** | `initShortcuts()` | 1937 | Keyboard shortcut customization |
| **Account** | `initAccount()` | 2133 | Username, password change, 2FA setup, logout |
| **Reminders** | `initReminderSettings()` | 2354 | Reminder channels, public URL |
| **Email** | `initEmailSettings()` | 3124 | Email accounts configuration |
| | `initEmailAccountsSettings()` | 2822 | Email account CRUD |
| **Integrations** | `initIntegrations()` | 3309 | Legacy integration management |
| | `initUnifiedIntegrations()` | 3588 | Unified integrations: API, CalDAV, CardDAV, Email, Vault, MCP, Agent |

Admin-only tabs (`services`, `added-models`, `integrations`, `tools`, `users`,
`system`) are defined in `ADMIN_TABS` (L25) and delegate to `adminModule.open()`.

### Storage Mechanism

All user settings are persisted server-side via `POST /api/auth/settings` and
read via `GET /api/auth/settings`. Each init function reads current values on
open and saves on change. The server stores settings per-user in the database.

Client-side preferences (UI visibility, sidebar state, toggle states) use
localStorage through the Storage module.

### Settings UI Features

- **Draggable window** with dock-to-left/right support (L49-85)
- **Peek mode** on Appearance tab -- semi-transparent modal so user can see
  theme changes in real time (L146-200)
- **Model fallback chains** -- Each model category supports ordered fallback
  lists via `_bindFallbackWidget()` (L334)
- **Provider logos** synced next to endpoint/model dropdowns (L250-279)
- **Per-section reset** buttons in Appearance (L790-805)

### Default Keyboard Shortcuts (L1827-1850)

`Ctrl+K` search, `Ctrl+B` sidebar, `Ctrl+Alt+N` new session,
`Ctrl+Alt+F` favorite, `Ctrl+Alt+D` delete, `Ctrl+,` settings,
`Ctrl+/` focus input, `Ctrl+Alt+C` calendar. Others unbound by default.

---

## 3. Session Management

### Data Model

Sessions are fetched from `GET /api/sessions` into a module-level `sessions`
array. Each session object contains: `id`, `name`, `model`, `endpoint_url`,
`endpoint_id`, `folder`, `archived`, `is_important`, `has_documents`,
`has_images`, `mode` (chat/agent/research), `is_openclaw`.

### Session Lifecycle

1. **Load** -- `loadSessions()` (L1669) fetches sessions, normalizes
   (deduplicates), and auto-selects a target session via priority:
   URL hash > currentSessionId > lastSessionId > most-recent non-transient.
   Transient sessions (folder = `Assistant` or `Tasks`) are skipped.

2. **Create** -- `createDirectChat()` (L2180) stores model info as a
   `_pendingChat` object without hitting the API. The session is only
   materialized on first message send via `materializePendingSession()` (L2255),
   which POSTs to `/api/session`.

3. **Select** -- `selectSession(id)` (L1816) sets `currentSessionId`, fetches
   history via paginated `GET /api/history/{id}`, renders messages through
   `chatRenderer`, and updates the model picker. Persists to
   `lastSessionId` in Storage and the URL hash.

4. **Rename** -- Double-click in sidebar or top-bar rename button. Sends
   `PATCH /api/session/{id}` with FormData containing `name`.

5. **Delete** -- `deleteCurrentSessionFromTopMenu()` (L2400) or dropdown menu.
   Sends `DELETE /api/session/{id}`.

6. **Archive/Restore** -- `POST /api/session/{id}/archive` and
   `POST /api/session/{id}/unarchive` (or `/restore`).

7. **Folder organization** -- `moveToFolder()` (L369) PATCHes the session's
   `folder` field. Folders are derived from session data, not stored separately.

### Incognito Mode

Sessions created with incognito toggle on get IDs stored in sessionStorage
under `ody-incognito-sessions`. On page reload, `_cleanupIncognitoSessions()`
(L262) deletes all incognito sessions except the currently active one.

### Session List UI

`renderSessionList()` (L1070) builds the sidebar session list with:
- Drag handles for manual reordering
- Provider logo dots (via `providerLogo()`)
- Session type icons (chat, agent, research, fork, group, document, image)
- Favorite bookmark indicators
- Context menu (rename, archive, delete, move-to-folder, fork, copy link)
- Long-press context menu on mobile
- Sort modes: `active` (last active), `newest`, `oldest`, `group` (by folder)
- Folder groups with expand/collapse state persisted to
  `vaidyx-folder-state` / `vaidyx-folder-order`

### History Pagination

Large chat histories are loaded page-by-page. `_historyUrl()` (L123) builds
`/api/history/{id}?limit=N&offset=M`. `_installHistoryPager()` (L191) attaches
a scroll listener that loads older messages when the user scrolls near the top.
Display limits: 8 messages per page on mobile, 24 on desktop.

### Background Stream Tracking

- `markResearching(sessionId)` / `clearResearching()` -- Tracks active research
  sessions; polls `GET /api/research/status/{id}` every 3 seconds.
- `markStreaming()` / `clearStreaming()` -- Tracks background chat streams.
- `markStreamComplete()` -- Shows notification dot for completed background
  streams. Checks `GET /api/chat/stream_status/{id}`.

### Library Modal

`openLibrary(defaultTab)` (L3163) opens a tabbed modal with: active Chats,
Archive, Documents, and Research tabs. Supports bulk select, archive, restore,
and delete across all tabs.

---

## 4. Storage Module

`storage.js` wraps `localStorage` with error handling and JSON safety.

### Key Constants (KEYS object)

| Key | localStorage name | Purpose |
|-----|-------------------|---------|
| THEME | `vaidyx-theme` | Active theme name |
| TOGGLES | `vaidyx-toggles` | Tool toggle states (JSON object) |
| SIDEBAR_COLLAPSED | `sidebar-collapsed` | Per-section collapse state |
| SIDEBAR_WIDTH | `sidebar-width` | Resizable sidebar width |
| SIDEBAR_SIDE | `sidebar-side` | Left or right placement |
| CURRENT_SESSION | `currentSessionId` | Active session |
| MODEL_SELECTED | `vaidyx-selected-model` | Last selected model |
| MODEL_ENDPOINTS | `vaidyx-model-endpoints` | Cached endpoint list |
| SORT_ORDER | `vaidyx-sessions-sort` | Session sort mode |
| INCOGNITO | `vaidyx-incognito` | Incognito mode state |
| RAG_ACTIVE | `vaidyx-rag-active` | RAG toggle |
| MCP_ACTIVE | `vaidyx-mcp-active` | MCP toggle |
| DENSITY | `vaidyx-density` | UI density preference |
| UI_SCALE | `vaidyx-ui-scale` | UI scale factor |
| WORKSPACE | `vaidyx-workspace` | Active workspace |

### API

- `get(key, fallback)` / `set(key, value)` -- Raw string access
- `getJSON(key, fallback)` / `setJSON(key, value)` -- JSON parse/stringify
- `remove(key)` -- Delete key
- `getToggle(name, fallback)` / `setToggle(name, value)` -- Per-toggle
  read/write within the `vaidyx-toggles` JSON object
- `loadToggleState()` / `saveToggleState(state)` -- Bulk toggle access

---

## 5. Platform Detection

`platform.js` exports two things:

- **`IS_MAC`** (L18-20) -- Boolean. True on Mac, iPhone, iPad. Uses
  `navigator.platform` and `navigator.userAgent`. Shared by keyboard-shortcuts,
  editor shortcuts, and settings modules.

- **`isAltGrEvent(e, isMac?)`** (L40-47) -- Returns true when a keyboard event
  is an AltGr keystroke (right Alt on AZERTY/QWERTZ layouts) that should be
  ignored for shortcut purposes. AltGr is reported as Ctrl+Alt by browsers;
  this function checks `e.getModifierState('AltGraph')` to distinguish it from
  a real Ctrl+Alt combination. Always false on macOS where Option legitimately
  sets AltGraph.

---

## 6. Service Worker (sw.js)

Cache name: `vaidyx-v376-settings-title-icons` (bumped on logic/precache changes).

### Caching Strategies

| Resource Type | Strategy | Details |
|--------------|----------|---------|
| HTML navigation (`/`) | Stale-while-revalidate | Instant from cache, background refresh |
| JS/CSS (`/static/*.js\|.css`) | Network-first | Always tries network; cache fallback offline |
| Other static assets | Cache-first | Serve from cache, background refresh |
| API calls (`/api/*`) | Never cached | Always hits server |
| Non-GET requests | Never cached | Passed through |

### Precache List

64 files precached on install including all core JS modules, `style.css`,
`highlight.min.js`, and the root `/`. Uses individual `cache.put()` calls
(not `addAll`) so a single 404 does not block the entire install.

### Lifecycle

- **Install** -- Precaches shell files, calls `skipWaiting()`.
- **Activate** -- Deletes old cache versions, calls `clients.claim()`.

---

## 7. API Endpoints Called

### Authentication and User

| Endpoint | Method | Used In |
|----------|--------|---------|
| `/api/auth/status` | GET | init.js, app.js, settings.js -- user info, privileges |
| `/api/auth/settings` | GET/POST | settings.js -- all user settings CRUD |
| `/api/auth/policy` | GET | settings.js -- password policy |
| `/api/auth/change-password` | POST | settings.js -- password update |
| `/api/auth/2fa/status` | GET | settings.js -- 2FA status check |
| `/api/auth/2fa/setup` | POST | settings.js -- initiate 2FA setup |
| `/api/auth/2fa/confirm` | POST | settings.js -- verify 2FA code |
| `/api/auth/2fa/disable` | POST | settings.js -- disable 2FA |
| `/api/auth/logout` | POST | settings.js -- logout |
| `/api/auth/features` | GET | app.js -- feature flags |
| `/api/activity/heartbeat` | POST | app.js -- foreground presence |

### Sessions

| Endpoint | Method | Used In |
|----------|--------|---------|
| `/api/sessions` | GET | sessions.js -- list all sessions |
| `/api/session` | POST | sessions.js -- create session |
| `/api/session/{id}` | PATCH | sessions.js, app.js -- rename, move folder |
| `/api/session/{id}` | DELETE | sessions.js, app.js -- delete session |
| `/api/session/{id}/archive` | POST | sessions.js -- archive session |
| `/api/session/{id}/unarchive` | POST | sessions.js -- restore session |
| `/api/session/{id}/restore` | POST | sessions.js -- restore (alt) |
| `/api/session/{id}/important` | POST | sessions.js -- toggle favorite |
| `/api/sessions/archived` | GET | sessions.js -- archived session list |
| `/api/sessions/auto-sort` | POST | app.js -- AI-powered tidy |
| `/api/history/{id}` | GET | sessions.js -- paginated chat history |
| `/api/default-chat` | GET | app.js, sessions.js -- default model config |

### Models and AI

| Endpoint | Method | Used In |
|----------|--------|---------|
| `/api/model-endpoints` | GET | settings.js -- endpoint list for dropdowns |
| `/api/models` | GET | settings.js, app.js -- model list |
| `/api/ai/name` | POST | app.js -- rename AI assistant |
| `/api/tts/synthesize` | POST | settings.js -- TTS preview |
| `/api/tts/clear-cache` | POST | settings.js -- clear TTS cache |
| `/api/search/query` | POST | settings.js -- test search |
| `/api/research/status/{id}` | GET | sessions.js -- research poll |
| `/api/chat/stream_status/{id}` | GET | sessions.js -- background stream check |

### Content

| Endpoint | Method | Used In |
|----------|--------|---------|
| `/api/document` | POST | app.js -- save chat as document |
| `/api/document/{id}` | DELETE | sessions.js -- delete document |
| `/api/documents/library` | GET | sessions.js -- document library |
| `/api/research/library` | GET | sessions.js -- research library |
| `/api/research/{id}` | DELETE | sessions.js -- delete research |

---

## 8. Key Functions Reference

### settings.js

| Function | Line | Purpose |
|----------|------|---------|
| `open(tab?)` | 5742 | Show settings modal, optionally jump to tab |
| `close()` | 5765 | Hide settings modal with animation |
| `initAll()` | 2319 | Initialize all setting tabs (called once) |
| `refreshAiModelEndpoints()` | 312 | Refresh endpoint dropdowns across all AI cards |
| `initDefaultChat()` | 444 | Default model + fallback chain |
| `initTeacherModel()` | 649 | Teacher/escalation model config |
| `initSearchSettings()` | 1157 | Search provider, keys, fallback chain |
| `initAppearance()` | 1732 | UI visibility toggles |
| `initShortcuts()` | 1937 | Keyboard shortcut editor |
| `initAccount()` | 2133 | User profile, password, 2FA, logout |
| `initUnifiedIntegrations()` | 3588 | API/CalDAV/CardDAV/Email/Vault/MCP/Agent |
| `_bindFallbackWidget()` | 334 | Reusable fallback-chain builder |

### sessions.js

| Function | Line | Purpose |
|----------|------|---------|
| `loadSessions()` | 1669 | Fetch and render session list, auto-select |
| `selectSession(id, opts)` | 1816 | Navigate to a session, load history |
| `createDirectChat(url, model, ep)` | 2180 | Prepare new chat (deferred creation) |
| `materializePendingSession()` | 2255 | Actually create session in DB on first send |
| `renderSessionList()` | 1070 | Build sidebar session DOM |
| `createSessionItem(s)` | 493 | Build single session list-item element |
| `deleteCurrentSessionFromTopMenu()` | 2400 | Delete active session with confirmation |
| `moveToFolder(sid, folder)` | 369 | Move session to folder |
| `openLibrary(defaultTab)` | 3163 | Open full library modal |
| `getCurrentSessionId()` | 2358 | Return active session ID |
| `getCurrentModel()` | 2370 | Return active model name |
| `markResearching(sid)` | 2578 | Start research status polling |
| `markStreaming(sid)` | 2591 | Track background stream |
| `setSortMode(mode)` | 3619 | Change session sort order |

### init.js

| Function/Block | Line | Purpose |
|----------------|------|---------|
| `markComposerUserEdited()` | 6 | Track user edits to composer |
| User-switch IIFE | 43 | Wipe state on account change |
| Sidebar collapse setup | 97 | Restore collapsed sections |
| CSS var sync block | 125 | Publish `--icon-rail-w` / `--sidebar-w` |
| Sidebar resize block | 218 | Drag-to-resize handlers |
| Welcome animation gate | 408 | Delay splash until fonts ready |
