# 04a2 -- Slash Commands, Autocomplete, and Markdown Rendering

Source files:

- `static/js/slashCommands.js` (6520 lines)
- `static/js/slashAutocomplete.js` (313 lines)
- `static/js/markdown.js` (1090 lines)
- `static/js/markdown/tableRow.js` (19 lines)

---

## 1. Slash Command System Architecture

### Registration

All commands live in a single `COMMANDS` object (line 5754). Each entry is keyed
by its canonical name and carries:

| Field | Purpose |
|---|---|
| `alias` | Array of alternative names (`/session` -> `chats`) |
| `category` | Grouping label used by autocomplete and `/help` |
| `help` | One-line description |
| `handler` | `async (args, ctx) => boolean` function |
| `subs` | Optional map of subcommands, each with its own handler/alias/help |
| `default` | Name of the sub to run when no sub is given |
| `hidden` | If true, excluded from `/help` output |
| `noUserBubble` | If true, dispatcher does not echo the command as a user message |
| `usage` | Usage string shown with `--help` |

### Dispatch Flow (`handleSlashCommand`, line 6277)

1. Strip the leading `/` or `!`, split on whitespace, lowercase the command token.
2. Build a context: `{ sid, esc }` (current session ID + HTML-escape helper).
3. If `--help` or `-h` is present in args, show usage text instead of running.
4. **Direct resolution** -- look up `rawCmd` in `_ALIAS_MAP` (built at line 6224
   from every command's `alias` array).
5. **Legacy alias** -- if not found, try `LEGACY_ALIASES` (line 6164), a map from
   old flat names (`/new`, `/clear`, `/web`) to `{ parent, sub }` pairs.
6. **Subcommand dispatch** -- if the resolved command has `subs`, the first arg
   is matched against sub names and sub aliases via `_resolveSubcommand` (line 6232).
   If no sub matches, the `default` sub runs.
7. **Skill invocation** -- if still unresolved, query `/api/skills/slash-catalog`
   and check whether `rawCmd` matches a published skill name (line 6384).
8. **Fuzzy match** -- Levenshtein distance (line 6242) suggests close matches
   for typos within edit-distance 2.
9. If nothing matches, return `false` -- the input passes through to the AI.

### Module Initialization (`initSlashCommands`, line 6418)

Called from `chat.js` with `{ apiBase, isStreaming }`. Sets up delegated click
handlers for the setup guide's provider chips, clickable code blocks, and the
welcome-screen `/setup` trigger link.

### Setup Wizard State Machine

The module maintains `setupMode` (line 29), a string that tracks sub-states
of the first-run onboarding wizard:

- `'endpoint-provider-first'` -- waiting for provider name or URL
- `'endpoint-key-for-provider'` -- provider chosen, waiting for API key
- `'endpoint-provider'` -- ambiguous key detected, waiting for provider clarification
- `'theme'` -- waiting for theme name
- `'features'` -- waiting for feature toggle name
- `false` -- normal mode

`handleSetupInput` (line 731) and `handleSetupWizard` (line 771) drive this
state machine. Provider detection uses `PROVIDER_PATTERNS` (line 40) and
`SETUP_PROVIDER_URLS` (line 49).

---

## 2. Complete Command List

### Chats (`/chats`, `/chat`, `/session`, `/s`) -- line 5755

| Sub | Aliases | Handler | Line | Description |
|---|---|---|---|---|
| new | create, mkdir | `_cmdSessionNew` | 955 | Create new chat session |
| delete | del, rm | `_cmdSessionDelete` | 1021 | Delete a chat (supports `all`, `-rf`) |
| archive | tar | `_cmdSessionArchive` | 1061 | Archive a chat |
| rename | mv | `_cmdSessionRename` | 1074 | Rename current chat |
| favorite | pin, important | `_cmdSessionImportant` | 1084 | Star/pin session |
| unfavorite | unpin, unimportant | `_cmdSessionUnimportant` | 1091 | Unstar session |
| fork | cp | `_cmdSessionFork` | 1098 | Fork chat keeping first N messages |
| truncate | -- | `_cmdSessionTruncate` | 1115 | Delete older messages, keep last N |
| switch | goto, cd | `_cmdSessionSwitch` | 1142 | Switch to chat by name or ID |
| sort | -- | `_cmdSessionSort` | 1156 | Auto-sort sessions into folders |
| info | stat | `_cmdSessionInfo` | 1173 | Show chat metadata |
| clear | -- | `_cmdSessionClear` | 1187 | Clear chat display |
| export | cat | `_cmdSessionExport` | 1193 | Download as md/json/txt/html |

### Toggle (`/toggle`, `/t`) -- line 5776

| Sub | Aliases | Handler | Line | Description |
|---|---|---|---|---|
| web | search, s, w | `_cmdToggleWeb` | 1217 | Toggle web search |
| bash | b, shell | `_cmdToggleBash` | 1218 | Toggle bash/shell access |
| research | r | `_cmdToggleResearch` | 1220 | Toggle deep research |
| doc | -- | `_cmdToggleDoc` | 1233 | Toggle document editor panel |
| sidebar | sb | `_cmdToggleSidebar` | 1305 | Cycle sidebar (full/mini/off) |

### Memory (`/memory`, `/m`) -- line 5799

| Sub | Aliases | Handler | Line | Description |
|---|---|---|---|---|
| list | ls | `_cmdMemoryList` | 1567 | List all memories |
| add | echo | `_cmdMemoryAdd` | 1578 | Save a new memory |
| delete | del, rm | `_cmdMemoryDelete` | 1591 | Delete memory by ID |
| search | grep | `_cmdMemorySearch` | 1630 | Search memories |

### RAG (`/rag`) -- line 5825, hidden

| Sub | Aliases | Handler | Line | Description |
|---|---|---|---|---|
| list | ls | `_cmdRagList` | 1885 | List indexed files |
| add | -- | `_cmdRagAdd` | 1902 | Add directory to index |
| remove | rm | `_cmdRagRemove` | 1917 | Remove directory from index |

### Flat Commands

| Command | Aliases | Cat. | Handler | Line | Description |
|---|---|---|---|---|---|
| workspace | ws | Agent | `_cmdWorkspace` | 1257 | Set/clear/pick agent workspace folder |
| skills | skill | Memory | `_cmdSkills` | 1645 | List, search, inspect, or run skills |
| reload-skills | reload_skills | Memory | `_cmdReloadSkills` | 1704 | Refresh slash skill catalog |
| note | n | Memory | `_cmdNote` | 1712 | Quick-save a note |
| todo | td | Productivity | `_cmdTodo` | 1806 | Add or list todos |
| event | ev | Productivity | `_cmdEvent` | 1831 | Create calendar event |
| setup | su, seutp | Getting started | `_cmdSetup` | 5082 | Add model endpoints |
| prompt | -- | Getting started | `_cmdPrompt` | 4885 | Send a random starter prompt |
| theme | -- | Settings | `_cmdTheme` | 1461 | Change/save/delete color themes |
| settings | cfg, preferences, config | Settings | `_cmdSettings` | 1439 | Open Settings panel |
| open | show | Utility | `_cmdOpen` | 1344 | Open a tool panel by name |
| cookbook | cook | Tools | `_cmdToolPanel` | 5993 | Open Cookbook panel |
| email | mail, inbox | Tools | `_cmdToolPanel` | 5998 | Open Email |
| notes | -- | Tools | `_cmdToolPanel` | 6005 | Open Notes |
| tasks | -- | Tools | `_cmdToolPanel` | 6012 | Open Tasks |
| brain | memories | Tools | `_cmdToolPanel` | 6019 | Open Brain |
| library | docs, documents | Tools | `_cmdToolPanel` | 6026 | Open Library |
| gallery | photos | Tools | `_cmdToolPanel` | 6033 | Open Gallery |
| research | -- | Tools | `_cmdToolPanel` | 6040 | Open Deep Research |
| compare | -- | Tools | `_cmdToolPanel` | 6047 | Open Compare |
| mcp | -- | Tools | `_cmdMcp` | 1544 | Show MCP server status |
| model | -- | Settings | `_cmdModel` | 1529 | Show current model |
| models | -- | Settings | `_cmdModels` | 1516 | List available models |
| search | ws, websearch | Utility | `_cmdWebSearch` | 1954 | Web search (hidden) |
| find | search-history | Utility | `_cmdSearch` | 1968 | Search all conversations (hidden) |
| stats | df | Utility | `_cmdStats` | 1989 | Database statistics (hidden) |
| usage | cost, tokens | Utility | `_cmdUsage` | 2002 | Show token/cost usage |
| compact | -- | Utility | `_cmdCompact` | 2051 | Compact older chat messages |
| sh | exec, run, shell | Utility | `_cmdShell` | 1860 | Run a shell command (hidden) |
| shortcuts | keys, keybinds, bind | Utility | `_cmdShortcuts` | 5210 | Show keyboard shortcuts (hidden) |
| help | ?, man, commands | Utility | `_cmdHelp` | 5695 | Show help (hidden) |
| ping | pong | Utility | `_cmdPing` | 5542 | Check endpoint liveness (hidden) |
| probe | test-models | Utility | `_cmdProbe` | 5574 | Test which models respond (hidden) |

### Tours

| Command | Aliases | Handler | Line |
|---|---|---|---|
| demo | tour | `_cmdDemo` | 2109 |
| tour-compare | compare-tour | `_cmdTourCompare` | 2549 |
| tour-cookbook | cookbook-tour | `_cmdTourCookbook` | 2832 |
| tour-research | research-tour | `_cmdTourResearch` | 4396 |
| tour-library | library-tour, tour-doc, etc. | `_cmdTourLibrary` | 4610 |
| tour-theme | theme-tour | `_cmdTourTheme` | 3058 |
| tour-settings | settings-tour | `_cmdTourSettings` | 3304 |
| tour-gallery | gallery-tour | `_cmdTourGallery` | 3536 |
| tour-brain | brain-tour, tour-memory | `_cmdTourBrain` | 3954 |
| tour-task-1 | tour-task, tasks-tour | `_cmdTourTask1` | 4356 |
| tour-task-2 | tour-tasks-2 | `_cmdTourTask2` | 4372 |

### Easter Eggs (all hidden)

| Command | Aliases | Handler | Line |
|---|---|---|---|
| flip | coin | `_cmdFlip` | 5330 |
| roll | dice, r | `_cmdRoll` | 5359 |
| 8ball | 8-ball | `_cmd8Ball` | 5379 |
| fortune | cookie | `_cmdFortune` | 5399 |
| odyssey | homer, quote | `_cmdOdyssey` | 5410 |
| ascii | banner | `_cmdAscii` | 5420 |
| matrix | -- | `_cmdMatrix` | 5445 |
| cowsay | moo, say | `_cmdSay` | 5482 |
| wisdom | inspire | `_cmdWisdom` | 5494 |
| uptime | -- | `_cmdUptime` | 5521 |
| color | colour | `_cmdColor` | 5680 |

### Legacy Aliases (line 6164)

Flat shortcuts that map to parent/sub pairs so old-style commands still work:

`/new` -> chats new, `/clear` -> chats clear, `/rename` -> chats rename,
`/web` -> toggle web, `/bash` -> toggle bash, `/rm` -> chats delete,
`/mv` -> chats rename, `/cd` -> chats switch, `/cp` -> chats fork,
`/cat` -> chats export, `/tar` -> chats archive, `/mkdir` -> chats new,
`/memories` -> memory list, `/forget` -> memory delete, and others.

---

## 3. Autocomplete System (`slashAutocomplete.js`)

### Overview

A lightweight popup that reads the `COMMANDS` and `LEGACY_ALIASES` registries
from `slashCommands.js` and shows a filterable list as the user types.

### Key Design Decisions

- **Excluded commands** (line 15): Easter eggs (`flip`, `roll`, `8ball`,
  `fortune`, `odyssey`, `ascii`) are hidden from autocomplete.
- **Promoted aliases** (line 20): Common shortcuts like `/new`, `/clear`,
  `/web`, `/doc` get their own rows so users find them without knowing the
  parent command.
- **Skill entries** load asynchronously from `/api/skills/slash-catalog` and
  merge into the list (line 84).

### Matching Algorithm (`_scoreMatch`, line 101)

Scores run from 0 (no match) to 1000 (exact match):

| Score | Condition |
|---|---|
| 1000 | Exact token match |
| 900 | Exact alias match |
| 500 | Token starts with query (bonus for shorter tokens) |
| 400 | Alias starts with query |
| 100 | Token contains query as substring |
| 25 | Help text contains query (minus leading `/`) |

When the query exactly matches a parent command (`/chats`), all its
subcommands are shown as a group via `_exactCommandGroupItems` (line 118).

### UI Behavior

- `_ensurePopup` (line 129): Creates the popup `div#slash-autocomplete` once.
- `_position` (line 141): Anchors above the textarea (or below if not enough
  room); width is clamped between 280 and 520px.
- `_render` (line 159): Groups items by category with header dividers.
- Max 14 visible items (`MAX_VISIBLE`, line 8).
- Keyboard: ArrowUp/Down navigate, Tab inserts, Enter inserts if not an exact
  match (otherwise submits), Escape closes.
- Initialized via `initSlashAutocomplete(textarea)` (line 191), which wires
  `input`, `focus`, `blur`, and `keydown` listeners.

---

## 4. Markdown Rendering (`markdown.js`)

### Core Pipeline: `mdToHtml(src, opts)` -- line 488

Converts markdown text to HTML. Processing order (critical for correctness):

1. **Fenced code blocks** -- Extract ` ```lang ... ``` ` blocks into
   `codeBlocks[]` placeholders. Mermaid blocks go into `mermaidBlocks[]`.
   Each code block gets copy, edit, and (for runnable languages) run buttons.
2. **Inline code spans** -- Extract `` `code` `` into `inlineCodeBlocks[]`
   placeholders, protecting contents from later passes.
3. **Entity anchor repair** -- Fix broken `[Name](#kind-<id>)` patterns the
   model often mangles in tables (lines 548-573).
4. **Images** -- `![alt](url "title")` -> `<img>` (line 577).
5. **Links** -- `[text](url)` -> `<a>` with `target="_blank"` for external,
   class `chat-link` for `#hash` links (line 583).
6. **Bare URL autolinking** -- HTTP/HTTPS URLs (line 589) and scheme-less
   domains like `techcrunch.com/ai` (line 602).
7. **HTML preservation** -- `<details>` blocks and `<a>`/`<img>` tags are
   sanitized and stored as `allowedHtmlBlocks[]` placeholders (lines 613-625).
8. **HTML escaping** -- All remaining `&`, `<`, `>` are escaped (line 628).
9. **KaTeX math** -- `\[...\]`, `\(...\)`, `$$...$$`, `$...$` delimiters,
   with Pandoc-style rules to avoid triggering on currency (lines 633-676).
10. **Pipe tables** -- Detected and rendered as `<table>` using
    `splitTableRow()` from `tableRow.js` (line 678).
11. **Horizontal rules** -- `---`, `***`, `___` (line 710).
12. **Bold/italic/strikethrough** -- `**bold**`, `*italic*`, `~~strike~~` (lines 713-714).
13. **Headers** -- `# h1` through `###### h6` (lines 717-722).
14. **Lists** -- Ordered (`1. item`), task lists (`- [x] item`), unordered
    (`- item`) (lines 725-741).
15. **Blockquotes** -- `> text` (lines 744-746).
16. **Paragraphs and line breaks** (lines 749-759).
17. **Restore placeholders** -- Allowed HTML, math, mermaid, code blocks, and
    inline code are restored in order. Uses function replacers to avoid
    `$&`/`` $` `` corruption (lines 770-794).
18. **Emoji SVG conversion** -- Unicode emoji become monochrome SVG line icons
    themed to text color (line 795).

### HTML Sanitization: `sanitizeAllowedHtml` -- line 136

Applied to preserved `<details>`, `<a>`, and `<img>` fragments before they
enter `innerHTML`. Uses a `<template>` element for inert parsing:

- Removes dangerous tags: `SCRIPT`, `IFRAME`, `OBJECT`, `EMBED`, `SVG`, `MATH`,
  `STYLE`, `FORM`, and others (line 72).
- Strips all `on*` event-handler attributes and `srcdoc` (line 113).
- Neutralizes `javascript:`, `vbscript:`, `data:` in URL attributes (line 127).
- Cleans CSS `style` for `expression()` and script URL schemes (line 118).
- Re-parses up to 4 times to reach a fixpoint, defending against mutation-XSS
  (line 145).

### Thinking Block Processing: `processWithThinking` -- line 460

Entry point for rendering AI responses. Delegates to:

- `normalizeThinkingMarkup` (line 171): Normalizes `<thought>`, `<mm:think>`,
  and Gemma `<|channel>thought` tags into standard `<think>` tags.
- `normalizePlainThinking` (line 190): Detects "stealth reasoning" -- models
  that emit raw thinking text without tags (checks for prefixes like "Let me
  think", "The user wants", etc.) and wraps it in `<think>` tags.
- `extractThinkingBlocks` (line 250): Extracts and merges all thinking blocks,
  handles edge cases (orphaned tags, empty blocks, stray openers).
- `createThinkingSection` (line 335): Renders a collapsible dropdown with
  toggle state persisted to localStorage via content hashing.

### Emoji Handling: `svgifyEmoji` -- line 414

Replaces Unicode emoji with monochrome SVG line icons (OpenMoji-black) served
via `/api/emoji/<codepoints>.svg` and rendered as CSS mask images tinted to
`currentColor`. Also expands `:shortcode:` text to emoji via
`replaceEmojiShortcodes`. Skips `<code>` and `<pre>` blocks.

### Other Exported Functions

| Function | Line | Purpose |
|---|---|---|
| `squashOutsideCode` | 801 | Collapse excess whitespace outside code fences |
| `renderContent` | 816 | Handle text or content-block arrays |
| `renderMermaid` | 831 | Initialize unprocessed Mermaid diagrams |
| `createCollapsible` | 447 | Generic collapsible section (reuses thinking CSS) |
| `hasUnclosedThinkTag` | 156 | Check for unclosed `<think>` during streaming |
| `startsWithReasoningPrefix` | 167 | Detect stealth-reasoning text patterns |

---

## 5. Table Row Handling (`markdown/tableRow.js`)

A pure function, no DOM dependency, safe for Node unit tests.

```js
export function splitTableRow(row) {
  return text
    .replace(/^\s*\|/, '')   // strip leading pipe
    .replace(/\|\s*$/, '')   // strip trailing pipe
    .split('|')              // split on pipes
    .map(cell => cell.trim());
}
```

Key design choice: intentionally-empty interior cells (`| a |  | c |`) are
preserved as empty strings rather than filtered out. The old behavior collapsed
them, misaligning columns with the header row.

Called from `mdToHtml` at line 692 during pipe-table rendering.

---

## 6. Key Utility Functions in slashCommands.js

| Function | Line | Purpose |
|---|---|---|
| `slashReply` | 308 | Render a static HTML reply bubble with copy/dismiss footer |
| `typewriterReply` | 427 | Animated character-by-character reply, returns Promise |
| `typewriterBlocksReply` | 466 | Animated block-by-block reply (used by setup guide) |
| `typewriterInto` | 592 | Typewriter into an existing DOM element |
| `maskKey` | 607 | Mask API key for display (first 6 + last 4) |
| `detectProvider` | 616 | Auto-detect provider from pasted key or URL |
| `handleSetupInput` | 731 | Process setup-mode user input (key/URL) |
| `handleSetupWizard` | 771 | Drive setup wizard sub-modes |
| `_persistMsg` | 290 | Fire-and-forget message persistence to session |
| `_slashFooter` | 391 | Build copy + dismiss footer for slash replies |
| `_loadSkillSlashCatalog` | 342 | Fetch and cache skill catalog (15s TTL) |
| `_invokeSkillByName` | 371 | POST to `/api/skills/<name>/invoke`, submit result |
| `_submitComposedMessage` | 357 | Inject text into chat input and submit |
| `_resolveSession` | 947 | Resolve short ID or name to full session UUID |
| `_buildAliasMap` | 6216 | Build flat alias -> canonical name map at module load |
| `_resolveCommand` | 6227 | Look up canonical command from typed string |
| `_resolveSubcommand` | 6232 | Match sub name or sub alias within a command |
| `_levenshtein` | 6242 | Edit distance for fuzzy matching |
| `_fuzzyMatch` | 6258 | Find close command matches within edit distance 2 |
| `_isCmd` | 6273 | Check if string starts with `/` or `!` |
| `connectDetectedSetupEndpoint` | 658 | POST to `/api/model-endpoints`, auto-start chat |

### Exports (line 6505)

Named: `handleSlashCommand`, `handleSetupInput`, `handleSetupWizard`,
`slashReply`, `typewriterReply`, `COMMANDS`, `initSlashCommands`, `isCommand`,
`getSetupMode`, `clearSetupMode`.

Default export: `slashCommands` object containing all public API functions
plus `typewriterInto`.
