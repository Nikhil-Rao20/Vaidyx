# 04c -- Image Editor Core

Source: `static/js/editor/`

The Odysseus image editor is a browser-based, layer-compositing canvas editor. All
modules share a single mutable state object and communicate through dependency-injected
callback bags rather than an event bus.

---

## 1. State Management

**File:** `state.js`

A single exported `state` object replaces the ~110 module-scope `let` declarations that
once lived in `galleryEditor.js`. Every tool module imports `state` and reads/writes its
properties directly.

### State Slices

| Slice | Key Properties | Purpose |
|---|---|---|
| **Document** | `layers`, `activeLayerId`, `imgWidth`, `imgHeight`, `imageId`, `originalExt` | Document dimensions, layer stack, originating gallery image |
| **Viewport** | `zoom`, `panX`, `panY`, `editorOpen` | Display zoom (1 = 100%), pan offset, open/close guard |
| **Undo/Redo** | `undoStack[]`, `redoStack[]` | Snapshot-based history stacks |
| **Layer offsets** | `layerOffsets` (Map), `nextLayerId` | Per-layer {x,y} position; monotonic ID counter |
| **Transform tool** | `transformActive`, `transformLayer`, `transformHandle`, `hoveredHandle`, `transformPending{W,H,Rot,FlipH,FlipV}`, `transformAspectLock`, `transformOverlay/Ctx` | Resize/rotate session: original snapshot, pending dims, overlay canvas |
| **Magic Wand** | `wandMask`, `wandLayerId`, `wandTolerance`, `wandMode`, `wandLastSeed`, `wandSrcCache` | Binary selection mask, tolerance, cached layer pixel data |
| **Brush/Eraser/Clone** | `color`, `brushSize`, `brush/eraser/cloneOpacity`, `brush/eraser/cloneFlow`, `brush/eraser/cloneSoftness`, `cloneSource{X,Y}`, `cloneSourceSnapshot` | Per-tool stroke modifiers; clone stamp source/offset/snapshot |
| **Stroke drag** | `drawing`, `lastX`, `lastY` | In-progress paint stroke interpolation |
| **Move tool** | `moving`, `moveStart{X,Y}`, `moveLayerOffset{X,Y}`, `activeSnapGuides` | Layer dragging with snap guides |
| **Crop tool** | `cropping`, `cropStart`, `cropEnd`, `cropRect`, `cropAspectLock`, `cropMoving` | Crop rectangle session |
| **Lasso tool** | `lassoPoints[]`, `lassoActive` | Freehand selection polygon |
| **Inpaint/Mask** | `maskCanvas`, `maskCtx`, `maskVisible`, `maskTintColor`, `maskTintOpacity`, `inpaintEraseMode`, `lastInpaintLayerId` | Active mask canvas, tint overlay, erase mode |
| **Background remove** | `rembgLiveLayer`, `rembgLiveSnap`, `rembgInstalledCache` | Pristine snapshot for edge cleanup sliders |
| **Clipboard** | `internalClipboard` | Editor-internal copy buffer (preserves alpha/metadata) |
| **DOM refs** | `container`, `mainCanvas`, `mainCtx`, `cursorEl`, `layerThumbEl`, `editorLoadingEl` | Root container, canvases, UI overlays |
| **Popups/Panels** | `fxPopupEl`, `adjPopupEl`, `historyPanelEl`, `fxMenuEl` | Floating adjustment/history panel elements |
| **Draft persistence** | `draftId`, `draftName`, `persistTimer`, `persistInFlight`, `persistDirty` | Auto-save sequencing with dirty flag |

---

## 2. Canvas System

### 2.1 Coordinate Conversion (`canvas-coords.js`)

`canvasCoords(e, canvas)` converts client coordinates (mouse or first touch finger) to
canvas-internal pixel coordinates by computing the ratio of `canvas.width` to the
element's CSS bounding rect. Handles both `MouseEvent` and `TouchEvent`.

### 2.2 Event Wiring (`canvas-events.js`)

`wireCanvasEvents(ctx)` binds three input layers:

| Input | Events | Behavior |
|---|---|---|
| **Mouse** | `mousedown` on canvas, `mousemove`/`mouseup` on window | Drag continues past canvas edge; `mouseenter`/`mouseleave` toggle brush cursor |
| **Touch 1-finger** | `touchstart`/`touchmove`/`touchend` | Routes to `beginDraw`/`continueDraw`/`endDraw` |
| **Touch 2-finger** | 2+ touches | Pinch-zoom (0.1x--5x) + two-finger pan via CSS `translate3d` |
| **Pan (empty space)** | `pointerdown`/`pointermove`/`pointerup` on canvas-area | Drag in empty space around the canvas pans both main canvas and transform overlay |

The lasso tool has a special fallback: `mousedown` on `canvasArea` (not the canvas) so
lasso paths can begin in empty space around the image.

`canvasArea._resetPan()` is exposed so zoom/fit-reset can clear the pan offset.

### 2.3 Document Transforms (`canvas-transforms.js`)

`createCanvasTransforms(deps)` returns two methods:

- **`rotateAll(deg)`** -- Rotates every layer by 90/180/270 degrees. Each layer is
  rotated around its own center, then that center is rotated around the old image center
  and translated into the new frame. 90/270 swap document width/height. Wrapped in
  `requestAnimationFrame` to let the loading spinner paint before blocking. Invalidates
  adjustment caches (`_adjCacheKey`, `_adjFinalKey`).

- **`flipAll(axis)`** -- Mirrors every layer horizontally (`'h'`) or vertically (`'v'`).
  Layer offsets are reflected around the image center. Dimensions stay unchanged.

### 2.4 Checkerboard (`checkerboard.js`)

`drawCheckerboard(ctx, w, h)` paints a 10px transparency grid (#ccc / #fff) behind all
layer passes so transparent areas are visible.

### 2.5 Snap Guides (`snap.js`)

`computeSnap(layer, nx, ny, ctx)` implements snap-while-dragging for the move tool.
Snap targets include canvas edges, canvas center, and other visible layers' edges/centers.
Threshold is `6 / zoom` pixels -- constant in screen space regardless of zoom.

Returns `{x, y, guides[]}` where guides are vertical/horizontal lines to render.

`cursorForHandle(id)` maps transform handle IDs (`tl`, `tr`, `bl`, `br`, `rot`) to CSS
cursor names.

---

## 3. Layer System

### 3.1 Layer Helpers (`layer-helpers.js`)

Pure stateless utilities:

| Function | Purpose |
|---|---|
| `layerHasAdjustments(layer)` | True if the layer has FX/adjustment sub-layers |
| `layerNeedsPixelPass(layer)` | True if Levels or Color Balance need the expensive per-pixel pass |
| `adjustmentsKey(adj)` | Compact hash of Levels + Color Balance values for cache keying |
| `defaultAdjParams(type)` | Identity parameters for each adjustment type |
| `adjLayerLabel(type)` | Human-readable name for adjustment type |
| `isMaskCanvasEmpty(canvas)` | Quick downsampled-alpha check (samples at max 200x200) |
| `isLayerEmpty(layer)` | Same check on a layer wrapper |
| `relTime(ts)` | Compact relative time string ("now", "30s", "12m", "4h") |

Adjustment types: `brightness-contrast`, `hue-saturation`, `levels`, `color-balance`.

`ADJ_ICONS` provides per-type SVG icon strings used in popups, FX dock chips, and layer
panel sub-rows.

### 3.2 Composite Helpers (`composite-helpers.js`)

- **`buildThumbnail(layers, imgW, imgH, offsets, maxDim, quality)`** -- Cheap downscaled
  JPEG preview composited from all visible layers. Respects per-layer opacity and offsets.

- **`buildMergedMaskCanvas(layers, imgW, imgH)`** -- Union of every visible mask sub-layer
  using `lighter` composite operation (additive). Returns null when no mask contributed
  pixels.

### 3.3 Layer Panel (`layer-panel.js`)

`createLayerPanelRenderer(deps)` returns `{ render }`. Each call rebuilds the right-side
layer list from `state.layers` (rendered in reverse order -- top layer first).

**Per-layer row structure:**
```
[drag handle] [eye] [name] [opacity slider] [FX] [dup] [mask] [merge-down] [x]
```

**Sub-rows:**
- Adjustment sub-rows: `[eye] [name+icon] [opacity slider] [merge-bake] [x]`
- Mask sub-rows: `[eye] [name] [merge-up] [x]`

Key behaviors:
- **Double-click name** to inline-rename
- **Shift+click** a layer row to load its transparency as a wand selection
- **Drag handle** reorders layers via `dragSortModule`
- **FX button** opens the adjustment popup for that layer
- **Mask button** creates a mask from current lasso/wand selection, or an empty mask
- **Duplicate** clones pixels, offset, opacity, masks, and adjustment sub-layers
- **Merge Down** bakes the layer into the one beneath (hidden for the bottom layer)
- **Delete** removes the layer with undo support; base layer prompts for confirmation
- **Opacity slider** has `pointerdown`/`pointerup` handling for a JS `dragging` class
- **Mobile peek height** is auto-calculated from header + min(N, 2) rows

---

## 4. History / Undo

**File:** `history-panel.js`

`createHistoryPanel({ undo, redo })` returns:

| Method | Purpose |
|---|---|
| `toggleHistoryPanel()` | Opens/closes the floating frosted-glass history list |
| `refreshHistoryPanelIfOpen()` | Rebuilds the entry list if the panel is visible |
| `jumpToHistory(offset)` | Calls undo/redo N times to reach the target state |

The panel shows entries in chronological order: past (undo) states, a "Current" marker,
then future (redo) states. Each entry shows a label and a relative timestamp via
`relTime()`. Clicking an entry calls `jumpToHistory(offset)` to reach that state.

Features: draggable header for repositioning, Esc/click-away dismissal, minimize to
`modalManager` chip chain (restore/close from chip).

---

## 5. Keyboard Shortcuts

**File:** `keyboard-shortcuts.js`

All shortcuts are bound to `document` and gated by `state.editorOpen`. Text input fields
are excluded for tool keys.

### Modifier Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as / export to gallery |
| `Ctrl+Shift+T` | Open resize popup |
| `Ctrl+Alt+T` | Start free transform |
| `Ctrl+Alt+I` | Invert wand/lasso selection |
| `Ctrl+Alt+J` | New empty layer |
| `Ctrl+Alt+A` | Select all canvas (lasso = full bounds) |
| `Ctrl+Shift+D` | Deselect (clear wand + lasso) |
| `Ctrl+C` | Copy selection (wand/lasso) or entire active layer |
| `Ctrl+X` | Cut selection (copy + erase + new layer) |
| `Ctrl+V` | Paste (handled by paste event listener) |

### Direct Keys (no modifier, outside text fields)

| Key | Action |
|---|---|
| `?` | Toggle shortcuts cheatsheet |
| `Enter` | Confirm in-progress transform |
| `Esc` | Cancel transform / lasso / crop (priority order) |
| `[` / `]` | Shrink / grow brush size by 10% |
| Tool keys (`V`, `B`, `E`, `L`, etc.) | Switch tool via toolbar click |
| `D` (with lasso 3+ pts) | Delete lasso selection |
| `C` (with lasso 3+ pts) | Copy lasso to new layer |
| `M` (with lasso 3+ pts) | Convert lasso to mask |
| `Delete` / `Backspace` | Delete wand or lasso selection pixels |

AltGr keystrokes skip the Ctrl+Alt chord block but still reach the bracket handlers
(for AZERTY/QWERTZ layouts).

### Shortcuts Popover (`shortcuts-popover.js`)

`createShortcutsPopover()` returns `{ toggleShortcuts, isOpen }`. The popover is a
frosted-glass panel anchored above the topbar keyboard icon. Draggable header with
position persisted to `localStorage`. Esc or click-outside dismisses.

---

## 6. Clipboard and Import

**File:** `clipboard-and-drop.js`

`wireClipboardAndDrop(deps)` sets up two import paths:

### Paste (Ctrl+V)
1. Checks `state.internalClipboard` first (set by lasso/wand copy/cut)
2. Falls back to system clipboard `image/*` items
3. Creates a new layer named "Pasted Selection" or "Pasted"
4. Activates the layer and switches tool to Move
5. Listener uses capture phase to beat chat input

### Drag-and-Drop
1. Shows "Drop image to add as new layer" overlay during drag
2. Filters for `image/*` files only
3. Routes each dropped image through `handleImportedImage` (same path as toolbar Import)
4. Tracks `dragDepth` counter for nested dragenter/dragleave events

Both paths are gated by `state.editorOpen`.

---

## 7. Slider UX (`slider-ux.js`)

`wireSliderUx({ registerDocClickAway })` adds three behaviors to all editor sliders:

- **`is-using` class** while dragging (cleared 0.5s after release for smooth animation)
- **Floating value bubble** above thumb during drag (desktop: layer-opacity only; mobile:
  all sliders). Fixed-positioned on `document.body` to escape overflow clipping.
- **Click-to-type** on value chips: replaces the chip with an inline input, commits on
  blur/Enter, cancels on Esc

---

## 8. Key Functions Reference

| Function | File | Line | Signature |
|---|---|---|---|
| `canvasCoords` | `canvas-coords.js` | 11 | `(e, canvas) => {x, y}` |
| `wireCanvasEvents` | `canvas-events.js` | 39 | `({canvasArea, beginDraw, continueDraw, endDraw, updateBrushCursor, syncZoomControls})` |
| `createCanvasTransforms` | `canvas-transforms.js` | 21 | `({saveState, composite, fitZoom, showCanvasLoading, hideCanvasLoading}) => {rotateAll, flipAll}` |
| `drawCheckerboard` | `checkerboard.js` | 12 | `(ctx, w, h)` |
| `wireClipboardAndDrop` | `clipboard-and-drop.js` | 31 | `({container, saveState, createLayer, renderLayerPanel, composite, handleImportedImage, uiModule})` |
| `buildThumbnail` | `composite-helpers.js` | 23 | `(layers, imgW, imgH, offsets, maxDim, quality) => string\|null` |
| `buildMergedMaskCanvas` | `composite-helpers.js` | 64 | `(layers, imgW, imgH) => canvas\|null` |
| `layerHasAdjustments` | `layer-helpers.js` | 10 | `(layer) => boolean` |
| `layerNeedsPixelPass` | `layer-helpers.js` | 20 | `(layer) => boolean` |
| `adjustmentsKey` | `layer-helpers.js` | 41 | `(adj) => string` |
| `defaultAdjParams` | `layer-helpers.js` | 53 | `(type) => object` |
| `isMaskCanvasEmpty` | `layer-helpers.js` | 97 | `(canvas) => boolean` |
| `isLayerEmpty` | `layer-helpers.js` | 114 | `(layer) => boolean` |
| `relTime` | `layer-helpers.js` | 124 | `(ts) => string` |
| `createLayerPanelRenderer` | `layer-panel.js` | 54 | `(deps) => {render}` |
| `createHistoryPanel` | `history-panel.js` | 25 | `({undo, redo}) => {toggleHistoryPanel, refreshHistoryPanelIfOpen, jumpToHistory}` |
| `wireKeyboardShortcuts` | `keyboard-shortcuts.js` | 55 | `(deps)` |
| `computeSnap` | `snap.js` | 25 | `(layer, nx, ny, ctx) => {x, y, guides[]}` |
| `cursorForHandle` | `snap.js` | 102 | `(id) => string` |
| `wireSliderUx` | `slider-ux.js` | 23 | `({registerDocClickAway})` |
| `createShortcutsPopover` | `shortcuts-popover.js` | 15 | `() => {toggleShortcuts, isOpen}` |
