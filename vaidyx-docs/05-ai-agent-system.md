# 05 - AI Agent System

> Comprehensive documentation of the Vaidyx AI/Agent system architecture, covering the full stack from user message to AI response, including tool calling, model management, search integration, and multi-model support.

---

## Table of Contents

1. [AI System Overview](#1-ai-system-overview)
2. [Agent Tools](#2-agent-tools)
3. [Model Capability Readers](#3-model-capability-readers)
4. [Search Integration](#4-search-integration)
5. [Tool System](#5-tool-system)
6. [Model Management](#6-model-management)
7. [Conversation Flow](#7-conversation-flow)
8. [Streaming](#8-streaming)
9. [Context Management](#9-context-management)
10. [Multi-Model Support](#10-multi-model-support)

---

## 1. AI System Overview

### Architecture Summary

Vaidyx is a self-hosted AI assistant built as a FastAPI application with a modular agent architecture. The system supports both simple chat interactions and autonomous agent loops with tool calling. Its key architectural layers are:

```
User Message (Browser/API)
    |
    v
FastAPI Routes (routes/chat_routes.py)
    |
    v
Chat Handler (src/chat_handler.py)
    |
    v
Chat Processor (src/chat_processor.py)
    |--- Memory enrichment (src/memory.py, src/memory_vector.py)
    |--- RAG context injection (src/rag_manager.py)
    |--- Tool selection (src/tool_index.py)
    |--- Skill injection (services/memory/skills.py)
    |
    v
AI Interaction Layer (src/ai_interaction.py)
    |--- Endpoint resolution (src/endpoint_resolver.py)
    |--- Model capability detection (src/model_capabilities.py)
    |--- System prompt construction
    |
    v
LLM Core (src/llm_core.py)
    |--- OpenAI-compatible API calls
    |--- Streaming SSE responses
    |
    v
Agent Loop (src/agent_loop.py) [if agent mode]
    |--- Tool parsing (src/tool_parsing.py)
    |--- Tool execution (src/tool_execution.py)
    |--- Tool policy enforcement (src/tool_policy.py)
    |--- Context budget management (src/context_budget.py)
    |--- Teacher escalation (src/teacher_escalation.py)
    |
    v
Response Stream (SSE back to client)
```

### Key Design Principles

- **Local-first**: All data stays on the user's machine. The database is SQLite, settings are JSON files under `data/`.
- **Multi-model**: Supports any OpenAI-compatible endpoint (local or cloud), plus dedicated readers for Ollama, LM Studio, llama.cpp, OpenRouter, Google AI, and GitHub Copilot.
- **Agent autonomy**: The AI can call tools, run shell commands, read/write files, search the web, manage documents, and interact with external services.
- **Teacher-student escalation**: When a self-hosted model fails at a task, a more capable "teacher" model can take over and distill a reusable skill for next time.
- **MCP support**: Built-in and user-configured MCP (Model Context Protocol) servers extend the tool set via stdio subprocesses.

### File Organization

| Directory | Purpose |
|---|---|
| `src/agent_tools/` | Tool handler classes (bash, web, filesystem, documents, sessions, admin) |
| `src/model_capability_readers/` | Per-vendor model capability detection (Ollama, LM Studio, OpenAI, etc.) |
| `src/search/` | Web search providers, caching, ranking, content extraction |
| `src/tools/` | Domain-specific tool implementations (calendar, notes, cookbook, vault, etc.) |
| `src/*.py` | Core AI system files (LLM calls, agent loop, context management, etc.) |

### Initialization Flow

Application initialization is managed by `src/app_initializer.py` (`initialize_managers()`), which creates all manager instances in order:

1. **MemoryManager** -- loads/saves `data/memory.json`
2. **SkillsManager** -- manages SKILL.md files under `data/skills/`
3. **SessionManager** -- manages chat sessions via `data/sessions.json` and SQLite
4. **UploadHandler** -- file upload handling with deduplication and rate limiting
5. **PersonalDocsManager** -- personal document indexing and RAG
6. **APIKeyManager** -- third-party API key storage
7. **PresetManager** -- chat presets
8. **MemoryVectorStore** -- ChromaDB-backed semantic memory search
9. **MemoryProviderRegistry** -- unified memory access layer
10. **ChatProcessor** -- message preprocessing (memory, RAG, tool selection, skills)
11. **ResearchHandler** -- deep research orchestration
12. **ChatHandler** -- main chat request handler
13. **ModelDiscovery** -- model listing across endpoints

---

## 2. Agent Tools

All agent tools are defined in `src/agent_tools/` and registered in `src/agent_tools/__init__.py`. Each tool is a class with an `async def execute(self, content: str, ctx: dict) -> dict` method. The `ctx` dict provides: `session_id`, `owner`, `progress_cb`, `subproc_env`, and optionally `doc_id`.

### 2.1 Tool Registration

Tools are registered in the `TOOL_HANDLERS` dict (`src/agent_tools/__init__.py`, lines 37-68), mapping tool name strings to `ToolClass().execute` methods. There are 25 built-in tool handlers plus 5 admin tool handlers (merged via `TOOL_HANDLERS.update(ADMIN_TOOL_HANDLERS)`).

**Constants** (`src/agent_tools/__init__.py`):
- `MAX_AGENT_ROUNDS = 50` (line 74)
- `SHELL_TIMEOUT = 60` (line 75)
- `PYTHON_TIMEOUT = 30` (line 76)
- `TOOL_TAGS` (lines 79-114) -- set of all recognized tool type strings (over 60 entries)
- `ToolBlock = namedtuple("ToolBlock", ["tool_type", "content"])` (line 116)

### 2.2 Subprocess Tools (`subprocess_tools.py`)

File: `src/agent_tools/subprocess_tools.py` (356 lines)

#### BashTool (lines 275-329)

Executes shell commands with persistent tmux session support. Prefers tmux for session continuity; falls back to direct subprocess execution.

```python
class BashTool:
    async def execute(self, content: str, ctx: dict) -> dict
```

- Accepts string content or dict with `command`/`cmd`/`code` key
- Uses tmux sessions named `ody-agent-<session_id>` for command persistence across agent rounds
- Marker-based output capture from tmux panes for reliable stdout extraction
- Progress callbacks every 2 seconds with tail of last 12 output lines
- Default timeout: 1 hour (`DEFAULT_BASH_TIMEOUT = 3600`)

#### PythonTool (lines 331-355)

Runs Python code via `python -I -c` (isolated mode).

```python
class PythonTool:
    async def execute(self, content: str, ctx: dict) -> dict
```

- Always uses direct subprocess (no tmux)
- Streams output with progress callbacks
- Default timeout: 1 hour (`DEFAULT_PYTHON_TIMEOUT = 3600`)

**Supporting functions:**
- `_tmux_session_name(session_id)` (line 18) -- derives safe tmux session name
- `_run_exec(*args, timeout)` (line 23) -- low-level async subprocess runner
- `_ensure_tmux_session(name, cwd, env)` (line 64) -- creates tmux session with bash `--noprofile --norc`
- `_run_tmux_bash(content, session_id, cwd, env, timeout, progress_cb)` (line 111) -- runs command in tmux with marker-based output capture
- `_run_subprocess_streaming(proc, timeout, progress_cb)` (line 186) -- streams subprocess output with progress callbacks

### 2.3 Web Tools (`web_tools.py`)

File: `src/agent_tools/web_tools.py` (167 lines)

#### WebSearchTool (lines 8-78)

```python
class WebSearchTool:
    async def execute(self, content: str, ctx: dict) -> dict
```

- JSON args: `query`, `time_filter`/`freshness` ("day"/"week"/"month"/"year"), `max_pages` (1-10, default 5)
- Auto-infers time_filter from query keywords ("today" -> "day", "this week" -> "week", "news" -> "week")
- Delegates to `comprehensive_web_search` from `src/search/core.py`
- 30-second timeout; output capped at `MAX_OUTPUT_CHARS` (10,000)

#### WebFetchTool (lines 80-166)

```python
class WebFetchTool:
    async def execute(self, content: str, ctx: dict) -> dict
```

- JSON args: `url`, `full` (bool, raises download budget to hard max), `max_bytes` (int)
- Auto-prepends `https://` if no scheme; validates http/https only
- Delegates to `fetch_webpage_content` from `src/search/content.py`
- Reports truncation with instructions for re-fetching with `"full": true`
- 30-second timeout; output capped at `MAX_OUTPUT_CHARS`

### 2.4 Filesystem Tools (`filesystem_tools.py`)

File: `src/agent_tools/filesystem_tools.py` (678 lines)

| Tool Class | Lines | JSON Parameters | Description |
|---|---|---|---|
| `ReadFileTool` | 133-181 | `path`, `offset`, `limit` | Read file with optional line range; capped at `MAX_READ_CHARS` (20,000) |
| `WriteFileTool` | 183-231 | `path`, `content` | Write file; creates directories as needed; returns diff |
| `EditFileTool` | 73-131 | `path`, `old_string`, `new_string`, `replace_all` | Exact string replacement; validates uniqueness unless `replace_all=true` |
| `ApplyPatchTool` | 233-317 | `patch_text` | Codex-style patches (`*** Begin Patch`); rejects entire patch if any hunk fails |
| `LsTool` | 408-455 | `path` | List directory; hides dotfiles; sorts dirs first; capped at 200 entries |
| `GlobTool` | 457-556 | `pattern`, `path` | Glob search; skips `.git`, `node_modules`, etc.; sorted by mtime descending |
| `GrepTool` | 558-659 | `pattern`, `path`, `ignore_case`, `glob`, `max_results` | Prefers `rg` (ripgrep); falls back to Python walk; capped at 200 results |
| `GetWorkspaceTool` | 661-677 | (none) | Reports active workspace folder |

**Constants:**
- `_CODENAV_SKIP_DIRS` (line 12) -- directories skipped: `.git`, `node_modules`, `venv`, `__pycache__`, `dist`, `build`, etc.
- `_CODENAV_MAX_HITS = 200` (line 17)
- `_CODENAV_MAX_LINE = 400` (line 18)

### 2.5 Document Tools (`document_tools.py`)

File: `src/agent_tools/document_tools.py` (836 lines)

| Tool Class | Lines | Description |
|---|---|---|
| `CreateDocumentTool` | 317-441 | Creates new documents with auto-detected language; supports line-based and XML tag formats |
| `UpdateDocumentTool` | 443-513 | Full content replacement of existing documents |
| `EditDocumentTool` | 515-657 | Targeted FIND/REPLACE edits with `<<<FIND>>>...<<<REPLACE>>>...<<<END>>>` block syntax |
| `SuggestDocumentTool` | 659-698 | Creates inline suggestions WITHOUT modifying the document |
| `ManageDocumentTool` | 704-835 | Actions: `list`, `read`/`view`/`open`, `delete`, `tidy` |

**Document state management:**
- `set_active_document(doc_id)` (line 23) -- sets the currently-active document for the agent
- `set_active_model(model)` (line 28) -- tracks current model name for version summaries
- `clear_active_document(doc_id)` (line 39) -- clears active pointer

**Email document handling** (lines 87-219):
- `_looks_like_email_document(text, title)` -- detects email documents by title or To:/Subject: headers
- `_split_email_header_body(text)` -- splits email doc at `\n---\n` separator
- `_merge_email_headers(old_header, new_header)` -- preserves routing metadata (In-Reply-To, References, X-Source-UID)
- `_coerce_email_document_content(existing, incoming)` -- keeps email docs in To/Subject/---/body shape

### 2.6 Session Tools (`session_tools.py`)

File: `src/agent_tools/session_tools.py` (491 lines)

| Function | Lines | Description |
|---|---|---|
| `create_session(content, session_id, owner)` | 22-71 | Creates new chat session with model spec |
| `list_sessions(content, session_id, owner)` | 73-160 | Lists sessions with clickable markdown anchors (`[Name](#session-id)`) |
| `send_to_session(content, session_id, owner)` | 162-243 | Sends message to another session and returns AI response |
| `manage_session(content, session_id, owner)` | 245-466 | Actions: switch, rename, archive, unarchive, delete, important, truncate, fork |

### 2.7 Interaction Tools (`interaction_tools.py`)

File: `src/agent_tools/interaction_tools.py` (95 lines)

#### AskUserTool (lines 6-56)
Returns an `ask_user` SSE payload that **ends the agent turn** and waits for user selection. Multiple choice with 2-6 options.

#### UpdatePlanTool (lines 58-95)
Returns a `plan_update` SSE payload with a markdown checklist. Does NOT end the turn. Capped at 8192 chars.

**Note:** Both return `(description_str, result_dict)` tuples rather than just a dict.

### 2.8 Model Interaction Tools (`model_interaction_tools.py`)

File: `src/agent_tools/model_interaction_tools.py` (210 lines)

| Function | Lines | Description |
|---|---|---|
| `chat_with_model(content, session_id, owner)` | 30-67 | Sends message to a specific model (format: `model_name@endpoint_name`) |
| `ask_teacher(content, session_id, owner)` | 70-113 | Asks a more capable model for help; uses teacher system prompt |
| `list_models(content, session_id, owner)` | 116-190 | Lists all available models across configured endpoints |

### 2.9 Background Job Tools (`bg_job_tools.py`)

File: `src/agent_tools/bg_job_tools.py` (99 lines)

```python
class ManageBgJobsTool:
    async def execute(self, content: str, ctx: dict) -> dict
```

Actions: `list` (show all jobs for session), `output`/`status` (read job output by job_id), `kill` (stop running job). Jobs are scoped to the caller's `session_id`.

### 2.10 Admin Tools (`admin_tools.py`)

File: `src/agent_tools/admin_tools.py` (793 lines)

| Function | Lines | Description |
|---|---|---|
| `do_manage_endpoints(content, owner)` | 22 | Manage model endpoints: list, add, delete, enable, disable |
| `do_manage_mcp(content, owner)` | 218-366 | Manage MCP servers: list, add (with validation), delete, reconnect, enable, disable, list_tools |
| `do_manage_webhooks(content, owner)` | 373-438 | Manage webhooks: list, add, delete, enable, disable |
| `do_manage_tokens(content, owner)` | 445-492 | Manage API tokens: list, create (bcrypt hash), delete |
| `do_manage_settings(content, owner)` | 498-769 | Manage settings: list, get, set, delete/reset, disable_tool, enable_tool |

**MCP Security** (lines 97-132):
- `_MCP_DENIED_COMMANDS` -- frozenset of 80+ denied shells/interpreters/runtimes
- `_MCP_CODE_EXEC_SHORT_FLAGS` / `_MCP_CODE_EXEC_LONG_FLAGS` -- denied execution flags
- `_MCP_SHELL_METACHARS` -- shell metacharacters refused in MCP command/args
- `_MCP_DANGEROUS_ENV` -- environment variables that could allow code injection (LD_PRELOAD, PYTHONPATH, NODE_OPTIONS, PATH, etc.)

### 2.11 Coding Tools (`coding_tools.py`)

File: `src/agent_tools/coding_tools.py` (68 lines)

```python
class TodoWriteTool:
    async def execute(self, content: str, ctx: dict) -> dict
```

Manages agent task lists. Each todo has `content`, `status` (pending/in_progress/completed), optional `priority`. Validates only one todo can be `in_progress`. Persists to `data/agent_todos/<session_id>.json`.

---

## 3. Model Capability Readers

The model capability reader system (`src/model_capability_readers/`) provides a unified interface for detecting model capabilities across different LLM providers. Each reader module conforms to the `CapabilityReader` protocol and transforms vendor-specific model metadata into standardized `ModelCapabilityRecord` instances.

### 3.1 Architecture

```
Endpoint URL / Kind
    |
    v
detect_vendor(base_url, endpoint_kind) -> vendor string
    |
    v
reader_for_vendor(vendor) -> reader module
    |
    v
records_from_payload(payload) -> tuple[ModelCapabilityRecord, ...]
```

**Dispatch** (`src/model_capability_readers/__init__.py`, line 54): `records_from_payload()` detects the vendor, looks up the reader module, and delegates. Falls back to `generic_openai` for unknown vendors.

### 3.2 Base Types (`base.py`)

File: `src/model_capability_readers/base.py` (312 lines)

#### Vendor Constants (lines 20-31)

```python
VENDOR_GENERIC_OPENAI = "generic_openai"
VENDOR_OPENAI         = "openai"
VENDOR_OPENROUTER     = "openrouter"
VENDOR_GOOGLE         = "google"
VENDOR_ANTHROPIC      = "anthropic"
VENDOR_OLLAMA         = "ollama"
VENDOR_LMSTUDIO       = "lmstudio"
VENDOR_LLAMACPP       = "llamacpp"
VENDOR_VLLM           = "vllm"
VENDOR_SGLANG         = "sglang"
VENDOR_HUGGINGFACE    = "huggingface"
VENDOR_UNKNOWN        = "unknown"
```

#### ModelCapabilityRecord (line 34)

```python
@dataclass(frozen=True)
class ModelCapabilityRecord:
    vendor: str
    model_id: str
    capability: ModelCapability
    display_name: str = ""
    stable_model_id: str = ""
    capability_assertions: tuple[CapabilityAssertion, ...] = ()
    deterministic_controls: tuple[DeterministicControl, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
```

#### Vendor Detection (`detect_vendor`, line 271)

Detection priority:
1. `endpoint_kind` string (14 known kinds mapped to vendors)
2. URL hostname/port patterns:
   - `.openrouter.ai` -> openrouter
   - `.openai.com` -> openai
   - `.anthropic.com` -> anthropic
   - `.googleapis.com` -> google
   - `.ollama.com` or port 11434 -> ollama
   - Port 1234 -> lmstudio
   - Port 8000 -> vllm
   - Port 30000 -> sglang
3. Falls back to `generic_openai` if host present, `unknown` otherwise

#### Key Utility Functions

| Function | Line | Purpose |
|---|---|---|
| `stable_model_id_for(vendor, model_id, endpoint_id, base_url)` | 125 | Builds `"{vendor}|{scope}|{model}"` composite ID |
| `openai_model_items(payload)` | 171 | Extracts model items from OpenAI-shaped payloads |
| `modalities_from_value(value)` | 200 | Parses modality strings into normalized tokens |
| `family_from_modalities(input_mod, output_mod)` | 224 | Determines model family (chat/embedding/image/audio/video) |
| `build_capability(...)` | 250 | Convenience builder for `ModelCapability` objects |

### 3.3 Reader Modules

#### READER_MODULES Registry (`__init__.py`, lines 28-36)

```python
READER_MODULES = {
    VENDOR_GENERIC_OPENAI: generic_openai,
    VENDOR_OPENAI:         openai,
    VENDOR_OPENROUTER:     openrouter,
    VENDOR_GOOGLE:         google,
    VENDOR_LLAMACPP:       llamacpp,
    VENDOR_OLLAMA:         ollama,
    VENDOR_LMSTUDIO:       lmstudio,
}
```

#### Generic OpenAI Reader (`generic_openai.py`, 58 lines)

Fallback reader. Assigns **no capabilities** -- identity only (model ID and display name). Used when the vendor is unknown.

#### OpenAI Reader (`openai.py`, 66 lines)

Reads OpenAI's `/v1/models` endpoint. OpenAI provides only `{id, object, created, owned_by}` -- no capability data -- so this reader also assigns `unknown_capability`.

#### OpenRouter Reader (`openrouter.py`, 200 lines)

The **richest** reader. OpenRouter's model metadata includes:
- Input/output modalities (text, image, audio, file, pdf, video, embedding)
- Supported parameters (tools, response_format, structured_outputs, reasoning, web_search)
- Context/token limits from `architecture`, `top_provider`, `per_request_limits`
- Supported voices (for TTS detection)
- Default parameter controls

**Capabilities detected:** CAP_VISION, CAP_TOOL_CALL, CAP_JSON_MODE, CAP_STRUCTURED_OUTPUT, CAP_REASONING, CAP_WEB_SEARCH, CAP_FILES, CAP_PDF, CAP_AUDIO_INPUT, CAP_AUDIO_OUTPUT, CAP_TTS, CAP_IMAGE_GENERATION, CAP_IMAGE_EDITING, CAP_VIDEO_GENERATION.

#### llama.cpp Reader (`llamacpp.py`, 429 lines)

Reads from multiple llama.cpp endpoints: `/v1/models`, `/props`, and `/slots`. Merges data from all three for the richest possible record.

**Capabilities detected:** CAP_TOOL_CALL (supports_tools), CAP_STREAMING (params.stream), CAP_VISION (modalities.vision), CAP_AUDIO_INPUT (modalities.audio).

**Deterministic controls detected:** temperature, top_p, seed, CONTROL_SYSTEM_PROMPT, CONTROL_TOOL_CHOICE.

#### Ollama Reader (`ollama.py`, 204 lines)

Reads from Ollama's `/api/tags` (model list) and `/api/show` (per-model detail).

**Capabilities detected:** CAP_REASONING (thinking/reasoning), CAP_VISION (vision), CAP_TOOL_CALL (tools/tool).

#### LM Studio Reader (`lmstudio.py`, 187 lines)

Reads LM Studio's native model metadata with `loaded_instances` and `capabilities` sub-objects.

**Capabilities detected:** CAP_VISION (vision capability), CAP_TOOL_CALL (trained_for_tool_use/tools/tool_use), CAP_REASONING (reasoning capability).

#### Google AI Studio Reader (`google.py` + `google_ai_studio_mapping.py`, 223 lines total)

Reads Google's Model resource format with `supportedGenerationMethods`.

**Capabilities detected:** CAP_REASONING (thinking field). **Controls detected:** temperature, topP, topK, prompt_caching, batch.

### 3.4 Capability Detection Summary

| Capability | Detected By |
|---|---|
| CAP_REASONING | Google, Ollama, LM Studio, OpenRouter |
| CAP_VISION | llama.cpp, LM Studio, Ollama, OpenRouter |
| CAP_TOOL_CALL | llama.cpp, LM Studio, Ollama, OpenRouter |
| CAP_STREAMING | llama.cpp |
| CAP_AUDIO_INPUT | llama.cpp, OpenRouter |
| CAP_JSON_MODE | OpenRouter |
| CAP_STRUCTURED_OUTPUT | OpenRouter |
| CAP_WEB_SEARCH | OpenRouter |
| CAP_IMAGE_GENERATION | OpenRouter |
| Generic/OpenAI | Identity only -- no capabilities assigned |

---

## 4. Search Integration

The search system (`src/search/`) provides web search, content extraction, caching, and ranking. It supports six search providers with automatic fallback.

### 4.1 Provider Registry

Defined in `services/search/providers.py`, line 19:

| Provider ID | Label | Needs API Key | Needs URL |
|---|---|---|---|
| `searxng` | SearXNG | No | Yes |
| `brave` | Brave Search | Yes | No |
| `duckduckgo` | DuckDuckGo | No | No |
| `google_pse` | Google PSE | Yes | No |
| `tavily` | Tavily | Yes | No |
| `serper` | Serper | Yes | No |
| `disabled` | Disabled | No | No |

**Provider chain** (`core.py`, `_build_provider_chain`): Primary provider first, then user-configured `search_fallback_chain` (default: `["duckduckgo"]`), skipping duplicates and "disabled".

### 4.2 Search Flow

```
User query
    |
    v
comprehensive_web_search() [core.py, line 250]
    |
    |-- Check SHA-256 cache key
    |-- Build provider chain
    |-- Try each provider (2 attempts each)
    |
    v
rank_search_results() [ranking.py, line 92]
    |-- Title relevance (2.0x weight)
    |-- Snippet quality (1.0x)
    |-- Domain authority (1.5x)
    |-- Recency score (1.0x)
    |-- News quality adjustment
    |
    v
Parallel content fetch (ThreadPoolExecutor)
    |
    v
Format output with sources, key points, TL;DR
```

### 4.3 Content Fetching (`content.py`)

`fetch_webpage_content(url, timeout, retry_attempt, max_bytes)` (line 481):

**SSRF Protection:**
- `_public_http_url(url)` -- validates http/https scheme, rejects private/loopback/link-local IPs
- `_PinnedBackend` -- pins TCP connections to pre-resolved IP (closes DNS-rebinding TOCTOU)
- `_PinnedTransport` -- full httpx transport wrapper with pinned backend
- Manual redirect following with re-validation at each hop

**Content handling:**
- PDF files -- extracted via pdfminer
- Plain text/Markdown/JSON -- returned verbatim
- HTML -- BeautifulSoup extraction with semantic container heuristic (`article`, `main`, `[role=main]`), body fallback when content < 600 chars

**Byte limits** (from `src/constants.py`):
- `WEB_FETCH_SOFT_MAX_BYTES = 2_000_000` (2 MB default download budget)
- `WEB_FETCH_HARD_MAX_BYTES = 20_000_000` (20 MB absolute ceiling)

### 4.4 Query Enhancement (`query.py`)

`enhance_query(original_query)` (line 86) processes queries through:
1. Site filter extraction (`site:example.com`)
2. Multi-part splitting (on `and`, `or`, `;`)
3. Question-type boost keywords (who->person, when->date, where->location, etc.)
4. Entity boosting (capitalized words, dates appended as OR-joined quoted terms)
5. AND-joining of sub-queries

### 4.5 Caching (`cache.py`)

- **Search cache**: SHA-256 keyed files in `data/cache/search/`; 30-minute TTL for news queries, 24 hours otherwise
- **Content cache**: SHA-256 keyed files in `data/cache/content/`; 2-hour TTL
- **LRU eviction**: At 1000 entries (`CACHE_MAX_ENTRIES`), oldest entries are removed
- **In-memory indices**: `search_cache_index` and `content_cache_index` dicts track timestamps
- **Metrics**: `cache_metrics` dict tracks `hits`, `misses`, `evictions`

### 4.6 Analytics (`analytics.py`)

Persists query statistics to `data/logs/search_analytics.json`:
- Total/successful/failed query counts
- Cache hit/miss/eviction counts
- Per-query pattern tracking (top 5 queries)
- Dedicated error logger at `data/logs/search_engine_error.log`

---

## 5. Tool System

### 5.1 Tool Schema Definitions (`tool_schemas.py`)

The `FUNCTION_TOOL_SCHEMAS` dict defines OpenAI function-calling-compatible JSON schemas for every tool. Each schema includes `name`, `description`, and `parameters` (JSON Schema).

### 5.2 Tool Parsing (`tool_parsing.py`)

Parses tool calls from model output. Supports multiple formats:

1. **XML tool calls**: `<tool_call><tool_name>name</tool_name><parameters>...</parameters></tool_call>`
2. **XML invoke**: `<invoke name="tool"><parameter name="key">value