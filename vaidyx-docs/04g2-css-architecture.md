# CSS Architecture

The entire Vaidyx front-end is styled through a single monolithic file:
`/static/style.css` (~41,100 lines). There is no CSS preprocessor, no
CSS-in-JS, and no component-scoped stylesheets. Every selector lives in this
one file, organized into commented sections that follow the logical structure
of the application.

---

## 1. CSS Custom Properties (Design Tokens)

All theme colors and a few layout values are declared as CSS custom properties
on `:root` (lines 17-68). These act as the single source of truth for the
entire UI palette.

### Core tokens

| Token | Dark default | Purpose |
|-------|-------------|---------|
| `--bg` | `#282c34` | Page / body background |
| `--fg` | `#9cdef2` | Primary text color |
| `--panel` | `#111` | Card / sidebar / modal surfaces |
| `--border` | `#355a66` | Borders and dividers |
| `--red` | `#e06c75` | Accent / brand color (used pervasively) |
| `--green` | `#50fa7b` | Success indicator |
| `--warn` | `#f0ad4e` | Warning indicator |

### Syntax-highlight tokens

Code blocks use a separate set of tokens (`--hl-*`) so the code theme stays
independent of the app theme:

`--hl-bg`, `--hl-fg`, `--hl-keyword`, `--hl-string`, `--hl-comment`,
`--hl-function`, `--hl-number`, `--hl-builtin`, `--hl-variable`, `--hl-params`

### Semantic tokens

Status colors (`--color-error`, `--color-success`, `--color-warning`,
`--color-danger`, `--color-recording`, `--color-muted`, `--color-accent`) and
select-element tokens (`--select-*`) are also on `:root`.

A warm accent (`--accent-warm: #d19a66`) is available for secondary emphasis.
Many components also reference `--accent-primary` or `--accent` with fallbacks
to `--red`, allowing per-user accent color overrides.

---

## 2. Theme System

### Dark / Light toggle

Dark is the default theme. The light theme is activated by adding the class
`light` to the root element (`<html class="light">`). The `:root.light`
selector (lines 70-90) overrides every token:

```
--bg: #f5f5f5    --fg: #2b2b2b    --panel: #fff    --border: #bbb
```

Syntax-highlight tokens also flip to darker hues that read well on white.

### Frosted glass variant

A second visual layer, `body.theme-frosted` (lines ~40197-40306), applies a
translucent `backdrop-filter: blur(24px) saturate(170%)` to every major
surface (sidebar, modals, dropdowns, doc/research/cookbook panes). All
panels become semi-transparent via `color-mix(in srgb, var(--panel) 32%,
transparent)` and gain subtle inner-highlight box-shadows. This works in
both dark and light modes since it reads from the same CSS custom properties.

### Animated backgrounds

Five decorative background patterns can be applied to the body: `dots`,
`synapse`, `perlin-flow`, `petals`, and `sparkles` (lines ~197-222). Each
is a CSS-only animation layered behind the main UI.

---

## 3. Layout System

### Top-level structure

The body is `display: flex; height: 100dvh` with two children:

1. **Sidebar** (`.sidebar`) -- fixed at 240px wide, `flex-shrink: 0`, with a
   draggable resize handle for user-adjustable width.
2. **Chat container** (`.chat-container`) -- `flex: 1`, fills remaining space.

A 48px-wide icon rail (`.icon-rail`) can replace the full sidebar on narrow
viewports or when the sidebar is collapsed.

### Chat area layout

`.chat-history` centers messages with `max-width: var(--chat-max, 800px)` and
`margin: 0 auto`. Messages (`.msg`) are flex-column children.
`.msg-user` aligns right; `.msg-ai` aligns left.

### Container queries

The chat input bar (`.chat-input-bar`) uses `container-type: inline-size` and
`@container` rules to progressively shrink controls as the bar narrows. This
provides component-level responsiveness independent of the viewport width.

The email reader header uses `container-name: emailreader` with `@container`
breakpoints at 450px and 380px to restructure the action-button cluster from a
single row into a 2-row wrapped grid, then into an overlay layout.

Document panes use `container-name: docpane` for similar breakpoint behavior.

### Modal / window system

Modals (`.modal`) are full-viewport overlays. `.modal-content` provides the
framed window. Modals support minimize, dock-left, dock-right, and tile-snap
states through CSS classes. An edge-docking system (lines ~15840-16500) pins
document and email panes to the left or right edge of the viewport.

---

## 4. Key Component Sections

The file is organized into commented sections, roughly in this order:

| Lines (approx.) | Section |
|-----------------|---------|
| 1-68 | `:root` custom properties |
| 70-90 | Light theme overrides |
| 92-150 | Reset, base styles, `@font-face` |
| 153-222 | Density, UI scale, background patterns |
| 225-1450 | Sidebar, icon rail, hamburger, sidebar sections |
| 1450-1900 | List items, form elements, session management |
| 1888-2290 | Chat container, chat history, welcome screen, messages |
| 2290-3000 | Chat input bar, mode toggle, send button |
| 3000-3700 | Model picker, overflow menu |
| 4200-4500 | Code block buttons (copy/edit/run), toast notifications |
| 5000-8000 | Gallery editor (image editing tools) |
| 8000-8700 | Compare tool, print styles, components, spinners |
| 8700-9500 | Markdown heading styles, thinking sections, sources |
| 10000-14000 | Notes, tasks, calendar |
| 14000-16000 | Admin panel, MCP tool toggles, provider management |
| 16000-17000 | Document library, email library, edge docking |
| 17000-20000 | Gallery system, image viewer |
| 20000-24000 | Cookbook (model download, serve, hardware fitting) |
| 24000-30000 | Gallery editor mobile responsive |
| 30000-32000 | Group chat, email document type, email inbox |
| 32000-39000 | Calendar UI, research panel |
| 39000-40200 | Deep Research, color picker, PDF export, signatures |
| 40200-40600 | Frosted glass theme, emoji, iOS zoom fix |
| 40600-41132 | Cookbook scheduling, ask-user cards, workspace picker, diagnostics log |

### Naming conventions

- Feature-scoped BEM-like prefixes: `.ge-*` (gallery editor), `.research-*`,
  `.cookbook-*`, `.email-*`, `.cal-*`, `.doc-*`, `.adm-*`, `.hwfit-*`
- State classes: `.active`, `.collapsed`, `.running`, `.done`, `.error`,
  `.dismissed`, `.just-checked`
- Animation trigger classes: `.email-auto-done-flash`, `.note-card-flash`,
  `.dock-chip-in`, `.chip-long-press-pulse`

---

## 5. Responsive Design

### Viewport breakpoints

| Breakpoint | Target |
|-----------|--------|
| `max-width: 768px` | Primary mobile breakpoint (sidebar hides, modals go full-screen, grids stack) |
| `max-width: 640px` | Tight mobile (ask-user cards, some padding reductions) |
| `max-width: 600px` | Secondary mobile (cookbook, research chip scrolling, serve icons hidden) |
| `max-width: 520px` | Narrow mobile (email inline images, some controls rearranged) |
| `max-height: 380px` | Landscape phones |
| `max-height: 500px` | Short viewports |
| `max-height: 650px` | Medium-height viewports |

### Container queries

Used alongside viewport media queries for component-level responsiveness:

- `.chat-input-bar` -- shrinks controls as container narrows
- `emailreader` -- restructures action buttons at 450px and 380px container widths
- `docpane` -- adjusts email reader header layout at 460px

### Mobile patterns

- Bottom-sheet slide-ups (`.ge-controls`, resize/edge/save menus) for touch targets
- Horizontal scroll strips with hidden scrollbars for chip rows
- `@media (hover: none) and (pointer: coarse)` for iOS auto-zoom prevention
  (all text inputs bumped to 16px on touch devices)
- `100dvh` / `90dvh` for safe-area-aware modal heights

---

## 6. Animations

The file defines 50+ `@keyframes` animations. They fall into several categories:

### Structural transitions (domino cascades)

Sidebar sections and overflow menus use staggered entrance/exit animations
with CSS custom property `--i` for per-item delay:

```css
@keyframes section-domino-in {
  from { opacity: 0; transform: translateY(-6px); }
  to   { opacity: 1; transform: translateY(0); }
}
/* Applied with: animation-delay: calc(var(--i, 0) * 30ms) */
```

The same pattern is used for `overflow-item-in`, `overflow-item-out`,
`mp-domino-in` (model picker), and `adm-ep-just-added-glow`.

### Button state animations

The send button has five distinct animation states:
- `btn-launch` -- rocket launch on send
- `btn-land` -- landing after completion
- `btn-spin-in` / `btn-spin-out` -- processing spinner
- `siren-icon` -- error/alert state
- `quarter-turn` -- 90-degree rotation tick

### Breathing / pulse animations

Many indicators use subtle breathing/pulse effects:
`pulse-recording`, `rail-notes-pulse`, `email-notif-breathe`,
`research-badge-breathe`, `cookbook-srv-pulse`, `research-dot-pulse`,
`email-card-unread-breathe`

### Loading indicators

`dots`, `loading-bounce`, `thinking-dots`, `spin` (360-degree rotation),
`whirlpool-spin` + `whirlpool-burst` (combined spinner effect),
`email-skeleton-shimmer` (gradient shimmer for skeleton screens)

### Micro-interactions

`check-pop` / `check-unpop` (checkbox toggle), `toastCheckPop` +
`toastCheckDraw` (toast notification entrance), `code-copy-pulse` (code
copy feedback), `fadeSlideIn` (general entrance), `note-card-flash-anim`
(link target highlight)

---

## 7. Font System

### Self-hosted fonts

Two font families are loaded via `@font-face` (lines ~112-148) from local
woff2 files under `/static/fonts/`:

1. **Fira Code** -- Monospace font used for code blocks, the chat composer,
   and technical UI elements. Three weights: 300 (Light), 400 (Regular),
   600 (SemiBold).

2. **OpenDyslexic** -- Accessibility-focused font, available as an option in
   user settings. Two weights: 400 (Regular), 700 (Bold).

### Font stacks

- **Code**: `'Fira Code', ui-monospace, monospace` (referenced via
  `var(--mono)` in some contexts)
- **System**: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`
  (used in email reader body for native emoji rendering)
- **Emoji**: The email reader body appends `"Apple Color Emoji",
  "Segoe UI Emoji", "Noto Color Emoji", "Twemoji Mozilla"` with
  `font-variant-emoji: emoji`

### Monochrome emoji

Project-wide emoji (outside email content) are rendered as monochrome line
icons (lines ~40312-40325). The `.emoji` class uses a CSS mask filled with
`currentColor`:

```css
.emoji {
  background-color: currentColor;
  -webkit-mask: var(--em) center / contain no-repeat;
  mask: var(--em) center / contain no-repeat;
}
```

This ensures emoji tint to the current theme color rather than rendering as
colorful system glyphs.

---

## 8. Density & UI Scale

### Density system

Three density levels are controlled by root-level classes:

- **Default** -- Standard spacing (no class needed)
- `.density-compact` -- Tighter padding, smaller gaps, reduced font sizes
  on sidebar items and list elements
- `.density-spacious` -- Larger padding and gaps throughout

### UI scale

The `.ui-scale-125` class applies `zoom: 1.25` to the root element for users
who want a magnified interface. Compensating `height: calc(100dvh / 1.25)`
is applied to prevent the zoomed content from overflowing the viewport.

---

## 9. Accessibility Styles

### Reduced motion

`@media (prefers-reduced-motion: reduce)` blocks are placed throughout the
file (not consolidated into one block). Every breathing animation, shimmer,
pulse, and entrance animation is disabled or reduced when this preference is
active. Key examples:

- Research badge breathing animation -> `animation: none`
- Email skeleton shimmers -> `animation: none`
- Email card removing transitions -> reduced to `opacity 0.08s`
- Research pane synapse glow -> `opacity: 0.4` (static)
- Email unread dot breathing -> `animation: none`

### iOS focus-zoom prevention

A dedicated section (lines ~40553-40601) uses `@media (hover: none) and
(pointer: coarse)` to bump all text input font sizes to 16px on touch devices,
preventing iOS Safari's automatic zoom-on-focus behavior.

### High-contrast patterns

The `color-mix(in srgb, ...)` function is used extensively (~hundreds of
occurrences) to create transparent overlays that maintain contrast ratios
regardless of the underlying surface. Hover states, disabled states, and
selection highlights all derive from the theme's `--fg` or `--accent` tokens
mixed with transparency, ensuring they adapt correctly across dark, light,
and frosted-glass themes.

### Print / PDF export

A `@media print` block (lines ~8290-8336) hides the sidebar, input bar,
topbar, buttons, and other interactive chrome. Only the chat history content
is printed, with adjusted margins and font sizes.

### OpenDyslexic font

The availability of OpenDyslexic as a user-selectable font (loaded via
`@font-face`) provides an accessibility option for users with dyslexia.

---

## 10. Notable Patterns

### color-mix usage

The `color-mix(in srgb, ...)` CSS function is the dominant approach for
creating semi-transparent colors throughout the codebase. Rather than
hardcoded `rgba()` values, the pattern `color-mix(in srgb, var(--fg) 12%,
transparent)` ensures overlays adapt to theme changes. This is used for
hover backgrounds, disabled states, border tints, and box shadows.

### Per-category theming (Research)

Research job cards use a `data-category` attribute to set a `--cat-color`
CSS variable per card. Category colors (product: blue, comparison: gold,
howto: green, landscape: purple, factcheck: red) cascade into headings,
badges, hero banners, and report body styles.

### Skeleton screens

Email inbox and reader use shimmer-based skeleton loading screens with
gradient-animated placeholder bars (`email-skeleton-shimmer` keyframes),
providing visual feedback during data loading.

### Bottom-sheet pattern (mobile)

On mobile, tool controls, menus, and panels that are normally positioned
inline or as dropdowns transform into fixed bottom-sheet slide-ups with
`border-radius: 12px 12px 0 0`, a grab-handle pseudo-element, and the
`ge-controls-slide-up` animation. A `.dismissed` class allows swipe-to-hide.
