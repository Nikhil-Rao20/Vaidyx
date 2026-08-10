# Vaidyx Frontend & UI Documentation

## Table of Contents

1. [UI Architecture](#1-ui-architecture)
2. [Main Application UI](#2-main-application-ui)
3. [Calendar Module](#3-calendar-module)
4. [Color Module](#4-color-module)
5. [Compare Module](#5-compare-module)
6. [Image Editor](#6-image-editor)
7. [Email Library](#7-email-library)
8. [Markdown Module](#8-markdown-module)
9. [Model Management UI](#9-model-management-ui)
10. [Research UI](#10-research-ui)
11. [Utility Functions](#11-utility-functions)
12. [Styling](#12-styling)
13. [Font System](#13-font-system)
14. [User Workflow](#14-user-workflow)
15. [UX Patterns](#15-ux-patterns)

---

## 1. UI Architecture

### Framework Approach

Vaidyx uses **vanilla JavaScript ES modules** -- no React, Vue, or Angular. The frontend is a single-page application (SPA) built with:

- **ES Module imports** (`import`/`export`) for code organization
- **Direct DOM manipulation** via `document.createElement`, `innerHTML`, and `querySelector`
- **Custom event system** via `CustomEvent` and `dispatchEvent`
- **Module pattern** where each feature exports a default object or named functions
- **No virtual DOM** -- all UI updates manipulate the real DOM directly

### File Structure

```
static/
  index.html          -- Main SPA entry point (2,539 lines)
  login.html          -- Authentication page
  app.js              -- Application orchestrator (4,614 lines)
  style.css           -- Monolithic stylesheet (41,132 lines)
  sw.js               -- Service worker for PWA/offline
  manifest.json       -- PWA manifest
  fonts/              -- Web fonts (Inter, FiraCode, OpenDyslexic, GohuFont)
  icons/              -- PWA icons + provider logos
  lib/                -- Third-party libraries (highlight.js, xlsx, mammoth, etc.)
  js/
    init.js            -- Bootstrap/initialization
    chat.js            -- Core chat logic
    chatRenderer.js    -- Message rendering
    chatStream.js      -- SSE streaming handler
    streamingRenderer.js -- Live streaming render pipeline
    streamingSegmenter.js -- Streaming text segmentation
    ui.js              -- Shared UI utilities (toast, confirm, escape)
    sessions.js        -- Session/conversation management
    settings.js        -- Settings panel
    theme.js           -- Theme engine (dark/light/custom)
    storage.js         -- localStorage abstraction
    platform.js        -- Platform detection (Electron, PWA, mobile)
    workspace.js       -- Workspace management
    sidebar-layout.js  -- Sidebar layout logic
    a11y.js            -- Accessibility utilities
    spinner.js         -- Loading spinners (wave, whirlpool, ASCII)
    modalManager.js    -- Unified modal lifecycle manager
    modalSnap.js       -- Modal edge-docking/snapping
    tileManager.js     -- Window tiling system
    toolWindowZOrder.js -- Z-index stacking for tool windows
    escMenuStack.js    -- ESC key menu dismissal stack
    windowDrag.js      -- Draggable window behavior
    windowResize.js    -- Window resize handles
    dragSort.js        -- Drag-and-drop list reordering
    keyboard-shortcuts.js -- Global keyboard shortcuts
    calendar.js        -- Calendar module (3,723 lines)
    calendar/
      reminders.js     -- Calendar reminders
      utils.js         -- Calendar date/color utilities
    color/
      hex.js           -- Hex color utilities
    colorPicker.js     -- HSV color picker popover
    compare/           -- Model A/B comparison module
      index.js         -- Orchestrator (1,541 lines)
      state.js         -- Shared mutable state
      models.js        -- Model fetching/classification
      panes.js         -- Pane lifecycle/actions
      stream.js        -- SSE streaming to compare panes (737 lines)
      vote.js          -- Voting, revealing, confetti
      scoreboard.js    -- Vote history display
      selector.js      -- Model selection modal
      probe.js         -- Model probe/check system
      icons.js         -- SVG icons + eval prompts
    editor/            -- Full image editor
      state.js         -- Editor state store
      canvas-coords.js -- Canvas coordinate transforms
      canvas-events.js -- Canvas mouse/touch events
      canvas-transforms.js -- Canvas zoom/pan/rotate
      checkerboard.js  -- Transparency checkerboard
      clipboard-and-drop.js -- Paste/drop image import
      composite-helpers.js -- Layer compositing
      harmonize-masks.js -- Mask harmonization
      history-panel.js -- Undo/redo history panel
      keyboard-shortcuts.js -- Editor keyboard shortcuts
      layer-helpers.js -- Layer manipulation utilities
      layer-panel.js   -- Layer panel UI
      mask-utils.js    -- Selection mask utilities
      shortcuts-popover.js -- Keyboard shortcut help
      slider-ux.js     -- Slider interaction behavior
      snap.js          -- Layer snap guides
      stroke-pipeline.js -- Brush stroke rendering
      stroke-tool-sliders.js -- Brush tool slider UI
      ai-inpaint.js    -- AI inpainting integration
      ai-models.js     -- AI model selection for editor
      ai-rembg.js      -- AI background removal
      ai-tool-runner.js -- AI tool execution pipeline
      ai-tools-misc.js -- Miscellaneous AI tools
      filters/
        blur.js        -- Gaussian blur filter
        edge-feather.js -- Edge feather/smooth filter
      fx/
        adj-popup.js   -- Adjustment popup (brightness, contrast)
        filter-string.js -- CSS filter string builder
        histogram.js   -- Image histogram
        pixel-pass.js  -- Pixel-level operations
      tools/
        clone.js       -- Clone stamp tool
        crop.js        -- Crop tool
        flood-fill.js  -- Paint bucket / flood fill
        lasso.js       -- Lasso selection tool
        lasso-mask.js  -- Lasso to mask conversion
        move.js        -- Move tool
        stroke.js      -- Brush/eraser stroke handler
        transform-drag.js -- Transform drag interactions
        transform-handles.js -- Transform handle rendering
        transform-session.js -- Transform session lifecycle
        wand.js        -- Magic wand selection tool
      build/
        controls.js    -- Control panel builder
        popups.js      -- Editor popup builder
        right-panel.js -- Right-side panel (layers, history)
        toolbar.js     -- Toolbar builder
        topbar.js      -- Top menu bar builder
        transform-popup.js -- Transform popup builder
      wire-import.js     -- Image import wiring
      wire-inpaint-controls.js -- Inpaint UI wiring
      wire-merge-buttons.js -- Layer merge button wiring
      wire-selection-controls.js -- Selection control wiring
      wire-topbar.js     -- Top bar event wiring
      wire-topbar-menus.js -- Menu dropdown wiring
      wire-topbar-overflow.js -- Overflow menu wiring
    emailLibrary.js    -- Email library modal
    emailLibrary/
      replyRecipients.js -- Reply recipient handling
      signatureFold.js -- Signature collapsing
      state.js         -- Email library state
      utils.js         -- Email utility functions
    emailInbox.js      -- Email inbox integration
    emailShared.js     -- Shared email utilities
    markdown.js        -- Markdown renderer
    markdown/
      tableRow.js      -- Table row parser
    model/
      matchKey.js      -- Model match key utility
    models.js          -- Model/provider management
    modelPicker.js     -- Inline model picker dropdown
    modelSort.js       -- Model sorting algorithm
    research/
      jobs.js          -- Research job queue manager
      panel.js         -- Research panel UI (1,260 lines)
    researchSynapse.js -- Research SVG visualization
    [... additional modules listed below]
```

### Module Loading Pattern

All JavaScript is loaded as ES modules via `<script type="module">`. The main entry point is `static/app.js`, which:

1. Imports all major modules
2. Calls each module's `init(apiBase)` function
3. Wires global event listeners (submit, keyboard shortcuts, theme)
4. Sets up the service worker registration

**Key pattern** (`app.js`): Modules register themselves on `window` for cross-module access:
```javascript
window.compareModule = compareModule;
window.chatModule = chatModule;
window.documentModule = documentModule;
```

### State Management

There is no centralized state store. Each module manages its own state:

- **Module-scope `let` variables** -- most common pattern (e.g., `let _open = false` in calendar.js)
- **Exported state objects** -- used by compare module (`compare/state.js` exports a mutable object)
- **`Storage` wrapper** -- abstraction over `localStorage` for persistence (`storage.js`)
- **DOM as state** -- many UI states are read directly from DOM elements (checked, classList, style)

### API Communication

All API calls use the `fetch` API with these patterns:

- **Base URL**: `window.location.origin` or passed as `apiBase` parameter
- **SSE Streaming**: `EventSource` for research jobs; manual `ReadableStream` reader for chat
- **Form data**: Many endpoints use `FormData` (session creation, file upload)
- **JSON body**: Used for structured payloads (`Content-Type: application/json`)
- **Credentials**: `credentials: 'same-origin'` or `credentials: 'include'`

### Third-Party Libraries

Located in `static/lib/`:

| Library | File | Purpose |
|---------|------|---------|
| highlight.js | `highlight.min.js` | Code syntax highlighting |
| xlsx | `xlsx.full.min.js` | Excel file reading/writing |
| mammoth | `mammoth.browser.min.js` | Word document conversion |
| docx | `docx.umd.min.js` | Word document generation |
| html2pdf | `html2pdf.bundle.min.js` | HTML to PDF export |
| qrcode | `qrcode.min.js` | QR code generation |

---

## 2. Main Application UI

### HTML Structure (`index.html`)

The main page is a single HTML file with this key DOM structure:

```
<body>
  <div id="icon-rail">           -- Vertical icon rail (left edge)
  <div id="sidebar">             -- Collapsible sidebar (session list, tools)
  <div id="chat-container">      -- Main content area
    <div class="chat-history">   -- Message display area
    <div class="chat-input-bar"> -- Input area
      <div class="chat-input-top"> -- Model picker, toggles
      <textarea id="message">   -- User input
      <div class="input-bar-tools"> -- Tool buttons
  </div>
</body>
```

### Application Bootstrap (`app.js`)

The app initializes in this sequence:

1. **Module imports** -- all JS modules imported at top
2. **`DOMContentLoaded`** -- triggers initialization
3. **`init()` calls** -- each module's init function called with API base URL
4. **Event wiring** -- form submit, keyboard shortcuts, mode toggles
5. **Session loading** -- loads the last active session or creates a new one
6. **Theme application** -- applies saved theme preferences
7. **Service worker** -- registers `sw.js` for PWA support

### Chat System

The chat system spans several files:

**`chat.js`** -- Core chat logic:
- `handleChatSubmit()` -- Main submit handler; routes to compare, research, or standard chat
- Manages the message lifecycle: user input -> API call -> response rendering
- Handles file attachments, voice input, image generation
- Supports agent mode (with tool use: bash, web search, etc.)

**`chatStream.js`** -- SSE streaming:
- Connects to `/api/chat_stream` via POST with `FormData`
- Reads the response as a `ReadableStream` with `getReader()`
- Parses SSE `data:` lines for deltas, tool events, metrics, research progress
- Handles `[DONE]` sentinel for stream completion

**`chatRenderer.js`** -- Message rendering:
- `renderMessage()` -- Renders a single message bubble (user or AI)
- `safeDisplayImageSrc()` -- Sanitizes image URLs for display
- `getModelCost()` -- Calculates per-request cost estimates
- `modelColor()` -- Returns a consistent color per model name
- Renders tool-use blocks (bash output, web search results, file operations)
- Handles image display with lightbox capability

**`streamingRenderer.js`** -- Live streaming rendering:
- Throttled markdown rendering (every ~80ms) to avoid O(n^2) on growing buffers
- Manages thinking/reasoning block folding during streaming
- Auto-scrolls to bottom as content arrives

**`streamingSegmenter.js`** -- Text segmentation:
- Segments streaming text into renderable chunks
- Handles code block boundaries, think tags, and markdown structures

### Session Management (`sessions.js`)

- `loadSessions()` -- Fetches session list from `/api/sessions`
- `selectSession(id)` -- Loads a session's messages via `/api/session/{id}/messages`
- `createDirectChat(url, model, endpointId)` -- Creates a new session with a specific model
- `deleteSession(id)` -- Deletes via `DELETE /api/session/{id}`
- Renders the sidebar session list with folders, search, and drag reordering
- Supports session pinning, renaming, and folder organization

### Sidebar Layout (`sidebar-layout.js`)

- Manages sidebar open/close state
- Handles responsive behavior (mobile: overlay; desktop: push)
- Icon rail integration (collapsed sidebar shows icon-only rail)
- Swipe gestures for mobile sidebar open/close

### Input Bar Features

The chat input bar includes:

- **Model picker** (`modelPicker.js`) -- dropdown to switch active model inline
- **Mode toggle** -- Switch between Chat and Agent modes
- **Tool toggles** -- Web search, bash/code, RAG, research
- **File attachment** -- Upload files via drag-drop or button
- **Voice recorder** (`voiceRecorder.js`) -- Whisper-based speech-to-text
- **TTS** (`tts-ai.js`) -- AI text-to-speech for responses
- **Emoji picker** (`emojiPicker.js`) -- Emoji insertion with shortcode support
- **Slash commands** (`slashCommands.js`, `slashAutocomplete.js`) -- `/command` autocomplete
- **Arrow-up recall** (`composerArrowUpRecall.js`) -- Edit last message with arrow-up

---

## 3. Calendar Module

**Files**: `calendar.js` (3,723 lines), `calendar/reminders.js`, `calendar/utils.js`

### Architecture

The calendar is a full CalDAV-backed calendar application rendered as a modal. It supports:

- **Four views**: Month, Week, Year, and Agenda
- **CalDAV sync** via `/api/calendar/sync` (POST)
- **CRUD operations** on events via `/api/calendar/events` endpoints
- **Optimistic updates** -- UI updates immediately, rolls back on server error
- **Local caching** -- events cached in `_allEvents` object, with range tracking in `_fetchedRanges`
- **Background prefetching** -- adjacent months/years fetched asynchronously via `_prefetchAdjacent()`

### Key Functions

| Function | Line | Description |
|----------|------|-------------|
| `_fetchEvents(start, end, force)` | ~116 | Fetches events from API with local cache check |
| `_createEvent(data)` | ~252 | Creates event with optimistic UI update |
| `_updateEvent(uid, data)` | ~276 | Updates event with merge and rollback on failure |
| `_deleteEvent(uid, {scope})` | ~304 | Deletes with sibling UID handling for recurring events |
| `_renderMonth()` | ~1007 | Renders month grid with multi-day overlay bars |
| `_renderWeek()` | ~1256 | Renders hour-grid week view with positioned event blocks |
| `_renderYear()` | (later) | Renders year overview with heat dots |
| `_renderAgenda()` | (later) | Renders upcoming events list |
| `_showEventForm(ev)` | (later) | Opens event creation/edit modal |

### API Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/calendar/events?start=&end=` | Fetch events in date range |
| POST | `/api/calendar/events` | Create new event |
| PUT | `/api/calendar/events/{uid}` | Update event |
| DELETE | `/api/calendar/events/{uid}` | Delete event |
| GET | `/api/calendar/calendars` | List calendars |
| POST | `/api/calendar/sync` | Trigger CalDAV sync |

### Features

- **Quick-add input** -- Natural language event creation (e.g., "dinner with Penelope Friday 8pm")
- **Drag-and-drop** -- Events can be dragged between days in month view
- **Multi-day bars** -- Events spanning multiple days render as continuous bars across the week row
- **Event types/tags** -- Events classified as work, personal, health, travel, etc.
- **Importance filtering** -- "Only important" mode shows high/critical events only
- **Calendar filters** -- Toggle visibility of individual calendars and event types
- **Color picker** -- Custom colors per event, including background images
- **Reminders** -- Creates reminder notes via `/api/notes` endpoint
- **Recurring events** -- Full recurring event support with series/occurrence delete scope
- **Week view zoom** -- Adjustable hour height (28-120px) with pinch-to-zoom
- **Now-line indicator** -- Red line showing current time in week view
- **Undo stack** -- Cmd/Ctrl+Z to undo recent event operations

---

## 4. Color Module

**Files**: `colorPicker.js`, `color/hex.js`

### Color Picker (`colorPicker.js`)

A custom HSV color picker popover that wraps `<input type="color">` elements:

**Color math functions**:
- `hexToRgb(hex)` / `rgbToHex(r, g, b)` -- Hex/RGB conversion
- `rgbToHsv(r, g, b)` / `hsvToRgb(h, s, v)` -- RGB/HSV conversion
- `hsvToHex(h, s, v)` / `hexToHsv(hex)` -- Direct HSV/Hex conversion

**UI Components**:
- **SV square** -- 2D saturation/value picker with hue-tinted background
- **Hue bar** -- Horizontal hue slider (0-360 degrees)
- **Hex input** -- Direct hex code entry with validation
- **Recent colors** -- Last 12 used colors stored in localStorage (`vaidyx-recent-colors`)
- **Harmony suggestions** -- 5 computed swatches: complement, analogous +/-30 degrees, split-complement, tone shift
- **Eyedropper** -- Native EyeDropper API integration (where supported)

**Interaction**:
- Drag on SV square updates saturation and value
- Drag on hue bar updates hue
- All changes dispatch `input` events on the original `<input type="color">`
- Popover positioned relative to anchor element, clamped to viewport

### Hex Utilities (`color/hex.js`)

Lightweight hex color manipulation helpers used by the editor and theme system.

---

## 5. Compare Module

**Files**: `compare/index.js` (1,541 lines), `compare/state.js`, `compare/models.js`, `compare/panes.js`, `compare/stream.js`, `compare/vote.js`, `compare/scoreboard.js`, `compare/selector.js`, `compare/probe.js`, `compare/icons.js`

### Architecture

The compare module is a sophisticated A/B testing system for AI models, supporting up to 8 simultaneous models. It uses a submodule architecture to avoid circular dependencies:

```
index.js (orchestrator)
  -> state.js (shared mutable state object)
  -> models.js (model fetching/classification)
  -> selector.js (model selection modal)
  -> panes.js (pane lifecycle)
  -> stream.js (SSE streaming)
  -> vote.js (voting/confetti)
  -> scoreboard.js (vote history)
  -> probe.js (model verification)
  -> icons.js (SVG icons + eval prompts)
```

Cross-module function sharing uses a **registration pattern** to avoid circular imports:
```javascript
// In panes.js
function registerPaneActions({ setSendBtn, deactivate, streamToPane, ... }) { ... }

// In index.js
registerPaneActions({ setSendBtn: _setSendBtn, deactivate, streamToPane, ... });
```

### State (`compare/state.js`)

Single exported mutable object with all compare state:

| Field | Type | Description |
|-------|------|-------------|
| `isActive` | boolean | Compare mode is active |
| `_streaming` | boolean | Currently streaming responses |
| `_blindMode` | boolean | Model names hidden until vote |
| `_parallel` | boolean | Run all panes simultaneously vs sequentially |
| `_selectedModels` | array | `[{model, endpoint, endpointId, name}, ...]` |
| `_paneSessionIds` | array | Session IDs for each pane |
| `_paneMetrics` | array | Response metrics per pane |
| `_abortControllers` | array | Per-pane AbortControllers for cancellation |
| `_compareMode` | string | `'chat'`, `'agent'`, `'search'`, or `'research'` |
| `_expectedAnswer` | string | Expected answer for eval prompt grading |
| `_timeout` | number | Seconds before timing out a pane (default 300) |

### Compare Modes

1. **Chat** -- Pure LLM comparison, no tools
2. **Agent** -- Full agent mode with web search, bash, etc.
3. **Search** -- Search provider comparison (DuckDuckGo, Brave, Google, etc.)
4. **Research** -- Deep research model comparison

### Key Functions (`compare/index.js`)

| Function | Line | Description |
|----------|------|-------------|
| `init(apiBase)` | 55 | Initialize with API base, set up beforeunload cleanup |
| `toggleMode()` | 130 | Show model selector, build UI on confirm |
| `deactivate(teardown)` | 158 | Close compare, abort streams, clean up sessions |
| `_buildCompareUI()` | 232 | Build header bar, grid, vote bar, eval picker |
| `handleCompareSubmit(e)` | 577 | Handle submit from main chat input during compare |
| `_executeCompare(message)` | 638 | Send prompt to all panes, stream responses |
| `_buildComparisonMarkdown()` | 1030 | Export comparison as markdown |

### Pane System (`compare/panes.js`)

Each model gets its own pane with:
- **Header**: Model name (or blind label), timer, finish badge, action buttons
- **Chat history**: Message display area with user/AI bubbles
- **Preview iframe**: Sandboxed HTML preview for code responses
- **Vote footer**: Per-pane vote button

**Pane actions**: stop, reroll, expand/collapse, copy, preview toggle, close, model swap

### Streaming (`compare/stream.js`)

The `streamToPane()` function (line 147) handles SSE streaming with:
- **Live timer** via `requestAnimationFrame` loop
- **Throttled markdown render** (every ~80ms) to prevent O(n^2) DOM work
- **Tool blocks** -- agent thread nodes for bash, web search, etc.
- **Image generation** -- inline image rendering with download/copy
- **Metrics footer** -- tokens, tok/s, cost/1k, context utilization
- **Auto-grade** -- stamps checkmark/cross against expected answers
- **Timeout handling** -- retry button with doubled timeout
- **Finish badge** -- "Fastest" awarded to first-complete (parallel) or lowest-time (sequential)

### Voting (`compare/vote.js`)

- **Per-pane vote buttons** -- each pane has a "Vote X" button in its footer
- **Tie button** -- declares a draw between all models
- **Reveal** -- shows model names without recording a vote
- **Confetti** (`spawnConfetti()`, line 226) -- particle burst at winner's pane header using `element.animate()`
- **Persistence** -- votes saved to localStorage and POSTed to `/api/compare/record`
- **Scoreboard** -- aggregated win/loss/tie stats per model, filterable by mode

### Model Selector (`compare/selector.js`)

Modal with:
- Grouped model list (Chat/Image) with checkboxes
- Blind mode toggle (eye icon)
- Parallel/Sequential toggle
- Save/Continue toggle
- Timeout slider
- Shuffle pool management
- Random model selection (dice button)
- Search filter for large model lists

---

## 6. Image Editor

**Files**: 45+ files in `editor/` subdirectory, `galleryEditor.js`, `gallery.js`

### Architecture

A full-featured image editor built entirely with HTML5 Canvas. The editor uses a **state store pattern** (`editor/state.js`) where a single exported mutable object holds all editor state, and tool modules import and mutate it directly.

### State Store (`editor/state.js`)

The state object contains 80+ properties organized into slices:

- **Transform tool**: `transformActive`, `transformLayer`, `transformPendingW/H/Rot/FlipH/FlipV`
- **Magic Wand**: `wandMask`, `wandTolerance`, `wandMode`, `wandLastSeed`
- **Brush/Eraser/Clone**: `color`, `brushSize`, `opacity`, `flow`, `softness`
- **Selection**: `selectionMask`, `selectionSource`
- **Layers**: `layers[]`, `activeLayerId`, `layerCounter`
- **Canvas**: `canvasW`, `canvasH`, `zoom`, `panX`, `panY`
- **History**: `undoStack[]`, `redoStack[]`

### Tool Implementations

Each tool in `editor/tools/` follows a consistent pattern:

**Stroke Tool** (`tools/stroke.js`):
- Handles brush, eraser, and clone stamp strokes
- Uses `stroke-pipeline.js` for anti-aliased stroke rendering
- Supports pressure sensitivity, softness (Gaussian falloff), and flow/opacity

**Clone Stamp** (`tools/clone.js`):
- Alt+click to set source point
- Offset-preserved cloning with crosshair indicator

**Flood Fill** (`tools/flood-fill.js`):
- Scanline flood fill with configurable tolerance
- Supports contiguous and global fill modes

**Magic Wand** (`tools/wand.js`):
- Color-based selection with tolerance slider
- Replace, Add, Subtract selection modes
- Live retune -- adjusting tolerance re-runs the flood fill without re-clicking

**Lasso** (`tools/lasso.js`, `tools/lasso-mask.js`):
- Freehand selection drawing
- Converts lasso path to binary mask for masking operations

**Crop** (`tools/crop.js`):
- Interactive crop rectangle with corner/edge handles
- Aspect ratio lock option

**Move** (`tools/move.js`):
- Layer repositioning with snap guides
- Snap-to-edge and snap-to-center alignment

**Transform** (`tools/transform-drag.js`, `transform-handles.js`, `transform-session.js`):
- Resize via corner handles with aspect ratio lock
- Rotation via dedicated rotation handle
- Flip horizontal/vertical
- Cancel restores original state from snapshot

### Canvas System

**Canvas Coordinates** (`canvas-coords.js`):
- Converts between screen coordinates and canvas pixels
- Handles zoom and pan transformations
- `screenToCanvas(x, y)` -- maps mouse position to canvas pixel

**Canvas Events** (`canvas-events.js`):
- Unified mouse and touch event handling
- Dispatches to active tool's start/move/end handlers
- Handles pinch-to-zoom and two-finger pan

**Canvas Transforms** (`canvas-transforms.js`):
- Zoom with mouse wheel (centered on cursor)
- Pan with middle-mouse or space+drag
- Fit-to-view and zoom-to-100%

**Checkerboard** (`checkerboard.js`):
- Draws transparency checkerboard pattern behind image layers

### Layer System

**Layer Helpers** (`layer-helpers.js`):
- `addLayer()`, `removeLayer()`, `duplicateLayer()`
- `mergeDown()`, `flattenAll()`
- Layer visibility toggle, opacity, blend modes
- Each layer is an offscreen canvas with position offset

**Layer Panel** (`layer-panel.js`):
- Visual layer stack with thumbnails
- Drag reordering
- Visibility toggle (eye icon)
- Layer name editing
- Blend mode and opacity controls

### Filters & Effects

**Blur** (`filters/blur.js`):
- Gaussian blur with configurable radius
- Applied as pixel-level operation on layer canvas

**Edge Feather** (`filters/edge-feather.js`):
- Smooth selection edges with falloff
- Used by lasso and wand selections

**Adjustments** (`fx/adj-popup.js`):
- Brightness, Contrast, Saturation, Hue rotation
- Real-time preview with CSS filter strings

**Filter String** (`fx/filter-string.js`):
- Builds CSS `filter:` strings from adjustment values
- Combines multiple adjustments into a single filter chain

**Histogram** (`fx/histogram.js`):
- Draws RGB/luminance histogram of active layer
- Canvas-based chart rendering

**Pixel Pass** (`fx/pixel-pass.js`):
- Direct pixel manipulation (getImageData/putImageData)
- Used for invert, grayscale, threshold, posterize

### AI Integration

**AI Inpaint** (`ai-inpaint.js`):
- Selection-based inpainting using AI models
- User paints a mask, sends to `/api/inpaint` endpoint
- Result composited into the layer at mask position

**AI Background Removal** (`ai-rembg.js`):
- Sends image to `/api/rembg` endpoint
- Returns alpha-masked result as new layer

**AI Tool Runner** (`ai-tool-runner.js`):
- Generic AI tool execution pipeline
- Manages loading states, error handling, result application

**AI Models** (`ai-models.js`):
- Fetches available AI models for editor features
- Model selection dropdown for inpaint/upscale

### Build System

Files in `editor/build/` construct the editor UI:

- **`toolbar.js`** -- Left-side tool palette (brush, eraser, wand, lasso, etc.)
- **`topbar.js`** -- Top menu bar (File, Edit, View, Filters, AI)
- **`right-panel.js`** -- Right panel (layers, history, adjustments)
- **`controls.js`** -- Tool-specific control panels (brush size, tolerance, etc.)
- **`popups.js`** -- Color picker, brush settings popups
- **`transform-popup.js`** -- Transform tool popup (width, height, rotation inputs)

### Wire Modules

Files prefixed with `wire-` connect UI elements to functionality:

- **`wire-topbar.js`** -- Wires File/Edit/View menu items to functions
- **`wire-topbar-menus.js`** -- Dropdown menu creation and positioning
- **`wire-topbar-overflow.js`** -- Mobile overflow menu
- **`wire-import.js`** -- Image import from file/URL/clipboard
- **`wire-inpaint-controls.js`** -- AI inpaint panel events
- **`wire-merge-buttons.js`** -- Layer merge button events
- **`wire-selection-controls.js`** -- Selection tool panel events

### Keyboard Shortcuts (`editor/keyboard-shortcuts.js`)

| Shortcut | Action |
|----------|--------|
| Ctrl+Z | Undo |
| Ctrl+Shift+Z | Redo |
| Ctrl+C/V | Copy/Paste |
| [ / ] | Decrease/Increase brush size |
| B | Brush tool |
| E | Eraser tool |
| G | Flood fill |
| W | Magic wand |
| L | Lasso |
| V | Move tool |
| C | Crop tool |
| Space+drag | Pan canvas |

---

## 7. Email Library

**Files**: `emailLibrary.js`, `emailLibrary/replyRecipients.js`, `emailLibrary/signatureFold.js`, `emailLibrary/state.js`, `emailLibrary/utils.js`, `emailInbox.js`, `emailShared.js`, `signature.js`

### Architecture

A full email client UI embedded as a modal, supporting:
- Multiple IMAP accounts
- Folder navigation (Inbox, Sent, Drafts, etc.)
- Email viewing with HTML rendering
- Compose/Reply/Forward
- Auto-reply (vacation/away) configuration
- AI-powered email summarization
- Signature management
- Writing style analysis

### State (`emailLibrary/state.js`)

Module-level state tracking:
- `_libAccountId` -- Currently selected email account
- `_libAccounts` -- Available email accounts
- `_libFolder` -- Current folder (INBOX, Sent, etc.)
- `_libEmails` -- Loaded email list
- `_libSearchQuery` -- Active search filter

### Email Utilities (`emailLibrary/utils.js`)

- `_esc(s)` -- HTML escaping
- `_escLinkify(s)` -- Escape + auto-link URLs
- `_extractName(addr)` -- Extract display name from email address
- `_parseTurnMeta(text)` -- Parse email thread turn metadata
- `_formatBubbleDate(d)` -- Format dates for message bubbles
- `_formatRecipients(list)` -- Format recipient list display
- `_senderColor(email)` -- Consistent color per sender
- `_initials(name)` -- Extract initials for avatars
- `_sanitizeHtml(html)` -- Sanitize HTML email content

### Signature Folding (`emailLibrary/signatureFold.js`)

Intelligent email signature and quote detection:
- `_looksLikeSignature(text)` -- Heuristic signature detection
- `_harvestAttribution(text)` -- Extract "On date, person wrote:" blocks
- `_foldSignature(el)` -- Collapse signatures with expand button
- `_isBloatedSig(text)` -- Detect overly long signatures
- Constants: `_TALON_WROTE`, `_TALON_FROM`, etc. -- regex patterns for quote detection

### Reply Recipients (`emailLibrary/replyRecipients.js`)

Handles Reply/Reply-All recipient resolution:
- Deduplicates recipients
- Handles self-replies
- Manages CC/BCC fields

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/email/messages` | List messages in folder |
| GET | `/api/email/message/{id}` | Get full message |
| POST | `/api/email/send` | Send new email |
| POST | `/api/email/reply` | Reply to email |
| GET | `/api/email/config` | Get email configuration |
| PUT | `/api/email/config` | Update email configuration |
| GET | `/api/email/style` | Get writing style profile |

---

## 8. Markdown Module

**Files**: `markdown.js`, `markdown/tableRow.js`

### Architecture

A custom markdown-to-HTML renderer with security-first design. Does NOT use a library like marked.js -- implements markdown parsing directly.

### Key Features

**Security (`sanitizeAllowedHtml()`, line 136)**:
- Parses HTML into a `<template>` element (inert -- no script execution)
- Removes dangerous elements: `SCRIPT`, `IFRAME`, `OBJECT`, `EMBED`, `SVG`, `MATH`
- Strips event handler attributes (`on*`)
- Neutralizes `javascript:`, `vbscript:`, `data:` URL schemes
- Sanitizes to a fixpoint (re-parses until stable to prevent mutation XSS)

**Thinking/Reasoning Block Handling**:
- `normalizeThinkingMarkup(text)` (line 171) -- Normalizes various thinking tag formats:
  - `<think>...</think>` (standard)
  - `<mm:think>...</mm:think>` (MiniMax M-series)
  - `<thought>...</thought>` (alternative)
  - `<|channel>thought...<channel|>` (channel format)
- `hasUnclosedThinkTag(text)` (line 156) -- Detects streaming state
- `startsWithReasoningPrefix(text)` (line 167) -- Heuristic for untagged reasoning
- `processWithThinking(text)` -- Wraps reasoning blocks in collapsible `<details>` elements

**Content Rendering**:
- `renderContent(text)` -- Full markdown render (headers, lists, tables, code, links, images)
- `squashOutsideCode(text)` -- Collapses whitespace outside code blocks
- Code block rendering with `highlight.js` syntax highlighting
- Table rendering with `splitTableRow()` from `markdown/tableRow.js`
- Link/image sanitization via `safeLinkUrl(url)`
- Emoji shortcode replacement via `emojiShortcodes.js`

### Table Row Parser (`markdown/tableRow.js`)

`splitTableRow(line)` -- Correctly splits markdown table rows on `|` delimiters while respecting:
- Escaped pipes (`\|`)
- Inline code spans containing pipes
- Leading/trailing whitespace

---

## 9. Model Management UI

**Files**: `models.js`, `modelPicker.js`, `modelSort.js`, `model/matchKey.js`

### Model List (`models.js`)

Renders a browsable, sortable model list panel:

- **Favorites** -- Star models for quick access, persisted in localStorage (`vaidyx-model-favorites`)
- **Usage tracking** -- Records selection count and last-used time (`vaidyx-model-usage`)
- **Sort modes** -- Alphabetical, by usage, by recency
- **Drag reordering** -- Custom model order via `dragSort.js`
- **Provider logos** -- SVG logos per provider via `providers.js`
- **Model types** -- Distinguishes chat vs image models with badges
- **Endpoint grouping** -- Models grouped by endpoint with collapsible sections
- **Cache** -- 30-second client-side cache for `/api/models` responses

**Key function**: `_startChat(url, mid, endpointId)` (line 79) -- Creates a new session with the selected model:
```javascript
sessionModule.createDirectChat(url, mid, endpointId);
```

### Model Picker (`modelPicker.js`)

Inline dropdown in the chat input bar for switching the active model without leaving the conversation. Renders a compact model list anchored to the picker button.

### Model Sorting (`modelSort.js`)

`sortModelIds(models)` -- Sorts model ID lists with intelligent ordering:
- Prioritizes well-known models (GPT-4, Claude, Llama, etc.)
- Groups by provider family
- Alphabetical fallback within groups

`sortModelObjects(models)` -- Same sorting for model objects (used by compare module).

### Match Key (`model/matchKey.js`)

Generates a normalized key for model name matching across different naming conventions (e.g., "gpt-4o" matches "GPT-4o" matches "gpt4o").

---

## 10. Research UI

**Files**: `research/panel.js` (1,260 lines), `research/jobs.js`, `researchSynapse.js`

### Research Panel (`research/panel.js`)

A modal-based deep research interface:

**Panel structure**:
- Header with minimize/close buttons (draggable)
- Query textarea with rotating placeholder hints
- Collapsible settings panel (rounds, format, search engine, endpoint, model)
- Queue/Start buttons
- Active and Past research sections (collapsible)

**Job card states**:
1. **Queued** -- Shows query, settings, Start/Edit/Remove buttons
2. **Running** -- Shows progress bar, phase label, synapse visualization, cancel button
3. **Done** -- Shows thumbnail, sources count, elapsed time, Visual Report/Discuss/Copy/Delete buttons
4. **Error/Cancelled** -- Shows error message, Retry/Edit/Dismiss buttons

**Key functions**:
| Function | Line | Description |
|----------|------|-------------|
| `init(apiBase, markdownMod, sessionMod)` | 210 | Initialize panel |
| `openPanel(focusJobId)` | 236 | Open research modal |
| `closePanel()` | 328 | Close modal |
| `_handleStart()` | 540 | Start research (handles single and batch) |
| `_handleAdd()` | 502 | Add query to queue |
| `_renderJobs()` | 663 | Render all job cards |
| `_buildJobCard(job)` | 888 | Build individual job card DOM |

**Settings persistence**: Settings saved to localStorage (`vaidyx-research-settings`) and restored on panel open.

### Job Queue Manager (`research/jobs.js`)

Manages research job lifecycle:

- `addToQueue(query, settings)` -- Create a queued job
- `startJob(query, settings)` -- Queue and immediately launch
- `startAllQueued()` -- Launch all queued jobs in parallel
- `startAllQueuedSequential()` -- Launch queued jobs one at a time
- `cancelJob(id)` -- Cancel via `POST /api/research/cancel/{id}`
- `retryJob(id)` -- Reset and relaunch a failed job
- `clearAll()` -- Clear all jobs from list

**Streaming**: Uses `EventSource` for real-time progress:
```javascript
const es = new EventSource(`${_apiBase}/api/research/stream/${job.id}`);
```

Progress events include phases: probing, planning, searching, reading, analyzing, writing.

**Notifications**: Browser `Notification` API for job completion.

### Research Synapse Visualization (`researchSynapse.js`)

An SVG-based animated visualization of research progress:

- Central query node with radiating sub-question branches
- Source leaves that pop in as rounds progress
- Phase-dependent animation states
- Status bar: phase label, round number, source count, elapsed timer
- Root node pulses during active phases

---

## 11. Utility Functions

### Storage (`storage.js`)

`localStorage` abstraction with JSON serialization:
- `Storage.get(key, default)` / `Storage.set(key, value)` -- String values
- `Storage.getJSON(key, default)` / `Storage.setJSON(key, value)` -- JSON values
- `Storage.loadToggleState()` / `Storage.saveToggleState(state)` -- Tool toggle persistence

### UI Utilities (`ui.js`)

- `uiModule.esc(str)` / `uiModule.escapeHtml(str)` -- HTML entity escaping
- `uiModule.showToast(msg, opts)` -- Toast notifications with optional action button
- `uiModule.showError(msg)` -- Error toast with red styling
- `uiModule.styledConfirm(msg, opts)` -- Styled confirmation dialog (replaces `window.confirm`)
- `uiModule.emptyStateIcon()` -- Standard empty-state placeholder SVG

### Spinner (`spinner.js`)

Three spinner styles:
1. **Wave** -- ASCII wave animation (`▁▂▃▄▅▆▇`)
2. **Whirlpool** -- Rotating gradient circle (CSS animation)
3. **Right-aligned** -- Spinner with label text

API: `spinnerModule.create(label, align, type)` -- returns `{ createElement(), start(), stop(), destroy(), updateLabel() }`

### ESC Menu Stack (`escMenuStack.js`)

- `bindMenuDismiss(el, closeFn, shouldDismiss)` -- Registers a popup for ESC/outside-click dismissal
- `dismissOrRemove(el)` -- Programmatic dismissal
- Stack-based: ESC closes topmost popup first

### Modal Manager (`modalManager.js`)

Unified lifecycle for tool modals (Gallery, Calendar, Email, Research, etc.):
- `register(id, { railBtnId, restoreFn, closeFn })` -- Register a modal
- `toggle(id)` -- Cycle: closed -> open -> minimize -> restore -> minimize
- `minimize(id)` -- Hide modal, preserve JS state, show badge on rail icon
- `restore(id)` -- Un-hide modal with bring-to-front z-index
- `close(id)` -- Full teardown via registered closeFn
- Integrates with tileManager for edge-docking and windowDrag for dragging

### Window Management

**`windowDrag.js`** -- `makeWindowDraggable(modal, { content, header })`:
- Header-initiated drag
- Edge-docking preview zones
- Position memory via localStorage

**`windowResize.js`** -- Adds resize handles to modals for freeform resizing.

**`tileManager.js`** -- Window tiling system:
- `previewZoneAt(x, y)` -- Shows dock preview zone when dragging near edges
- `snapModalToZone(modal, zone)` -- Snaps modal to left/right/top/bottom half

**`toolWindowZOrder.js`** -- Z-index management:
- `nextToolWindowZ({ exclude, current, floor })` -- Returns next z-index for bring-to-front
- `topPortalZ()` -- Returns z-index above all tool windows (for overlays)

### Drag Sort (`dragSort.js`)

Generic drag-and-drop list reordering:
- Touch and mouse support
- Visual placeholder during drag
- Callback on reorder completion

### Platform Detection (`platform.js`)

- Detects Electron, PWA, mobile browser
- Adjusts behavior for platform-specific features (file system access, notifications)

### Accessibility (`a11y.js`)

- ARIA attribute management
- Focus trap for modals
- Screen reader announcements
- Keyboard navigation support

---

## 12. Styling

### CSS Architecture (`style.css` -- 41,132 lines)

The entire application is styled in a single monolithic CSS file using:

- **CSS Custom Properties** (variables) for theming
- **No preprocessor** (no Sass/LESS)
- **No CSS modules** or scoped styles
- **BEM-like naming** without strict convention (e.g., `.compare-pane`, `.pane-header`, `.pane-title-btn`)

### Theme System

**CSS Variables** (defined on `:root` and `[data-theme]`):

```css
--bg: ...;              /* Background */
--fg: ...;              /* Foreground text */
--panel: ...;           /* Panel/card background */
--border: ...;          /* Border color */
--accent: ...;          /* Primary accent (usually red) */
--red: ...;             /* Brand red */
--green: ...;           /* Success green */
--input-bg: ...;        /* Input field background */
--code-bg: ...;         /* Code block background */
--color-error: ...;     /* Error state */
--color-success: ...;   /* Success state */
```

**Theme module** (`theme.js`):
- Dark/Light/System/Custom themes
- Custom accent color picker
- Font family and size preferences
- `makeDraggable(content, header)` -- Utility for making modals draggable

### Responsive Design

The CSS uses extensive media queries for mobile adaptation:

```css
@media (max-width: 768px) { ... }   /* Mobile breakpoint */
@media (max-width: 480px) { ... }   /* Small mobile */
@media (min-width: 1200px) { ... }  /* Wide desktop */
```

**Mobile adaptations**:
- Sidebar becomes a swipeable overlay
- Compare grid changes to single-column layout
- Calendar modal goes full-screen
- Toolbar items move to overflow menu
- Touch-optimized hit targets (larger buttons)
- Keyboard dismiss helpers for iOS/Android

### Key CSS Components

**Chat UI**:
- `.msg`, `.msg-user`, `.msg-ai` -- Message bubbles
- `.chat-history` -- Scrollable message area
- `.chat-input-bar` -- Fixed bottom input area
- `.mode-toggle` -- Chat/Agent mode switcher

**Compare**:
- `.compare-grid` -- CSS Grid with `data-cols` attribute for column count
- `.compare-pane` -- Individual model pane
- `.pane-header` -- Pane title bar with actions
- `.compare-vote-bar` -- Vote action bar
- `.confetti-piece` -- Confetti particle (animated via Web Animations API)

**Calendar**:
- `.cal-grid` -- Month grid (CSS Grid)
- `.cal-week-row` -- Week row with multi-day bar positioning
- `.cal-multiday` -- Multi-day event bar using CSS custom properties (`--col`, `--span`, `--slot`)
- `.cal-wk-grid` -- Week view hour grid
- `.cal-wk-block` -- Positioned event block

**Editor**:
- Canvas-based (not CSS for drawing surfaces)
- `.ed-toolbar` -- Tool palette
- `.ed-layer-panel` -- Layer stack panel

**Modals**:
- `.modal` -- Full-screen overlay backdrop
- `.modal-content` -- Centered content box
- `.modal-header` -- Draggable header with title + close
- `.modal-body` -- Scrollable content area

### Animations

CSS animations defined in the stylesheet:

- `pane-shake` -- Shuffle animation for compare panes
- `pulse` -- Pulsing dot for active states
- `spin` -- Rotation for loading spinners
- `slide-in-right`, `slide-in-left` -- Calendar month transitions
- `fadeIn` -- Generic fade-in
- `confetti-fall` -- Confetti particle trajectory (also uses Web Animations API)
- `orbit` -- Orbiting edge animation for research panel
- Research synapse pulse animation

---

## 13. Font System

### Font Stack

```
static/fonts/
  Inter-Regular.woff2       -- Primary UI font
  Inter-Medium.woff2        -- Medium weight
  Inter-SemiBold.woff2      -- Semi-bold weight
  FiraCode-Light.woff2      -- Code font (light)
  FiraCode-Regular.woff2    -- Code font (regular)
  FiraCode-SemiBold.woff2   -- Code font (semi-bold)
  OpenDyslexic-Regular.woff2 -- Accessibility font
  OpenDyslexic-Bold.woff2   -- Accessibility font (bold)
  custom/GohuFont.ttf       -- Pixel/bitmap font option
```

### Font Usage

- **Inter** -- All UI text (navigation, labels, buttons, messages)
- **Fira Code** -- Code blocks, inline code, terminal output, metrics
- **OpenDyslexic** -- Optional accessibility font (selectable in settings)
- **GohuFont** -- Optional pixel font for retro aesthetic

Font preferences are stored in localStorage and applied via CSS custom properties or `font-family` overrides in the theme system.

### Icon System

The application uses **inline SVG** exclusively for icons -- no icon font (Font Awesome, etc.):

```javascript
// Typical icon pattern (from compare/icons.js)
const ICON_DICE = '<svg width="14" height="14" viewBox="0 0 24 24" ...>...</svg>';
```

Provider-specific icons are in `static/icons/`:
- `ollama-mark.png`, `ollama-mark-crop.png` -- Ollama provider logo
- `sglang-logo.png`, `sglang-mark.png` -- SGLang provider logo
- `icon-192.png`, `icon-512.png` -- PWA icons
- `icon-maskable-512.png` -- PWA maskable icon

---

## 14. User Workflow

### Step 1: Opening the Application

1. User navigates to the app URL or opens the PWA
2. `index.html` loads, importing `app.js` as an ES module
3. `app.js` initializes all modules, loading saved theme and session state
4. If a previous session exists (from localStorage), it is loaded automatically
5. The sidebar shows the session list; the main area shows the last conversation
6. If no session exists, a blank chat view is shown with the input bar ready

### Step 2: Starting a Conversation

1. User types a message in the `#message` textarea
2. User can optionally:
   - Select a model via the model picker (top-right of input bar)
   - Toggle Agent mode (enables tools: bash, web search, file operations)
   - Toggle Web search for grounded responses
   - Toggle Research mode for deep multi-step research
   - Attach files via the attachment button or drag-drop
   - Use slash commands (`/help`, `/clear`, `/compare`, etc.)
   - Use voice input via the microphone button
3. User presses Enter (or clicks send)
4. `handleChatSubmit()` in `chat.js` processes the input

### Step 3: Receiving a Response

1. A POST request goes to `/api/chat_stream` with the message and session context
2. The response is a Server-Sent Events (SSE) stream
3. `chatStream.js` reads the stream chunk by chunk:
   - `delta` events contain text tokens -- accumulated and rendered with throttled markdown
   - `tool_start` events show tool-use indicators (terminal, web search, etc.)
   - `tool_output` events show tool results
   - `metrics` events provide token counts, speed, cost
   - `research_progress` events update the research synapse visualization
   - `web_sources` events display search source cards
4. The spinner animates during processing
5. Markdown is rendered progressively with `highlight.js` for code blocks
6. When the stream completes (`[DONE]`), final rendering and metrics display

### Step 4: Using Tools and Features

**Model Comparison**:
1. Click Compare button in sidebar/rail
2. Select 2-8 models in the model selector modal
3. Configure: blind mode, parallel/sequential, timeout
4. Type a prompt -- all models receive it simultaneously
5. Watch responses stream into separate panes with live timers
6. Vote for the best response (or Tie)
7. Reveal model names, view scoreboard

**Deep Research**:
1. Click Research button in sidebar/rail
2. Enter research query in the textarea
3. Optionally configure: rounds, format, search engine, model
4. Click Start -- job begins with multi-round web research
5. Watch progress: planning -> searching -> reading -> analyzing -> writing
6. View synapse visualization showing query decomposition
7. Open Visual Report, Discuss (creates follow-up chat), or Copy report

**Calendar**:
1. Click Calendar button in sidebar/rail
2. Calendar modal opens with month view and today highlighted
3. Click a day to see events; click "New" or "+" to create an event
4. Use quick-add input for natural language event creation
5. Drag events between days to reschedule
6. Switch between Month/Week/Year/Agenda views
7. Filter by calendar, event type, or importance

**Image Editor**:
1. Click Gallery button or generate an image via chat
2. Click Edit on an image to open the full editor
3. Use tools: brush, eraser, clone stamp, crop, wand, lasso, flood fill
4. Work with layers: add, reorder, merge, adjust opacity/blend mode
5. Apply AI features: inpainting, background removal
6. Apply filters: blur, adjustments (brightness, contrast, etc.)
7. Export or save the result

**Email**:
1. Click Email button in sidebar/rail
2. Email library modal opens with folder navigation
3. Browse emails in Inbox or other folders
4. Click an email to read it (HTML rendered, signatures folded)
5. Reply, Forward, or Compose new emails
6. Configure auto-reply for vacation/away messages

### Step 5: Managing Sessions

1. Sessions appear in the sidebar, grouped by folders
2. Right-click or long-press for context menu: Rename, Pin, Move to Folder, Delete
3. Drag sessions to reorder or move between folders
4. Search sessions using the sidebar search box
5. Create new sessions via the "+ New Chat" button

---

## 15. UX Patterns

### Modal System

All tool windows (Calendar, Gallery, Email, Research, Notes, Documents) use a consistent modal pattern:

```
Overlay (.modal) -- semi-transparent backdrop
  Content (.modal-content) -- centered panel
    Header (.modal-header) -- title + minimize + close, draggable
    Body (.modal-body) -- scrollable content
```

**Behaviors**:
- **Draggable** via header (`windowDrag.js`)
- **Resizable** via edge handles (`windowResize.js`)
- **Dockable** to screen edges (left-half, right-half) via `modalSnap.js`
- **Minimizable** to a badge on the rail icon (state preserved)
- **Z-index management** via `toolWindowZOrder.js` (bring-to-front on click)
- **ESC to close** via `escMenuStack.js` (closes topmost first)
- **Click-outside to close** on the overlay backdrop

### Toast Notifications

`uiModule.showToast(message, options)`:
- Auto-dismiss after configurable duration (default ~3s)
- Optional action button with callback (e.g., "Undo")
- Optional keyboard shortcut hint
- Stacks from bottom-right
- Smooth slide-in/out animation

### Styled Confirm Dialogs

`uiModule.styledConfirm(message, options)`:
- Returns a Promise resolving to true/false
- Customizable button text and danger styling
- ESC and click-outside dismiss (resolves false)
- Replaces native `window.confirm`

### Dropdown Menus

Consistent dropdown pattern across the app:

1. Create a `<div>` with fixed positioning
2. Position relative to anchor element's `getBoundingClientRect()`
3. Viewport clamping: ensure dropdown stays within screen bounds
4. Register with `bindMenuDismiss()` for ESC/outside-click handling
5. Smooth open/close transitions

### Keyboard Shortcuts

**Global** (`keyboard-shortcuts.js`):
- `Ctrl/Cmd+Enter` -- Send message
- `Ctrl/Cmd+K` -- Focus search
- `Ctrl/Cmd+N` -- New chat
- `Ctrl/Cmd+Shift+S` -- Toggle sidebar

**Context-specific**:
- Arrow Up in empty composer -- recalls last message
- ESC -- closes topmost modal/menu
- Calendar: Ctrl+Z for undo
- Editor: full Photoshop-like shortcut set

### Drag and Drop

Multiple drag-and-drop implementations:

1. **File attachment** (`fileHandler.js`) -- Drop files on chat to attach
2. **Calendar events** -- Drag events between days in month view
3. **Session reordering** (`dragSort.js`) -- Drag sessions in sidebar
4. **Model reordering** -- Drag models in the model list
5. **Layer reordering** -- Drag layers in the editor panel
6. **Editor images** (`clipboard-and-drop.js`) -- Drop images onto the canvas

### Loading States

Consistent loading pattern:
1. Show spinner (`spinnerModule.create()`) with contextual label
2. Disable interactive elements
3. On completion: destroy spinner, enable elements
4. On error: show error toast, restore previous state

### Responsive Patterns

**Mobile adaptations** (breakpoint: 768px):
- Sidebar becomes a full-screen overlay with swipe-to-dismiss
- Compare grid collapses to single column
- Tool modals go full-screen (100vw, 90dvh)
- Toolbar items move to overflow "+" menu
- Keyboard dismiss helpers for virtual keyboards
- Touch-optimized button sizes (minimum 44px tap targets)
- Quick-add search inputs skip auto-focus on mobile (prevents keyboard popup)

### Optimistic Updates

Calendar and other CRUD operations use optimistic updates:
1. Apply change to local state and UI immediately
2. Fire API request in background
3. On success: persist to local cache
4. On failure: rollback local state, show error toast

### Prefetching

- Calendar prefetches adjacent months in background
- Model list has 30-second client-side cache
- Research jobs poll for active sessions every 20 seconds
- Compare module caches model list with 30-second TTL

### PWA Support

- `manifest.json` -- PWA manifest with app name, icons, colors
- `sw.js` -- Service worker for offline caching
- Installable on mobile and desktop
- Icons: 192px, 512px, maskable variants
