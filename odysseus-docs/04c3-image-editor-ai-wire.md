# 04c3 -- Image Editor: AI Tools & Wiring

## Overview

The Odysseus image editor (`static/js/editor/`) is a canvas-based,
layer-aware photo editor with AI-powered tools.  Its architecture
separates concerns into three tiers:

1. **Build modules** -- pure DOM/HTML generators (no state, no listeners).
2. **Wire modules** -- attach event listeners and connect UI to state.
3. **AI modules** -- orchestrate server-side model calls and handle results.

`galleryEditor.js` (4386 lines) is the orchestrator that imports every
module, instantiates shared state, and calls each wire/build function with
the correct dependency bag.

---

## 1. AI Inpainting (`ai-inpaint.js`)

Three operations share one `runInpaint` core (L52):

| Button | ID | Behavior |
|---|---|---|
| **Generate** | `#ge-inpaint-run` | Fills the masked region using the user's prompt and strength slider |
| **Remove** | `#ge-inpaint-remove` | Content-aware fill; detects OpenAI vs SDXL backend and adjusts prompt/strength |
| **Outpaint** | `#ge-inpaint-outpaint` | Auto-generates a mask over transparent regions, dilates 12px inward for context |

### runInpaint flow (L52-253)

1. `buildMergedMaskCanvas()` unions every visible mask sub-layer across all
   parent layers into a single mask.
2. `dilateMask(mask, padPx)` grows the mask by `~4%` of the shortest
   dimension (min 20, max 80px) so post-gen feathering has AI content to
   fade into.
3. Flattens visible layers, base64-encodes image + dilated mask, POSTs to
   `/api/image/inpaint` with endpoint/model from the inpaint picker.
4. Drops the result as a new layer, snapshots the AI image + hard mask on
   `layer.inpaintSource` for live edge tuning, hides contributing mask
   sub-layers, and reveals the post-gen Feather + Edge Stroke sliders.

### Remove variant (L272-297)

Detects OpenAI (`api.openai.com` in URL) vs SDXL. OpenAI gets a semantic
"remove" prompt; SDXL gets a generic fill prompt at strength 0.99.

### Outpaint variant (L303-379)

Scans for alpha=0 pixels, builds a mask, dilates 12px via blur+threshold,
temporarily replaces the active mask, runs inpaint, then restores the
user's previous mask drawing.

---

## 2. AI Background Removal (`ai-rembg.js`)

Exports `wireRembgAndSharpen()` (L40).

### Bg Remove flow (L60-98)

1. Optionally builds a selection hint mask from the active wand/lasso
   selection (`buildSelectionHintMask`, L203-227).
2. POSTs to `/api/image/remove-bg` via the shared `applyImageTool` runner.
3. Polls for up to 60 frames for the new layer, then binds the live edge
   tuner and auto-hides underlying layers.

### Live edge-cleanup tuner (L103-167)

Snapshots the pristine cutout on arrival. Slider tweaks rebuild alpha from
that snapshot without re-running the model:

- **Grow > 0**: blur + low threshold (32) = dilate alpha (grow edge).
- **Grow < 0**: blur + high threshold (200) = erode alpha (shrink edge).
- **Feather > 0**: blur entire layer (alpha + RGB) to soften edge and hide
  residual color fringing.

### Sharpen (L44-54)

Slider + button; calls `applyImageTool('/api/image/sharpen', {amount})`.

---

## 3. AI Models (`ai-models.js`)

Exports `wireAIModelSelectors()` (L64). Populates three dropdown surfaces:

| Select | ID / Selector | Purpose |
|---|---|---|
| Gen | `#ge-ai-model` | Text-to-image generation |
| Inpaint | `#ge-ai-inpaint` | Image+mask edit |
| Per-tool | `select.ge-tool-model[data-ge-tool-model]` | Harmonize, upscale, style |

### Model capability classifier (`modelCaps`, L34-62)

Heuristic on model ID + endpoint name. Returns `{gen, inpaint}` booleans.
Recognizes DALL-E-2/3, GPT-Image, SDXL/SD3/Flux/Playground/PixArt/Kandinsky
families. Rejects text-only models (GPT-4, Claude, Llama, etc.).

### Sentinel option

Every dropdown ends with "+ Serve a model in Cookbook..." which opens the
Cookbook model-serve UI and reverts the picker to its prior value.

### Auto-refresh (L259-272)

Re-fetches `/api/model-endpoints` on dropdown mousedown (debounced 3s) so
models served mid-edit appear without reopening the editor.

---

## 4. AI Tool Runner (`ai-tool-runner.js`)

Exports `createApplyImageTool()` (L39) -- a factory that returns an
`applyImageTool(endpoint, payload, layerName, btn, opts)` function.

Used by Sharpen, Harmonize, Upscale, Style, Bg-Remove, and any tool that
flattens the document, POSTs a PNG, and drops the result as a new layer.

### Orchestration (L45-146)

1. Locks button width, swaps label for busy text + whirlpool spinner.
2. Resolves endpoint+model from the per-tool picker or global fallback.
3. Flattens layers, base64-encodes, POSTs to the endpoint.
4. On success: decodes PNG, creates new layer, composites, refreshes panel.
5. On failure: detects "needs img2img server" or "package not installed"
   and surfaces an action-toast that opens Cookbook.

---

## 5. AI Misc Tools (`ai-tools-misc.js`)

Exports `wireAIToolsMisc()` (L34). Four tools plus a helper:

| Tool | Endpoint | Notes |
|---|---|---|
| **Harmonize** | `/api/image/harmonize` | Reinhard color transfer on body mask + optional seam inpaint |
| **Canvas 2x/4x** | none (client) | In-browser bicubic resampling, no server |
| **AI Upscale** | `/api/image/upscale-local` | Real-ESRGAN, updates canvas dimensions |
| **Style Transfer** | `/api/gallery/style-transfer` | img2img with prompt+strength, uses FormData |
| **Add Empty Layer** | none | Helper returned for keyboard shortcut use |

Harmonize requires a non-base layer. Canvas upscale resizes all layers.

---

## 6. Build System (`build/`)

Pure DOM generators -- no state, no listeners. Return HTML strings or DOM
elements; the caller attaches all event wiring.

### `build/controls.js`

`controlsHTML({color, brushSize, wandTolerance})` (L12) returns the right-
panel innerHTML. Sections for each tool (brush, eraser, clone, lasso, wand,
SAM, inpaint, sharpen, rembg, import, harmonize, style) are all rendered
with `display:none`; the tool-switch handler shows the active one.

`layerPanelHTML()` (L386) returns the layers header with Merge Down, Merge
All, Flatten Copy, and + Add buttons.

### `build/toolbar.js`

`buildToolbar({currentTool, onSelectTool, onClearSelection})` (L16) creates
the left-side tool palette. Tools: Move(V), Crop(C), Transform(T),
Brush(B), Eraser(E), Clone(K), Lasso(L), Wand(W), SAM, Inpaint(M),
Bg Remove, Sharpen(S). AI tools get a star marker. Selection tools get a
clear badge.

### `build/topbar.js`

`buildTopbar()` (L11) creates the top bar with: undo/redo/history, zoom
controls (fit/1:1/+/-), canvas size badge, Image menu (resize, rotate,
flip), Filter menu (Gaussian/Zoom blur), shortcuts button, Import button,
and Save dropdown (save/save-as/download/project save/load).

### `build/right-panel.js`

`buildRightPanel({controlsHTML, layerPanelHTML})` (L29) creates the right
panel wrapper. Handles mobile bottom-sheet swipe-to-dismiss, slider value
chip repositioning, layer panel peek/expand gestures, and horizontal drag-
resize with localStorage persistence.

### `build/popups.js`

- `shortcutsPopupHTML()` (L9) -- keyboard shortcuts cheatsheet.
- `historyPanelHTML(icon)` (L71) -- undo history sidebar.
- `canvasSizePromptHTML()` (L89) -- new canvas / resize modal.

### `build/transform-popup.js`

`transformPopupHTML()` (L10) -- W/H/rotation inputs with aspect lock.
`attachSpinRepeat(root)` (L72) -- hold-to-repeat on +/- buttons with
acceleration after 1.5s.

---

## 7. Wire System (`wire-*.js`)

Attach event listeners to the DOM IDs created by build modules.

### `wire-topbar.js`

`wireTopbar(deps)` (L55) wires undo/redo/history, save dropdown (reparented
to `<body>` to escape transform containing blocks), zoom buttons, export/
download/project, edge popup, and global outside-click coordination.

### `wire-topbar-menus.js`

`wireTopbarMenus(deps)` (L40) wires Image menu (resize, rotate, flip,
fill), Filter menu (blur), Resize popup. Returns `{applyResize,
resizeCustomPrompt}` for keyboard shortcuts.

### `wire-topbar-overflow.js`

`wireTopbarOverflow(deps)` (L18) hides AI model controls when the topbar
overflows (ResizeObserver). Updates the canvas-size badge.

### `wire-inpaint-controls.js`

`wireInpaintControls(deps)` (L40) wires pre-gen strength slider, post-gen
live edge tuner (rAF-throttled), mask vis/invert/clear, paint/erase toggle,
and mask tint picker (synced between inpaint section and topbar).

### `wire-selection-controls.js`

`wireSelectionControls(deps)` (L46) wires lasso (feather, grow, invert,
delete, copy, mask) and wand (tolerance with rAF live retune, mode toggle,
feather, grow, vis, clear, invert, delete, copy, mask, rembg).

### `wire-merge-buttons.js`

`wireMergeButtons(deps)` (L71) wires Flatten Copy (new merged layer, keeps
originals), Merge All (collapse visible layers into lowest visible), and
Merge Down (merge active into layer below). Also exports
`mergeLayerDownAtIndex()` (L42) for programmatic use.

### `wire-import.js`

`wireImport(deps)` (L30) wires four import entry points: topbar, File,
Clipboard (async API), Gallery picker (`/api/gallery/library?limit=50`).
Returns `{handleImportedImage}` for drag-drop reuse.

---

## 8. Gallery Editor Integration (`galleryEditor.js`)

The 4386-line orchestrator. Key responsibilities:

### Imports (L1-109)

Imports ~40 modules: UI utilities (spinner, dragSort, colorPicker,
modalManager), editor tools (move, crop, lasso, wand, clone, transform,
stroke), build modules, wire modules, AI modules, FX modules (pixel-pass,
histogram, filters), and helpers (snap, harmonize-masks, composite-helpers).

### State & Shared Functions (L111-830)

- `createLayer(name, w, h)` (L580) -- layer factory with adjustments, masks.
- `_getSelectedAIEndpoint(type)` (L230) -- parses `base_url::model_id` from
  dropdown values.
- `createApplyImageTool()` instantiated at L271 as `_applyImageTool`.
- AI Quick Edit command box (L333-573) -- collapsible text input with
  suggestions that parses natural language into tool invocations (rotate,
  flip, remove bg, upscale, denoise, sharpen, enhance face, style).
- `composite()` (L831) -- central render loop compositing all layers.
- Undo/redo with `MAX_HISTORY=20` (L225).

### _buildEditor (L2890-3548)

The main DOM assembly function, called from `openEditor()`:

1. Builds toolbar via `_buildToolbar()` with the tool-switch handler.
2. Builds topbar via `_buildTopbar()`.
3. Creates canvas area with main canvas + transform overlay + AI command box.
4. Wires canvas events (mouse, touch, pinch-zoom, pan).
5. Builds right panel via `buildRightPanel()`.
6. Calls every wire function in sequence, passing dependency bags:
   - `wireSliderUx`, `wireTopbar`, `wireTopbarOverflow`, `wireTopbarMenus`
   - `wireInpaintControls`, `wireInpaintButtons`, `wireStrokeToolSliders`
   - `wireRembgAndSharpen`, `wireImport`, `wireAIToolsMisc`
   - `wireSelectionControls`, `wireMergeButtons`
   - `wireAIModelSelectors`, `wireKeyboardShortcuts`, `wireClipboardAndDrop`

### openEditor / closeEditor (L4068, ~L4300)

`openEditor(imageUrl, imageId, presetSize, displayName, draftId)` resets
state, calls `_buildEditor()`, then initializes canvas from URL, preset
dims, or saved draft. `closeEditor()` tears down listeners and clears
state. Exports: `{openEditor, closeEditor, isEditorOpen, exportPNG,
exportToGallery, downloadPNG}`.

---

## 9. Key Functions (with line numbers)

### AI Modules

| Function | File | Line |
|---|---|---|
| `wireInpaintButtons()` | `ai-inpaint.js` | 45 |
| `runInpaint()` | `ai-inpaint.js` | 52 |
| `wireAIModelSelectors()` | `ai-models.js` | 64 |
| `modelCaps()` | `ai-models.js` | 34 |
| `loadAIModels()` | `ai-models.js` | 92 |
| `wireRembgAndSharpen()` | `ai-rembg.js` | 40 |
| `bindRembgLiveTuner()` | `ai-rembg.js` | 103 |
| `buildSelectionHintMask()` | `ai-rembg.js` | 203 |
| `createApplyImageTool()` | `ai-tool-runner.js` | 39 |
| `wireAIToolsMisc()` | `ai-tools-misc.js` | 34 |

### Build Modules

| Function | File | Line |
|---|---|---|
| `controlsHTML()` | `build/controls.js` | 12 |
| `layerPanelHTML()` | `build/controls.js` | 386 |
| `buildToolbar()` | `build/toolbar.js` | 16 |
| `buildTopbar()` | `build/topbar.js` | 11 |
| `buildRightPanel()` | `build/right-panel.js` | 29 |
| `shortcutsPopupHTML()` | `build/popups.js` | 9 |
| `canvasSizePromptHTML()` | `build/popups.js` | 89 |
| `transformPopupHTML()` | `build/transform-popup.js` | 10 |
| `attachSpinRepeat()` | `build/transform-popup.js` | 72 |

### Wire Modules

| Function | File | Line |
|---|---|---|
| `wireTopbar()` | `wire-topbar.js` | 55 |
| `closeOtherTopbarMenus()` | `wire-topbar.js` | 47 |
| `wireTopbarMenus()` | `wire-topbar-menus.js` | 40 |
| `wireTopbarOverflow()` | `wire-topbar-overflow.js` | 18 |
| `wireInpaintControls()` | `wire-inpaint-controls.js` | 40 |
| `wireSelectionControls()` | `wire-selection-controls.js` | 46 |
| `wireMergeButtons()` | `wire-merge-buttons.js` | 71 |
| `mergeLayerDownAtIndex()` | `wire-merge-buttons.js` | 42 |
| `wireImport()` | `wire-import.js` | 30 |

### galleryEditor.js

| Function | Line |
|---|---|
| `createLayer()` | 580 |
| `_getSelectedAIEndpoint()` | 230 |
| `composite()` | 831 |
| `_buildEditor()` | 2890 |
| `_wireAiCommandBox()` | 396 |
| `openEditor()` | 4068 |
| `closeEditor()` | ~4300 |
| `isEditorOpen()` | 4373 |
