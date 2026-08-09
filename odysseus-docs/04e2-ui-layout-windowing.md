# UI Layout and Windowing System

This document covers the Odysseus frontend layout engine, modal/window management, theming, and interaction systems found in `static/js/`.

---

## 1. UI Core (`ui.js`, 1329 lines)

Central utility module exporting `uiModule` as the default. Provides feedback, dialogs, scrolling, and global interaction handling.

### Toast Notifications
- `showToast(msg, durationOrOpts)` (line 300) -- success toast with optional action button, leading icon (checkmark or whirlpool spinner), keyboard hint, and close button. Auto-hides after configurable duration (default 1200ms). Supports swipe-to-dismiss on touch devices via `_wireToastSwipe()` (line 243).
- `showError(msg)` (line 413) -- error variant with red styling and 6-second auto-hide.

### Styled Dialogs
- `styledConfirm(message, opts)` (line 584) -- promise-based replacement for `window.confirm()`. Supports confirm/cancel/alternate buttons, danger styling, arrow-key and Tab focus trapping. Exposed globally as `window.styledConfirm`.
- `styledPrompt(message, opts)` (line 681) -- promise-based replacement for `window.prompt()` with text input, Enter-to-submit, and focus trapping.

### Scrolling
- `scrollHistory()` (line 457) -- smooth rAF-based lerp scroll for chat history during streaming, throttled to 500ms intervals. Respects user scroll position (skips if >300px from bottom).
- `scrollHistoryInstant()` (line 502) -- instant snap-to-bottom for session loads.
- `setAutoScroll(enabled)` / `getAutoScroll()` (lines 514/520).

### Utility Functions
- `copyToClipboard(text)` (line 220) -- clipboard API with execCommand fallback.
- `autoResize(textarea)` (line 528) -- hidden-clone measurement for dynamic textarea height.
- `debounce(func, wait)` (line 559) -- standard debounce.
- `el(id)` (line 574) -- shorthand `getElementById`.
- `esc(s)` (line 786) -- HTML-escape for XSS prevention (`&<>"'`).
- `emptyStateIcon(kind)` (line 839) -- SVG icons for empty states (smiley/sad/neutral).
- `isTouchInsideModal()` (line 810) -- guards backdrop dismiss from synthetic touch events.

### Global Escape Arbiter (line 1211)
Capture-phase keydown handler that closes exactly one thing per Escape press with priority: hovered window > transient menus (escMenuStack) > expanded library card > thinking block > gallery editor > settings inner form > topmost modal by z-index. Auto-promotes modal z-indexes via MutationObserver so most-recently-opened always wins visually and for Escape.

### Space-Key Card Toggle (line 167)
Hover-tracking system that lets Space toggle cards, minimize hovered windows, or restore minimized dock chips. Tracks pointer position and uses `SPACE_CARD_SELECTOR` / `SPACE_BLOCKED_SELECTOR` to distinguish actionable vs. interactive targets.

### Mobile Features
- Swipe-down-to-dismiss for bottom-sheet modals (line 912): velocity-based with rubber-band resistance on upward pull, `DISMISS_THRESHOLD=50px`.
- Keyboard scroll-into-view for focused inputs in modal sheets (line 1162).

---

## 2. Sidebar Layout (`sidebar-layout.js`, 613 lines)

### Three-State Sidebar
`initSidebarLayout(Storage, opts)` (line 28) manages the sidebar in three modes persisted via `odysseus-sidebar-mode` in localStorage:
- **full** -- expanded sidebar visible
- **mini** -- sidebar hidden, icon rail visible
- **off** -- both hidden, hamburger only

### Hamburger Cycling
Desktop: full <-> mini toggle. Mobile: full <-> off toggle. The hamburger button (line 183) manages sidebar opening with keyboard blur handling on mobile (250ms delay for keyboard dismiss).

### Auto-Collapse
`checkSidebarAutoCollapse()` (line 266) hides the sidebar when viewport < 700px or chat area < 380px. Respects tile-snapped modals to avoid reactive loops. Monitors resize events and MutationObserver on body classes.

### Mobile Features
- Backdrop overlay (`sidebar-backdrop`, line 318) closes sidebar on tap, suppressed during inline renames and open dropdowns.
- Swipe-to-close: 60px horizontal swipe threshold, direction-aware for left/right sidebar (line 362).
- Swipe-to-open from chat area (`_initChatSwipeToOpenSidebar`, line 529): 40px threshold, direction determines sidebar side, excludes modals/inputs/Compare mode.
- Tool button auto-close: sidebar auto-hides on mobile when a tool opens, restores when all tools close (line 428).

### Icon Rail
Section-click navigation: clicking a rail button opens the sidebar and scrolls to the corresponding section (line 246).

---

## 3. Modal System

### Modal Manager (`modalManager.js`, 1560 lines)

Central state machine for tool modals using a `Map<id, state>` registry.

**Lifecycle**: `register()` (line 1146) -> `minimize()` (line 1225) -> `restore()` (line 1262) -> `close()` (line 1307). `toggle()` (line 1297) restores if minimized, returns false otherwise.

**State per modal**: `restoreFn`, `closeFn`, `btnIds` (rail/sidebar), `isMinimized`, `restoreMinHeight`.

**Z-Order**: monotonic counter starting at 300, `_bringToFront()` (line 66) uses `nextToolWindowZ()` to always surface the most recently activated modal.

**Dock Chip System** (line 154+): minimized modals render as draggable chips in `#minimized-dock`. Labels and icons defined in `_LABELS` map (line 129) for ~16 tool types. Features:
- FLIP animation for reorder transitions
- Chip drag modes: `reorder` (desktop middle chips), `move-dock` (edge/single), `free` (mobile peel-off), `chain` (multi-chip physics)
- Chain physics (`_initChainPhysics`, line 497): spring-following snake behavior with trail direction tracking, critically-damped follower easing
- Trash zone: magnetic close target with whirlpool burst animation, positioned opposite the dragged chip
- Long-press (380ms) to peel a chip from a chain into free drag
- Dock position persistence via localStorage (`odysseus.mobileDockState.v1`)

**Auto-Wire** (line 1404): `_AUTO_WIRE` map registers known modals lazily on first minimize/swipe, injecting minimize buttons via `injectMinimizeButton()` (line 1354).

**Swipe-Down Minimize** (line 1472): allowlisted modals (cookbook, calendar, email) survive swipe-dismiss as dock chips instead of fully closing.

### Modal Snapping (`modalSnap.js`, 1079 lines)

Edge-dock system for modals as side panels.

**Core API**:
- `applyEdgeDock(modal, side)` (line 335) -- docks modal to left or right edge. Snapshots pre-dock geometry, collapses sidebar if needed, sets CSS vars (`--right-dock-w`, `--left-dock-w`).
- `clearRightDock(modal, cx, cy)` (line 607) -- undocks and restores pre-dock geometry, re-anchoring near cursor for peel-off feel.
- `suspendDock(modal)` / `resumeDock(modal)` (lines 676/721) -- temporarily releases body push during minimize, re-applies on restore.
- `makeEdgeDockController(modal, side)` (line 751) -- returns drag-session controller with `onMove()`, `hovering()`, `commit()`, `release()`.

**Edge Dock Resize** (line 788): fixed resize handles at dock boundaries with pointer-capture drag, width persistence per modal+side in localStorage.

**Email/Document Split** (line 992): special split-seam indicator for email+document side-by-side layout with its own resize handle.

---

## 4. Theme System (`theme.js`, 2115 lines)

### Built-in Themes (line 11)
16 presets: dark, light, midnight, paper, cyberpunk, retrowave, forest, ocean, ume, copper, terminal, organs, lavender, gpt, claude, cute. Each defines 5 base colors: `bg`, `fg`, `panel`, `border`, `red`.

### Custom Themes
- Up to 8 custom themes stored in localStorage (`odysseus-custom-themes`) and synced to server via `/api/prefs/custom-themes`.
- `saveCustomTheme(name, colors, opts)` (line 91) / `deleteCustomTheme(name)` (line 113).
- Import/export as JSON files.

### Color Application (`applyColors`, line 257)
Sets 15+ CSS custom properties including derived syntax highlighting colors (`deriveSyntaxColors`, line 160): keyword, string, comment, function, number, builtin, variable, params. Dark/light detection via background luminance.

### Advanced Color Overrides (line 182)
14 fine-grained overrides: user/AI bubble backgrounds, sidebar, brand color, input, send button, code block, toggle active. Defaults computed from base palette via `computeAdvancedDefaults()` (line 199).

### Color Harmony Generator (line 220)
`generateHarmonyColors(accentHex, harmonyType, mode)` -- creates full 5-color palettes from a single accent using complementary, analogous, triadic, or monochromatic harmony rules.

### Additional Features
- Font selection: mono, sans, serif, OpenDyslexic, plus custom fonts from `/api/fonts/custom` (line 376).
- Density modes: comfortable, compact, spacious (line 376).
- UI scale: 100% or 125% (line 397).
- Background patterns: dots, synapse, rain, constellations, perlin-flow, petals, sparkles, embers -- each with canvas-based animation (line 405+).
- Frosted glass mode: `body.theme-frosted` for translucent panels (line 432).
- Effect color, intensity (0-1), and size (0.3-2.5) sliders.
- Zone highlighter: hovering a color picker row overlays the affected UI region (line 1360).
- Dynamic favicon: SVG favicon updates to match theme accent, with per-route shapes (line 297).

---

## 5. Window Management

### Window Drag (`windowDrag.js`, 333 lines)
`makeWindowDraggable(modal, options)` (line 57) -- unified drag handler replacing per-file copies across 12+ tool modals.

Features: cursor-following via `position:fixed`, cancel in-flight animations on grab, move-threshold (4px) to suppress synthetic clicks, edge-dock integration (left+right via `makeEdgeDockController`), touch support.

Options: `content`, `header`, `fsClass`, `onEnterFullscreen`/`onExitFullscreen`, `skipSelector` (default: `button, input, select`), `onDragEnd`, `mobileSkip` (default 768), `enableDock`, `enableResize`.

Auto-wires `makeWindowResizable` unless `enableResize: false`.

### Window Resize (`windowResize.js`, 233 lines)
`makeWindowResizable(content, options)` (line 32) -- edge/corner proximity detection (7px) for native-feel resize.

Detects 4 edges + 4 corners, shows appropriate resize cursor on hover, pins to `position:fixed` during drag, enforces min dimensions (320x200 default), clamps to viewport, persists size in localStorage via `storageKey`. Skips interactive elements and locked states (fullscreen/docked).

### Tile Manager (`tileManager.js`, 394 lines)
Desktop window tiling via snap zones detected during header drag.

**Snap Zones** (line 94): fullscreen (over top edge, covers entire viewport), maximize (near top, fills safe area beside sidebar), top-half, left-half, right-half, bottom-half. Computed relative to `_viewportSafeRect()` which accounts for sidebar/rail.

**Ghost Preview**: translucent overlay showing snap target during drag. Spring animation (0.22s cubic-bezier) on commit.

**Pre-snap Geometry**: stored in `dataset._tilePreSnap` for restore on drag-away. `_reclampAll()` re-tiles on viewport resize or sidebar toggle.

**Public API**: `previewZoneAt(x, y)`, `clearPreview()`, `snapModalToZone(modal, zone)` -- used by dock chip drag-to-snap.

### Z-Order (`toolWindowZOrder.js`, 46 lines)
- `topToolWindowZ(options)` (line 3) -- scans visible modals/overlays for highest z-index (floor: 250).
- `nextToolWindowZ(options)` (line 23) -- returns current z if already top, else top+1.
- `topPortalZ(options)` (line 44) -- z for body-portaled dropdowns, clears dock chip z-indexes (floor 10030).

---

## 6. Workspace (`workspace.js`, 208 lines)

Directory browser for scoping agent file/shell tools to a folder.

- `openWorkspaceBrowser()` (line 185) -- draggable modal with editable path bar, folder listing (from `/api/workspace/browse`), "Use this folder" button.
- `vetAndSetWorkspace(path)` (line 72) -- server-side path validation via `/api/workspace/vet`.
- `syncWorkspaceIndicator(path)` (line 36) -- shows/hides removable pill in chat input bar, hidden in chat mode (agent-only feature).
- Workspace stored in localStorage, scopes file tools (not a security sandbox).

---

## 7. Keyboard Shortcuts (`keyboard-shortcuts.js`, 292 lines)

`initKeyboardShortcuts(modules)` (line 49) -- configurable keybinds loaded from `/api/auth/settings`.

**Default Bindings**: `Ctrl+K` search, `Ctrl+Alt+B` toggle sidebar, `Ctrl+Alt+N` new session, `Ctrl+Alt+F` favorite session, `Ctrl+Alt+D` delete session, `Escape` cancel, `Alt+Shift+T` TTS, `Ctrl+Alt+I` incognito, `Ctrl+,` settings/toggle window, `Ctrl+/` focus input, `Ctrl+Alt+C` calendar.

**Tool shortcuts**: open_calendar through open_theme -- unbound by default, configurable.

**Features**: AltGr detection to avoid false triggers on non-US layouts (`_matchesCombo`, line 19). Global Escape cancels bulk-select mode across all tools (line 73). Window toggle (line 98) remembers last-opened tool window.

---

## 8. Accessibility (`a11y.js`, 165 lines)

IIFE that enhances click-only `<div>` controls for keyboard and screen-reader users.

- Adds `tabindex="0"` and `role="button"` to sidebar list items and user bar (line 30).
- Delegated Enter/Space activation (line 113).
- Skips rows containing nested interactive elements to avoid invalid nesting (line 27).
- Modal enhancement: adds `role="dialog"`, `aria-modal="true"`, `aria-labelledby` linked to heading, normalizes heading level to 2 (line 78).
- MutationObservers on sidebar (subtree) and body (childList) to enhance dynamically added elements.

---

## 9. Tour and Onboarding

### Tour Autoplay (`tourAutoplay.js`, 133 lines)
Auto-fires `/tour-<x>` slash commands on first modal open. Maps 7 modals to tours (library, cookbook, research, compare, theme, settings, gallery). One-shot via localStorage markers. Currently disabled for v1 stability (line 122).

### Tour Hints (`tourHints.js`, 179 lines)
One-time "Pro tip" popup on first tool modal open: animated SVG showing drag-to-snap gesture. Positioned adjacent to modal, auto-dismisses after 14 seconds. Desktop only (>768px). Tracks seen state in localStorage.

---

## 10. Supporting Modules

### Escape Menu Stack (`escMenuStack.js`, 102 lines)
LIFO stack for transient dropdown/popup dismiss callbacks. `registerMenuDismiss(fn)` returns unregister function. `dismissTopMenu()` pops and invokes. `bindMenuDismiss(el, onClose)` wires outside-click + Escape in one call, stashes `el._dismiss` for bulk cleanup.

### Drag Sort (`dragSort.js`, 265 lines)
`enable(containerId, itemSelector, options)` -- vertical drag-and-drop reorder with magnetic snap. Mouse drag immediate, touch requires 400ms long-press with haptic feedback. Persists order via `storageKey`. FLIP-animated placeholder insertion.

### Spinner (`spinner.js`, 390 lines)
`Spinner` class with three animation modes: text-frame (`|/-\`), sinewave (canvas), whirlpool (canvas spiral). `createWhirlpool(size)` and `createLoadingRow(text)` factory functions. Whirlpool self-terminates when element leaves DOM.

### Section Management (`section-management.js`, 260 lines)
`initSectionCollapse(Storage)` -- chevron-based collapse/expand with domino animation (CSS keyframe `section-domino-out`). `initSectionDrag(Storage, loadUIVis)` -- drag-handle reorder of sidebar sections, order persisted in Storage.

### Language Icons (`langIcons.js`, 187 lines)
`langIcon(lang, size, opts)` -- SVG icon markup for 25+ languages/file types (Python, JS, TS, Rust, Go, Java, etc.) with alias map (py->python, md->markdown, etc.).

---

## 11. Key Functions Reference

| Function | File | Line | Purpose |
|---|---|---|---|
| `showToast` | ui.js | 300 | Success notification with actions |
| `styledConfirm` | ui.js | 584 | Promise-based confirm dialog |
| `styledPrompt` | ui.js | 681 | Promise-based text input dialog |
| `scrollHistory` | ui.js | 457 | Smooth rAF chat scroll |
| `esc` | ui.js | 786 | HTML escape for XSS prevention |
| `initSidebarLayout` | sidebar-layout.js | 28 | Sidebar modes, rail, mobile |
| `register` | modalManager.js | 1146 | Register modal with manager |
| `minimize` | modalManager.js | 1225 | Minimize to dock chip |
| `restore` | modalManager.js | 1262 | Restore from dock |
| `close` | modalManager.js | 1307 | Full teardown + unregister |
| `injectMinimizeButton` | modalManager.js | 1354 | Add `_` button to header |
| `applyEdgeDock` | modalSnap.js | 335 | Dock modal to screen edge |
| `clearRightDock` | modalSnap.js | 607 | Undock with geometry restore |
| `makeEdgeDockController` | modalSnap.js | 751 | Drag-session dock controller |
| `applyColors` | theme.js | 257 | Apply theme colors + syntax |
| `initThemeUI` | theme.js | 523 | Wire theme popup controls |
| `generateHarmonyColors` | theme.js | 220 | Color harmony generator |
| `applyBgPattern` | theme.js | 445 | Set background animation |
| `makeWindowDraggable` | windowDrag.js | 57 | Unified window drag |
| `makeWindowResizable` | windowResize.js | 32 | Edge/corner resize |
| `previewZoneAt` | tileManager.js | 361 | Tile snap zone detection |
| `snapModalToZone` | tileManager.js | 386 | Commit tile snap |
| `nextToolWindowZ` | toolWindowZOrder.js | 23 | Next z-index for stacking |
| `initKeyboardShortcuts` | keyboard-shortcuts.js | 49 | Wire all keybinds |
| `registerMenuDismiss` | escMenuStack.js | 22 | Register transient menu |
| `enable` (dragSort) | dragSort.js | 14 | Enable drag-sort on container |
| `initWorkspace` | workspace.js | 199 | Wire workspace pill/browser |
