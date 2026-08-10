# Tests, Scripts, and Specs

This document covers the Vaidyx test suite, CLI/utility scripts, and architectural specifications. It is organized into ten sections matching the major structural areas.

---

## 1. Test Suite Overview

### Framework and Configuration

Vaidyx uses **pytest** as its Python testing framework and **Node.js `node:test`** for JavaScript/streaming tests. Configuration lives in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Test counts at a glance:**

| Metric | Value |
|---|---|
| Total test files | 762 Python + streaming/JS files |
| Collected pytest items (last survey) | 3,586 |
| Total test lines (est.) | ~54,800 |
| CLI test files (in `tests/cli/`) | 28 |
| Streaming test files (in `tests/streaming/`) | 4 |
| Helper modules (in `tests/helpers/`) | 7 |
| Top-level infrastructure files | 6 |

### Taxonomy System

Tests are classified at collection time via `tests/_taxonomy.py` (162 lines) and `tests/conftest.py` (95 lines). The taxonomy assigns two markers per file:

- **`area_*`** -- broad category marker (8 areas)
- **`sub_*`** -- fine-grained sub-area marker (derived from filename tokens)

**Area distribution:**

| Area | Files | Description |
|---|---:|---|
| `uncategorized` | 310 | Tests not matched by keyword rules (fallback) |
| `services` | 202 | LLM, cookbook, email, calendar, memory, gallery, research, MCP, etc. |
| `security` | 89 | Auth, owner-scope, SSRF, XSS, confinement, redaction |
| `js` | 50 | JavaScript/Node-backed tests (`.js`, `.mjs`, `.ts` extension) |
| `unit` | 41 | Pure parser/utility tests (nonstring, nondict, atomic, regex) |
| `routes` | 39 | HTTP route/API behavior |
| `cli` | 30 | CLI/script behavior |
| `helpers` | 1 | Self-tests for `tests/helpers/` |

Classification priority: `js` (by extension) > `helpers` (by directory) > `security` > `cli` > `routes` > `services` > `unit` > `uncategorized`.

### Running Tests

```bash
# Full suite
./venv/bin/python -m pytest

# By taxonomy area
./venv/bin/python -m pytest -m area_security
./venv/bin/python -m pytest -m "area_services and sub_cookbook"

# Focused runner (validates area/sub-area names)
./venv/bin/python tests/run_focus.py --area security
./venv/bin/python tests/run_focus.py --area services --sub-area cookbook
./venv/bin/python tests/run_focus.py --fast  # excludes @pytest.mark.slow

# Fast lane with duration reporting
./venv/bin/python tests/run_focus.py --area services --fast --durations 25

# Order-sensitivity diagnostic (randomized order)
./venv/bin/python tests/run_order_report.py --seed 123 -- tests/cli/ -q

# JavaScript streaming tests
node --test tests/streaming/invariant.test.mjs
node --test tests/streaming/segmenter.test.mjs
```

### Key Source Files

| File | Lines | Purpose |
|---|---:|---|
| `tests/conftest.py` | 95 | Root conftest: adds project root to `sys.path`, stubs heavy deps, registers taxonomy markers, tags every test item |
| `tests/_taxonomy.py` | 162 | Conservative test classifier: maps filenames to `area_*`/`sub_*` markers using keyword sets and extension rules |
| `tests/run_focus.py` | 325 | Focused test selection runner -- wraps `pytest -m` with validated area/sub-area/keyword/fast-lane selection |
| `tests/run_order_report.py` | 156 | Report-only randomized-order runner -- shuffles collected items with a seeded RNG to surface order-sensitive tests |

---

## 2. CLI Tests

**Location:** `tests/cli/` (28 files, all classified `area_cli`)

All CLI tests follow a consistent pattern:

1. Create database stubs via `tests.helpers.db_stubs.make_core_db_stub()`
2. Load the script under test via `tests.helpers.cli_loader.load_script()`
3. Exercise internal functions (prefixed `_`) with `SimpleNamespace` fake rows
4. Assert JSON output, error handling, or data normalization

No CLI test uses `TestClient`, FastAPI, or a real SQLite database -- they are the lowest-coupling test group in the suite.

### CLI Test Files

| File | Lines | What It Tests |
|---|---:|---|
| `test_calendar_cli_name.py` | 13 | `_calendar_name()` handles missing/non-string calendar relations |
| `test_contacts_cli_rows.py` | 24 | Contact serialization row formatting |
| `test_cookbook_cli_state.py` | 17 | Cookbook CLI state management |
| `test_docs_cli_content_length.py` | 11 | Document CLI content length calculation |
| `test_gallery_cli_album_count.py` | 13 | Gallery album count serialization |
| `test_gallery_cli_preview.py` | 35 | Gallery preview text generation |
| `test_logs_cli_resolve_nonstring.py` | 13 | Logs CLI handles non-string values without crash |
| `test_mail_cli_read_empty_fetch.py` | 57 | Mail read subcommand handles empty IMAP fetch |
| `test_mail_cli_recipients.py` | 57 | Mail recipient parsing and formatting |
| `test_mcp_cli_env_serialize.py` | 29 | MCP CLI serializes non-object env JSON without crash |
| `test_mcp_cli_json.py` | 14 | MCP CLI JSON output formatting |
| `test_memory_cli_rows.py` | 22 | Memory CLI row serialization |
| `test_notes_cli_items.py` | 70 | Notes CLI item listing and filtering |
| `test_personal_cli_rows.py` | 22 | Personal docs CLI row formatting |
| `test_preset_cli_invalid_entries.py` | 18 | Preset CLI rejects non-object store files |
| `test_preset_cli_set_corrupt_entry.py` | 34 | Preset CLI handles corrupt preset entries |
| `test_preset_cli_store.py` | 14 | Preset CLI store load/save |
| `test_research_cli_preview.py` | 25 | Research CLI preview text truncation |
| `test_research_cli_status_filter.py` | 106 | Research CLI status filter (done/complete mapping) |
| `test_research_cli_status.py` | 57 | Research CLI status display |
| `test_research_cli_store.py` | 32 | Research CLI file store: skips non-object/broken JSON |
| `test_sessions_cli.py` | 39 | Session CLI normalizes numeric counters (string/None to int) |
| `test_signature_cli_export.py` | 45 | Signature CLI export formatting |
| `test_skills_cli_preview.py` | 32 | Skills CLI preview text generation |
| `test_skills_cli_rows.py` | 22 | Skills CLI row serialization |
| `test_tasks_cli_preview.py` | 11 | Tasks CLI preview text truncation |
| `test_theme_cli_store.py` | 15 | Theme CLI store operations |
| `test_webhook_cli_mask.py` | 12 | Webhook CLI token masking (short values, full reveal) |

### Example: Typical CLI Test Pattern

```python
# tests/cli/test_webhook_cli_mask.py (12 lines)
from tests.helpers.cli_loader import load_script
from tests.helpers.db_stubs import make_core_db_stub

def test_mask_token_handles_short_values(monkeypatch):
    make_core_db_stub(monkeypatch, models=["ScheduledTask"])
    cli = load_script("vaidyx-webhook")
    assert cli._mask_token("") == ""
    assert cli._mask_token("short") == "***"
    assert cli._mask_token("abcdef1234567890") == "abcdef...7890"
    assert cli._mask_token("short", reveal=True) == "short"
```

---

## 3. Streaming Tests

**Location:** `tests/streaming/` (4 JavaScript files, classified `area_js`)

These tests validate the streaming markdown segmenter -- the frontend component that decides which parts of a streamed markdown response are safe to "freeze" (render once and never re-render) versus which parts must stay live. This prevents visual flicker during token-by-token streaming.

### Core Invariant

```
render(finalized_prefix) + render(live_tail) === render(full_text)
```

At every prefix length of every streaming step, the split between finalized and live content must produce the same HTML as rendering the full text at once.

### Streaming Test Files

| File | Lines | Purpose |
|---|---:|---|
| `corpus.mjs` | 27 | Test corpus of 18 markdown samples: paragraphs, headings, lists, code fences, tables, mermaid diagrams, mixed documents |
| `markdownHarness.mjs` | 66 | Loads the real browser markdown renderer (`static/js/markdown.js`) under Node by mocking minimal browser globals. Also provides `normalizeRender()` for HTML comparison |
| `invariant.test.mjs` | 107 | **Centerpiece correctness test**: streams every corpus sample char-by-char and whitespace-chunked through three renderer pipelines, asserting the freeze/tail invariant at every step. Also tests `<think>` block handling |
| `segmenter.test.mjs` | 65 | Focused unit tests for `splitFinalized()`: verifies it finalizes closed fences, never finalizes into open fences, never splits loose lists, and correctly handles paragraph boundaries |

### How to Run

```bash
node --test tests/streaming/invariant.test.mjs
node --test tests/streaming/segmenter.test.mjs
```

### Renderer Pipelines Tested

1. **`mdToHtml`** -- bare markdown to HTML conversion
2. **`mdToHtml` after `squashOutsideCode`** -- the live-reply path (chat.js)
3. **`processWithThinking` after `squashOutsideCode`** -- the main path (chat.js, floats `<think>` blocks)

---

## 4. Tool and Feature Tests

The 734 test files in `tests/` (top-level) cover every major Vaidyx feature. The largest files by test count and line count:

### Largest Test Files

| File | Lines | Collected Tests | Area |
|---|---:|---:|---|
| `test_model_routes.py` | 1,778 | 139 | routes |
| `test_security_regressions.py` | 1,224 | 92 | security |
| `test_cookbook_helpers.py` | 912 | 65 | services |
| `test_pr_blocker_audit.py` | 964 | 58 | uncategorized |
| `test_agent_loop.py` | 469 | 52 | uncategorized |
| `test_service_health.py` | 472 | 47 | uncategorized |
| `test_embedding_lanes.py` | 1,104 | 29 | services |
| `test_email_oauth.py` | 580 | 28 | services |
| `test_review_regressions.py` | 930 | 26 | uncategorized |
| `test_rename_user_owner_sync.py` | 686 | 26 | security |

### Feature Coverage by Sub-Area

| Sub-Area | Files | What Is Tested |
|---|---:|---|
| `owner_scope` | 23 | Multi-user data isolation: every query filters by owner |
| `nonstring` | 22 | Robustness to non-string inputs (None, int, list, etc.) |
| `llm` | 16 | LLM core: temperature, sanitization, provider routing |
| `research` | 16 | Deep research sessions: lifecycle, preview, status |
| `session` | 16 | Chat session management: archiving, model filter, search |
| `memory` | 15 | AI memory store: consolidation, vector degradation, pinning |
| `owner` | 14 | Owner-based access control enforcement |
| `cookbook` | 13 | Model serving cookbook: download, serve, diagnose, deps |
| `calendar` | 10 | Calendar events: recurrence, parsing, import, timezones |
| `email` | 12 | Email: OAuth, IMAP, leak fixes, owner scope |
| `security` | 9 | Security regressions, prompt security, diffusion server security |
| `auth` | 9 | Auth: config lock concurrency, session revocation, regressions |
| `mcp` | 8 | MCP server management: builtin, npx cache, Python path |
| `confinement` | 7 | Tool path confinement and workspace restrictions |
| `nondict` | 7 | Robustness to non-dict inputs |
| `xss` | 5 | Cross-site scripting prevention |
| `gallery` | 5 | Image gallery features |
| `parse` / `parser` | 4 | Date/time parsing, calendar parsing |
| `ssrf` | 3 | Server-side request forgery prevention |
| `embedding` | 3 | Embedding lanes and vector operations |
| `scheduler` | 3 | Task scheduler behavior |
| `webhook` | 3 | Webhook management |

### Notable Individual Test Files

| File | Purpose |
|---|---|
| `test_agent_loop.py` | 52 tests for the agent loop: tool dispatch, rounds exhausted, budget enforcement |
| `test_tool_path_confinement.py` | 24 tests ensuring filesystem tools cannot escape the workspace |
| `test_prompt_security.py` | 21 tests for prompt injection resistance |
| `test_context_compactor.py` | 21 tests for context window management and compaction |
| `test_copilot.py` | 23 tests for the copilot feature |
| `test_tool_support_heuristic.py` | 22 tests for tool capability detection |
| `test_caldav_writeback.py` | CalDAV calendar sync and write-back operations |
| `test_carddav_password_encryption.py` | Contact sync password encryption |
| `test_builtin_mcp_bg_tasks.py` | Background task tracking in built-in MCP servers |
| `test_blind_compare_redaction.py` | Blind model comparison with data redaction |
| `test_cors_preflight.py` | CORS preflight request handling |
| `test_database_utcnow.py` | Database timestamp handling (UTC normalization) |
| `test_kv_cache_invalidation_2927.py` | KV cache invalidation regression (issue #2927) |

### Additional Test Artifacts

| File | Lines | Purpose |
|---|---:|---|
| `bombadil-spec.ts` | 107 | **Antithesis Bombadil spec** for UI fuzzing: defines extractors (login page, chat input, clickable elements, visible modals), login actions, explore actions (click random elements, type in chat, scroll), and three always-hold properties (`noBlankPage`, `noModalStacking`, `chatInputAppears`) |
| `markdown_codefence_placeholder_regression.mjs` | 69 | Regression test: code fence content inside blockquotes must not leak `___ALLOWED_HTML_` placeholders. Loads the real markdown renderer in a Node VM sandbox |

---

## 5. Helper Utilities

**Location:** `tests/helpers/` (7 files)

### `cli_loader.py` (25 lines)

Loads scripts from `scripts/` by name using `importlib.machinery.SourceFileLoader`. Returns the script as a module object. Every CLI test uses this.

```python
from tests.helpers.cli_loader import load_script
cli = load_script("vaidyx-webhook")  # loads scripts/vaidyx-webhook
```

### `db_stubs.py` (33 lines)

Creates lightweight `core.database` stubs for tests that need `SessionLocal` and model classes without a real database.

```python
from tests.helpers.db_stubs import make_core_db_stub
make_core_db_stub(monkeypatch, models=["Note", "Session"])
# or with explicit attribute values:
make_core_db_stub(monkeypatch, attributes={"SessionLocal": object}, install_core_package=True)
```

### `import_state.py` (169 lines)

Manages Python import state for tests that temporarily stub modules.

**Key functions:**

- `clear_module(dotted_name)` -- removes a module from `sys.modules` and its parent-package attribute
- `preserve_import_state(*module_names)` -- context manager that saves and restores `sys.modules` entries and parent-package attributes (two-phase restore: modules first, then parent attrs)
- `clear_fake_database_modules()` -- evicts a stubbed `core.database` (detected by missing string `__file__`), leaving real modules untouched
- `clear_fake_endpoint_resolver_modules(*extra_modules)` -- evicts a stubbed `src.endpoint_resolver` and dependent route modules

### `sqlite_db.py` (29 lines)

Constructs a file-backed temporary SQLite database for tests needing a real database.

```python
from tests.helpers.sqlite_db import make_temp_sqlite
SessionLocal, engine, tmpfile = make_temp_sqlite(metadata)
```

### `embedding_lanes.py` (124 lines)

Fakes for embedding-lane tests:

- `FakeEmbedder` / `FailingEmbedder` -- mock embedding model with configurable dimensions
- `FakeCollection` -- in-memory ChromaDB collection with `add`, `upsert`, `get`, `query`, `delete`
- `FakeChroma` -- in-memory ChromaDB client with `get_or_create_collection`, `delete_collection`
- `patch_chroma(monkeypatch, fake)` -- monkeypatches `src.chroma_client.get_chroma_client`

### `calendar_routes.py` (8 lines)

Deferred import wrapper for calendar route tests -- imports `routes.calendar_routes` after test stubs are installed.

### `__init__.py` (0 lines)

Empty package marker.

---

## 6. Scripts Overview

**Location:** `scripts/` (44 files total, ~9,860 lines)

The scripts directory contains:
- **20 `vaidyx-*` CLI tools** -- Unix-style subcommand CLIs for every feature
- **1 `vaidyx` dispatcher** -- umbrella command that discovers and dispatches to sub-CLIs
- **2 shell completion scripts** -- bash and zsh tab-completion
- **1 shared library** -- `_lib/cli.py` with common scaffolding
- **3 demo scripts** -- email demo seeding
- **12 standalone utility scripts** -- data migration, model catalog, GPU diagnostics

### CLI Architecture

All `vaidyx-*` CLIs share a common pattern via `scripts/_lib/cli.py` (122 lines):

| Function | Purpose |
|---|---|
| `quiet_logs()` | Forces root logger to WARNING (overridable via `LOG_LEVEL` env var) |
| `emit(obj, args)` | Writes JSON to stdout; pretty-prints if `--pretty` or TTY |
| `fail(msg, code=1)` | Prints error to stderr and exits non-zero |
| `common_parser(prog, description)` | Returns `ArgumentParser` with `--pretty`, `--version` pre-wired |
| `run(parser, argv=None)` | Parses args, dispatches to `args.func()`, catches KeyboardInterrupt (exit 130) and uncaught exceptions |

### The `vaidyx` Dispatcher (`scripts/vaidyx`, 134 lines)

Entry point for all CLI tools. Discovers `scripts/vaidyx-<name>` siblings and dispatches to them (like `git` finds `git-foo`):

```bash
vaidyx                    # list all subcommands
vaidyx mail list --pretty # runs vaidyx-mail list --pretty
vaidyx help mail          # shows vaidyx-mail --help
vaidyx --version          # prints version
```

Runs subcommands with the project's venv Python so dependencies resolve. Can be symlinked to `~/.local/bin/vaidyx`.

---

## 7. Shell Completion

### Bash Completion (`scripts/_completion/vaidyx.bash`, 92 lines)

Source from shell rc:
```bash
source /path/to/vaidyx-ui/scripts/_completion/vaidyx.bash
```

Features:
- First word after `vaidyx`: completes with subcommand names
- Subsequent words: completes with subcommand-specific subcommands (cached by parsing `--help` output)
- Works for both `vaidyx mail <tab>` and direct `vaidyx-mail <tab>`
- Lazy cache refresh via `_vaidyx_refresh_cache`

### Zsh Completion (`scripts/_completion/vaidyx.zsh`, 72 lines)

Drop in any `$fpath` directory:
```bash
fpath=(/path/to/scripts/_completion $fpath)
autoload -U compinit; compinit
```

Same behavior as the bash completion: lazy cache, subcommand discovery from `--help` output, works for both umbrella and direct invocation.

---

## 8. Demo Scripts

**Location:** `scripts/demo_email/` (3 files)

### `manage.sh` (71 lines)

Orchestrates the entire email demo lifecycle:

```bash
./manage.sh setup      # add Dovecot user, create account, seed mail
./manage.sh reseed     # wipe + re-seed the fake mail
./manage.sh teardown   # remove account, Dovecot user, and maildir
```

Safe by design: the demo user is in NO mbsync channel, so nothing touches a real mail server.

### `demo_account.py` (88 lines)

Creates/removes a switchable "Demo" EmailAccount in the Vaidyx database. Points at a local Dovecot instance (`localhost:31143`, STARTTLS) with password stored via Fernet encryption.

```bash
python demo_account.py setup     # add or update Demo account
python demo_account.py teardown  # remove it
```

### `seed_demo_emails.py` (394 lines)

Seeds a throwaway local-only mailbox with curated fake demo emails: varied senders, read/unread/flagged mix, reply threads, attachments, newsletters, calendar invites, urgent messages, and spam. Includes a pre-seeded cached AI reply keyed by Message-ID for reliable demo beats.

```bash
python seed_demo_emails.py            # append demo mail
python seed_demo_emails.py --reset    # wipe then re-seed (idempotent)
python seed_demo_emails.py --wipe-only # just empty the mailbox
```

---

## 9. Library and Utility Scripts

### Data Migration Scripts

| Script | Lines | Purpose | Usage |
|---|---:|---|---|
| `migrate_faiss_to_chroma.py` | 173 | One-time migration from FAISS to ChromaDB for memory and RAG vectors | `python scripts/migrate_faiss_to_chroma.py` |
| `update_database.py` | 168 | Database schema migration: adds `last_accessed`, `is_important`, `message_count` columns to sessions table | `python update_database.py` |
| `claim_ownerless.py` | 106 | Claims all ownerless data for a specific user after enabling multi-user auth | `python scripts/claim_ownerless.py admin@example.com` |
| `fix_paths.py` | 9 | Fixes `BASE_DIR` line in `app.py` (one-off path correction) | `python scripts/fix_paths.py` |

### Model Catalog Scripts

| Script | Lines | Purpose | Usage |
|---|---:|---|---|
| `add_hwfit_models.py` | 422 | Bulk-adds HuggingFace models to the hwfit catalog from specified authors/repos. Re-runnable (merges by name) | `python3 scripts/add_hwfit_models.py` |
| `backfill_model_release_dates.py` | 133 | Backfills `release_date` from HuggingFace API for catalog entries missing dates | `python scripts/backfill_model_release_dates.py [--refresh] [--limit N] [--dry-run]` |
| `import_from_vllm_recipes.py` | 341 | Imports models from the vllm-project/recipes catalog into hf_models.json | `python scripts/import_from_vllm_recipes.py --update-existing` or `--add-missing` |
| `hf_download.py` | 182 | Downloads HuggingFace models with clean pipe-friendly progress output | `python3 scripts/hf_download.py <repo_id> [--include "pattern"]` |

### Server Scripts

| Script | Lines | Purpose | Usage |
|---|---:|---|---|
| `diffusion_server.py` | 1,506 | OpenAI-compatible image generation API server using diffusers. Serves `/v1/images/generations` and `/v1/models` | `python3 scripts/diffusion_server.py --model /path/to/model --port 8100` |
| `mlx_image_server.py` | 465 | OpenAI-compatible image API wrapper for MLX image models. Delegates to MLX image CLI | `python3 scripts/mlx_image_server.py --model <model> --port <port>` |

### Document and Index Scripts

| Script | Lines | Purpose | Usage |
|---|---:|---|---|
| `index_documents.py` | 117 | Indexes documents from `personal_docs/` into the vector database using RAGManager. Chunks at 1000 chars with 200 overlap | `python scripts/index_documents.py` |

### Agent and Code Quality Scripts

| Script | Lines | Purpose | Usage |
|---|---:|---|---|
| `agent_migration_manifest.py` | 635 | Builds a portable JSON manifest from common agent export shapes for preview or import. Read-only, no app imports | `python scripts/agent_migration_manifest.py <input_dir> [--output manifest.json]` |
| `pr_blocker_audit.py` | 1,051 | Read-only pull request overlap audit helper. Invokes `gh` to find competing/conflicting PRs by file overlap and area rules | `python scripts/pr_blocker_audit.py [--input prs.json]` |

### GPU Diagnostic Scripts

| Script | Lines | Purpose | Usage |
|---|---:|---|---|
| `check-docker-gpu.sh` | 615 | NVIDIA Docker GPU diagnostic and optional setup helper. Default mode is read-only | `scripts/check-docker-gpu.sh` (diag), `--install-nvidia-toolkit` (install), `--enable-nvidia-overlay` (write .env) |
| `check-docker-amd-gpu.sh` | 205 | Read-only AMD/ROCm Docker passthrough diagnostic. Checks `/dev/kfd`, `/dev/dri`, render groups, Docker device passthrough | `scripts/check-docker-amd-gpu.sh` |

### Media Scripts

| Script | Lines | Purpose | Usage |
|---|---:|---|---|
| `encode_previews.sh` | 39 | Encodes screen recordings into web-optimized preview clips (VP9 .webm + H.264 .mp4) for the landing page. Auto-speeds clips longer than max_secs | `./encode_previews.sh <input> <name> [max_secs]` |

---

## 10. Specs

**Location:** `specs/` (1 file)

### `architecture-runtime-inventory.md` (412 lines)

Phase 0 planning baseline for codebase readability improvements (issue #4071). Maps the current runtime module structure, identifies high-risk boundaries, and recommends safe first refactor slices. Key sections:

**Structure overview:**

| Directory | Files | Concern |
|---|---|---|
| `src/` | 95 flat `.py` files + 2 subdirs | No domain grouping |
| `routes/` | 54 flat `.py` files | All route handlers in one flat directory |
| `core/` | 10 files | Manageable, but `database.py` is oversized |

**Largest modules (top 5):**

| File | Lines | Risk |
|---|---:|---|
| `src/tool_implementations.py` | 4,032 | HIGH -- 33 `do_*` functions, 17 importers |
| `routes/email_routes.py` | 3,245 | MEDIUM |
| `routes/cookbook_routes.py` | 2,969 | MEDIUM |
| `src/agent_loop.py` | 2,961 | HIGH -- 22 importers |
| `core/database.py` | 2,265 | HIGH -- 28 classes, 102 importers |

**Import dependency highlights:**

- `core/database.py` has **102 importers** -- the most depended-upon module
- `src/tool_implementations.py` has **17 importers**
- `src/agent_loop.py` has **22 importers**
- 31 backward-dependency imports from `src/` into `routes/` (function-level inline imports)

**Recommended refactor sequence:**

1. Split `tool_implementations.py` into `src/tools/*.py` by tool category (MEDIUM risk)
2. Group `routes/` by domain subdirectories, one domain per PR (MEDIUM risk)
3. Extract `agent_loop.py` submodules: prompt, classifier, verifier, runaway, context (MEDIUM-HIGH risk)
4. Structural reorganization of flat `src/` into layered packages (MEDIUM risk)
5. `core/database.py` split -- LAST, highest risk, 102 importers

**Safety guardrails:** one domain/slice per PR, no behavior changes mixed with file moves, compatibility shims via `__init__.py` re-exports, validate with `python -m compileall` and `pytest`.

---

## Appendix A: Complete File Inventory

### `tests/cli/` (28 files, 849 total lines)

All files follow the `load_script` + `make_core_db_stub` pattern and exercise internal `_` functions of the corresponding `scripts/vaidyx-*` CLI.

### `tests/helpers/` (7 files, 388 total lines)

| File | Lines | Key Exports |
|---|---:|---|
| `__init__.py` | 0 | Package marker |
| `calendar_routes.py` | 8 | `import_calendar_routes()` |
| `cli_loader.py` | 25 | `load_script(script_name)` |
| `db_stubs.py` | 33 | `make_core_db_stub(monkeypatch, ...)` |
| `embedding_lanes.py` | 124 | `FakeEmbedder`, `FailingEmbedder`, `FakeCollection`, `FakeChroma`, `patch_chroma()` |
| `import_state.py` | 169 | `clear_module()`, `preserve_import_state()`, `clear_fake_database_modules()`, `clear_fake_endpoint_resolver_modules()` |
| `sqlite_db.py` | 29 | `make_temp_sqlite(metadata)` |

### `tests/streaming/` (4 files, 265 total lines)

| File | Lines | Purpose |
|---|---:|---|
| `corpus.mjs` | 27 | 18 markdown test samples |
| `invariant.test.mjs` | 107 | Char-by-char and chunk invariant tests with 3 renderer pipelines |
| `markdownHarness.mjs` | 66 | Loads real browser renderer under Node |
| `segmenter.test.mjs` | 65 | Focused `splitFinalized()` unit tests |

### `scripts/` (44 files, ~9,860 total lines)

| File | Lines | Category |
|---|---:|---|
| `vaidyx` | 134 | Dispatcher |
| `vaidyx-backup` | 272 | CLI: backup |
| `vaidyx-calendar` | 259 | CLI: calendar |
| `vaidyx-contacts` | 147 | CLI: contacts |
| `vaidyx-cookbook` | 555 | CLI: cookbook |
| `vaidyx-docs` | 203 | CLI: documents |
| `vaidyx-gallery` | 185 | CLI: gallery |
| `vaidyx-logs` | 147 | CLI: logs |
| `vaidyx-mail` | 406 | CLI: email |
| `vaidyx-mcp` | 206 | CLI: MCP servers |
| `vaidyx-memory` | 157 | CLI: AI memory |
| `vaidyx-notes` | 176 | CLI: notes |
| `vaidyx-personal` | 127 | CLI: personal docs |
| `vaidyx-preset` | 139 | CLI: presets |
| `vaidyx-research` | 189 | CLI: research |
| `vaidyx-sessions` | 153 | CLI: sessions |
| `vaidyx-signature` | 142 | CLI: signatures |
| `vaidyx-skills` | 163 | CLI: skills |
| `vaidyx-tasks` | 163 | CLI: tasks |
| `vaidyx-theme` | 199 | CLI: themes |
| `vaidyx-webhook` | 156 | CLI: webhooks |
| `_lib/cli.py` | 122 | Shared CLI scaffolding |
| `_lib/__init__.py` | 0 | Package marker |
| `_completion/vaidyx.bash` | 92 | Bash tab-completion |
| `_completion/vaidyx.zsh` | 72 | Zsh tab-completion |
| `demo_email/manage.sh` | 71 | Demo orchestrator |
| `demo_email/demo_account.py` | 88 | Demo account setup |
| `demo_email/seed_demo_emails.py` | 394 | Demo email seeding |
| `add_hwfit_models.py` | 422 | Model catalog: bulk add |
| `agent_migration_manifest.py` | 635 | Agent migration manifest builder |
| `backfill_model_release_dates.py` | 133 | Model catalog: date backfill |
| `check-docker-amd-gpu.sh` | 205 | AMD GPU diagnostic |
| `check-docker-gpu.sh` | 615 | NVIDIA GPU diagnostic/setup |
| `claim_ownerless.py` | 106 | Data ownership claim |
| `diffusion_server.py` | 1,506 | Diffusion image server |
| `encode_previews.sh` | 39 | Video encoding |
| `fix_paths.py` | 9 | Path fix utility |
| `hf_download.py` | 182 | HuggingFace downloader |
| `import_from_vllm_recipes.py` | 341 | vLLM recipe importer |
| `index_documents.py` | 117 | Document indexer |
| `migrate_faiss_to_chroma.py` | 173 | FAISS-to-ChromaDB migration |
| `mlx_image_server.py` | 465 | MLX image server |
| `pr_blocker_audit.py` | 1,051 | PR overlap auditor |
| `update_database.py` | 168 | Database schema migration |

### `specs/` (1 file, 412 lines)

| File | Lines | Purpose |
|---|---:|---|
| `architecture-runtime-inventory.md` | 412 | Runtime module structure inventory and refactor planning baseline |

### Documentation Files in `tests/`

| File | Lines | Purpose |
|---|---:|---|
| `README.md` | 256 | Test suite notes: helper conventions, running focused subsets, validation expectations, roadmap |
| `LAYOUT_INVENTORY.md` | 203 | First low-risk split inventory (CLI tests to `tests/cli/`): 28 files identified, verification commands |
| `OVERSIZED_TEST_SPLIT_PLAN.md` | 327 | Oversized test file split plan: metrics-driven candidates, risk signals, split rules |
