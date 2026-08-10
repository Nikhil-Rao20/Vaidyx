# Model Capabilities and Search System

This document covers the model capability detection pipeline, multi-provider web
search system, MCP server management, and application-wide constants.

---

## 1. Model Capability Readers

The `src/model_capability_readers/` package normalizes already-fetched provider
API payloads into a canonical `ModelCapabilityRecord` shape. Readers perform
**no network I/O** and do not infer capabilities from model IDs or display names
-- they only map fields explicitly present in the provider response.

### 1.1 Architecture

A central registry (`__init__.py`) maps vendor identifiers to reader modules:

| Vendor constant       | Reader module     | Provider                      |
|-----------------------|-------------------|-------------------------------|
| `generic_openai`      | `generic_openai`  | Any OpenAI-compatible server  |
| `openai`              | `openai`          | OpenAI Models API             |
| `openrouter`          | `openrouter`      | OpenRouter catalog            |
| `google`              | `google`          | Google Gemini / AI Studio     |
| `ollama`              | `ollama`          | Ollama native API             |
| `lmstudio`            | `lmstudio`        | LM Studio native API          |
| `llamacpp`            | `llamacpp`        | llama.cpp server              |

Vendors without a dedicated reader (`anthropic`, `huggingface`, `vllm`, `sglang`)
are listed in `PLACEHOLDER_VENDOR_IDS` and fall through to `generic_openai`.

### 1.2 Core Data Model (`base.py`)

**`ModelCapabilityRecord`** (frozen dataclass, line 34) is the universal output:

| Field                    | Type                              | Purpose                                  |
|--------------------------|-----------------------------------|------------------------------------------|
| `vendor`                 | `str`                             | Canonical vendor identifier              |
| `model_id`               | `str`                             | Provider-native model identifier         |
| `stable_model_id`        | `str`                             | Deterministic cross-endpoint key         |
| `display_name`           | `str`                             | Human-friendly label                     |
| `capability`             | `ModelCapability`                 | Canonical capability object              |
| `capability_assertions`  | `tuple[CapabilityAssertion, ...]` | Claimed/unsupported capability proofs    |
| `deterministic_controls` | `tuple[DeterministicControl, ...]`| Supported sampling parameters            |
| `raw`                    | `Mapping[str, Any]`               | Original provider payload                |

**`stable_model_id_for()`** (line 125) produces a deterministic key in the format
`{vendor}|{scope}|{model}` where scope is either `endpoint:{id}`,
`url:{sha256_prefix}`, or `global`.

### 1.3 Vendor Detection

`detect_vendor()` (line 271) resolves a vendor from two signals:

1. **`endpoint_kind`** -- explicit string (e.g. `"openai"`, `"ollama"`, `"gemini"`).
2. **`base_url`** -- hostname/port heuristics:
   - `*.openrouter.ai` -> `openrouter`
   - `*.openai.com` -> `openai`
   - `*.googleapis.com` -> `google`
   - Port 11434 -> `ollama`, Port 1234 -> `lmstudio`, Port 8000 -> `vllm`, Port 30000 -> `sglang`

### 1.4 Reader Details

**OpenAI** (`openai.py`): The `/v1/models` endpoint exposes only identity metadata
(`id`, `object`, `created`, `owned_by`). Capabilities are kept `unknown` since the
API does not report them.

**OpenRouter** (`openrouter.py`): The richest reader. Extracts modalities from
`architecture` or arrow notation, capabilities from `supported_parameters`, token
limits, and deterministic controls.

**Google** (`google.py` + `google_ai_studio_mapping.py`): Maps Gemini `models.list`
/ `models.get`. Reads `supportedGenerationMethods`, token limits, `thinking`,
and sampling controls.

**Ollama** (`ollama.py`): Handles `/api/tags` and `/api/show`. Maps `capabilities`
values (`vision`, `tools`, `thinking`) and `context_length`.

**LM Studio** (`lmstudio.py`): Resolves `type`/`model_type` to family. Extracts
vision/tools/reasoning capabilities and context lengths from loaded instances.

**llama.cpp** (`llamacpp.py`): Merges up to three payloads (`/v1/models`, `/props`,
`/slots`). Extracts modalities, tool support, sampling parameters, and slot counts.

**Generic OpenAI** (`generic_openai.py`): Fallback; extracts only `id` and
`display_name`, capability set to `unknown`.

### 1.5 Modality and Capability Normalization

`base.py` provides shared normalization:

- **`normalize_modality_token()`** (line 179): Maps aliases like `img` -> `image`,
  `speech` -> `audio`, `documents` -> `file`.
- **`split_modality_arrow()`** (line 213): Parses `"text->image"` arrow notation.
- **`family_from_modalities()`** (line 224): Determines model family (`chat`,
  `embedding`, `image`, `video`, `audio`) from output modalities.

---

## 2. Search Integration

The search system lives canonically in `services/search/`; `src/search/` contains
thin compatibility shims that re-export from there so legacy import paths keep
working.

### 2.1 Provider Layer (`providers.py`)

Six search providers, registered in `PROVIDER_INFO`:

| Provider    | API Key Required | Notes                                |
|-------------|------------------|--------------------------------------|
| `searxng`   | No               | Self-hosted; JSON API + HTML fallback|
| `brave`     | Yes              | Brave Search API                     |
| `duckduckgo`| No               | `ddgs` library + HTML scraping       |
| `google_pse`| Yes              | Google Programmable Search Engine     |
| `tavily`    | Yes              | Tavily Search API                    |
| `serper`    | Yes              | Serper.dev Google SERP API           |
| `disabled`  | --               | Search fully disabled                |

API keys are resolved from admin settings first, then legacy `search_api_key`,
then environment variables (`DATA_BRAVE_API_KEY`, `GOOGLE_API_KEY`,
`TAVILY_API_KEY`, `SERPER_API_KEY`).

**SafeSearch** is normalized to three canonical levels (`strict`, `moderate`,
`off`) and translated to each provider's native parameter format.

**SearXNG** has multiple fallback strategies: news -> general, language-pinned ->
language-free, pinned engines -> default engines, JSON API -> HTML scraping.

### 2.2 Core Orchestrator (`core.py`)

**`searxng_search_results()`** (line 136): The primary search entry point.
- Checks disk cache (SHA-256 key, JSON files under `data/cache/search/`)
- Builds a provider fallback chain: primary provider, then user-configured or
  default fallbacks (default: `["duckduckgo"]`)
- Retries each provider up to 2 times
- Ranks results via `rank_search_results()` before caching
- Cache TTL: 30 minutes for news queries, 24 hours for reference queries

**`comprehensive_web_search()`** (line 250): Advanced search with parallel content
fetching. Supports domain whitelist/blacklist, content type and language filters.
Extracts key points, TL;DR, quotes, and statistics from fetched pages.

### 2.3 Result Ranking (`ranking.py`)

`rank_search_results()` (line 92) scores results on four dimensions:

| Factor            | Weight | Method                                        |
|-------------------|--------|-----------------------------------------------|
| Title relevance   | 2.0x   | Word-boundary term matching                   |
| Snippet quality   | 1.0x   | Length factor + term frequency                |
| Domain authority   | 1.5x   | Trusted news = 1.0, .edu/.gov = 1.0, .org = 0.7 |
| Recency           | 1.0x   | 1.0 for <=7 days, linear decay to 0.0 at 30 days |

News queries receive additional adjustments: trusted news domains get +1.2,
low-value aggregators (Facebook, Yahoo, MSN) get -0.8, and off-topic sports
results are penalized -1.5.

### 2.4 Query Enhancement (`query.py`)

`enhance_query()` (line 86): extracts `site:` filters, splits multi-part queries,
detects question types (`who` -> person, `when` -> date), extracts entities
(capitalized words, dates), and boosts them via `OR` clauses.

### 2.5 Content Fetching (`content.py`)

`fetch_webpage_content()` (line 481) is SSRF-hardened: DNS validates public IPs,
TCP is pinned to resolved IP (`_PinnedTransport`), body size is capped (soft 2 MB,
hard 20 MB), compressed encoding is refused. Handles HTML, PDF (pdfminer), plain
text, Markdown, and JSON. Cached 2 hours under `data/cache/content/`.

### 2.6 Caching (`cache.py`)

Two LRU-evicted disk caches under `data/cache/` (max 1000 entries each):
**search/** keyed on `query|count|time_filter` and **content/** keyed on
`url#cap={bytes}`. `cleanup_cache()` (line 40) evicts by age then by count.

### 2.7 Analytics (`analytics.py`)

`get_search_stats()` (line 123) returns total/successful/failed queries, cache
hit rates, top 5 query patterns, and eviction counts. Persisted to
`data/logs/search_analytics.json`.

---

## 3. MCP Management

### 3.1 McpManager (`mcp_manager.py`)

The `McpManager` class (line 135) manages the lifecycle of MCP server connections.

**Transports supported:**
- `stdio` -- subprocess communication (built-in and user-added servers)
- `sse` -- Server-Sent Events over HTTP
- `http` -- Streamable HTTP with automatic OAuth (background authorization flow)

**Key internal state:**

| Dict                | Contents                                    |
|---------------------|---------------------------------------------|
| `_connections`      | `server_id -> {status, name, transport, ...}` |
| `_tools`            | `server_id -> [tool_schema, ...]`            |
| `_sessions`         | `server_id -> ClientSession`                 |
| `_stacks`           | `server_id -> AsyncExitStack`                |
| `_connect_tasks`    | `server_id -> background Task` (HTTP/OAuth)  |

**Tool routing**: Tools are namespaced as `mcp__{server_id}__{tool_name}`.
`call_tool()` (line 467) dispatches to the correct session; crashed built-in
servers are auto-reconnected.

**Plan mode safety**: `plan_mode_blocked_mcp()` (line 621) blocks non-read-only
tools using server annotations (`readOnlyHint`/`destructiveHint`) or a verb-prefix
heuristic (`list`, `get`, `read`, `search`, `fetch`, `query`, etc.).

**Prompt integration**: `get_tool_descriptions_for_prompt()` (line 659) generates
cached tool descriptions with parameter hints for the agent system prompt.

### 3.2 Built-in MCP Servers (`builtin_mcp.py`)

Four Python-based built-in servers run as stdio subprocesses:

| Server ID    | Script                           | Purpose           |
|--------------|----------------------------------|--------------------|
| `image_gen`  | `mcp_servers/image_gen_server.py`| Image generation   |
| `memory`     | `mcp_servers/memory_server.py`   | Persistent memory  |
| `rag`        | `mcp_servers/rag_server.py`      | RAG retrieval      |
| `email`      | `mcp_servers/email_server.py`    | Email (IMAP)       |

One NPX-based server:

| Server ID          | Package                  | Purpose              |
|--------------------|--------------------------|----------------------|
| `builtin_browser`  | `@playwright/mcp@latest` | Browser automation   |

**Environment flags:** `VAIDYX_DISABLE_MCP` (disable all), `VAIDYX_BROWSER_MCP_REQUIRE_CACHE` (require cached package), `VAIDYX_BROWSER_EXECUTABLE`,
`VAIDYX_BROWSER_ISOLATED` (default on), `VAIDYX_BROWSER_NO_SANDBOX` (default on).

Registration is async and background-scheduled; NPX servers delayed 3 seconds.

---

## 4. Constants (`src/constants.py`)

### 4.1 Core Application Settings

| Constant              | Value / Source               | Purpose                          |
|-----------------------|------------------------------|----------------------------------|
| `APP_VERSION`         | `"1.0.2"`                    | Application version string       |
| `DATA_DIR`            | `VAIDYX_DATA_DIR` or default| Root for all persisted data      |
| `MAX_CONTEXT_MESSAGES`| `90`                         | Conversation history cap         |
| `REQUEST_TIMEOUT`     | `20` seconds                 | HTTP request timeout             |
| `DEFAULT_TEMPERATURE` | `1.0`                        | Default LLM temperature          |
| `DEFAULT_MAX_TOKENS`  | `0` (unlimited)              | Default max token output         |
| `PASSWORD_MIN_LENGTH` | `8`                          | Auth password minimum            |

### 4.2 Agent Tool Output Limits

| Constant           | Value      | Purpose                                    |
|--------------------|------------|--------------------------------------------|
| `MAX_OUTPUT_CHARS` | `10,000`   | Cap for bash/python/web_search output      |
| `MAX_READ_CHARS`   | `20,000`   | Cap for read_file / document preview       |
| `MAX_DIFF_LINES`   | `400`      | Cap for edit_file unified-diff display     |

### 4.3 Web Fetch Size Policy

| Constant                  | Value       | Purpose                          |
|---------------------------|-------------|----------------------------------|
| `WEB_FETCH_SOFT_MAX_BYTES`| `2,000,000` | Default download budget (2 MB)   |
| `WEB_FETCH_HARD_MAX_BYTES`| `20,000,000`| Absolute ceiling (20 MB)         |

### 4.4 Data File Paths

All persisted files live under `DATA_DIR` (40+ paths defined). Key databases:
`APP_DB`, `SCHEDULED_EMAILS_DB`, `EMAIL_CACHE_DB`. Key subdirectories:
`RAG_DIR`, `CHROMA_DIR`, `DEEP_RESEARCH_DIR`, `MCP_OAUTH_DIR`,
`MEMORY_VECTORS_DIR`.

`internal_api_base()` (line 112) resolves the loopback URL for in-process API
calls: `VAIDYX_INTERNAL_BASE` > `APP_PORT` > fallback `http://127.0.0.1:7000`.

---

## 5. Multi-model Support

### 5.1 Supported Vendors

Twelve vendor identifiers are defined, covering the major LLM ecosystem:

- **Cloud APIs**: OpenAI, Anthropic, Google (Gemini), OpenRouter
- **Local runtimes**: Ollama, LM Studio, llama.cpp, vLLM, SGLang
- **Platforms**: HuggingFace
- **Generic**: Any OpenAI-compatible endpoint

### 5.2 Capability Taxonomy

Families: `chat`, `embedding`, `image`, `video`, `audio`, `rerank`, `unknown`.

Capabilities: `vision`, `tool_call`, `reasoning`, `streaming`, `json_mode`,
`structured_output`, `web_search`, `audio_input/output`, `tts`,
`image_generation/editing`, `video_generation`, `files`, `pdf`, `transcription`.

Controls: `temperature`, `top_p`, `top_k`, `seed`, `system_prompt`,
`tool_choice`, `prompt_caching`, `batch`.

---

## 6. Key Functions Reference

### Model Capability Readers

| Function | File | Line | Purpose |
|----------|------|------|---------|
| `records_from_payload()` | `__init__.py` | 54 | Top-level entry: detect vendor, dispatch to reader |
| `reader_for_vendor()` | `__init__.py` | 49 | Map vendor string to reader module |
| `detect_vendor()` | `base.py` | 271 | Resolve vendor from URL/kind |
| `stable_model_id_for()` | `base.py` | 125 | Generate deterministic model key |
| `build_capability()` | `base.py` | 250 | Construct canonical ModelCapability |
| `family_from_modalities()` | `base.py` | 224 | Determine model family from output modalities |
| `record_from_model()` | `openrouter.py` | 128 | Parse OpenRouter model catalog entry |
| `capability_from_model()` | `google_ai_studio_mapping.py` | 101 | Map Google model resource to capability |
| `record_from_props_payload()` | `llamacpp.py` | 317 | Parse llama.cpp /props payload |
| `record_from_show_payload()` | `ollama.py` | 118 | Parse Ollama /api/show response |
| `record_from_native_model()` | `lmstudio.py` | 107 | Parse LM Studio native model metadata |

### Search System

| Function | File | Line | Purpose |
|----------|------|------|---------|
| `searxng_search_results()` | `core.py` | 136 | Primary cached search entry point |
| `comprehensive_web_search()` | `core.py` | 250 | Advanced search with content fetching |
| `invalidate_search_cache()` | `core.py` | 220 | Clear search result cache |
| `fetch_webpage_content()` | `content.py` | 481 | SSRF-safe page content extraction |
| `rank_search_results()` | `ranking.py` | 92 | Score and sort search results |
| `enhance_query()` | `query.py` | 86 | Query processing with entity boosting |
| `searxng_search_api()` | `providers.py` | 135 | SearXNG JSON API with fallback chain |
| `brave_search()` | `providers.py` | 284 | Brave Search API call |
| `duckduckgo_search()` | `providers.py` | 384 | DuckDuckGo library + HTML fallback |
| `get_search_stats()` | `analytics.py` | 123 | Aggregated search metrics |

### MCP Management

| Function | File | Line | Purpose |
|----------|------|------|---------|
| `McpManager.connect_server()` | `mcp_manager.py` | 152 | Connect to MCP server (any transport) |
| `McpManager.call_tool()` | `mcp_manager.py` | 467 | Route and execute MCP tool call |
| `McpManager.plan_mode_blocked_mcp()` | `mcp_manager.py` | 621 | Identify write-mode tools to block |
| `McpManager.get_tool_descriptions_for_prompt()` | `mcp_manager.py` | 659 | Generate prompt tool descriptions |
| `mcp_tool_is_readonly()` | `mcp_manager.py` | 107 | Classify tool as read-only or write |
| `register_builtin_servers()` | `builtin_mcp.py` | 163 | Auto-register built-in MCP servers |
