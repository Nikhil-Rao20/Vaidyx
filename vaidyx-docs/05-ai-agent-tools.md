# 05 - AI Agent Tools

## 1. AI System Overview

Vaidyx uses a streaming agent loop that wraps LLM inference with multi-round tool execution. The architecture is split across these key files:

| File | Purpose |
|------|---------|
| `src/agent_loop.py` | Main agent loop: intent classification, tool selection, streaming SSE dispatch |
| `src/tool_execution.py` | Tool dispatcher: path confinement, MCP routing, workspace binding, policy enforcement |
| `src/tool_parsing.py` | Parses 7+ LLM output formats into canonical `ToolBlock` namedtuples |
| `src/tool_schemas.py` | ~50 OpenAI-compatible function schemas; `function_call_to_tool_block` converter |
| `src/agent_tools/__init__.py` | Central registry: `TOOL_HANDLERS` dict, `TOOL_TAGS` set, constants |
| `src/ai_interaction.py` | Model resolution, pipelines, memory management, image generation, UI control |
| `src/tools/` | Domain-specific implementations (cookbook, notes, calendar, contacts, vault, etc.) |

**Constants** (from `agent_tools/__init__.py`):
- `MAX_AGENT_ROUNDS = 50` -- maximum tool-use rounds per turn
- `SHELL_TIMEOUT = 60` / `PYTHON_TIMEOUT = 30` -- default subprocess timeouts (seconds)
- `AI_CHAT_TIMEOUT = 120` -- LLM API call timeout (from `ai_interaction.py`)

**Security layers**:
- Path confinement via `_resolve_tool_path` (line 154, `tool_execution.py`)
- Sensitive-file deny-list via `_is_sensitive_path` (line 84)
- Admin-only tool gate via `_ADMIN_TOOLS` set (line 308)
- Owner-scoped sessions prevent cross-user access
- MCP command validation with `_MCP_DENIED_COMMANDS` frozenset (`admin_tools.py`, line 97)
- Tool policy enforcement: disabled tools, guide-only mode, per-owner blocked tools

---

## 2. Agent Tools

### 2.1 Subprocess Tools (`agent_tools/subprocess_tools.py`)

| Tool | Description |
|------|-------------|
| `bash` | Shell commands via tmux (persistent sessions) or direct subprocess. Supports `#!bg` marker for background jobs via tmux detach. Default timeout 3600s. |
| `python` | Python execution in isolated mode (`-I` flag). Default timeout 3600s. |

Progress streaming: both tools accept a `progress_cb` callback that emits `{elapsed_s, tail}` payloads during execution (lines 186-273).

### 2.2 Filesystem Tools (`agent_tools/filesystem_tools.py`)

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with optional offset/limit |
| `write_file` | Write content to a file (creates or overwrites) |
| `edit_file` | Exact string replacement with uniqueness check (lines 73-131) |
| `apply_patch` | Codex-style unified diff patching with strict context matching (lines 233-317) |
| `ls` | List directory contents |
| `glob` | Custom glob-to-regex file search with directory pruning (lines 457-556) |
| `grep` | Uses ripgrep when available, falls back to Python walk (lines 558-659) |
| `get_workspace` | Returns the current workspace path |

### 2.3 Document Tools (`agent_tools/document_tools.py`)

| Tool | Description |
|------|-------------|
| `create_document` | Create a new document; auto-detects language via `_sniff_doc_language` (line 87) |
| `update_document` | Full content replacement of the active document |
| `edit_document` | FIND/REPLACE block-based partial editing (lines 221-249) |
| `suggest_document` | Add inline suggestions/feedback |
| `manage_document` | CRUD operations: list, view, delete, rename, set_version, export |

Special handling: email documents split into header/body (lines 129-219). PDF-sourced documents create derivatives for editing (lines 275-314).

### 2.4 Web Tools (`agent_tools/web_tools.py`)

| Tool | Description |
|------|-------------|
| `web_search` | Comprehensive search with auto-detected `time_filter` (day/week/month/year). Max 10 pages. 30s timeout. |
| `web_fetch` | Fetch and extract webpage content. Supports `full: true` for large downloads. Partial-content notice when truncated. |

### 2.5 Interaction Tools (`agent_tools/interaction_tools.py`)

| Tool | Description |
|------|-------------|
| `ask_user` | Present multiple-choice questions; ends the agent turn (lines 6-56) |
| `update_plan` | Update a checklist-style plan; does not end turn (lines 58-95) |

### 2.6 Session Tools (`agent_tools/session_tools.py`)

| Tool | Description |
|------|-------------|
| `create_session` | Create a new chat session |
| `list_sessions` | List sessions (owner-scoped) |
| `send_to_session` | Send a message to another session |
| `manage_session` | Actions: list, switch, rename, archive, delete, important, truncate, fork (lines 245-466) |

### 2.7 Model Interaction Tools (`agent_tools/model_interaction_tools.py`)

| Tool | Description |
|------|-------------|
| `chat_with_model` | Send a message to a specific model via `_resolve_model` (lines 30-67) |
| `ask_teacher` | Escalate to a more capable model with `_TEACHER_SYSTEM_PROMPT` (lines 70-113) |
| `list_models` | Enumerate available models across all endpoints (lines 116-191) |

### 2.8 Coding Tools (`agent_tools/coding_tools.py`)

| Tool | Description |
|------|-------------|
| `todo` | Structured task list with pending/in_progress/completed states. Only one item may be in_progress at a time (line 51). |

### 2.9 Background Job Tools (`agent_tools/bg_job_tools.py`)

| Tool | Description |
|------|-------------|
| `manage_bg_jobs` | List/output/kill detached background bash jobs. Jobs scoped to chat `session_id` (line 83). |

### 2.10 Admin Tools (`agent_tools/admin_tools.py`)

| Tool | Description |
|------|-------------|
| `manage_endpoints` | CRUD for LLM API endpoints |
| `manage_mcp` | MCP server configuration with command validation (`_validate_mcp_command`, lines 144-215) |
| `manage_webhooks` | Webhook CRUD |
| `manage_tokens` | API token management |
| `manage_settings` | System settings with alias resolution, enum validation, secret protection (lines 498-768) |

Admin tools are gated behind the `_ADMIN_TOOLS` set in `tool_execution.py` and require owner authentication.

### 2.11 Domain Tools (`src/tools/`)

| Tool | Module | Description |
|------|--------|-------------|
| `manage_skills` / `manage_tasks` | `system.py` | Skill and task management |
| `api_call` / `app_api` | `system.py` | External API integration and internal app API |
| `download_model` / `serve_model` / `list_served_models` | `cookbook.py` | Model downloading, serving (vLLM/SGLang/llama.cpp), management |
| `search_chats` | `search.py` | Full-text search across chat history |
| `manage_notes` | `notes.py` | Notes CRUD |
| `manage_calendar` | `calendar.py` | Calendar event management |
| `edit_image` | `image.py` | Image editing operations |
| `manage_research` / `trigger_research` | `research.py` | Deep research workflows |
| `resolve_contact` / `manage_contact` | `contacts.py` | Contact lookup and management |
| `vault_search` / `vault_get` / `vault_unlock` | `vault.py` | Bitwarden vault integration |

### 2.12 AI Interaction Tools (`src/ai_interaction.py`)

| Tool | Description |
|------|-------------|
| `pipeline` | Multi-step AI chain: each model's output feeds the next (lines 221-327) |
| `manage_memory` | Memory CRUD with vector index support (lines 338-515) |
| `ui_control` | Frontend control: toggles, themes, panels, email replies (lines 613-930) |
| `generate_image` | Image generation via OpenAI-compatible APIs (lines 937-1177) |

---

## 3. Tool System

### 3.1 Registration

Tools are registered in `TOOL_HANDLERS` (`agent_tools/__init__.py`, line 37) -- a dict mapping tool name strings to async handler functions:

```python
TOOL_HANDLERS = {
    "bash": BashTool().execute,
    "python": PythonTool().execute,
    "web_search": WebSearchTool().execute,
    ...
}
```

Each handler has the signature `async execute(self, content: str, ctx: dict) -> dict` and returns `{"output": str, "exit_code": int}` or `{"error": str, "exit_code": 1}`.

`TOOL_TAGS` (line 79) is a set of ~60+ recognized tool type strings used for validation.

### 3.2 Schema Definition

`FUNCTION_TOOL_SCHEMAS` (`tool_schemas.py`, line 34) provides ~50 OpenAI-compatible function schemas. Each schema defines `name`, `description`, and `parameters` (JSON Schema). These are sent to the LLM so it knows which tools are available and their argument shapes.

### 3.3 Parsing

`parse_tool_blocks` (`tool_parsing.py`, line 1244) handles 7+ LLM output formats:

1. **Fenced code blocks** -- ` ```tool_name\ncontent\n``` ` (matched by `_TOOL_BLOCK_RE`, line 33)
2. **`[TOOL_CALL]` markers** -- `[TOOL_CALL] tool_name\ncontent\n[/TOOL_CALL]`
3. **XML invoke** -- `<invoke name="tool">`
4. **StepFun tokens** -- `<|tool_call|>...<|tool_call_end|>`
5. **DeepSeek DSML** -- normalized by `_normalize_dsml` (line 215)
6. **Gemma-style** -- `<tool_call>{"name": ...}</tool_call>`
7. **Raw OpenAI JSON** -- function call objects

`_TOOL_NAME_MAP` (line 232) maps ~80 model-generated aliases to canonical tool names.

`_iter_delimited` (line 1135) uses forward-only scanning to prevent ReDoS attacks.

### 3.4 Execution

`execute_tool_block` (`tool_execution.py`, line 570) is the main dispatcher:

1. **Policy check** -- verifies tool is not disabled/blocked (lines 681-712)
2. **Path resolution** -- `_resolve_tool_path` confines file ops to allowed roots (line 154)
3. **Workspace binding** -- `_active_workspace` ContextVar scopes execution per-turn (line 241)
4. **MCP routing** -- `_call_mcp_tool` tries MCP servers first, falls back to direct (lines 448-477)
5. **Background detection** -- `_split_bg_marker` checks for `#!bg` in bash commands (lines 503-516)
6. **Handler dispatch** -- looks up handler in `TOOL_HANDLERS` and calls it
7. **Result formatting** -- `format_tool_result` converts result dict to text for LLM context (line 983)

### 3.5 Native Function Calls

When the LLM uses native function calling (OpenAI format), `function_call_to_tool_block` (`tool_schemas.py`, line 1370) converts the call into a `ToolBlock` namedtuple for unified processing. `_repair_document_function_args` (line 1338) salvages malformed document tool arguments.

---

## 4. Conversation Flow

A user message follows this path through the system:

1. **Route handler** receives the HTTP request with messages and model configuration
2. **`stream_agent_loop`** (`agent_loop.py`, line 3079) is called as an async generator
3. **Intent classification** -- `_classify_agent_request` (line 1275) determines which domain tools are relevant (cookbook, email, notes, web, files, etc.)
4. **Low-signal detection** -- casual greetings bypass the tool loop entirely and get a direct LLM response (lines 3217-3278)
5. **System prompt assembly** -- `_assemble_prompt` (line 817) builds the system prompt with domain-specific rules based on detected intent
6. **Tool schema selection** -- only schemas for relevant tools are sent to the LLM, reducing context size
7. **LLM streaming** -- `stream_llm_with_fallback` calls the primary endpoint with automatic fallback to alternate models
8. **Tool parsing** -- response text is parsed by `parse_tool_blocks` to extract tool invocations
9. **Tool execution** -- each `ToolBlock` is dispatched via `execute_tool_block`
10. **Result injection** -- tool results are appended to the conversation as assistant/tool messages
11. **Next round** -- if tools were called, the loop continues (up to `MAX_AGENT_ROUNDS = 50`)
12. **SSE emission** -- throughout, SSE events are yielded for real-time frontend updates

The active document state is maintained via module globals in `document_tools.py` (lines 19-54) and is only injected into the context when the turn targets document operations (`_turn_targets_active_document`, line 1377).

---

## 5. Streaming

### 5.1 SSE Event Types

`stream_agent_loop` yields Server-Sent Events (SSE) in these formats:

| Event | Payload | When |
|-------|---------|------|
| `delta` | `{"delta": "text"}` | Text token from LLM |
| `tool_start` | `{"type": "tool_start", "tool": "...", "command": "..."}` | Before tool execution |
| `tool_progress` | `{"type": "tool_progress", "tool": "...", "elapsed_s": N, "tail": "..."}` | During long-running tools |
| `tool_output` | `{"type": "tool_output", "tool": "...", ...}` | After tool completes |
| `agent_step` | `{"type": "agent_step", "round": N}` | New agent round begins |
| `doc_stream_delta` | `{"type": "doc_stream_delta", "content": "..."}` | Document content streaming |
| `budget_exceeded` | `{"type": "budget_exceeded", "limit": N, "used": N}` | Tool call limit hit |
| `metrics` | `{"type": "metrics", "data": {...}}` | Final turn metrics |
| `[DONE]` | `data: [DONE]` | Stream end |

### 5.2 Progress Streaming

For long-running bash and python tools, an `asyncio.Queue`-based progress system (lines 4646-4690 of `agent_loop.py`) forwards real-time updates:

1. `_push_progress` callback is passed to `execute_tool_block` via `progress_cb`
2. Subprocess tools emit `{elapsed_s, tail}` payloads periodically
3. The agent loop drains the queue and yields `tool_progress` SSE events
4. A sentinel `None` signals tool completion
5. If the SSE client disconnects, orphaned tool tasks are cancelled (lines 4685-4690)

### 5.3 Fallback Streaming

`stream_llm_with_fallback` accepts a list of `(endpoint_url, model, headers)` tuples. If the primary endpoint fails, it automatically retries with the next fallback, emitting a `fallback` event so the frontend can display which model answered.

---

## 6. Key Functions (with line numbers)

### `src/agent_loop.py`

| Function | Line | Purpose |
|----------|------|---------|
| `stream_agent_loop` | 3079 | Main streaming agent loop generator |
| `_classify_agent_request` | 1275 | Classify user intent into domain categories |
| `_assemble_prompt` | 817 | Build system prompt with domain rules |
| `_turn_targets_active_document` | 1377 | Determine if active document is relevant |
| `_detect_admin_intent` | 976 | Check if message requires admin tools |
| `_run_verifier_subagent` | 2946 | Run verification sub-agent |

### `src/tool_execution.py`

| Function | Line | Purpose |
|----------|------|---------|
| `execute_tool_block` | 570 | Main tool dispatcher entry point |
| `_execute_tool_block_impl` | 600 | Core dispatch implementation |
| `_resolve_tool_path` | 154 | Path confinement to allowed roots |
| `_is_sensitive_path` | 84 | Check against sensitive-file deny-list |
| `_tool_path_roots` | 105 | Compute allowed filesystem roots |
| `_call_mcp_tool` | 448 | Route tool calls through MCP servers |
| `format_tool_result` | 983 | Format result dict for LLM context |

### `src/tool_parsing.py`

| Function | Line | Purpose |
|----------|------|---------|
| `parse_tool_blocks` | 1244 | Parse LLM output into ToolBlock list (7+ formats) |
| `strip_tool_blocks` | 1419 | Remove executed tool markup from display text |
| `_normalize_dsml` | 215 | Normalize DeepSeek DSML markup |
| `_iter_delimited` | 1135 | Forward-only scanner (ReDoS prevention) |

### `src/tool_schemas.py`

| Function | Line | Purpose |
|----------|------|---------|
| `FUNCTION_TOOL_SCHEMAS` | 34 | List of ~50 OpenAI-compatible function schemas |
| `function_call_to_tool_block` | 1370 | Convert native function calls to ToolBlock |
| `_repair_document_function_args` | 1338 | Salvage malformed document tool args |

### `src/agent_tools/__init__.py`

| Symbol | Line | Purpose |
|--------|------|---------|
| `TOOL_HANDLERS` | 37 | Dict mapping tool names to handler functions |
| `TOOL_TAGS` | 79 | Set of ~60+ recognized tool type strings |
| `MAX_AGENT_ROUNDS` | 74 | Maximum tool-use rounds per turn (50) |

### `src/ai_interaction.py`

| Function | Line | Purpose |
|----------|------|---------|
| `_resolve_model` | 78 | Resolve model specifier to (endpoint, model_id, headers) |
| `do_pipeline` | 221 | Multi-step AI pipeline execution |
| `do_manage_memory` | 338 | Memory CRUD with vector index |
| `do_ui_control` | 613 | Frontend UI control dispatch |
| `do_generate_image` | 937 | Image generation via OpenAI-compatible APIs |
| `dispatch_ai_tool` | 1444 | Route pipeline/memory/ui_control calls |
