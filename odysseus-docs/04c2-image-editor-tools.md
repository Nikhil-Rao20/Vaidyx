# Image Editor Tools

Tools, filters, effects, and mask utilities that power the Odysseus image editor's
canvas interactions. All modules live under `static/js/editor/` and follow a
factory pattern: each exports a `create*()` function that receives a dependency
bag and returns handler objects (begin/drag/end or tryBegin/tryContinue/tryEnd).

---

## 1. Drawing Tools

### 1.1 Stroke Pipeline (`stroke-pipeline.js`)

Central paint engine shared by brush, eraser, inpaint, and clone tools.
`strokeTo(x, y)` dispatches per-tool rendering onto the active layer or mask
canvas.

| Tool    | Composite Op      | Target Canvas             | Notes                                   |
|---------|--------------------|---------------------------|-----------------------------------------|
| Brush   | `source-over`      | Layer (or mask sub-layer) | Respects opacity, flow, softness blur   |
| Eraser  | `destination-out`  | Layer (or mask sub-layer) | Alpha = opacity x flow                  |
| Inpaint | `source-over`/`out`| Mask canvas               | White = inpaint area; Ctrl+Alt toggles  |
| Clone   | Custom stamp loop  | Layer canvas              | Radial-gradient soft mask per stamp     |

- **Line interpolation**: Brush/eraser draw `moveTo -> lineTo` segments.
  Clone walks last-to-current in half-brush steps for continuous stamp overlap
  (L34-69, `cloneStrokeTo`).
- **Mask-aware routing**: When a mask sub-layer is active, brush/eraser paint
  white (add) or destination-out (carve) onto the mask canvas (L88-94).
- **Softness**: Applied as a CSS `blur()` filter on the stroke context (L109-111).

### 1.2 Stroke Tool (`tools/stroke.js`)

Orchestrates begin/continue/end lifecycle around the shared pipeline.
`tryBegin(e)` handles brush, eraser, and inpaint tools (L55). For inpaint, it
auto-creates a mask sub-layer if none exists (L65-88), ensuring a totally
empty canvas can accept strokes.

`strokeLabel(tool)` at L37 produces undo labels: "Brush stroke", "Eraser stroke",
"Paint mask", or "Erase mask".

### 1.3 Clone Tool (`tools/clone.js`)

Alt-click (desktop) or double-tap (mobile) sets the sample source; drag stamps
from source to target with a constant offset.

- **Source pick**: Alt or double-tap sets `cloneSourceX/Y` and the source layer
  ID (L48-54). Double-tap uses 500 ms / 40 px tolerance for finger drift (L39).
- **Snapshot**: At stroke start, the source layer's pixels are snapshotted into
  an offscreen canvas so the brush never cascades cloned data (L67-72).

### 1.4 Stroke Tool Sliders (`stroke-tool-sliders.js`)

Shared slider wiring for opacity, flow, and softness across eraser, brush, and
clone tools. `wireStrokeToolSliders()` at L60 wires all three tool groups via
`wireToolSliders(prefix, fields)` (L24). Preview swatches animate:
- Opacity: swatch opacity fades (L32).
- Flow: border cycles dashed/dotted by denseness (L41-43).
- Softness: radial-gradient inner stop tweens hard-disk to soft-falloff (L54-55).

---

## 2. Selection Tools

### 2.1 Lasso (`tools/lasso.js`)

Freehand polygon selection with begin/drag/end handlers. Each drag appends a
point and redraws a dashed-white outline with translucent red fill (L34-48).
Lines are scaled by `1 / state.zoom` so dashes look consistent at all zoom
levels (L42-43). End requires at least 3 points or the selection is cleared
(L53-56).

### 2.2 Lasso Mask (`tools/lasso-mask.js`)

Pixel and path helpers for the lasso polygon:

- **`lassoOffsetPoints(points, grow)`** (L18): Shifts each vertex along the
  outward normal by `grow` pixels. Computes polygon winding to flip normals
  correctly regardless of draw direction (L23-27).
- **`getLassoPath(ctx, points)`** (L52): Traces the polygon as a canvas path
  (moveTo + lineTo + closePath) for caller to stroke/fill.
- **`buildLassoMask(points, w, h, offX, offY, feather, grow)`** (L74):
  Builds a selection mask canvas with optional feathering and grow/shrink.
  - Hard mask rasterized from polygon (L78-86).
  - Grow/shrink via blur + threshold (L91-107).
  - Feather via two-pass chamfer distance transform (L137-152): forward pass
    propagates distances top-left to bottom-right, reverse pass bottom-right
    to top-left. Edge pixels get reduced alpha proportional to distance (L163).

### 2.3 Magic Wand (`tools/wand.js`)

Single-click flood-fill selection. Has only a `click` handler (no drag).
Modifier keys override the persistent `wandMode`:
- Shift = add to selection (L31).
- Alt = subtract from selection (L32).
- Click inside existing selection with no modifier = deselect (L35-41).

### 2.4 Flood Fill (`tools/flood-fill.js`)

Pure function `floodFillMask(src, w, h, seedX, seedY, tolerance)` (L21).
Iterative 4-connected fill using an explicit stack (no recursion). Tolerance
is squared and scaled to RGBA distance space (max ~195k at tolerance 100,
L30). Returns a white-opaque mask canvas for visited cells.

---

## 3. Transform Tools

### 3.1 Move (`tools/move.js`)

Drag a layer around the canvas. Ctrl/Cmd held = snap to canvas edges/center
and other visible layers' edges/center via `computeSnap()` (L63-68). Snap
guides are stored in `state.activeSnapGuides` for overlay rendering.

### 3.2 Crop (`tools/crop.js`)

Drag-rect canvas crop with:
- **Shift-lock**: Aspect ratio captured on first Shift-held drag; resets when
  Shift is released (L66-89).
- **Move mode**: Click inside existing crop rect to reposition without
  redrawing, clamped to canvas bounds (L27-33, L46-58).
- **Visual overlay**: Dims everything outside the rect, redraws checkerboard +
  layers inside the clipped region, dashed white border (L96-118).
- Minimum 5x5 px to count as valid crop (L132).

### 3.3 Transform Drag (`tools/transform-drag.js`)

Canvas-side drag interactions for the transform tool.
`tryBegin` hit-tests handle positions; if no handle is hit but click is inside
the layer bbox, it falls through to Move (L57-65). Handle types:

| Handle | Behavior                                              |
|--------|-------------------------------------------------------|
| `tl/tr/br/bl` | Corner resize with optional Shift aspect lock  |
| `rot`  | Rotation from layer center; Shift snaps to 15 degrees |

Resize anchors the opposite corner via `transformOrigOffset` to prevent drift
(L142-149). All mutations flow through `reapplyTransform()` and sync back into
the popup inputs if open (L152-157).

### 3.4 Transform Handles (`tools/transform-handles.js`)

Pure geometry for rendering and hit-testing transform handles on the overlay canvas:

- **`syncOverlay(margin)`** (L31): Positions the overlay canvas over the main
  canvas, matching zoom and pan transforms.
- **`drawHandles(margin)`** (L118): Renders rotated bounding outline (dashed
  white + black halo), 4 corner circles, rotation knob with tether line. Hover
  state shows a red ring; active state changes fill to red (L206-220).
- **`getHandleAt(x, y)`** (L233): Hit-test returning handle ID or null.
  Threshold is `8 / state.zoom` pixels (L239).
- **`knobPosition()`** (L73): Computes rotation knob position, flipping inside
  the layer if the outside position would be off-screen or clipped.

### 3.5 Transform Session (`tools/transform-session.js`)

Full transform lifecycle management:

- **`startTransform()`** (L43): Snapshots active layer pixels, opens popup,
  fits zoom so corner handles are visible.
- **`openTransformPopup()`** (L85): Builds floating popup with W/H/Rot numeric
  inputs, aspect-lock toggle, flip buttons, and 90-degree rotation. Supports
  header-drag on both desktop and mobile (L218-311).
- **`reapplyTransform()`** (L316): Live preview from snapshot. Computes rotated
  bounding box (L327-328), draws into temp canvas with flip/rotation, recenters
  the layer to keep the pivot stable (L345-350).
- **`confirmTransform()`** (L355): Commits and clears session state.
- **`cancelTransform()`** (L366): Restores via undo and clears state.
- **Aspect lock**: Driver/follower model where the last-typed field drives and
  the other becomes read-only + visually dimmed (L108-123).

---

## 4. Filters

### 4.1 Blur Renderers (`filters/blur.js`)

Three pure renderers with signature `renderer(snap, params, dst)`:

- **`gaussianBlur(snap, {radius}, dst)`** (L24): Clamp-to-edge Gaussian. Pads
  the source with stretched edge pixels (4 strips + 4 corners, L39-47) to avoid
  transparent-edge fade, blurs the padded buffer, crops back to original size.
- **`zoomBlur(snap, {strength}, dst)`** (L68): Radial smear from canvas center.
  16 scaled copies at globalAlpha 0.18 approximate a Gaussian zoom blur.
- **`motionBlur(snap, {length, angle}, dst)`** (L98): Directional smear using
  additive (`lighter`) compositing into an offscreen accumulator. Each of N
  stamps contributes `1/N` alpha so they sum to full brightness without
  source-over wash-out (L109-110). Steps capped at 80 for performance (L105).

### 4.2 Edge Feather (`filters/edge-feather.js`)

`edgeFeather(imgData, width, hardDelete)` (L14) operates in-place on ImageData.
Uses a two-pass chamfer distance transform (L27-46) to compute each opaque
pixel's distance to the nearest transparent pixel or canvas edge. Canvas
borders are treated as boundaries (L49-55). Pixels within `width` are either
faded proportionally (`hardDelete=false`) or fully cleared (`hardDelete=true`).

---

## 5. Effects (FX)

### 5.1 Adjustment Popup System (`fx/adj-popup.js`)

Self-contained subsystem for per-layer adjustments. Supports four types:

| Type                | Params                                          |
|---------------------|-------------------------------------------------|
| Brightness/Contrast | `brightness`, `contrast` (multipliers, 1 = id)  |
| Hue/Saturation      | `hue` (degrees), `saturation` (multiplier)       |
| Levels              | `inBlack/inWhite`, `gamma`, `outBlack/outWhite`  |
| Color Balance       | `shadows/midtones/highlights` (per-channel r/g/b)|

Lifecycle: FX button -> chooser menu -> type-specific slider popup -> live
preview via `composite()` -> Apply commits to `layer.adjLayers` stack, Cancel
drops staged state.

Key implementation details:
- **`buildAdjBody()`** (L434): Renders type-specific slider UIs. Levels includes
  a histogram canvas with draggable triangle handles for input black/white/gamma.
  Color Balance uses color-tinted slider endpoints and a tone picker dropdown.
- **`wireHistogramHandles()`** (L593): Pointer-drag wiring for histogram handles.
  Gamma uses log-scale mapping (L637-639).
- **`scheduleAdjRefresh()`** (L424): rAF-throttled live preview refresh.
- **`minimiseAdjPopup()`** (L216): Docks popup into modalManager chip; click
  restores with staged state intact.
- **`editAdjLayer()`** (L251): Re-opens committed adjustment for editing.

### 5.2 Filter String Helpers (`fx/filter-string.js`)

- **`layerFilterString(adj)`** (L16): Builds a CSS `filter` string from a
  layer's adjustments object. Returns empty string at identity so composite
  can skip filtering.
- **`fxFilterToSlider(key, value)`** (L32): Converts stored multipliers
  (0..2 range) to UI slider range (-100..+100; hue uses -180..+180).

### 5.3 Histogram (`fx/histogram.js`)

`drawHistogram(canvas, layer)` (L16). Renders a luminance histogram using
Rec. 709 weights (`0.2126R + 0.7152G + 0.0722B`, L39). Down-samples to
400x400 max for performance on large images (L27-28). Bars are sqrt-scaled
so tails remain visible when the central mass dominates (L54). Draws input
black/white markers when a staged Levels adjustment is present (L61-66).

### 5.4 Pixel Pass (`fx/pixel-pass.js`)

Per-pixel adjustment engine with three entry points:

- **`applyAdjustment(srcCanvas, adj)`** (L16): Pure function. B/C and H/S use
  native CSS filter pipeline for speed (L23-36). Levels builds a 256-entry LUT
  with gamma correction (L53-58). Color Balance applies bell-curve tone weights
  (`exp(-d^2 / 2*sigma^2)`) per shadow/midtone/highlight band (L76-82),
  shifting RGB proportionally.
- **`renderLayerPixelAdjustments(layer, cacheKey)`** (L117): In-place Levels +
  Color Balance pass. Cached on `layer._adjCache` keyed by a stable signature
  so repeated composite calls are O(1) when params haven't changed.
- **`renderLayerWithAdjLayers(layer)`** (L214): Walks the layer's `adjLayers`
  stack, applying each visible adjustment in order. Skips the one currently
  being edited to avoid doubling. Result is memoised on `layer._adjFinal` keyed
  by a composite signature of all params + staged state.

---

## 6. Mask System

### 6.1 Mask Utilities (`mask-utils.js`)

- **`dilateMask(src, px)`** (L19): Dilates (positive px) or erodes (negative px)
  a binary alpha mask. Strategy: blur by `|px|`, then re-threshold (dilate cutoff
  = 8, erode cutoff = 247) (L34-35).
- **`applyInpaintFeather(layer, featherPx, edgeShiftPx)`** (L64): Re-derives an
  inpaint-result layer's alpha from its cached AI image + mask. Applies optional
  dilate/erode then Gaussian blur to the mask, draws the AI image fresh, and
  multiplies alpha via `destination-in` compositing (L85-89). Requires
  `layer.inpaintSource = { ai, mask }` cache.

### 6.2 Harmonize Masks (`harmonize-masks.js`)

Mask builders for the AI Harmonize pipeline. All are pure functions taking the
visible layer list + canvas dimensions:

- **`layerUnionAlpha(w, h, layers)`** (L34): Union of all non-base visible
  layers' alpha as binary (0/255) mask. First visible layer is treated as
  background. Returns null if fewer than 2 visible layers or all-transparent.
- **`seamMask(w, h, layers, featherPx)`** (L73): Feathered band along alpha
  edges. Blurs the union mask, applies triangular weighting peaked at mid-grey
  (picks out the alpha-edge band, L86-88), then a second softer blur. Returns
  base64 PNG for API POST.
- **`layerBodyMask(w, h, layers, featherPx)`** (L107): Feathered full shape of
  all non-base layers. Simpler than seam -- just blur the binary union. Returns
  base64 PNG.

---

## 7. Key Functions Reference

| Function | File | Line | Purpose |
|----------|------|------|---------|
| `createStrokePipeline` | `stroke-pipeline.js` | 23 | Factory for `strokeTo` + `cloneStrokeTo` |
| `strokeTo` | `stroke-pipeline.js` | 77 | Route paint by tool type |
| `cloneStrokeTo` | `stroke-pipeline.js` | 24 | Stamp-based clone paint loop |
| `createStrokeTool` | `tools/stroke.js` | 44 | tryBegin/tryContinue/tryEnd for strokes |
| `createCloneTool` | `tools/clone.js` | 21 | Clone source pick + stroke start |
| `wireStrokeToolSliders` | `stroke-tool-sliders.js` | 60 | Wire opacity/flow/softness sliders |
| `createLassoTool` | `tools/lasso.js` | 18 | Freehand polygon selection |
| `lassoOffsetPoints` | `tools/lasso-mask.js` | 18 | Offset polygon by outward normal |
| `buildLassoMask` | `tools/lasso-mask.js` | 74 | Build feathered selection mask |
| `createWandTool` | `tools/wand.js` | 23 | Magic wand flood-fill selection |
| `floodFillMask` | `tools/flood-fill.js` | 21 | 4-connected flood fill to mask |
| `createMoveTool` | `tools/move.js` | 22 | Layer drag with snap guides |
| `createCropTool` | `tools/crop.js` | 21 | Drag-rect crop with Shift-lock |
| `createTransformDragTool` | `tools/transform-drag.js` | 27 | Canvas-side resize/rotate drag |
| `syncOverlay` | `tools/transform-handles.js` | 31 | Position transform overlay canvas |
| `drawHandles` | `tools/transform-handles.js` | 118 | Render corner + rotation handles |
| `getHandleAt` | `tools/transform-handles.js` | 233 | Hit-test transform handles |
| `createTransformSession` | `tools/transform-session.js` | 39 | Full transform lifecycle |
| `reapplyTransform` | `tools/transform-session.js` | 316 | Live preview from snapshot |
| `gaussianBlur` | `filters/blur.js` | 24 | Clamp-to-edge Gaussian blur |
| `zoomBlur` | `filters/blur.js` | 68 | Radial zoom blur |
| `motionBlur` | `filters/blur.js` | 98 | Directional motion blur |
| `edgeFeather` | `filters/edge-feather.js` | 14 | Distance-based edge fade/delete |
| `createAdjPopupSystem` | `fx/adj-popup.js` | 50 | Adjustment popup factory |
| `buildAdjBody` | `fx/adj-popup.js` | 434 | Render type-specific slider UI |
| `layerFilterString` | `fx/filter-string.js` | 16 | Build CSS filter from adjustments |
| `drawHistogram` | `fx/histogram.js` | 16 | Luminance histogram renderer |
| `applyAdjustment` | `fx/pixel-pass.js` | 16 | Single adjustment pass (pure) |
| `renderLayerWithAdjLayers` | `fx/pixel-pass.js` | 214 | Walk + cache full adj stack |
| `dilateMask` | `mask-utils.js` | 19 | Dilate/erode binary mask |
| `applyInpaintFeather` | `mask-utils.js` | 64 | Re-derive inpaint alpha with feather |
| `layerUnionAlpha` | `harmonize-masks.js` | 34 | Union alpha of non-base layers |
| `seamMask` | `harmonize-masks.js` | 73 | Feathered seam-edge mask (base64) |
| `layerBodyMask` | `harmonize-masks.js` | 107 | Feathered body mask (base64) |
