# 04g - Odysseus HTML Structure

Reference for the static HTML files that define the Odysseus UI.

---

## 1. Main Application (`static/index.html`)

### Head: Bootstrap and Theme Restoration

Before any CSS or module loads, inline scripts (nonce-gated via `{{CSP_NONCE}}`) execute to:

- Read `odysseus-theme` from localStorage and apply all CSS custom properties (bg, fg, panel, border, red, advanced overrides, syntax highlighting colors) to `:root`.
- Restore saved font family, density class, UI text-size scale, and sidebar mode (full / mini / off) so there is no visual flash on load.
- Apply background pattern class on `<body>` if one was saved.
- Swap the favicon SVG and page title per route (`/calendar`, `/notes`, `/cookbook`, `/email`, `/memory`, `/gallery`, `/tasks`, `/library`).
- Generate a per-route PWA manifest blob for "Add to Home Screen."

### Loading Overlay

```
#app-loader  (fixed fullscreen, z-index 99999)
  #loader-wave  (ASCII wave animation: dot + block chars, 9-frame loop at 150ms)
```

Auto-dismissed after 5 seconds or when the app removes it.

### DOM Hierarchy (major sections)

```
body
  #app-loader                    Loading splash
  #memory-modal .modal           Brain modal (memories/skills/settings)
  #theme-modal .modal            Theme customization popup
  #mobile-backdrop               Overlay for mobile sidebar
  #mobile-menu-btn               Hamburger for mobile
  #hamburger-btn                 Desktop sidebar toggle
  #icon-rail                     Vertical icon rail (left side)
  nav#sidebar                    Left sidebar navigation
  main#chat-container            Chat area (entire right pane)
    #welcome-screen              New-chat landing with logo and tips
    #chat-history                Message log (role="log")
    #attach-strip                File attachment thumbnails
    .chat-input-bar              Unified input area
    #custom-preset-modal         Prompt / Persona / Group modal
  #scroll-bottom-btn             Scroll-to-bottom FAB
  #rename-session-modal          Session rename dialog
  #cookbook-modal                 Cookbook (model catalog)
  #settings-modal                Full settings panel
  #search-overlay                Ctrl+K command palette
  #toast                         Toast notification area
```

### Icon Rail (`#icon-rail`)

Static core actions at top, tool launchers in the middle, settings at bottom:

| ID | Purpose |
|---|---|
| `rail-search-btn` | Search conversations (Ctrl+K) |
| `rail-new-session` | New chat |
| `rail-delete-session` | Delete session |
| `rail-chats` | Chat ready indicator (dynamic) |
| `rail-documents` | Documents indicator (dynamic) |
| `rail-calendar` | Calendar |
| `rail-compare` | Compare |
| `rail-cookbook` | Cookbook |
| `rail-research` | Deep Research |
| `rail-email` | Email |
| `rail-gallery` | Gallery |
| `rail-archive` | Library |
| `rail-memory` | Brain |
| `rail-notes` | Notes |
| `rail-tasks` | Tasks |
| `rail-theme` | Theme |
| `rail-settings` | Settings |

### Sidebar (`nav#sidebar`)

```
#sidebar
  .sidebar-resize-handle
  .sidebar-header
    #sidebar-toggle-btn           Hamburger
    .sidebar-brand                "Odysseus" brand link
  .sidebar-inner
    #sidebar-new-chat-btn         New Chat action
    #sidebar-search-btn           Search action
    #sessions-section             Chat history
      #session-list               Dynamic session entries
      #session-actions-dropdown   Context menu (rename/delete/memory)
      #session-bulk-bar           Bulk select controls
    #email-section                Email sidebar
    #tools-section                Tools listing
      tool-memory-btn .. tool-theme-btn  (12 tool entries)
  #sidebar-user-bar               User avatar + name + settings cog
```

### Chat Container (`main#chat-container`)

```
#chat-container .welcome-active
  h1.a11y-visually-hidden         "Odysseus" (screen reader only)
  .chat-top-bar
    #incognito-indicator          Nobody mode indicator
    .chat-meta-overlay            Model name, export menu, context pill
  #welcome-screen                 Logo + subtitle + tips + Nobody button
  #chat-history                   Message log
  #attach-strip                   Attachment previews
  .chat-input-bar
    .chat-input-top
      #message-ghost              Ghost/autocomplete overlay
      #message                    Main textarea
      #plan-mode-status           Plan mode indicator
      #model-picker-wrap          Model picker dropdown
    #pinned-tools-bar             Pinned tools strip
    .chat-input-bottom
      .chat-input-left            Tool toggles (overflow, web, shell, indicators)
      .chat-input-right           Agent/Chat mode toggle + send/new button
  #chat-form                      Hidden form element
```

### Memory Modal (`#memory-modal`)

Four tabs: Browse, Skills, Add, Settings.

| Tab | Panel key | Key elements |
|---|---|---|
| Browse | `browse` | `#memory-list`, `#memory-search`, `#memory-sort-btn`, `#memory-tidy-btn`, `#memory-select-btn`, `#memory-bulk-bar` |
| Skills | `skills` | `#skills-list`, `#skills-search`, `#skills-sort`, `#skills-audit-btn`, `#skills-bulk-bar` |
| Add | `add` | `#new-memory-input`, `#memory-import-btn`, `#memory-export-btn`, `#skill-import-url`, `#new-skill-title`, `#new-skill-problem`, `#new-skill-solution` |
| Settings | `settings` | `#auto-memory-toggle`, `#auto-skills-toggle`, `#auto-approve-skills-toggle`, `#skill-confidence-slider`, `#skill-max-input` |

### Theme Modal (`#theme-modal`)

Two tabs: Themes (browse) and Customize.

**Browse tab** (`#theme-tab-browse`): `#themeGrid` (default themes), `#themeUserGrid` (user themes).

**Customize tab** (`#theme-tab-customize`):
- Color pickers: `clr-bg`, `clr-fg`, `clr-panel`, `adv-sidebarBg`, `clr-border`, `clr-red`
- Advanced sections: chat bubbles, sidebar, input/prompt area, code blocks, controls, custom fonts
- Color Harmony generator: `#harmony-accent`, `#harmony-type`, `#harmony-mode`, `#harmony-generate-btn`
- Font/Layout: `#theme-font-select`, `#theme-density-select`, `#theme-text-size-select`, `#theme-frosted-toggle`
- Background effect: `#theme-bg-pattern-select`, `#theme-bg-effect-color`, `#theme-bg-intensity`, `#theme-bg-size`
- Save/Share: `#theme-save-name`, `#theme-import-btn`, `#theme-export-btn`

### Settings Modal (`#settings-modal`)

Sidebar navigation with 12 tab panels:

| Tab key | Title | Section |
|---|---|---|
| `services` | Add Models | AI |
| `added-models` | Added Models | AI |
| `ai` | AI Defaults | AI |
| `search` | Search | AI |
| `integrations` | Integrations | Comms |
| `email` | Email | Comms |
| `reminders` | Reminders | Comms |
| `appearance` | Appearance | UX |
| `shortcuts` | Shortcuts | UX |
| `account` | Account | Account |
| `tools` | Agent Tools | Admin only |
| `users` | Users | Admin only |
| `system` | System | Admin only |

### Other Modals

- `#rename-session-modal` -- Session rename dialog with `#session-name-input`
- `#cookbook-modal` -- Model catalog browser
- `#custom-preset-modal` -- Prompt / Persona / Group chat configuration (3 tabs: inject, character, group)
- `#search-overlay` -- Ctrl+K command palette with `#search-input` and `#search-results`

---

## 2. Login Page (`static/login.html`)

Self-contained single-page login with no external dependencies beyond theme.js.

### Structure

```
body
  main.card
    h1.logo                      Boat SVG + "Odysseus" wordmark
    #setupNote                   First-time setup message (hidden by default)
    #error                       Error display (role="alert")
    form#authForm
      #username                  Username input (with #rememberToggle dot)
      #password                  Password input (with #pwToggle eye)
      #confirmGroup              Confirm password (hidden, shown for signup/setup)
      #submitBtn                 Sign In / Create Account / Verify
    #toggleArea                  Sign up / Sign in toggle link
  footer.version-label           Version display (fetched from /api/version)
```

### Modes

The form operates in three modes controlled by `setMode()`:
- **login** -- Standard sign-in
- **signup** -- New account creation (shows confirm password, toggle link)
- **setup** -- First-time admin account creation (shows confirm password, setup note)

### Theme Bootstrap

An inline script reads `odysseus-theme` from localStorage and applies base palette + advanced overrides. A random background pattern is chosen from 7 options (dots, synapse, rain, constellations, petals, sparkles, embers) and applied on each page load. A deferred module import of `theme.js` starts the canvas-based effects.

### 2FA Support

When the server returns `requires_totp`, a TOTP input field is dynamically injected into the form, and the submit button changes to "Verify."

---

## 3. Design Variant Pages

### `static/modal-control-variants.html`

A standalone design exploration page showing **5 modal close/minimize button styles**:

| Variant | Class | Description |
|---|---|---|
| A | `.v1` | Soft bordered circles |
| B | `.v2` | macOS traffic-light hover (yellow/red on hover) |
| C | `.v3` | Glass capsule group (buttons inside a pill) |
| D | `.v4` | Ghost controls (only visible on hover) |
| E | `.v5` | Subtle liquid glass (gradient + shadow) |

Each variant renders inside a `.card > .modal > .header` with `.ctrl.min` and `.ctrl.close` pseudo-element buttons. This is a design reference page, not loaded by the app.

### `static/wave-variants.html`

Design exploration for the **app loading wave animation** (the ship-on-wave splash). Shows 6 variants:

| Variant | Description |
|---|---|
| A (dot boat) | Minimal dot riding above the wave |
| B (hollow dot) | Circle character above the wave |
| C (mast dot) | Vertical line + dot above wave |
| D (tiny sail) | `/\` sail shape + dot |
| E (tiny hull) | `/\ \_/` boat shape |
| F (no boat) | Pure wave, no ship marker |

Uses the same 9-frame ASCII wave animation (`block chars`) as the real loader. Includes a larger "splash scale preview" at the bottom.

### `static/whirlpool-variants.html`

Design exploration for the **loading spinner** (whirlpool). Shows 4 canvas-rendered spiral variants:

| Variant | Mode | Description |
|---|---|---|
| A (Current) | `current` | Fixed spiral rotation with visible head loop |
| B (Soft Tail) | `softTail` | Head fades through loop |
| C (Breathing) | `breathing` | Subtle radius pulse hides reset |
| D (Continuous Flow) | `flow` | Moving dash window, no fixed head snap |

Interactive controls: Size (14-42px), Speed (650-1700ms), Turns (18-38). Each variant renders via `requestAnimationFrame` with spiral point calculations.

---

## 4. Documentation Site (`docs/index.html`)

A standalone marketing/landing page for the Odysseus project.

### Structure

```
nav (sticky)
  .brand                         Boat logo + "Odysseus"
  .nav-links                     Features, Testimonials, How, Get started, GitHub

header.hero
  #hero-flow                     Perlin flow field canvas (particle streams)
  .hero-logo                     Large boat SVG + "Odysseus" wordmark
  h1                             "Your own AI workspace, running on your hardware."
  .hero-cta                      Get started + GitHub buttons

section#features                 9 capability cards (Chat, Tools, Cookbook, Email, Research, Compare, Memory, Skills, Privacy)
section#testimonials             Carousel with 4 testimonial cards (including Polyphemus gag)
section (terminal)               Typewriter-animated "origin prompt" terminal
section#previews                 8 hover-expand video preview panels
section#how                      "How it started" with background video
section#start                    Get started with git clone codeblock
footer
```

### Interactive Features

- **Perlin flow field**: Canvas-rendered particle system in hero (cyan/coral/teal colors)
- **Typewriter effect**: Terminal types out the origin prompt, loops every 4 seconds
- **Preview panels**: Hover/tap to expand; videos autoplay on hover; swipe on mobile
- **Testimonial carousel**: Click/swipe/arrow navigation; Polyphemus card shakes
- **Domino reveal**: IntersectionObserver fades sections in as they scroll into view
- **Terminal controls**: Minimize (pill mode) and close (with reopen button)

---

## 5. Script Loading Order

### External Libraries (loaded in `<head>`)

1. `highlight.min.js` (defer) -- Syntax highlighting
2. KaTeX CSS (media="print", flipped to "all" on load) + KaTeX JS (async) -- Math rendering
3. Mermaid JS (async) -- Diagram rendering

### Application Stylesheets

1. `style.css?v=20260723tasksbulkfeedback1` -- Main stylesheet
2. Modulepreload hints: `app.js`, `chat.js`, `ui.js`, `sessions.js`, `markdown.js`

### Application Modules (bottom of body, in order)

```
storage.js       -- localStorage/sessionStorage abstraction
ui.js            -- DOM utilities and UI helpers
markdown.js      -- Markdown rendering
dragSort.js      -- Drag-and-drop session reordering
sessions.js      -- Session management
memory.js        -- Memory system
skills.js        -- Skills system
tourHints.js     -- First-run tour hints
tourAutoplay.js  -- Tour autoplay logic
fileHandler.js   -- File upload/drag-drop handling
voiceRecorder.js -- Voice input recording
models.js        -- Model picker and endpoint management (MUST come before app.js)
rag.js           -- RAG (retrieval-augmented generation)
presets.js       -- Prompt presets and personas
search.js        -- Search overlay (Ctrl+K)
spinner.js       -- Whirlpool loading spinner
tts-ai.js        -- Text-to-speech
document.js      -- Document editor
gallery.js       -- Image gallery
chatRenderer.js  -- Message rendering pipeline
codeRunner.js    -- In-browser code execution
chatStream.js    -- SSE streaming for chat responses
chat.js          -- Core chat logic
cookbook.js       -- Cookbook (model catalog) UI
cookbookSchedule.js -- Cookbook background schedule (non-module)
search-chat.js   -- In-chat search
theme.js         -- Theme system (colors, patterns, effects)
censor.js        -- Sensitive data blur
settings.js      -- Settings modal logic
assistant.js     -- Background assistant/tasks
app.js           -- Main app init (MUST be second-to-last)
init.js          -- Final initialization
a11y.js          -- Accessibility enhancements
```

Service worker registration: `sw.js` (inline script, last).

---

## 6. Font and Icon Loading

### Fonts

All fonts are self-hosted (no Google/CDN dependencies):

**index.html** loads Inter (UI font):
- `Inter-Regular.woff2` (400)
- `Inter-Medium.woff2` (500)
- `Inter-SemiBold.woff2` (600)

**login.html** loads Fira Code (monospace):
- `FiraCode-Regular.woff2` (400)
- `FiraCode-SemiBold.woff2` (600)

All use `font-display: swap` for progressive rendering.

Additional fonts available via theme selection:
- `OpenDyslexic` (accessibility)
- System font stacks: `system-ui`, `Georgia`/serif
- Custom user fonts from `static/fonts/custom/`

### Icons

Odysseus uses **no icon font library**. All icons are inline SVGs embedded directly in the HTML. The boat logo is a custom SVG path used as:
- Inline favicon (data URI SVG, dynamically recolored to match accent)
- Apple touch icon (`/static/icons/icon-192.png`)
- PWA manifest icon (blob URL SVG for per-route icons)

Per-route favicons use unique SVG shapes (calendar grid, envelope, lightbulb, etc.) rendered in the current theme accent color.
