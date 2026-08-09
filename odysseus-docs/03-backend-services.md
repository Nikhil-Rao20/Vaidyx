# Backend Services

This document provides comprehensive documentation for the Odysseus service layer located in `services/`. Every module, class, and significant function is documented with line references, external dependencies, configuration options, and integration details.

---

## 1. Services Overview

**Architecture:** The service layer follows a plug-in architecture where each service does one thing well, exposes a clean async interface, and can run in-process or as a standalone HTTP service (`services/__init__.py`, lines 1-9).

**Organization:** Services are organized into subdirectories by domain:

| Subdirectory | Purpose |
|---|---|
| `docs/` | Document RAG (retrieval-augmented generation) |
| `faces/` | Face detection and embedding (stub) |
| `hwfit/` | Hardware fitness, GPU detection, model compatibility |
| `memory/` | Persistent AI memory, skills, and knowledge extraction |
| `research/` | Deep research with LLM-in-the-loop |
| `search/` | Web search with multiple provider support |
| `shell/` | Safe shell command execution |
| `stt/` | Speech-to-text with multiple providers |
| `tts/` | Text-to-speech with multiple providers |
| `youtube/` | YouTube transcript and comment extraction |

**Top-level exports** (`services/__init__.py`, lines 11-37): The package facade exports the primary service classes and their associated data types:
- `SearchService`, `SearchResult`, `SearchResponse`
- `DocsService`, `DocChunk`, `IndexResult`
- `ResearchService`, `ResearchResult`, `ResearchSource`
- `MemoryService`, `Memory`, `MemorySearchResult`
- `ShellService`, `ShellResult`

The TTS, STT, YouTube, Faces, and Hardware Fitness services are accessed via their own subpackage imports rather than the top-level facade.

---

## 2. Document Service (`services/docs/`)

### Purpose
Provides personal document RAG (Retrieval-Augmented Generation) using ChromaDB for vector storage and retrieval.

### Files
- `__init__.py` (lines 1-18) -- Facade that re-exports `DocsService`, `DocChunk`, `IndexResult` from `service.py`, and `RAGManager`/`VectorRAG` from `src/`.
- `service.py` (lines 1-92) -- Core service implementation.

### Key Classes

**`DocChunk`** (dataclass, line 12)
A retrieved document chunk with fields: `text`, `source`, `score`, `metadata`.

**`IndexResult`** (dataclass, line 20)
Result of document indexing: `indexed` (count), `failed` (count), `errors` (list).

**`DocsService`** (line 28)
Main service class wrapping `RAGManager` from `src/rag_manager.py`.

| Method | Line | Description |
|---|---|---|
| `__init__(persist_dir)` | 38 | Initializes with ChromaDB persistence directory (defaults to `CHROMA_DIR` from `src/constants`) |
| `query(query, top_k=5)` | 41 | Searches the document index, returns `List[DocChunk]` |
| `index(directory)` | 64 | Indexes all documents from a directory, returns `IndexResult` |
| `add_document(text, metadata)` | 81 | Adds a single document to the index |
| `get_stats()` | 85 | Returns index statistics |
| `rebuild_index()` | 89 | Rebuilds the entire index |

### External Dependencies
- `src.rag_manager.RAGManager` -- Canonical RAG implementation
- `src.rag_vector.VectorRAG` -- Vector search backend
- `src.constants.CHROMA_DIR` -- Default persistence directory
- ChromaDB (via RAGManager)

### Configuration
- `persist_dir`: ChromaDB persistence directory, defaults to `CHROMA_DIR`

---

## 3. Face Recognition Service (`services/faces/`)

### Purpose
Face detection and embedding service (standalone worker and helpers).

### Files
- `__init__.py` (line 1) -- Contains only a docstring: `"Face detection + embedding service (standalone worker + helpers)."`

### Status
This is currently a **stub module**. The `__init__.py` file contains only a docstring and no implementation. The actual face detection/recognition logic is expected to be implemented as a standalone worker process that produces face embeddings.

---

## 4. Hardware Fitness Service (`services/hwfit/`)

### Purpose
Detects system hardware (CPU, GPU, RAM), estimates model memory requirements, and ranks LLM/image models against the user's hardware to recommend what will run well. This is the engine behind the "Cookbook" feature in the Odysseus UI.

### Files
- `__init__.py` -- Empty file (package marker)
- `hardware.py` (908 lines) -- System hardware detection (local and remote via SSH)
- `fit.py` (877 lines) -- Model-hardware fitness scoring and ranking engine
- `models.py` (344 lines) -- Model catalog, quantization maps, parameter parsing
- `profiles.py` (239 lines) -- llama.cpp serve profile computation
- `hf_discovery.py` (375 lines) -- HuggingFace collection/model discovery and caching
- `image_models.py` (436 lines) -- Image generation model registry and VRAM fitting
- `data/hf_models.json` -- Static model catalog (bundled)
- `data/mlx_community_models.json` -- Static MLX model catalog (bundled)

### Key Modules in Detail

#### hardware.py -- System Detection

**Key Functions:**

| Function | Line | Description |
|---|---|---|
| `detect_system(host, ssh_port, platform, fresh)` | 792 | Main entry point. Detects RAM, CPU, GPU. Cached per host (24h TTL). Supports local and remote (SSH) detection. |
| `_detect_nvidia()` | 84 | Detects NVIDIA GPUs via `nvidia-smi`. Handles driver mismatches, WSL, unified memory (GB10/DGX Spark). |
| `_detect_amd()` | 205 | Detects AMD GPUs via sysfs `/sys/class/drm/`. Handles discrete GPUs and APUs (Strix Halo). Uses `rocminfo` for ISA classification. |
| `_detect_apple_silicon()` | 309 | Detects Apple Silicon via `sysctl`. Reports unified memory budget based on RAM tier fractions (67-80%). |
| `_detect_windows()` | 568 | Detects Windows hardware via PowerShell/WMI. Single encoded PowerShell command for all hardware info. |
| `classify_amd_gfx(gfx)` | 178 | Classifies AMD ISA targets into families: RDNA (consumer), CDNA (datacenter), GCN (older). |
| `_group_gpus(gpus)` | 53 | Groups identical GPUs by name/VRAM for tensor-parallel serving. |

**GPU Bandwidth Tables** (lines 9-48):
- `GPU_BANDWIDTH`: Maps ~80 GPU models to their memory bandwidth in GB/s (NVIDIA 10xx-50xx, AMD RX, datacenter cards)
- `APPLE_BANDWIDTH_FIXED`: Apple Silicon M1-M5 bandwidths
- `APPLE_BANDWIDTH_BY_CORES`: M3/M4/M5 Max variants keyed by GPU core count

**Caching:** Results cached per (host, ssh_port, platform) tuple with 24-hour TTL (`CACHE_TTL`, line 16). The "Rescan" button passes `fresh=True` to bypass.

**Container Detection** (line 705): `_is_containerized()` checks for `/.dockerenv` and cgroup markers to warn users about potentially limited hardware visibility inside Docker.

#### fit.py -- Model Fitness Scoring

**Key Functions:**

| Function | Line | Description |
|---|---|---|
| `analyze_model(model, system, target_quant, scoring_use_case, target_context)` | 431 | Core analysis: evaluates a single model against hardware. Returns fit level, run mode, speed estimate, composite score. |
| `rank_models(system, use_case, limit, search, sort, quant, target_context, fit_only)` | 708 | Ranks all models against detected hardware. Returns sorted list of fit results (default top 50). |
| `_estimate_speed(model, quant, run_mode, system, offload_frac)` | 184 | Estimates tokens/second. Uses bandwidth-based model for GPU, fallback constants for CPU. Models partial offload with harmonic-blend bandwidth. |
| `_quality_score(model, quant, use_case)` | 259 | Scores model quality (0-100) based on parameter count, model family bonuses (Qwen, DeepSeek, LLaMA), architecture generation, and quantization penalties. |
| `_fit_score(required, available)` | 314 | Scores how well a model fits available memory (ratio-based with sweet-spot zones). |

**Scoring System** (line 54-68):
- `USE_CASE_WEIGHTS`: Per-use-case weight tuples for (quality, speed, fit, context) scores
- `SPEED_TARGET`: Target tokens/second by use case (e.g., 40 tok/s for general, 25 for reasoning)
- `CONTEXT_TARGET`: Target context lengths by use case

**Fit Levels:** `perfect`, `good`, `marginal`, `too_tight`

**Run Modes:** `gpu` (fully on GPU), `cpu_offload` (partial GPU + system RAM), `cpu_only` (no GPU), `no_fit` (does not fit)

**Sort Options** (line 655): `score`, `speed`, `vram`, `params`, `context`, `newest`

**Platform-Specific Filtering** (lines 764-811):
- MLX models shown only on Apple Silicon
- Prequantized models (AWQ/GPTQ) hidden on ROCm unless explicitly filtered
- GGUF-only filtering on Apple Silicon, consumer AMD (RDNA), and Windows
- Multi-GPU: GGUF quants hidden (vLLM/SGLang cannot serve them)

#### models.py -- Model Catalog and Quantization

**Key Data Structures** (lines 1-86):

| Constant | Description |
|---|---|
| `QUANT_BPP` | Bytes per parameter for each quantization format (~25 formats including GGUF, AWQ, GPTQ, MLX, FP8, QAT) |
| `QUANT_SPEED_MULT` | Speed multiplier relative to baseline for each quant |
| `QUANT_QUALITY_PENALTY` | Quality score adjustments per quant (0 for FP8/BF16, -12 for Q2_K) |
| `QUANT_BYTES_PER_PARAM` | Memory bytes per parameter for speed estimation |
| `QUANT_HIERARCHY` | Ordered quant tiers from highest quality to lowest: Q8_0 -> Q2_K |

**Key Functions:**

| Function | Line | Description |
|---|---|---|
| `get_models()` | 300 | Returns the merged model catalog: static JSON + dynamic HF collections + MLX community. Cached in memory. |
| `params_b(model)` | 152 | Parses parameter count to billions. Handles "7B", "355M", raw counts. |
| `estimate_memory_gb(model, quant, ctx)` | 192 | Estimates VRAM needed: `params * bpp + KV_cache + 0.5 GB overhead`. |
| `best_quant_for_budget(model, budget_gb, ctx)` | 210 | Finds best quantization that fits a VRAM budget, walking down the quality hierarchy. |
| `infer_use_case(model)` | 246 | Classifies model by name/tags: coding, reasoning, multimodal, embedding, tts, stt, chat, general. |
| `is_prequantized(model)` | 138 | Checks if a model uses native quantization (AWQ/GPTQ/FP8/MLX) vs GGUF. |
| `refresh_dynamic_catalogs(force)` | 282 | Refreshes HuggingFace collection caches and invalidates the merged model list. |

#### profiles.py -- Serve Profile Generation

**`compute_serve_profiles(system, model, serve_weights_gb, serve_quant)`** (line 91)

Generates 1-4 ready-to-launch llama.cpp serving profiles (Quality/Balanced/Speed) with concrete flags:
- `n_gpu_layers` -- Always 999 (offload all possible layers)
- `n_cpu_moe` -- Number of MoE expert layers to offload to CPU
- `cache_type` -- KV cache type: `q4_0`, `q8_0`, or `f16`
- `ctx` -- Context length (capped at model's trained maximum)

Two modes:
1. **Download mode** (default): Varies quantization across profiles (Q6_K/Q4_K_M/Q2_K)
2. **Serve mode** (`serve_weights_gb` set): Fixed quant, varies only serving knobs (KV cache type, context)

Vision model headroom: +1.1 GB for image encoder (line 132).

#### hf_discovery.py -- HuggingFace Model Discovery

Discovers models from HuggingFace collections API across multiple providers (lines 20-88):
- mlx-community, zai-org, deepseek-ai, MiniMaxAI, Qwen, stepfun-ai, google, openai, mistralai, meta-llama, NousResearch, moonshotai, mllama

**Key Functions:**

| Function | Line | Description |
|---|---|---|
| `fetch_collection_models(source, timeout, max_pages)` | 274 | Fetches models from a provider's HF collections. Paginates up to 20 pages. |
| `refresh_mlx_community_cache(force)` | 343 | Refreshes the MLX community model cache (24h TTL). |
| `refresh_hf_collection_models_cache(force)` | 352 | Refreshes all non-MLX HF collection caches. Partial failures preserve other providers' data. |

Cache files stored under `DATA_DIR/hwfit/` as JSON with fetch timestamps.

#### image_models.py -- Image Model Registry

Manages image generation models (Stable Diffusion, FLUX, etc.) discovered from HuggingFace collections.

**Key Functions:**

| Function | Line | Description |
|---|---|---|
| `get_image_models()` | 302 | Returns merged image model registry (static + HF collections). |
| `rank_image_models(system, search, sort)` | 328 | Scores and ranks image models against hardware. Tries BF16 -> FP8 -> Q4 budget fit. |
| `_estimate_image_model(repo_id)` | 73 | Estimates VRAM requirements for BF16/FP8/Q4 variants from model name patterns. |

### External Dependencies
- `core.platform_compat` -- SSH command execution, NVIDIA path candidates
- `src.constants.DATA_DIR` -- Data directory for caches
- `httpx` (via `urllib.request`) -- HuggingFace API calls
- No GPU libraries required (detection uses CLI tools: `nvidia-smi`, `rocminfo`, `sysctl`)

---

## 5. Memory Service (`services/memory/`)

### Purpose
Persistent AI memory system that automatically extracts personal facts from conversations, stores them in JSON + FAISS vector index, periodically audits/consolidates memories via LLM, and supports a learned-skills system.

### Files
- `__init__.py` (lines 1-15) -- Exports `MemoryService`, `MemoryManager`, `MemoryVectorStore`
- `service.py` (lines 1-127) -- High-level memory service with remember/recall API
- `memory.py` (lines 1-20) -- Compatibility re-export of `MemoryManager` from `src/memory`
- `memory_vector.py` (lines 1-3) -- Compatibility re-export of `MemoryVectorStore` from `src/memory_vector`
- `memory_extractor.py` (679 lines) -- Background auto-extraction and auditing of memories from conversations
- `skill_extractor.py` (305 lines) -- Background auto-extraction of reusable skills from complex agent runs
- `skill_format.py` (445 lines) -- SKILL.md parser/writer with YAML frontmatter
- `skill_importer.py` (314 lines) -- Import SKILL.md bundles from GitHub URLs
- `skills.py` (717 lines) -- Skills storage layer (disk-backed SKILL.md files)

### Key Classes

**`Memory`** (dataclass, `service.py` line 15)
Fields: `id`, `text`, `timestamp`, `session_id`, `metadata`.

**`MemorySearchResult`** (dataclass, `service.py` line 25)
Fields: `memories` (list), `query`, `total`.

**`MemoryService`** (`service.py` line 32)
High-level service wrapping `MemoryManager`, `MemoryVectorStore`, and `NativeMemoryProvider`.

| Method | Line | Description |
|---|---|---|
| `remember(text, session_id)` | 75 | Stores a new memory via the provider pipeline |
| `recall(query, top_k=5)` | 90 | Searches memories by query (hybrid keyword + vector) |
| `get_all(limit=100)` | 111 | Returns all memories |
| `delete(memory_id)` | 116 | Deletes a memory by ID, removing from both JSON and vector store |

### Memory Extraction (`memory_extractor.py`)

**`extract_and_store(session, memory_manager, memory_vector, endpoint_url, model, headers)`** (line 278)

Background async task that runs after each LLM response:
1. Takes the last 6 messages from the session (`CONTEXT_WINDOW`, line 91)
2. Strips media content (images/audio), keeping only text
3. Flattens the conversation into a single "analyze this transcript" prompt (lines 337-353) -- this was found necessary because passing raw alternating-role messages caused models to treat the input as a conversation to continue rather than analyze
4. Sends to LLM with `EXTRACT_SYSTEM_PROMPT` (line 73): extracts max 2 durable personal facts per conversation
5. Also runs `_fallback_memory_candidates()` (line 152): regex-based extraction of names, locations, preferences, goals
6. Deduplicates against existing memories using vector similarity (threshold 0.72) and Jaccard text similarity (threshold 0.6)
7. Stores in both JSON (source of truth) and FAISS vector index
8. Auto-pins identity facts (name, job, location)
9. Fires `memory_added` events via the event bus
10. Triggers memory audit every 5 new memories (`AUDIT_INTERVAL`, line 114)

**Categories:** `identity`, `preference`, `fact`, `contact`, `project`, `goal`

**`audit_memories(...)`** (line 495)

Periodic LLM-driven memory consolidation:
1. Fingerprints current memories (SHA-256 of id+text+category, order-independent) -- skips if unchanged since last audit
2. Sends all memories to LLM with `AUDIT_SYSTEM_PROMPT` (line 93): conservative merge/dedup rules
3. Safety net: refuses to save if >50% of memories would be removed (line 628)
4. Merges audited entries back with other users' entries (multi-tenant safe)
5. Rebuilds vector index from the full saved set
6. Persists fingerprint for skip-on-unchanged optimization

### Skills System

**`Skill`** (dataclass, `skill_format.py` line 319)

A reusable procedure stored as a `SKILL.md` file with YAML frontmatter. Fields include: `name` (slug), `description`, `version`, `category`, `tags`, `platforms`, `requires_toolsets`, `fallback_for_toolsets`, `status` (draft/published), `confidence` (0-1), `source` (learned/taught/imported), `when_to_use`, `procedure` (steps), `pitfalls`, `verification`.

**Disk Layout:** `data/skills/<category>/<name>/SKILL.md` with optional sibling files (templates, references). Usage counters in `data/skills/_usage.json`.

**`SkillsManager`** (`skills.py` line 62)

| Method | Line | Description |
|---|---|---|
| `load(owner)` | 278 | Loads all skills for an owner (strict ownership filter) |
| `add_skill(...)` | 293 | Creates a new skill with auto-dedup (Jaccard >= 0.82), auto-rename on collision |
| `update_skill(skill_id, updates, owner)` | 432 | Updates skill fields, supports rename (moves directory) |
| `delete_skill(skill_id, owner)` | 505 | Removes skill directory and usage entry |
| `index_for(owner, active_toolsets, platform)` | 584 | Returns the lightweight skill index injected into the system prompt |
| `get_relevant_skills(query, ...)` | 645 | Jaccard-based relevance search with tag boosting and confidence gating |
| `import_bundle_from_files(files, ...)` | 384 | Installs a fetched skill bundle from GitHub |

**`maybe_extract_skill(...)`** (`skill_extractor.py` line 122)

Triggered when an agent run has >= 2 rounds or >= 2 tool calls. Sends conversation to LLM, extracts a reusable procedure if one exists. Minimum confidence threshold: 0.6. Auto-approves if user preference `auto_approve_skills` is enabled.

**`skill_importer.py`** -- Imports SKILL.md bundles from GitHub URLs. Includes SSRF protection (blocks private/loopback IPs on every redirect hop), file size limits (64 files, 2MB total, 400KB per file), and GitHub-only URL validation.

### External Dependencies
- `src.memory.MemoryManager` -- JSON-backed memory store
- `src.memory_vector.MemoryVectorStore` -- FAISS vector index
- `src.memory_provider.NativeMemoryProvider` -- Hybrid search provider
- `src.llm_core.llm_call_async` -- LLM inference for extraction/audit
- `src.text_helpers.strip_think` -- Strips reasoning model noise from responses
- `src.event_bus.fire_event` -- Event dispatch
- `httpx` -- GitHub API calls for skill import
- `src.url_safety.check_outbound_url` -- SSRF protection

---

## 6. Research Service (`services/research/`)

### Purpose
Deep research engine using an iterative LLM-in-the-loop approach. Performs multi-round web searches, analyzes sources, and synthesizes comprehensive research reports.

### Files
- `__init__.py` (lines 1-12) -- Exports `ResearchService`, `ResearchResult`, `ResearchSource`, `ResearchHandler`
- `service.py` (lines 1-167) -- Clean service interface
- `research_handler.py` (488 lines) -- Core handler with task registry, formatting, and fallback chain

### Key Classes

**`ResearchSource`** (dataclass, `service.py` line 17)
Fields: `url`, `title`, `snippet`, `relevance`.

**`ResearchResult`** (dataclass, `service.py` line 25)
Fields: `query`, `summary`, `sources`, `sections`, `tokens_used`, `duration_seconds`.

**`ResearchService`** (`service.py` line 35)

| Method | Line | Description |
|---|---|---|
| `research(topic, llm_endpoint, llm_model, max_time, on_progress)` | 49 | Performs deep research. Returns `ResearchResult`. |
| `start_background(session_id, topic, ...)` | 148 | Starts research as a background asyncio task. Returns task info dict. |
| `get_status(session_id)` | 161 | Gets status of background research. |
| `cancel(session_id)` | 165 | Cancels running research. |
| `_parse_sources(report)` | 115 | Extracts `[title](url)` links from the `### Sources` section of a markdown report. |

**`ResearchHandler`** (`research_handler.py` line 25)

The core orchestrator managing research lifecycle:

| Method | Line | Description |
|---|---|---|
| `start_research(session_id, query, llm_endpoint, llm_model, max_time, llm_headers)` | 52 | Starts research as background task with progress tracking. Cancels existing research for the session. |
| `call_research_service(query, ...)` | 233 | Runs the `DeepResearcher` (from `src.deep_research`): up to 8 rounds, configurable max time (default 300s), max report tokens from settings. |
| `get_status(session_id)` | 106 | Returns status from in-memory registry or disk persistence. |
| `get_result(session_id)` | 147 | Returns completed research result (in-memory or disk). |
| `get_sources(session_id)` | 163 | Returns deduplicated source list, filtering low-quality findings. |
| `cancel_research(session_id)` | 131 | Cancels the researcher and its asyncio task. |

**Fallback Chain** (`_fallback_research`, line 297):
1. Primary: `DeepResearcher` (iterative LLM-in-the-loop)
2. Fallback 1: Legacy `ResearchOrchestrator` from `research_engine.py`
3. Fallback 2: Basic `comprehensive_web_search` from `src.search`

**Persistence:** Completed results saved to `DEEP_RESEARCH_DIR/<session_id>.json` with query, status, result, sources, and timestamps.

**Report Format** (`_format_research_report`, line 335): Produces a markdown report with:
- Research summary (duration, rounds, queries, URLs analyzed)
- Full report body
- Clickable sources section (deduplicated, quality-filtered)
- Analyzed URLs list (audit trail)
- Expandable raw findings section (`<details>` block)

### External Dependencies
- `src.deep_research.DeepResearcher` -- Primary research engine
- `src.research_utils.is_low_quality` -- Source quality filter
- `src.settings.get_setting` -- `research_max_tokens` setting
- `src.constants.DEEP_RESEARCH_DIR` -- Result persistence directory

---

## 7. Search Service (`services/search/`)

### Purpose
Multi-provider web search with caching, content extraction, ranking, and analytics. Supports SearXNG, Brave, DuckDuckGo, Google PSE, Tavily, and Serper.

### Files
- `__init__.py` (lines 1-35) -- Exports service and low-level search functions
- `service.py` (lines 1-103) -- Clean async service interface
- `core.py` (479 lines) -- Search orchestration, config, caching, comprehensive search
- `providers.py` (642 lines) -- Six search provider implementations
- `query.py` (150 lines) -- Query enhancement, entity extraction, cache duration
- `ranking.py` (165 lines) -- Search result ranking by relevance, domain, recency
- `content.py` (743 lines) -- Webpage content fetching with SSRF protection, PDF extraction
- `cache.py` (64 lines) -- Search and content caching with LRU eviction
- `analytics.py` (149 lines) -- Search metrics tracking and exception hierarchy

### Search Providers (`providers.py`)

| Provider | Function | Line | API Key Required | Notes |
|---|---|---|---|---|
| SearXNG | `searxng_search_api()` | 136 | No | Self-hosted. JSON API with HTML fallback. Auto-switches to news category for fresh queries. Retries with language/engine fallbacks. |
| Brave | `brave_search()` | 284 | Yes | `DATA_BRAVE_API_KEY` env var or `brave_api_key` setting |
| DuckDuckGo | `duckduckgo_search()` | 384 | No | Uses `duckduckgo-search` library with HTML scraping fallback. Resolves DDG redirect URLs. |
| Google PSE | `google_pse_search()` | 455 | Yes | Requires `GOOGLE_API_KEY` + `GOOGLE_PSE_CX`. Max 10 results per request. |
| Tavily | `tavily_search()` | 526 | Yes | `TAVILY_API_KEY` env var or `tavily_api_key` setting |
| Serper | `serper_search()` | 585 | Yes | `SERPER_API_KEY` env var or `serper_api_key` setting |

**SafeSearch** (lines 88-121): Configurable levels (`strict`/`moderate`/`off`) translated per-provider. Defaults to `strict`.

**Fallback Chain** (`core.py` line 119): If the primary provider returns empty, falls back through a configurable chain (default: `["duckduckgo"]`). User-configurable via `search_fallback_chain` setting.

### Comprehensive Search (`core.py`, line 250)

`comprehensive_web_search(query, max_pages, max_workers, time_filter, domain_whitelist, domain_blacklist, content_type, language, min_content_length, return_sources)`

1. Calls the provider chain for search results
2. Ranks results via `rank_search_results()`
3. Applies URL filters (domain whitelist/blacklist, content type, language)
4. Fetches full page content in parallel (`ThreadPoolExecutor`, 4 workers)
5. Extracts key points, TL;DR, quotes, and statistics from each page
6. Formats numbered source blocks with matching `[CONTENT N]` labels
7. Returns formatted context string and optional source list

### Content Fetching (`content.py`)

**`fetch_webpage_content(url, timeout, retry_attempt, max_bytes)`** (line 482)

Fetches and extracts content from web pages with comprehensive security:

**SSRF Protection:**
- `_public_http_url()` (line 73): Validates URLs are public (not private/loopback/link-local)
- `_resolve_public_ips()` (line 96): DNS resolution with private IP rejection
- `_PinnedTransport` (line 175): Custom `httpx.BaseTransport` that pins TCP connections to pre-resolved IPs, closing DNS-rebinding TOCTOU vulnerabilities
- Manual redirect following with SSRF validation at each hop

**Size Limits:**
- Soft cap: `WEB_FETCH_SOFT_MAX_BYTES` (default)
- Hard cap: `WEB_FETCH_HARD_MAX_BYTES` (absolute maximum)
- `BodyTooLargeError` raised for oversized Content-Length declarations
- Streaming download with byte-counting truncation
- Forces `Accept-Encoding: identity` to prevent gzip decompression bombs

**Content Extraction:**
- PDF: Via `pdfminer.high_level.extract_text` (optional dependency)
- Plain text/Markdown/JSON: Returned verbatim
- HTML: Semantic extraction from `<main>`, `<article>`, content-classed `<div>` elements. Falls back to full `<body>` with boilerplate stripped.
- Also extracts: meta tags, OG images, lists, tables, code blocks, JS framework detection

### Ranking (`ranking.py`)

`rank_search_results(query, results)` (line 92)

Composite scoring:
- Title relevance (2.0x weight): Word-boundary term matching
- Snippet quality (1.0x): Length factor + term hits
- Domain authority (1.5x): Trusted news domains (AP, Reuters, BBC, etc.) = 1.0; .edu/.gov = 1.0; .org = 0.7
- Recency (1.0x): 1.0 for <= 7 days, linear decay to 0.0 at 30 days
- News quality adjustment: Boosts trusted news, penalizes low-value aggregators and off-topic sports results

### Caching (`cache.py`)

- Search cache: `DATA_DIR/cache/search/`, LRU with 1000 max entries
- Content cache: `DATA_DIR/cache/content/`, 2-hour TTL
- Cache keys: SHA-256 of query+params
- News queries: 30-minute cache duration. Reference queries: 24-hour cache duration.

### Analytics (`analytics.py`)

Tracks: total/successful/failed queries, cache hits/misses, query patterns (top 5). Persisted to `DATA_DIR/logs/search_analytics.json`. Error logging to `DATA_DIR/logs/search_engine_error.log`.

### External Dependencies
- `httpx` -- HTTP client for all providers
- `httpcore` -- Low-level HTTP for DNS-pinned transport
- `bs4` (BeautifulSoup) -- HTML parsing
- `pdfminer` (optional) -- PDF text extraction
- `ddgs` (optional) -- DuckDuckGo search library
- `src.constants` -- `SEARXNG_INSTANCE`, `REQUEST_TIMEOUT`, `WEB_FETCH_USER_AGENT`, size limits

---

## 8. Shell Service (`services/shell/`)

### Purpose
Safe asynchronous shell command execution with timeout protection, output limiting, and streaming support.

### Files
- `__init__.py` (lines 1-4) -- Exports `ShellService`, `ShellResult`
- `service.py` (lines 1-164) -- Full implementation

### Key Classes

**`ShellResult`** (dataclass, line 11)
Fields: `stdout`, `stderr`, `exit_code`, `timed_out`.

**`ShellService`** (line 19)

| Method | Line | Description |
|---|---|---|
| `__init__(timeout=30, max_output=200_000)` | 29 | Configures default timeout and output size limit. Working directory defaults to `$HOME`. |
| `execute(command, timeout, cwd)` | 34 | Executes a shell command via `asyncio.create_subprocess_shell`. Captures stdout/stderr with size truncation. Returns `ShellResult`. |
| `stream(command, timeout=120)` | 88 | Executes command and yields output line-by-line as `{"stream": "stdout"|"stderr", "data": line}` dicts, followed by `{"exit_code": int}`. Uses async queue with dual reader tasks. |

**Safety Features:**
- Timeout protection: Kills process and returns `timed_out=True` on `asyncio.TimeoutError`
- Output truncation: Caps stdout/stderr at `max_output` bytes (default 200KB)
- Exception handling: All exceptions caught and returned as `ShellResult` with `exit_code=-1`
- Stream cleanup: Reader tasks are cancelled in `finally` block

### External Dependencies
- Standard library only (`asyncio`, `pathlib`)

---

## 9. STT (Speech-to-Text) Service (`services/stt/`)

### Purpose
Multi-provider speech-to-text transcription supporting local Whisper models, OpenAI-compatible API endpoints, and browser-native Web Speech API.

### Files
- `__init__.py` (line 1) -- Exports `get_stt_service`
- `stt_service.py` (209 lines) -- Full implementation

### Key Classes

**`STTService`** (line 14)

| Method | Line | Description |
|---|---|---|
| `available` (property) | 41 | Checks if STT is enabled and the provider is functional |
| `transcribe(audio_bytes)` | 156 | Main entry point. Dispatches to local or API provider based on settings. Returns transcribed text or None. |
| `_transcribe_local(audio_bytes, language)` | 90 | Local transcription via faster-whisper. Writes audio to temp file, transcribes, cleans up. |
| `_transcribe_api(audio_bytes, endpoint_id, model, language)` | 119 | API transcription via OpenAI-compatible `/audio/transcriptions` endpoint. Looks up endpoint in database. |
| `get_stats()` | 176 | Returns provider status, model info, language setting. |

**Providers:**
| Provider Value | Description |
|---|---|
| `"disabled"` | No STT |
| `"browser"` | Client-side Web Speech API (no server transcription) |
| `"local"` | `faster-whisper` on CPU/GPU via CTranslate2 |
| `"endpoint:<id>"` | OpenAI-compatible API via ModelEndpoint database record |

**Local Whisper Details** (`_get_whisper`, line 58):
- Uses `faster-whisper` (CTranslate2 backend, not PyTorch)
- Auto-detects CUDA: uses `float16` on GPU, `int8` on CPU
- Tolerant of missing/broken PyTorch -- gracefully falls back to CPU
- Model sizes configurable via `stt_model` setting (default: `"base"`)

### Configuration (via `data/settings.json`)
- `stt_enabled`: Boolean toggle
- `stt_provider`: Provider string
- `stt_model`: Whisper model size (e.g., `"base"`, `"small"`, `"medium"`, `"large"`)
- `stt_language`: Language code (empty for auto-detect)

### External Dependencies
- `faster-whisper` (optional) -- Local Whisper inference
- `torch` (optional) -- CUDA detection only
- `httpx` -- API endpoint calls
- `src.database.SessionLocal`, `ModelEndpoint` -- Endpoint lookup
- `src.settings.load_settings` -- Configuration

---

## 10. TTS (Text-to-Speech) Service (`services/tts/`)

### Purpose
Multi-provider text-to-speech synthesis with disk caching, supporting local Kokoro-82M GPU synthesis, OpenAI-compatible API endpoints, and browser-native Web Speech API.

### Files
- `__init__.py` (lines 1-9) -- Exports `TTSService`, `get_tts_service`
- `tts_service.py` (351 lines) -- Full implementation

### Key Classes

**`TTSService`** (line 30)

| Method | Line | Description |
|---|---|---|
| `available` (property) | 65 | Checks if TTS is enabled and the provider is functional |
| `synthesize(text, use_cache=True)` | 199 | Main entry point. Truncates to 5000 chars. Checks cache, dispatches to provider, caches result. Returns MP3/WAV bytes. |
| `synthesize_to_base64(text)` | 243 | Convenience wrapper returning base64-encoded audio |
| `_synthesize_api(text, endpoint_id, model, voice, speed)` | 161 | API synthesis via OpenAI-compatible `/audio/speech` endpoint |
| `clear_cache()` | 145 | Removes all cached TTS files |
| `get_stats()` | 253 | Returns provider status, model, voice, speed, cache size |

**Providers:**
| Provider Value | Description |
|---|---|
| `"disabled"` | No TTS |
| `"browser"` | Client-side Web Speech API (no server synthesis) |
| `"local"` | Kokoro-82M on CUDA GPU |
| `"endpoint:<id>"` | OpenAI-compatible API via ModelEndpoint database record |

**`_KokoroPipeline`** (line 284)

Internal class encapsulating the Kokoro-82M local TTS:
- Requires CUDA GPU (`torch.cuda.is_available()`)
- Uses `kokoro.KPipeline` with language code `"a"` (American English)
- Default voice: `"af_heart"`
- Output: 24kHz mono 16-bit WAV
- Synthesis pipeline: text -> chunks of audio numpy arrays -> concatenated -> WAV bytes

**Caching:**
- Cache directory: `TTS_CACHE_DIR` from constants
- Cache key: SHA-256 of `provider|model|voice|speed|text`
- Auto-detects format: MP3 (ID3/MPEG header) or WAV
- Size limit: 500MB default, configurable via `ODYSSEUS_TTS_CACHE_MAX_BYTES` env var
- LRU eviction: Trims to 80% capacity when exceeded, oldest files first

### Configuration (via `data/settings.json`)
- `tts_enabled`: Boolean toggle (default: `True`)
- `tts_provider`: Provider string
- `tts_model`: Model identifier (default: `"tts-1"`)
- `tts_voice`: Voice name (default: `"alloy"`)
- `tts_speed`: Speech speed multiplier (default: `"1"`)

### External Dependencies
- `kokoro` (optional) -- Kokoro-82M TTS pipeline
- `torch` (optional) -- CUDA GPU support for Kokoro
- `numpy` (optional) -- Audio array processing
- `soundfile` (optional) -- Audio file I/O
- `httpx` -- API endpoint calls
- `src.database.SessionLocal`, `ModelEndpoint` -- Endpoint lookup
- `src.constants.TTS_CACHE_DIR` -- Cache directory

---

## 11. YouTube Service (`services/youtube/`)

### Purpose
YouTube video transcript extraction and comment fetching for LLM context injection. When a user shares a YouTube URL, this service extracts the transcript and top comments so the LLM can analyze the video content without web searching.

### Files
- `__init__.py` (lines 1-22) -- Exports all public functions
- `youtube_handler.py` (303 lines) -- Full implementation

### Key Functions

| Function | Line | Description |
|---|---|---|
| `init_youtube()` | 48 | Imports and caches `YouTubeTranscriptApi`. Called at app startup. |
| `is_youtube_url(url)` | 61 | Quick check for youtube.com or youtu.be domains |
| `extract_youtube_id(url)` | 78 | Extracts video ID from many URL formats: `/watch?v=`, `youtu.be/`, `/embed/`, `/shorts/`, `/live/`, `/v/`. Supports youtube.com, m.youtube.com, music.youtube.com. |
| `extract_transcript_async(url, video_id, max_retries=3)` | 104 | Async transcript extraction with retries (1s backoff). Returns timestamped segments. Truncates to 8000 chars. |
| `format_transcript_for_context(transcript_data, url, title, channel)` | 161 | Formats transcript for LLM context injection. Includes title, channel, video ID, language, timestamped segments. Falls back to plain text if > 12000 chars. |
| `fetch_youtube_comments(video_id, max_comments=25, timeout=30)` | 208 | Fetches top comments via `yt-dlp` subprocess. Sorts by like count. Extracts title and channel from metadata. |
| `format_comments_for_context(comments_data, url)` | 282 | Formats comments for LLM context. Includes author, like count. Truncates at 4000 chars. |

### YouTube URL Parsing

Supported hosts (line 69): `www.youtube.com`, `youtube.com`, `m.youtube.com`, `music.youtube.com`, `youtu.be`

Supported path patterns (line 75): `/watch?v=`, `/embed/`, `/shorts/`, `/live/`, `/v/`

### LLM Instruction Prompt (`YOUTUBE_INSTRUCTION_PROMPT`, line 22)

Injected into the system prompt when a YouTube video is shared, instructing the LLM to provide:
1. Summary (2-4 sentences)
2. Key Points (bullet list)
3. Notable Timestamps (3-5 moments)
4. Audience Reception (comment sentiment)

Explicitly instructs: "Do NOT web search for this video."

### External Dependencies
- `youtube-transcript-api` (optional) -- Transcript extraction API
- `yt-dlp` (optional) -- Comment fetching via CLI subprocess. Looked up from venv bin first, then system PATH.
- Standard library: `asyncio`, `json`, `urllib.parse`

### Configuration
- No settings.json configuration -- availability depends on installed dependencies
- `max_retries=3` for transcript extraction
- `max_comments=25` for comment fetching
- `timeout=30` for yt-dlp subprocess
