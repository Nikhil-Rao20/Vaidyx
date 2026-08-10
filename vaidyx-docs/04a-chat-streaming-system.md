# 04a - Chat & Streaming System

Deep-dive into the Vaidyx frontend chat pipeline: how user messages are sent,
streamed via SSE, rendered incrementally, and post-processed.

---

## 1. File Overview

| File | Lines | Role |
|------|------:|------|
| `chat.js` | 6007 | Main orchestrator -- submit handling, SSE reader loop, stream state management |
| `chatRenderer.js` | 2811 | DOM rendering -- `addMessage`, footers, metrics, model pricing, tool-block stripping |
| `chatStream.js` | 298 | SSE event helpers -- UI-control dispatch, background-stream notifications |
| `streamingRenderer.js` | 206 | Incremental DOM renderer -- freeze finalized blocks, re-render only the live tail |
| `streamingSegmenter.js` | 190 | Pure-logic markdown segmenter -- decides where to split finalized vs. live text |
| `composerArrowUpRecall.js` | 171 | ArrowUp/ArrowDown prompt history recall on the composer textarea |
| `assistant.js` | 475 | Personal Assistant sidebar/settings -- session management, check-ins, tool config |

---

## 2. Chat System Architecture

### 2.1 Module Relationships

```
chat.js (orchestrator)
  |-- imports chatRenderer.js     (addMessage, displayMetrics, stripToolBlocks, etc.)
  |-- imports chatStream.js       (handleUIControl, notifyStreamComplete)
  |-- imports streamingRenderer   (createStreamRenderer -- live incremental render)
  |-- imports composerArrowUpRecall (wireArrowUpRecall)
  |-- imports sessions.js, storage.js, ui.js, markdown.js, spinner.js,
  |   presets.js, fileHandler.js, search.js, document.js, emailInbox.js,
  |   codeRunner.js, slashCommands.js, researchSynapse.js, tts-ai.js
```

### 2.2 Key Global State (chat.js)

| Variable | Purpose |
|----------|---------|
| `isStreaming` | Boolean flag -- true while an SSE reader loop is active |
| `currentAbort` | The `AbortController` for the active fetch |
| `currentAccumulated` | Raw text accumulated so far (for stop-button rendering) |
| `currentHolder` | The `.msg.msg-ai` DOM element being streamed into |
| `_activeStreams` | `Map<sessionId, {abortCtrl, holder, query, startedAt}>` |
| `_backgroundStreams` | `Map<sessionId, {status, accumulated, abortCtrl, ...}>` for background tabs |
| `_streamSessionId` | Session ID of the currently active foreground reader |
| `_sendInFlight` | Guards against double-submits between click and stream start |
| `_stallWatchdog` | Interval that probes the server when the stream goes silent for 60s |
| `_autoNudges` | Counter for automatic recovery handshakes (capped at 3) |

### 2.3 Delegation Pattern

`chat.js` delegates rendering to `chatRenderer.js` via variable aliases:

```javascript
var addMessage       = chatRenderer.addMessage;
var stripToolBlocks  = chatRenderer.stripToolBlocks;
var createMsgFooter  = chatRenderer.createMsgFooter;
var displayMetrics   = chatRenderer.displayMetrics;
var _buildSourcesBox = chatRenderer.buildSourcesBox;
var _buildImageBubble = chatRenderer.buildImageBubble;
```

---

## 3. Message Flow

### 3.1 User Sends a Message (`handleChatSubmit`, line 989)

1. **Guard checks** -- re-click guard (`_sendInFlight`), compare mode, streaming queue
2. **Slash command intercept** -- if message starts with `/`, dispatch via `slashCommands.js`
3. **Session resolution** -- adopt existing session, materialize pending session, or auto-create via `/api/default-chat`
4. **API key guard** -- warn if message looks like `sk-...` / `gsk_...`
5. **User bubble** -- `addMessage('user', ...)` renders immediately (optimistic)
6. **File uploads** -- `fileHandlerModule.uploadPending()` uploads attachments, returns IDs
7. **Document context** -- auto-saves active document, injects selection context
8. **Build FormData** -- assembles: `message`, `session`, `selected_model`, `selected_endpoint_url`, `mode` (chat/agent), toggles (`use_web`, `use_research`, `allow_bash`, `use_rag`, `incognito`), `preset_id`, `workspace`, `attachments`, `active_doc_id`, `active_email_uid`, etc.
9. **POST to `/api/chat_stream`** -- with `X-Tz-Offset` and `X-Tz-Name` headers
10. **SSE reader loop** -- processes streamed events (see Section 3.2)

### 3.2 SSE Reader Loop (line 2200)

The loop reads chunks from `res.body.getReader()`, splits on newlines, and dispatches by event type:

| SSE `data` field | Handler |
|------------------|---------|
| `json.delta` | Appends text to `accumulated`/`roundText`, calls `_renderStream()` |
| `json.thinking: true` | Wraps delta in `<think>` tags, shows live thinking UI |
| `json.type === 'tool_start'` | Creates agent-thread node with wave animation |
| `json.type === 'tool_output'` | Finalizes tool node (check/cross icon, output details, diff) |
| `json.type === 'tool_progress'` | Updates tool node label (e.g., "Reading 47 lines") |
| `json.type === 'agent_step'` | New round -- freezes current text, prepares new bubble |
| `json.type === 'agent_prep'` | Shows "Preparing agent" thinking spinner |
| `json.type === 'generated_image'` | Appends image bubble via `_appendGeneratedImageBubble` |
| `json.type === 'research_progress'` | Updates research timer/synapse visualization |
| `json.type === 'doc_stream_open/delta'` | Streams document content to editor panel |
| `json.type === 'ui_control'` | Dispatched to `chatStream.handleUIControl()` |
| `json.type === 'ask_user'` | Renders multiple-choice card via `chatRenderer.renderAskUserCard()` |
| `json.metrics` | Stores for final `displayMetrics()` call |
| `json.sources` | Builds collapsible sources box |
| `json.context_percent` | Updates context header ring |
| `[DONE]` | Breaks the loop, triggers final render |

### 3.3 Final Render (after `[DONE]`)

1. Strip tool blocks from accumulated text
2. Full markdown render via `markdownModule.processWithThinking()`
3. Code highlighting via `hljs.highlightElement()`
4. Append sources box, findings box, RAG sources
5. Display metrics footer (tok/s, cost, context %)
6. Refresh context header ring
7. TTS auto-play if enabled
8. Drain queued requests (`_drainQueuedAgentRequests`)

---

## 4. Chat Rendering (`chatRenderer.js`)

### 4.1 `addMessage(role, content, modelName, metadata)` (line 2295)

Handles two distinct paths:

**Agent multi-bubble** (metadata has `tool_events`):
- Iterates `round_texts` and `tool_events` by round number
- Creates `.msg-ai` bubbles for text rounds, `.agent-thread` containers for tool rounds
- Connects them with `.has-top` / `.has-bottom` CSS classes for timeline lines
- Tool nodes show: icon, tool name, status, output details, diffs, screenshots

**Standard single-bubble**:
- Creates `.msg-user` or `.msg-ai` wrapper
- Sets role label with model color (HSL hash of model name) and provider logo
- Renders markdown with `markdownModule.processWithThinking()`
- Strips tool invocation blocks, vision descriptions, file markers
- Adds attachment cards, sources boxes, variant navigation

### 4.2 `stripToolBlocks(text)` (line 918)

Removes tool syntax from displayed text using these patterns:
- `[TOOL_CALL]...[/TOOL_CALL]` markers
- Exec fence blocks (dynamically loaded from `/api/tools`)
- XML tool calls (`<tool_call>`, `<function_call>`, `<invoke>`)
- DeepSeek DSML markup
- Raw OpenAI-style JSON function calls
- Qwen role markers (`<|assistant|>`, `<|end|>`)
- Tool result narration

### 4.3 `displayMetrics(messageElement, metrics)` (line 1862)

Renders a clickable metrics label in the message footer showing tok/s or cost.
Click opens a popup with: model, input/output tokens, speed, time, prep time,
cost, session total, context usage bar with compact button.

### 4.4 Model Pricing

`MODEL_INFO` (line 492) contains per-million-token pricing for 50+ models across
Anthropic, OpenAI, DeepSeek, Google, Mistral, xAI, Meta, Qwen, Cohere,
Perplexity, MiniMax, Kimi, Microsoft, Nvidia. Local endpoints (localhost, LAN,
Tailscale CGNAT, Docker names) are detected by `isLocalEndpoint()` and excluded
from cost tracking.

### 4.5 Other Key Exports

| Function | Line | Purpose |
|----------|------|---------|
| `createMsgFooter` | 1548 | Copy, edit, regen, shorten, explain, fork, delete buttons |
| `createUserMsgFooter` | 1760 | Edit, delete, copy, resend buttons for user messages |
| `buildSourcesBox` | 951 | Collapsible web/research sources with domain links |
| `buildFindingsBox` | 1006 | Collapsible raw research findings with summaries |
| `buildRagSourcesBox` | 987 | Collapsible RAG document sources with similarity % |
| `buildImageBubble` | 1257 | Generated image with download, attach, edit, gallery, delete |
| `buildAttachCards` | 86 | Attachment cards with image previews, OCR buttons, file icons |
| `renderAskUserCard` | 2169 | Multiple-choice / free-text card for agent `ask_user` events |
| `roleTimestamp` | 901 | Timestamp span for message headers |
| `applyModelColor` | 669 | HSL color + provider logo on role labels |

---

## 5. Streaming Pipeline

### 5.1 `streamingRenderer.js` -- Incremental DOM Renderer

Creates a renderer instance per streaming message via `createStreamRenderer(contentEl, { render, hljs })`.

**Architecture**: splits the DOM into finalized (frozen) blocks and a live tail,
separated by an invisible comment node `<!--tail-->`:

```
[ finalized block ] [ finalized block ] <!--tail--> [ live tail ]
```

Key methods:

| Method | Line | Purpose |
|--------|------|---------|
| `update(fullText)` | 148 | Main entry -- freezes new finalized blocks, re-renders tail |
| `freeze(src)` | 55 | Renders markdown, highlights code, inserts before tail marker |
| `renderTail(tailText)` | 63 | Re-renders the still-growing trailing block |
| `appendOpenFence(tailText, fence)` | 85 | Streams code in append-mode (text node append, no re-parse) |
| `fadeNewText(container, prevLen)` | 109 | Wraps new text in `<span class="token-new">` for fade-in CSS |
| `finalize()` | 187 | Freezes remaining content, removes tail marker |
| `fullRender(fullText)` | 135 | Fallback: `contentEl.innerHTML = render(fullText)` |

**Degradation**: if anything throws, the renderer latches into `degraded = true`
and falls back to full re-render on every token.

### 5.2 `streamingSegmenter.js` -- Pure Markdown Segmenter

Determines the safe split point between finalized and live text.

**Core contract**: `render(text.slice(0, n)) + render(text.slice(n)) === render(text)`

| Function | Line | Purpose |
|----------|------|---------|
| `splitFinalized(text, render, committedLen)` | 133 | Returns safe freeze offset |
| `findBoundaries(text, fromOffset)` | 52 | Scans for blank-line and fence-close boundaries |
| `cutIsRenderSafe(before, after, render)` | 117 | Verifies split equivalence by comparing rendered output |
| `describeOpenFence(text)` | 171 | Returns `{lang, contentStart}` for unterminated code fences |

Boundaries come in two types:
- **After closed fence** (`afterClosedFence: true`): unconditionally safe
- **Blank-line boundary**: verified via `cutIsRenderSafe()` before freezing

### 5.3 `chatStream.js` -- SSE Event Helpers

| Function | Line | Purpose |
|----------|------|---------|
| `handleUIControl(uiData)` | 16 | Dispatches AI-driven UI events (toggle, set_mode, switch_model, set_theme, create_theme, highlight, open_panel, research_started, open_email_reply) |
| `notifyStreamComplete(sessionId, query)` | 223 | Browser notification when background stream finishes |
| `insertStreamDoneToast(sessionId, query)` | 246 | In-chat clickable toast for background completion |
| `notifyResearchComplete(sessionId, query)` | 271 | Browser notification for deep research completion |

---

## 6. Message Recall (`composerArrowUpRecall.js`)

| Function | Line | Purpose |
|----------|------|---------|
| `getUserMessagesFromChatHistory(root)` | 12 | Collects user messages from `#chat-history` (newest first) |
| `getLastUserMessageFromChatHistory(root)` | 36 | Returns most recent user message |
| `wireArrowUpRecall(composer, getUserMessages, options)` | 46 | Wires ArrowUp/ArrowDown on the composer |

Behavior: ArrowUp walks older prompts, ArrowDown walks newer / returns to blank.
Ignores modifier keys, IME composition, and ghost autocomplete. Resets on manual
typing. Stores recall index in `composer.dataset.vaidyxRecallIndex`.

---

## 7. Assistant Handling (`assistant.js`)

The Personal Assistant is a specially-flagged CrewMember with a pinned session.

| Function | Line | Purpose |
|----------|------|---------|
| `openAssistantChat()` | 23 | Fetches session ID from `/api/assistant/session`, calls `selectSession()` |
| `openAssistantSettings()` | 401 | Opens settings modal with name, personality, timezone, model, tools, check-ins |
| `_saveSettings(payload)` | 45 | `PATCH /api/assistant/settings` |
| `_runCheckInNow(taskId)` | 66 | `POST /api/assistant/run/{taskId}` |
| `_ensureHeaderAffordances(sessionId)` | 422 | Adds gear icon to chat header when assistant session is active |
| `_renderSettingsBody(body, data, tzList)` | 139 | Renders full settings form with tool groups, character picker, endpoint/model dropdowns |

Tool groups defined in `TOOL_GROUPS` (line 122): Email, Calendar & Notes,
Knowledge, Code, Documents, AI & Models, System.

---

## 8. API Endpoints Called

### From `chat.js`

| Endpoint | Method | Context |
|----------|--------|---------|
| `/api/chat_stream` | POST | Main chat submission (SSE response) |
| `/api/chat/stop/{sessionId}` | POST | Stop streaming / cancel server-side run |
| `/api/chat/stream_status/{sessionId}` | GET | Probe stale local stream |
| `/api/session/{id}/compact` | POST | Context compaction |
| `/api/session/{id}/context` | GET | Context header ring data |
| `/api/session/{id}/mark-stopped` | POST | Mark message as stopped |
| `/api/session/{id}/delete-messages` | POST | Delete message pair |
| `/api/session/{id}/edit-message` | POST | Edit AI message content |
| `/api/session/{id}/update-last-meta` | POST | Persist variant metadata |
| `/api/session/{id}/context_info` | GET | Real context length for model popup |
| `/api/default-chat` | GET | Default model/endpoint for auto-session |
| `/api/rewrite` | POST | Rewrite AI response (SSE) |
| `/api/research/cancel/{sessionId}` | POST | Cancel deep research |
| `/api/research/report/{sessionId}` | GET | Visual research report |
| `/api/research/spinoff/{sessionId}` | POST | Create follow-up chat from research |
| `/api/document` | POST | Import file to document library |
| `/api/documents/import-pdf` | POST | Import PDF attachment |
| `/api/upload/{id}` | GET | Fetch attachment file |
| `/api/upload/{id}?thumb=1` | GET | Fetch thumbnail |
| `/api/client-perf` | POST | Client performance telemetry |
| `/api/models` | GET | List model endpoints |
| `/api/model-endpoints/probe-local` | GET | Probe local endpoint status |

### From `chatRenderer.js`

| Endpoint | Method | Context |
|----------|--------|---------|
| `/api/tools` | GET | Load tool IDs for exec-fence regex |
| `/api/upload/{id}/vision` | GET/PUT | Read/write OCR text for image attachments |
| `/api/gallery/{id}` | DELETE | Delete generated image |
| `/api/session/{id}/compact` | POST | Context compaction from ring popup |

### From `assistant.js`

| Endpoint | Method | Context |
|----------|--------|---------|
| `/api/assistant/session` | GET | Get/create assistant session |
| `/api/assistant/settings` | GET/PATCH | Read/write assistant configuration |
| `/api/assistant/available-timezones` | GET | List timezone options |
| `/api/assistant/run/{taskId}` | POST | Trigger check-in now |
| `/api/assistant/run-status/{taskId}` | GET | Poll check-in status |
| `/api/model-endpoints` | GET | List endpoints for settings dropdown |
| `/api/model-endpoints/{id}/models` | GET | List models for endpoint |
| `/api/presets` | GET | Presets for character picker |
| `/api/presets/templates` | GET | Templates for character picker |

---

## 9. Key Functions Reference

### chat.js

| Function | Line | Purpose |
|----------|------|---------|
| `init(apiBase)` | 693 | Initialize module, wire slash commands, arrow recall |
| `handleChatSubmit(e)` | 989 | Main submit handler (500+ lines) |
| `abortCurrentRequest(stopServer)` | 4042 | Abort active stream, optionally stop server |
| `compactCurrentChatContext()` | 219 | Compact context via API |
| `refreshChatContextHeader(reason)` | 241 | Refresh context pill in header |
| `updateSubmitButton(state, btn)` | 731 | Animate send/stop button transitions |
| `hasActiveStream(sessionId)` | 574 | Check if SSE reader is active for session |
| `queueStreamingComposerRequest()` | 954 | Queue message while streaming |
| `deleteMessage(msgElement)` | 5460 | Delete user+AI pair from chat and server |
| `editAIMessage(msgElement)` | 5601 | Inline edit with textarea overlay |
| `rewriteWith(aiMsgElement, instruction)` | 5689 | Rewrite via `/api/rewrite` SSE |
| `regenerateFrom(msgElement)` | ~5300 | Resend from a specific message |
| `forkFrom(msgElement)` | ~5400 | Fork conversation at a message |
| `_renderStream()` | 2097 | Live streaming render (per-token) |
| `_tryAutoRecover(holder, accumulated, sessionId)` | 4078 | Auto-recovery handshake |
| `_probeStaleLocalStream()` | 4152 | Detect dead local streams |

### chatRenderer.js

| Function | Line | Purpose |
|----------|------|---------|
| `addMessage(role, content, modelName, metadata)` | 2295 | Render message in chat history |
| `stripToolBlocks(text)` | 918 | Remove tool syntax from display text |
| `createMsgFooter(msgElement)` | 1548 | AI message action buttons |
| `createUserMsgFooter(msgElement)` | 1760 | User message action buttons |
| `displayMetrics(messageElement, metrics)` | 1862 | Render metrics + context ring |
| `buildSourcesBox(sources, type, expanded)` | 951 | Collapsible sources |
| `buildAttachCards(attachments)` | 86 | Attachment card elements |
| `renderAskUserCard(payload, options)` | 2169 | Multiple-choice card |
| `shortModel(name)` | 586 | Truncate model name for display |
| `applyModelColor(roleEl, modelName)` | 669 | HSL color + provider logo |
| `getModelCost(modelName, inputTokens, outputTokens)` | 766 | Calculate token cost |
| `isLocalEndpoint(url)` | 783 | Detect local/self-hosted endpoints |

### streamingRenderer.js

| Function | Line | Purpose |
|----------|------|---------|
| `createStreamRenderer(contentEl, {render, hljs})` | 29 | Factory for streaming renderer |

### streamingSegmenter.js

| Function | Line | Purpose |
|----------|------|---------|
| `splitFinalized(text, render, committedLen)` | 133 | Safe freeze boundary |
| `describeOpenFence(text)` | 171 | Detect unterminated code fence |

### chatStream.js

| Function | Line | Purpose |
|----------|------|---------|
| `handleUIControl(uiData)` | 16 | AI-driven UI manipulation dispatch |
| `notifyStreamComplete(sessionId, query)` | 223 | Background stream notification |

### composerArrowUpRecall.js

| Function | Line | Purpose |
|----------|------|---------|
| `wireArrowUpRecall(composer, getUserMessages, options)` | 46 | Wire prompt recall |
| `getUserMessagesFromChatHistory(root)` | 12 | Collect user messages |

### assistant.js

| Function | Line | Purpose |
|----------|------|---------|
| `openAssistantChat()` | 23 | Navigate to assistant session |
| `openAssistantSettings()` | 401 | Open settings modal |
