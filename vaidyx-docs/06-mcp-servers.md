# MCP Servers

## 1. MCP Overview

Vaidyx ships four built-in **Model Context Protocol (MCP)** servers plus one NPX-based browser server. Each runs as an independent stdio subprocess managed by the central `McpManager` (`src/mcp_manager.py`). The MCP layer gives the AI agent live access to email, memory, RAG documents, image generation, and browser automation without baking transport-specific code into the agent loop itself.

### Built-in Python Servers

| Server ID    | Script Path                          | Display Name                | Purpose                                |
|-------------|--------------------------------------|-----------------------------|----------------------------------------|
| `email`     | `mcp_servers/email_server.py`        | Built-in: Email             | IMAP/SMTP email management             |
| `memory`    | `mcp_servers/memory_server.py`       | Built-in: Memory            | Persistent memory CRUD and search      |
| `rag`       | `mcp_servers/rag_server.py`          | Built-in: RAG               | RAG document index management          |
| `image_gen` | `mcp_servers/image_gen_server.py`    | Built-in: Image Generation  | AI image generation via OpenAI-compatible APIs |

### Built-in NPX Server

| Server ID         | Package                        | Display Name        | Purpose                |
|-------------------|--------------------------------|---------------------|------------------------|
| `builtin_browser` | `@playwright/mcp@latest`       | Built-in: Browser   | Headless browser automation via Playwright |

### Package `__init__.py`

`mcp_servers/__init__.py` is an empty file serving only as a Python package marker.

---

## 2. Server Architecture

### 2.1 Common Pattern

Every Python MCP server follows an identical structural pattern:

1. **Import the MCP SDK** -- `mcp.server.Server`, `mcp.server.stdio.stdio_server`, `mcp.types.Tool`, `mcp.types.TextContent`.
2. **Path bootstrapping** -- `sys.path.insert(0, ...)` adds the project root so that `src.*`, `core.*`, and `routes.*` modules are importable.
3. **Server instance** -- A module-level `server = Server("<name>")` object.
4. **Tool registration** -- An `@server.list_tools()` handler returns a list of `Tool` objects describing each tool's name, description, and JSON Schema inputs.
5. **Tool dispatch** -- An `@server.call_tool()` handler receives `(name, arguments)` and routes to the correct implementation function.
6. **Entrypoint** -- An `async def run()` function opens a `stdio_server()` context and hands streams to `server.run()`. The module's `if __name__ == "__main__"` block calls `asyncio.run(run())`.

### 2.2 Lazy Initialization

The memory and RAG servers use lazy initialization (a `_ensure_init()` guard called on first tool invocation) to avoid importing heavyweight managers at import time. The email server loads config on demand through `_load_config()`.

### 2.3 Owner Scoping

Both the email and memory servers implement **owner-scoped access**. Environment variables (`VAIDYX_MCP_EMAIL_OWNER`, `VAIDYX_MCP_MEMORY_OWNER`) or a `_vaidyx_owner` argument injected by the agent identify the authenticated user. When owner-scoped rows exist in the database, the server filters results to only those belonging to the current owner, preventing cross-user data leaks.

### 2.4 Fixture / Demo Mode

The email server supports a **fixture email mode**: when `data/fixture_email_messages.json` exists, the server serves canned emails from that file instead of connecting to a real IMAP server. This is used for demos and testing.

---

## 3. Available Tools

### 3.1 Email Server (`mcp_servers/email_server.py`)

**Server name:** `"email"` (line 35)

The email server is the largest MCP server (2921 lines). It exposes 15 tools for full email lifecycle management. Every tool accepts an optional `account` parameter to select a non-default mailbox by name, email address, or account ID.

#### 3.1.1 `list_email_accounts`

- **Lines:** 2110-2117 (schema), 2472-2488 (handler)
- **Description:** List the email accounts configured in Vaidyx. Returns each account's name, email address, and whether it is the default.
- **Parameters:** None required.
- **Returns:** Markdown-formatted list of configured accounts with name, email, id, and default status.

#### 3.1.2 `list_emails`

- **Lines:** 2118-2153 (schema), 2492-2565 (handler)
- **Description:** List emails from the inbox, optionally filtered to unread or unresponded. When multiple accounts exist and no `account` is specified, results are merged across all accounts sorted by date.
- **Parameters:**
  - `folder` (string, default `"INBOX"`) -- IMAP folder to check.
  - `max_results` (integer, default `20`) -- Maximum emails to return.
  - `unresponded_only` (boolean, default `false`) -- Only show emails without replies.
  - `unread_only` (boolean, default `false`) -- Only show unread emails.
  - `account` (string, optional) -- Which email account to use.
- **Implementation:** `_list_emails()` (line 969) and `_list_emails_across_accounts()` (line 1058). Uses IMAP UID SEARCH with criteria `UNSEEN`, `UNANSWERED`, or `ALL`. Integrates with the AI summary cache (`email_cache.db`) to include pre-computed summaries.

#### 3.1.3 `read_email`

- **Lines:** 2431-2458 (schema), 2672-2705 (handler)
- **Description:** Read the full content of a specific email by UID or Message-ID. Returns subject, sender, date, full body text, and attachment metadata.
- **Parameters:**
  - `uid` (string, optional) -- Email UID from `list_emails` results.
  - `message_id` (string, optional) -- RFC Message-ID header value.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_read_email()` (line 1219). Fetches full email via `BODY.PEEK[]`, extracts plain text (falling back to stripped HTML), and lists attachments. Body is capped at 8000 characters. When multiple accounts exist and no `account` is given, `_read_email_across_accounts()` (line 1276) searches all visible accounts.

#### 3.1.4 `search_emails`

- **Lines:** 2399-2430 (schema), 2647-2670 (handler)
- **Description:** Search emails by free-text query across FROM, SUBJECT, and body TEXT. Walks INBOX, Sent, and Archive by default.
- **Parameters:**
  - `query` (string, required) -- Free-text search query.
  - `folders` (array of strings, optional) -- Folders to search (default: `["INBOX", "Sent", "Archive"]`).
  - `max_results` (integer, default `20`) -- Max results per folder.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_search_emails()` (line 1089). Constructs an IMAP SEARCH command using nested OR across FROM, SUBJECT, and TEXT fields.

#### 3.1.5 `send_email`

- **Lines:** 2212-2233 (schema), 2707-2732 (handler)
- **Description:** Send a new email via SMTP. When the `agent_email_confirm` setting is enabled (the default), the email is NOT sent immediately -- it is staged as an `agent_draft` in `scheduled_emails.db` for user approval.
- **Parameters:**
  - `to` (string, required) -- Recipient email address(es), comma-separated.
  - `subject` (string, required) -- Email subject line.
  - `body` (string, required) -- Plain text body.
  - `cc` (string, optional) -- CC addresses.
  - `bcc` (string, optional) -- BCC addresses.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_send_email()` (line 1470). Routes through `_stash_agent_draft()` (line 1393) when confirmation is required, or connects via `_smtp_connect()` (line 1330) for direct send. After SMTP delivery, a copy is appended to the Sent folder via IMAP.

#### 3.1.6 `draft_email`

- **Lines:** 2234-2256 (schema), 2734-2757 (handler)
- **Description:** Create a new Vaidyx email compose draft document. Does NOT send. Creates a reviewable Document record with `language="email"` containing To/Cc/Bcc/Subject headers and body separated by `---`. Respects the user's configured writing style from Settings.
- **Parameters:**
  - `to` (string, required) -- Recipient email address(es).
  - `subject` (string, required) -- Subject line.
  - `body` (string, required) -- Draft body.
  - `cc` (string, optional) -- CC addresses.
  - `bcc` (string, optional) -- BCC addresses.
  - `title` (string, optional) -- Vaidyx document title.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_create_email_draft_document()` (line 1602). Creates Document and DocumentVersion rows in the database. Fires `document_created` event via the event bus.

#### 3.1.7 `reply_to_email`

- **Lines:** 2257-2280 (schema), 2759-2778 (handler)
- **Description:** Reply to an existing email by UID. Sends immediately (subject to the agent confirmation setting). Threads the reply with In-Reply-To and References headers, prefixes "Re:" on the subject.
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `body` (string, required) -- Reply body text.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `reply_all` (boolean, default `false`) -- Reply to all recipients.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_reply_to_email()` (line 1884). Fetches the original message, extracts threading headers, builds the reply, and calls `_send_email()`. After sending, marks the original as `\Answered`.

#### 3.1.8 `draft_email_reply`

- **Lines:** 2281-2302 (schema), 2780-2803 (handler)
- **Description:** Create an Vaidyx email reply draft document for an existing email UID. Does NOT send. Threads the draft with proper In-Reply-To/References and prefills recipient/subject.
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `body` (string, required) -- Draft reply body.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `reply_all` (boolean, default `false`) -- Reply to all.
  - `title` (string, optional) -- Document title.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_draft_reply_to_email()` (line 1728). Fetches the original, builds threading headers, then delegates to `_create_email_draft_document()`. If a draft already exists for the same source UID/folder, it updates that document in-place via `_merge_email_reply_body()` (line 1580).

#### 3.1.9 `ai_draft_email_reply`

- **Lines:** 2303-2323 (schema), 2805-2826 (handler)
- **Description:** Generate an AI reply using Vaidyx' AI reply prompt and writing style, then create a compose draft document. Does NOT send.
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `reply_all` (boolean, default `false`) -- Reply to all.
  - `title` (string, optional) -- Document title.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_ai_draft_reply_to_email()` (line 1780). Reads the original email, constructs a system prompt incorporating the user's writing style, calls the LLM via `llm_call_async_with_fallback()` with a fallback chain of utility/default/chat endpoints, then creates the draft document.

#### 3.1.10 `archive_email`

- **Lines:** 2324-2336 (schema), 2828-2833 (handler)
- **Description:** Move an email from the inbox into the Archive folder.
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `folder` (string, default `"INBOX"`) -- Source folder.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_archive_email()` (line 2063). Delegates to `_move_message()` (line 2024) which tries IMAP MOVE first, falling back to COPY + DELETE + EXPUNGE. Folder names are resolved via `_resolve_folder()` (line 462) which detects provider-specific names (e.g. Gmail's `[Gmail]/All Mail`).

#### 3.1.11 `delete_email`

- **Lines:** 2337-2350 (schema), 2835-2845 (handler)
- **Description:** Delete an email. By default moves to Trash; `permanent=true` expunges immediately.
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `folder` (string, default `"INBOX"`) -- Source folder.
  - `permanent` (boolean, default `false`) -- Hard-delete instead of move to Trash.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_delete_email()` (line 2055). Routes to `_move_message()` for soft delete or `_set_flag()` (line 1931) with `\Deleted` for permanent expunge.

#### 3.1.12 `mark_email_read`

- **Lines:** 2351-2364 (schema), 2847-2854 (handler)
- **Description:** Mark an email as read (`\Seen` flag) or unread (`read=false`).
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `read` (boolean, default `true`) -- True to mark read, false to mark unread.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_set_flag()` (line 1931).

#### 3.1.13 `bulk_email`

- **Lines:** 2365-2398 (schema), 2856-2899 (handler)
- **Description:** Perform one action on many emails at once. Supports mark_read, mark_unread, archive, delete, and junk. Select messages by explicit UID list or `all_unread=true`.
- **Parameters:**
  - `action` (string, required, enum: `mark_read`, `mark_unread`, `archive`, `delete`, `junk`) -- What to do.
  - `uids` (array of strings, optional) -- Explicit list of UIDs.
  - `all_unread` (boolean, default `false`) -- Operate on all unread messages in the folder.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `permanent` (boolean, default `false`) -- For delete: expunge instead of Trash.
  - `account` (string, optional) -- Which email account.
- **Implementation:** Uses `_bulk_set_flag()` (line 1947) for flag operations and `_bulk_move()` (line 1976) for folder moves, both operating on comma-joined UID sets in single IMAP commands for efficiency.

#### 3.1.14 `scan_email_unsubscribes`

- **Lines:** 2154-2173 (schema), 2567-2598 (handler)
- **Description:** Scan recent email headers for likely spam/newsletter unsubscribe candidates. Returns reviewable candidates with UID, sender, subject, confidence score (0-100), reasons, and List-Unsubscribe methods (mailto or URL). Does NOT unsubscribe.
- **Parameters:**
  - `folder` (string, default `"INBOX"`) -- IMAP folder to scan.
  - `limit` (integer, default `25`) -- Maximum candidates to return (capped at 100).
  - `max_scan` (integer, default `150`) -- How many newest messages to inspect (capped at 500).
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_scan_unsubscribe_candidates()` (line 657). Fetches headers in bulk, parses `List-Unsubscribe` headers via `_parse_list_unsubscribe_header()` (line 534), scores candidates based on list headers, precedence, auto-submitted status, and promotional subject keywords, then deduplicates via `_dedupe_unsubscribe_candidates()` (line 632).

#### 3.1.15 `unsubscribe_email`

- **Lines:** 2174-2192 (schema), 2600-2628 (handler)
- **Description:** Execute one approved unsubscribe action for an email UID. Handles mailto unsubscribes directly by sending the unsubscribe email. For web URL methods, returns the URL with instructions to use browser tools.
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `method_index` (integer, default `0`) -- Unsubscribe method index.
  - `allow_web` (boolean, default `false`) -- Whether to return web URL instructions.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_unsubscribe_email()` (line 715). For mailto methods, sends via `_send_email()`. For URL methods, returns `requires_browser: true` with the URL.

#### 3.1.16 `download_attachment`

- **Lines:** 2193-2211 (schema), 2630-2645 (handler)
- **Description:** Download an email attachment to the local disk. Returns the local file path for subsequent reading.
- **Parameters:**
  - `uid` (string, required) -- Email UID.
  - `index` (integer, required) -- Attachment index from `read_email`'s attachments list.
  - `folder` (string, default `"INBOX"`) -- IMAP folder.
  - `account` (string, optional) -- Which email account.
- **Implementation:** `_download_attachment()` (line 2069). Fetches the full message, walks MIME parts via `_extract_attachment_to_disk()` (line 1188), and writes the binary payload to `data/mail-attachments/<folder>_<uid>/`.

---

### 3.2 Memory Server (`mcp_servers/memory_server.py`)

**Server name:** `"memory"` (line 22)

A single-tool server (286 lines) exposing all memory operations through a unified `manage_memory` tool with an `action` parameter.

#### 3.2.1 `manage_memory`

- **Lines:** 115-140 (schema), 143-276 (handler)
- **Description:** Manage the user's memory system: list, add, edit, delete, or search memories.
- **Parameters:**
  - `action` (string, required, enum: `list`, `add`, `edit`, `delete`, `search`) -- The action to perform.
  - `text` (string, optional) -- Memory text (for add/edit) or search query (for search).
  - `memory_id` (string, optional) -- Memory ID (for edit/delete). Prefix matching is supported (first 8 characters).
  - `category` (string, optional, enum: `fact`, `event`, `contact`, `preference`) -- Memory category (for add or list filtering).

**Actions:**

- **`list`** (lines 154-175): Returns all memories visible to the current owner, optionally filtered by category. Each entry shows category, truncated ID, and text (capped at 150 chars).
- **`add`** (lines 177-193): Creates a new memory entry with source `"ai_agent"`. Appends to the full memory list and saves. If a `MemoryVectorStore` is healthy, also indexes the entry for semantic search.
- **`edit`** (lines 195-222): Updates an existing memory's text and timestamp. Resolves the memory by ID prefix match within owner-visible entries. Updates vector store index.
- **`delete`** (lines 224-251): Removes a memory by ID prefix match. Updates vector store index.
- **`search`** (lines 253-273): Searches memories using `MemoryManager.get_relevant_memories()` (semantic/relevance scoring with threshold 0.05, max 20 results) when available, falling back to case-insensitive substring matching.

**Owner Scoping:** Uses `VAIDYX_MCP_MEMORY_OWNER` or `VAIDYX_MEMORY_OWNER` environment variables. When owner-scoped entries exist, the server filters to only show entries belonging to the current owner. The `_scope_entries(for_update=True)` path (line 60) specifically guards against a read-modify-write race that could overwrite the entire memory store.

**Lazy Initialization:** `_ensure_init()` (line 95) loads `MemoryManager` from `src.memory` and optionally `MemoryVectorStore` from `src.memory_vector` on first tool call.

---

### 3.3 RAG Server (`mcp_servers/rag_server.py`)

**Server name:** `"rag"` (line 17)

A compact single-tool server (161 lines) for managing the RAG (Retrieval-Augmented Generation) document index.

#### 3.3.1 `manage_rag`

- **Lines:** 46-65 (schema), 68-151 (handler)
- **Description:** Manage RAG indexed documents. List indexed files, add directories, or remove directories.
- **Parameters:**
  - `action` (string, required, enum: `list`, `add_directory`, `remove_directory`) -- The action to perform.
  - `directory` (string, optional) -- Directory path for add/remove operations.

**Actions:**

- **`list`** (lines 76-101): Lists indexed directories and files via `PersonalDocsManager`. Shows up to 50 files with a count of additional files.
- **`add_directory`** (lines 103-128): Indexes a directory into the RAG system. Normalizes the path to absolute, validates it exists, calls `_rag_manager.index_personal_documents(directory)`, then registers the directory with `PersonalDocsManager.add_directory(directory, index=False)` to make it visible for listing and removal.
- **`remove_directory`** (lines 131-148): Removes a directory from both the `PersonalDocsManager` and the RAG manager. Expands `~` in paths to match how `add_directory` stored the absolute path.

**Lazy Initialization:** `_ensure_init()` (line 25) loads `get_rag_manager()` from `src.rag_singleton` and `PersonalDocsManager` from `src.personal_docs`.

---

### 3.4 Image Generation Server (`mcp_servers/image_gen_server.py`)

**Server name:** `"image_gen"` (line 21)

A single-tool server (185 lines) for AI image generation via OpenAI-compatible APIs.

#### 3.4.1 `generate_image`

- **Lines:** 24-41 (schema), 44-175 (handler)
- **Description:** Generate an image using an image-capable model (e.g. gpt-image-1).
- **Parameters:**
  - `prompt` (string, required) -- Image description prompt.
  - `model` (string, optional) -- Model name. Auto-detects if omitted by trying `gpt-image-1.5`, `gpt-image-1`, then `dall-e-3` in order.
  - `size` (string, optional, default `"1024x1024"`) -- Image size. Valid for gpt-image: `1024x1024`, `1024x1536`, `1536x1024`, `auto`. Valid for DALL-E 3: `1024x1024`, `1024x1792`, `1792x1024`.
  - `quality` (string, optional, default `"medium"`) -- Quality level: `low`, `medium`, `high`, `auto`.

**Implementation flow:**
1. Checks `image_gen_enabled` setting; returns error if disabled (line 63).
2. Loads user settings for `image_model` and `image_quality` defaults (lines 67-70).
3. Auto-detects the best available image model if none specified (lines 73-82).
4. Resolves the model endpoint via `_resolve_model()` from `src.ai_interaction` (lines 84-90).
5. Constructs the API URL by replacing `/chat/completions` or `/v1/messages` with `/images/generations` (lines 93-94).
6. Sends the request via `httpx.AsyncClient` with a 300-second read timeout (line 107).
7. For base64-encoded responses: saves PNG to `data/generated_images/`, records it in the `GalleryImage` database table, and returns the API path (lines 131-154).
8. For URL responses: returns the URL directly (lines 156-157).
9. Prefixes `app_public_url` setting when available for fully-qualified links (line 129).

---

### 3.5 Browser Server (NPX-based)

**Server ID:** `builtin_browser`

Not a Python MCP server. Launched via `npx -y @playwright/mcp@latest --headless --caps vision`. Configured in `src/builtin_mcp.py` lines 80-86. Additional runtime arguments are injected by `_browser_mcp_args()` (line 132):
- `--executable-path <browser>` when a local Chrome/Chromium binary is found.
- `--isolated` unless `VAIDYX_BROWSER_ISOLATED=0`.
- `--no-sandbox` unless `VAIDYX_BROWSER_NO_SANDBOX=0`.

Cache directory: `data/local/playwright-mcp-cache/` (configurable via `VAIDYX_BROWSER_MCP_CACHE`).

---

## 4. Integration Points

### 4.1 Startup Registration

**File:** `app.py` lines 805-813, 1042-1057

On application startup:
1. `McpManager` is instantiated (line 810).
2. It is injected into `src.agent_tools` via `set_mcp_manager()` (line 811).
3. MCP HTTP routes are mounted via `routes/mcp_routes.py` (line 812).
4. After the web server starts accepting traffic, `register_builtin_servers()` connects all built-in servers as background tasks (lines 1044-1057). This is deliberately deferred so MCP startup latency does not block the UI.

**File:** `src/builtin_mcp.py` lines 163-254

`register_builtin_servers()` iterates `_BUILTIN_SERVERS` (line 72), spawns each Python server as a subprocess using the current `sys.executable`, and passes `builtin_python_env()` (line 148) which ensures the project root is on `PYTHONPATH`. NPX servers are started with a 3-second delay after Python servers.

### 4.2 Tool Routing

**File:** `src/mcp_manager.py` lines 467-507

MCP tools are namespaced as `mcp__<server_id>__<tool_name>` (e.g. `mcp__email__list_emails`). When the agent calls a tool with this prefix, `McpManager.call_tool()` extracts the server ID and tool name, forwards the call to the appropriate `ClientSession`, and converts the response to a standard `{stdout, stderr, exit_code}` dict. Image content (e.g. Playwright screenshots) is passed through as base64 in an `images` array.

### 4.3 Auto-Reconnect

**File:** `src/mcp_manager.py` lines 537-566

When a tool call fails on a built-in server (the subprocess may have crashed), `McpManager` automatically tears down and reconnects the server before retrying the call. This is limited to built-in servers identified by `is_builtin()` (line 639).

### 4.4 Agent Prompt Integration

**File:** `src/mcp_manager.py` lines 659-707

`get_tool_descriptions_for_prompt()` generates a text block appended to the agent system prompt listing all available MCP tools. Built-in Python servers are excluded from this block because they are already described in the hardcoded agent prompt; only NPX-based builtins (like browser) and user-added servers appear here. Each tool line includes the qualified name, a truncated description, and compact parameter hints generated by `_format_mcp_params()` (line 60).

### 4.5 Plan Mode Gating

**File:** `src/mcp_manager.py` lines 621-637

`plan_mode_blocked_mcp()` classifies every MCP tool as read-only or write. Tools with `readOnlyHint=true` in their annotations pass; tools with `readOnlyHint=false` or `destructiveHint=true` are blocked. When annotations are absent, a name-prefix heuristic checks against verbs like `list`, `get`, `read`, `search`, `fetch`, `query`, `find`, etc. Write tools are blocked from execution during plan mode.

### 4.6 OpenAI Function-Calling Schemas

**File:** `src/mcp_manager.py` lines 568-601

`get_all_openai_schemas()` converts MCP tools to OpenAI function-calling format for models that use native function calling. Built-in Python servers are excluded (they use code-block tool format), but NPX-based builtins are included.

### 4.7 Shutdown

**File:** `app.py` lines 1267-1271

On application shutdown, `mcp_manager.disconnect_all()` is called to clean up all MCP server connections and their associated `AsyncExitStack` contexts.

### 4.8 Database Persistence

**File:** `src/mcp_manager.py` lines 427-465

User-configured (non-builtin) MCP servers are persisted in the `McpServer` SQLAlchemy model. `connect_all_enabled()` loads all enabled servers from the database and connects them with a 20-second per-server timeout.

### 4.9 Email Server Database Dependencies

The email server reads from and writes to several database files:
- `data/app.db` -- `email_accounts` table for multi-account configuration.
- `data/email_cache.db` -- `email_ai` table for pre-computed AI summaries.
- `data/scheduled_emails.db` -- `scheduled_emails` table for agent draft staging.
- `data/auth.json` -- User authentication data for determining document owners.
- `data/settings.json` -- Email writing style, IMAP/SMTP fallback configuration.

---

## 5. Configuration

### 5.1 Environment Variables

#### Global MCP Control

| Variable | Default | Description |
|----------|---------|-------------|
| `VAIDYX_DISABLE_MCP` | `""` | Set to `1`/`true`/`yes` to disable all built-in MCP servers |
| `VAIDYX_BROWSER_MCP_REQUIRE_CACHE` | `""` | Set to `1`/`true` to require the Playwright package to be pre-cached (no auto-install on startup) |
| `VAIDYX_BROWSER_MCP_CACHE` | `data/local/playwright-mcp-cache` | Cache directory for the browser MCP server |
| `VAIDYX_BROWSER_EXECUTABLE` | auto-detected | Path to Chrome/Chromium binary for browser MCP |
| `VAIDYX_BROWSER_ISOLATED` | `"1"` | Run browser in isolated mode (no persistent profile) |
| `VAIDYX_BROWSER_NO_SANDBOX` | `"1"` | Run browser with `--no-sandbox` |
| `VAIDYX_STARTUP_WARMUPS` | `""` | Enable tool index pre-warming on startup |

#### Email Server

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAP_HOST` | `localhost` | IMAP server hostname |
| `IMAP_PORT` | `31143` | IMAP server port |
| `IMAP_USER` | `""` | IMAP username |
| `IMAP_PASSWORD` | `""` | IMAP password |
| `IMAP_SSL` | `false` | Use implicit TLS for IMAP |
| `IMAP_STARTTLS` | `true` | Use STARTTLS for IMAP |
| `SMTP_HOST` | `""` | SMTP server hostname |
| `SMTP_PORT` | `465` | SMTP server port |
| `SMTP_SECURITY` | `""` | SMTP security mode: `ssl`, `starttls`, or `none` |
| `SMTP_USER` | `""` | SMTP username |
| `SMTP_PASSWORD` | `""` | SMTP password |
| `EMAIL_FROM` | `""` | Sender email address |
| `ARCHIVE_FOLDER` | `Archive` | IMAP archive folder name |
| `TRASH_FOLDER` | `Trash` | IMAP trash folder name |
| `EMAIL_CACHE_DB` | `data/email_cache.db` | Path to AI summary cache |
| `EMAIL_SOCKET_TIMEOUT` | `20` | Socket timeout in seconds for IMAP/SMTP connections |
| `VAIDYX_MCP_EMAIL_OWNER` | `""` | Owner identity for owner-scoped email access |
| `VAIDYX_EMAIL_OWNER` | `""` | Alternate owner identity variable |
| `VAIDYX_DOCUMENT_OWNER` | `""` | Override owner for MCP-created draft documents |
| `VAIDYX_MAIL_ATTACHMENTS_DIR` | `data/mail-attachments` | Directory for downloaded email attachments |

#### Memory Server

| Variable | Default | Description |
|----------|---------|-------------|
| `VAIDYX_MCP_MEMORY_OWNER` | `""` | Owner identity for owner-scoped memory access |
| `VAIDYX_MEMORY_OWNER` | `""` | Alternate owner identity variable |

### 5.2 Multi-Account Email Configuration

Email accounts are stored in the `email_accounts` table of `data/app.db`. Each row contains:
- `id`, `owner`, `name`, `is_default`, `enabled`
- `imap_host`, `imap_port`, `imap_user`, `imap_password`, `imap_starttls`
- `smtp_host`, `smtp_port`, `smtp_security`, `smtp_user`, `smtp_password`, `from_address`

Passwords are encrypted via `src.secret_storage.encrypt` and decrypted at connection time.

Account resolution (line 233) matches by: exact ID, then case-insensitive substring on name/imap_user/from_address, then fuzzy matching via `difflib.get_close_matches` with cutoff 0.72.

When no database accounts exist, the server falls back to environment variables and `data/settings.json` flat keys (legacy single-account mode).

### 5.3 Settings-Based Configuration

The following settings from `data/settings.json` affect MCP server behavior:

- `email_writing_style` -- Global email writing style guidance injected into draft tool descriptions and AI reply prompts.
- `email_writing_styles_by_account` -- Per-account writing style overrides (keyed by account ID).
- `agent_email_confirm` -- When `true` (default), agent-initiated sends are staged for user approval instead of sending immediately.
- `image_gen_enabled` -- When `false`, the image generation tool returns an error.
- `image_model` -- Default image model name.
- `image_quality` -- Default image quality level.
- `app_public_url` -- Base URL prefix for generated image links.

### 5.4 MCP Transport Types

The `McpManager` supports three transport types for connecting to MCP servers:

1. **stdio** -- The server runs as a subprocess. The manager communicates via stdin/stdout. Used by all built-in servers.
2. **SSE (Server-Sent Events)** -- The manager connects to a remote SSE endpoint. Used for user-configured remote MCP servers.
3. **Streamable HTTP** -- The manager connects via HTTP with automatic OAuth support. Includes background authorization flow with `needs_auth` status and `auth_url` for browser-based approval. OAuth is managed by `src/mcp_oauth.py`.

### 5.5 Disabling Individual Tools

User-configured MCP servers can have individual tools disabled via the `disabled_map` parameter passed to `get_all_tools()`, `get_all_openai_schemas()`, and `get_tool_descriptions_for_prompt()`. This is managed through the MCP routes UI.
