# Vaidyx Core Architecture

> Comprehensive reference for the core infrastructure of the Vaidyx application.
> Generated from source files at commit `a44d666` (main branch).

---

## Table of Contents

1. [Application Entry Point](#1-application-entry-point)
2. [Core Module Breakdown](#2-core-module-breakdown)
3. [Database Layer](#3-database-layer)
4. [Authentication System](#4-authentication-system)
5. [Middleware](#5-middleware)
6. [Models / Data Layer](#6-models--data-layer)
7. [Configuration](#7-configuration)
8. [Dependencies](#8-dependencies)
9. [Session Management](#9-session-management)
10. [Error Handling](#10-error-handling)
11. [Platform Compatibility](#11-platform-compatibility)

---

## 1. Application Entry Point

Vaidyx has two entry points: `app.py` (the primary server orchestrator) and `launcher.py` (a Windows-specific GUI wrapper).

### 1.1 app.py -- The Main Orchestrator

**File:** `/app.py` (1282 lines)

This is the central file of the entire application. It assembles the FastAPI application, registers all middleware, initializes all subsystems, mounts all routers, and defines the server lifecycle.

**Startup sequence (in execution order):**

1. **Platform fixes** (lines 14-15): On Windows, forces `WindowsProactorEventLoopPolicy` so `asyncio.create_subprocess_exec` works regardless of how the process is launched (VS Code debugger, etc.).

2. **MIME type registration** (lines 18-31): Function `register_static_mime_types()` forces correct MIME types for `.js` and `.mjs` files. Windows can inherit stale registry mappings that break ES module loading.

3. **HuggingFace symlink workaround** (lines 38-40): On Windows, sets `HF_HUB_DISABLE_SYMLINKS=1` so HuggingFace/fastembed copies model files instead of symlinking (fails on network shares/UNC paths).

4. **Environment loading** (lines 42-48): Uses `python-dotenv` with `encoding="utf-8-sig"` to tolerate a UTF-8 BOM in `.env` files (a common Windows/Notepad issue).

5. **Logging setup** (lines 87-115): Configures root logger with console + rotating file handler (`data/logs/app.log`, 5 MB max, 3 backups). Falls back to console-only if file logging fails.

6. **FastAPI app creation** (lines 121-125):
   ```python
   app = FastAPI(
       title="AI Chat Application",
       description="Comprehensive AI chat with memory, research, and multi-modal capabilities",
       version="1.0.0",
   )
   ```

7. **Middleware stack** (added in order, executed in reverse):
   - `CORSMiddleware` (lines 128-146)
   - `GZipMiddleware` (line 156) -- minimum 1024 bytes, compression level 6
   - `SecurityHeadersMiddleware` (line 159) -- custom CSP, nonce generation
   - `_RequestTimeoutMiddleware` (lines 187-198) -- 45s hard timeout with exempt paths
   - `_InteractiveActivityMiddleware` (lines 201-215) -- stops background tasks when foreground requests arrive
   - `_SlowRequestLogMiddleware` (lines 218-239) -- logs requests exceeding 0.75s
   - `AuthMiddleware` (lines 356-471) -- cookie + bearer token auth (only when `AUTH_ENABLED=true`)

8. **Component initialization** (lines 569-594): Calls `initialize_managers()` which returns a dict of all manager objects:
   - `session_manager`, `memory_manager`, `memory_vector`, `upload_handler`
   - `personal_docs_manager`, `api_key_manager`, `preset_manager`
   - `chat_processor`, `research_handler`, `chat_handler`
   - `model_discovery`, `skills_manager`

9. **Router registration** (lines 624-863): Mounts 40+ route modules covering auth, sessions, chat, research, memory, uploads, models, TTS/STT, documents, gallery, notes, calendar, email, tasks, MCP, webhooks, API tokens, contacts, vault, shell, cookbook, workspace, compare, preferences, backup, fonts, signatures, editor drafts, and companion features.

10. **Lifecycle management** (lines 996-1272): Modern `asynccontextmanager` lifespan with:
    - **Startup** (`_startup_event`, lines 1008-1247): Purges leftover incognito sessions, starts upload cleanup, background job monitor, MCP server connections, optional warmups/keepalive, default task reconciliation, skill owner backfill, task scheduler, null-owner sweep loop, nightly skill audit loop, cookbook serve lifecycle.
    - **Shutdown** (`_shutdown_event`, lines 1249-1272): Cancels upload cleanup, stops task scheduler, closes webhook manager, disconnects MCP servers.

11. **Direct execution** (lines 1275-1281): When run as `__main__`, starts uvicorn on `APP_BIND` (default `127.0.0.1`) port `APP_PORT` (default `7000`).

**Key SPA routes** (lines 867-924): The root `/` and tool deep-link routes (`/notes`, `/calendar`, `/cookbook`, `/email`, `/memory`, `/gallery`, `/tasks`, `/library`) all serve the same `static/index.html` via `serve_html_with_nonce()`. The JS router handles tool-specific modals based on `window.location.pathname`.

**API endpoints defined in app.py:**
| Endpoint | Method | Purpose | Line |
|---|---|---|---|
| `/` | GET | Serve SPA index | 867 |
| `/login` | GET | Serve login page | 920 |
| `/api/version` | GET | Return `APP_VERSION` | 926 |
| `/api/health` | GET | Liveness check | 931 |
| `/api/ready` | GET | Readiness/integrity check (503 if subsystem down) | 963 |
| `/api/runtime` | GET | Docker detection, Ollama URL | 974 |
| `/api/activity/heartbeat` | POST | Browser keepalive, stops background tasks | 631 |
| `/api/client-perf` | POST | Frontend timing reports | 935 |
| `/api/generated-image/{filename}` | GET | Serve generated images with ownership check | 499 |

### 1.2 launcher.py -- Windows Portable Launcher

**File:** `/launcher.py` (143 lines)

A dedicated entry point for standalone Windows portable distribution (PyInstaller frozen bundles). Handles:

- **NullWriter** (lines 18-29): Replaces `sys.stdout`/`sys.stderr` with dummy writers when they are `None` (windowed GUI mode has no console, so `isatty()` calls would crash).

- **Splash screen** (lines 35-66): When running from a frozen PyInstaller bundle (`sys.frozen == True`), immediately shows a tkinter splash window on a daemon thread -- dark-themed (`#1a1c23` background, `#e06c75` accent), centered, 360x160 pixels, displays "Vaidyx -- Launching background services...".

- **System tray icon** (lines 69-109): Uses `pystray` and `Pillow` to create a 64x64 RGBA sailing-boat icon in the Vaidyx brand red (`#e06c75`). Tray menu offers "Open Vaidyx" (default action, opens browser) and "Exit" (calls `os._exit(0)`).

- **Browser launch** (lines 112-124): After a 3.5-second delay (allowing uvicorn warmup), destroys the splash screen and opens the default browser to the server URL.

- **Server start** (lines 127-142): Imports `app` from `app.py` and runs it with uvicorn. When frozen, also spawns browser-open and system-tray threads.

### 1.3 setup.py -- First-Time Setup Script

**File:** `/setup.py` (303 lines)

An interactive setup script that prepares the Vaidyx environment from scratch. Safe to re-run (skips what already exists).

**Steps (in order):**

1. **`check_arch()`** (lines 200-236): On macOS, detects Apple Silicon running under Rosetta (x86_64 Python on arm64 hardware) and exits with guidance to rebuild with Homebrew's arm64 Python.

2. **`create_dirs()`** (lines 38-41): Creates all required data directories: `DATA_DIR`, `UPLOAD_DIR`, `PERSONAL_DIR`, `PERSONAL_UPLOADS_DIR`, `TTS_CACHE_DIR`, `GENERATED_IMAGES_DIR`, `DEEP_RESEARCH_DIR`, `CHROMA_DIR`, `RAG_DIR`, `MEMORY_VECTORS_DIR`, and `logs/`.

3. **`create_env()`** (lines 156-169): Copies `.env.example` to `.env` if it does not exist.

4. **`check_deps()`** (lines 172-198): Verifies that `fastapi`, `uvicorn`, `sqlalchemy`, `bcrypt`, `httpx`, `dotenv` are importable. Also checks for `tmux` on non-Windows platforms (needed by the Cookbook feature).

5. **`init_database()`** (lines 44-51): Calls `Base.metadata.create_all(bind=engine)` to create all SQLAlchemy tables.

6. **`create_default_admin()`** (lines 89-153): Creates the initial admin user in `auth.json`. Credential priority: environment variables (`VAIDYX_ADMIN_USER`, `VAIDYX_ADMIN_PASSWORD`) > interactive prompt > auto-generated random password. Uses `bcrypt.hashpw` for password hashing. Validates against `RESERVED_USERNAMES`. Minimum password length enforced via `PASSWORD_MIN_LENGTH` (8 characters).

---

## 2. Core Module Breakdown

All core infrastructure lives in the `/core/` package.

### 2.1 core/__init__.py

**File:** `/core/__init__.py` (53 lines)

Package initializer that re-exports the public API of the core package. Exposes:

- **LLM functions** (from `src.llm_core`): `llm_call`, `llm_call_async`, `stream_llm`, `list_model_ids`, `normalize_model_id`, `LLMConfig`
- **Auth**: `AuthManager`
- **Middleware**: `SecurityHeadersMiddleware`
- **Exceptions**: `SessionNotFoundError`, `InvalidFileUploadError`, `LLMServiceError`, `WebSearchError`
- **Models**: `Session`, `ChatMessage`, `SessionManager`

### 2.2 core/atomic_io.py

**File:** `/core/atomic_io.py` (46 lines)

Provides crash-safe file writes for JSON config files. A plain `open("w") + json.dump` truncates first, then writes -- a kill/power loss/OOM in between produces a truncated or empty file. This module writes to a sibling `.tmp.<PID>` file, fsyncs, then `os.replace`s into place (atomic on POSIX same-filesystem).

**Functions:**

| Function | Signature | Line | Purpose |
|---|---|---|---|
| `atomic_write_json` | `(path: str, data: Any, *, indent: Optional[int] = None) -> None` | 21 | Atomically persist any data as JSON. Creates parent dirs. Uses PID-suffixed temp file to avoid collisions. |
| `atomic_write_text` | `(path: str, text: str) -> None` | 36 | Same atomic pattern but for raw text strings. Raises `TypeError` if input is not a string. |

Used by: `auth.py` (auth.json persistence), session tokens (sessions.json), settings, integrations, cookbook state.

### 2.3 core/auth.py

**File:** `/core/auth.py` (688 lines)

Multi-user authentication system with password hashing, session tokens, TOTP two-factor authentication, privilege management, and config file persistence to `data/auth.json`.

See [Section 4: Authentication System](#4-authentication-system) for full details.

### 2.4 core/constants.py

**File:** `/core/constants.py` (12 lines)

A backward-compatible shim that re-exports everything from `src/constants.py`. Historically there were two copies of this module (this one lagged behind). Now it simply does:

```python
from src.constants import *
from src.constants import internal_api_base
```

The single source of truth is `src/constants.py` (see [Section 7: Configuration](#7-configuration)).

### 2.5 core/database.py

**File:** `/core/database.py` (2563 lines)

The largest file in the core package. Contains the full SQLAlchemy ORM layer: engine setup, session factory, all database models (20+ tables), a comprehensive schema migration system, and utility functions.

See [Section 3: Database Layer](#3-database-layer) for full details.

### 2.6 core/exceptions.py

**File:** `/core/exceptions.py` (29 lines)

Custom exception classes with structured context fields.

See [Section 10: Error Handling](#10-error-handling) for full details.

### 2.7 core/log_safety.py

**File:** `/core/log_safety.py` (27 lines)

URL redaction for safe logging. Admin-configured endpoint URLs can embed credentials in userinfo (`https://user:pass@host`) or query strings (`?api_key=...`). Logging them raw leaks secrets.

**Functions:**

| Function | Signature | Line | Purpose |
|---|---|---|---|
| `redact_url` | `(url: str) -> str` | 14 | Strips userinfo, query, and fragment from a URL, keeping only scheme + host:port + path. Returns `"<endpoint>"` on parse failure. Handles IPv6 literals by re-bracketing. |

### 2.8 core/middleware.py

**File:** `/core/middleware.py` (127 lines)

Security middleware and request helpers. See [Section 5: Middleware](#5-middleware) for full details.

### 2.9 core/models.py

**File:** `/core/models.py` (132 lines)

Pure data models (no database logic, no side effects). See [Section 6: Models / Data Layer](#6-models--data-layer) for full details.

### 2.10 core/platform_compat.py

**File:** `/core/platform_compat.py` (453 lines)

Cross-platform OS compatibility helpers. See [Section 11: Platform Compatibility](#11-platform-compatibility) for full details.

### 2.11 core/session_manager.py

**File:** `/core/session_manager.py` (738 lines)

Session business logic and database operations. See [Section 9: Session Management](#9-session-management) for full details.

---

## 3. Database Layer

### 3.1 Engine and Connection

**File:** `/core/database.py`, lines 1-135

- **ORM**: SQLAlchemy (declarative base pattern)
- **Driver**: SQLite by default (`data/app.db`), configurable via `DATABASE_URL` environment variable
- **Session factory**: `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`

**Key setup details:**

```python
DATABASE_URL = _normalize_sqlite_url(os.getenv("DATABASE_URL", _default_database_url()))
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
```

- `_normalize_sqlite_url()` (line 47): Resolves relative SQLite paths without rewriting URI filenames.
- `_default_database_url()` (line 43): Returns `sqlite:///{DATA_DIR}/app.db`.
- `_sqlite_db_path()` (line 88): Extracts the filesystem path from a SQLite URL, handling `file:` URIs, `mode=memory`, UNC paths, and `uri=true` query parameters.

**Foreign key enforcement** (lines 142-148): A listener on the Engine class fires `PRAGMA foreign_keys=ON` on every SQLite connection.

**File security** (lines 82-85, 1887-1928): After `create_all`, the DB file and its sidecars (`-journal`, `-wal`, `-shm`) are locked to `0o600` via `safe_chmod`. A failed chmod on POSIX emits a warning.

### 3.2 Custom Types

**`EncryptedText`** (lines 150-173): A `TypeDecorator` wrapping `Text` that transparently Fernet-encrypts on write (`enc:` prefix) and decrypts on read. Legacy plaintext rows pass through until their next write. Used for API keys, signatures, OAuth tokens, and email passwords.

### 3.3 Mixins

**`TimestampMixin`** (lines 28-36): Adds `created_at` and `updated_at` DateTime columns with automatic defaults via `utcnow_naive()` (returns naive UTC datetimes for existing DateTime columns).

### 3.4 Database Models (Tables)

| Model | Table Name | Line | Primary Key | Owner-Scoped | Description |
|---|---|---|---|---|---|
| `Session` | `sessions` | 175 | `id` (String) | Yes | Chat session with config and metadata |
| `ChatMessage` | `chat_messages` | 254 | `id` (String) | Via session | Individual chat messages |
| `Document` | `documents` | 283 | `id` (String) | Yes | Living documents the AI can edit |
| `DocumentVersion` | `document_versions` | 316 | `id` (String) | Via document | Immutable document snapshots |
| `GalleryAlbum` | `gallery_albums` | 331 | `id` (String) | Yes | Photo album/folder |
| `GalleryImage` | `gallery_images` | 344 | `id` (String) | Yes | Photo and AI-generated image metadata |
| `EmailAccount` | `email_accounts` | 386 | `id` (String) | Yes | IMAP/SMTP account config (encrypted passwords) |
| `ModelEndpoint` | `model_endpoints` | 433 | `id` (String) | Yes | Admin-configured model provider endpoints |
| `ProviderAuthSession` | `provider_auth_sessions` | 469 | `id` (String) | Yes | OAuth/session credentials for providers |
| `McpServer` | `mcp_servers` | 483 | `id` (String) | No | MCP tool server configurations |
| `Comparison` | `comparisons` | 500 | `id` (String) | Yes | A/B model comparison results |
| `Signature` | `signatures` | 526 | `id` (String) | Yes | User-saved visual signatures (encrypted) |
| `ApiToken` | `api_tokens` | 547 | `id` (String) | Yes | API tokens for external integrations |
| `Webhook` | `webhooks` | 561 | `id` (String) | No | Outgoing webhooks |
| `UserTool` | `user_tools` | 576 | `id` (String) | Yes | User-created sandboxed mini-apps |
| `UserToolData` | `user_tool_data` | 601 | `id` (Integer, auto) | Via tool | Key-value storage for tool persistent data |
| `CrewMember` | `crew_members` | 619 | `id` (String) | Yes | Custom AI persona with personality/model/tools |
| `ScheduledTask` | `scheduled_tasks` | 643 | `id` (String) | Yes | Recurring/one-off tasks (LLM or action) |
| `EditorDraft` | `editor_drafts` | 691 | `id` (String) | Yes | Persisted image-editor session state |
| `TaskRun` | `task_runs` | 723 | `id` (String) | Via task | Record of a single task execution |
| `Memory` | `memories` | 746 | `id` (String) | Yes | Persistent memory entries |
| `Note` | `notes` | 1704 | `id` (String) | Yes | Google Keep-style notes/checklists |
| `CalendarCal` | `calendars` | 1734 | `id` (String) | Yes | Calendar (local or CalDAV) |
| `CalendarEvent` | `calendar_events` | 1752 | `uid` (String) | Via calendar | Calendar event with recurrence support |
| `CalendarDeletedEvent` | `caldav_deleted_events` | 1786 | `uid` (String) | Yes | CalDAV delete tombstones |
| `Integration` | `integrations` | 1800 | `id` (String) | Yes | External service connections |

### 3.5 Key Relationships

- `Session` 1-to-many `ChatMessage` (cascade delete-orphan)
- `Session` 1-to-many `Document` (SET NULL on session delete -- documents survive as orphans)
- `Session` 1-to-many `GalleryImage` (SET NULL on delete)
- `Session` 1-to-many `UserTool` (cascade delete-orphan)
- `Session` 1-to-1 `CrewMember`
- `Document` 1-to-many `DocumentVersion` (cascade delete-orphan)
- `GalleryAlbum` 1-to-many `GalleryImage` (SET NULL on delete)
- `CalendarCal` 1-to-many `CalendarEvent` (cascade delete-orphan)
- `ScheduledTask` self-referential `then_task` (SET NULL -- task chaining)
- `ScheduledTask` 1-to-many `TaskRun` (cascade delete-orphan)
- `UserTool` 1-to-many `UserToolData` (cascade delete-orphan)

### 3.6 Indexes

The database defines numerous composite indexes for query optimization:

- `ix_sessions_active` -- `(archived, last_accessed)` for active session listing
- `ix_sessions_search` -- `(name, archived)` for session search
- `ix_sessions_last_message_at` -- `(archived, last_message_at)` for "last active" sort
- `ix_messages_session_time` -- `(session_id, timestamp)` for efficient message retrieval
- `ix_gallery_images_active` -- `(is_active, created_at)` for gallery listing
- `ix_scheduled_tasks_due` -- `(status, next_run)` for task scheduling
- `ix_scheduled_tasks_event` -- `(trigger_type, trigger_event, status)` for event-driven tasks
- `ix_task_runs_task` -- `(task_id, started_at)` for task run history
- `ix_email_accounts_owner_default` -- `(owner, is_default)` for email account lookup
- `ix_user_tool_data_tool_key` -- `(tool_id, key)` unique composite for tool KV store

### 3.7 Full-Text Search

**Chat Messages FTS** (lines 2003-2086): Uses SQLite FTS5 for full-text search across chat transcripts. Created via `_migrate_chat_messages_fts()`:

- Virtual table `chat_messages_fts` with columns: `content`, `message_id` (unindexed), `session_id` (unindexed), `role` (unindexed)
- Auto-maintained via triggers (`chat_messages_fts_ai`, `chat_messages_fts_ad`, `chat_messages_fts_au`) on INSERT/DELETE/UPDATE
- Inline media (base64 images/audio) is excluded from the index via a CASE expression
- Legacy media rows are scrubbed on startup via `_scrub_legacy_chat_message_fts_media()`

### 3.8 Schema Migration System

The database uses a custom migration system (not Alembic) consisting of ~35 idempotent migration functions that run on every startup via `init_db()` (lines 1887-1975). Each migration checks whether a column/table already exists before altering, making them safe to re-run.

**Migration categories:**

1. **Column additions**: `_migrate_add_owner_column()`, `_migrate_add_folder_column()`, `_migrate_add_mode_column()`, `_migrate_add_token_columns()`, `_migrate_add_hidden_models_column()`, etc.
2. **Table rebuilds**: `_migrate_model_endpoints()` drops and recreates when schema changed (url -> base_url). `_migrate_add_task_automation_columns()` rebuilds `scheduled_tasks` to make columns nullable.
3. **Data backfills**: `_migrate_assign_legacy_owner()` assigns null-owner data to the first admin user across 20+ tables. `_migrate_backfill_document_owner_from_session()` derives document ownership from linked sessions.
4. **Encryption migrations**: `_migrate_encrypt_email_passwords()`, `_migrate_encrypt_signatures()`, `_migrate_encrypt_endpoint_keys()` encrypt existing plaintext sensitive fields.
5. **FTS setup**: `_migrate_chat_messages_fts()` creates the FTS5 virtual table and sync triggers.
6. **Cleanup**: `_migrate_drop_ping_notes_tasks()` removes deprecated task types.

### 3.9 Utility Functions

| Function | Signature | Line | Purpose |
|---|---|---|---|
| `get_db()` | `()` -> Generator | 2393 | FastAPI dependency for DB session injection |
| `get_db_session()` | `()` -> Generator (context manager) | 2407 | Context manager with auto-commit/rollback |
| `bulk_insert_messages()` | `(session_id: str, messages: list)` | 2420 | Efficient bulk message insert |
| `cleanup_old_sessions()` | `(days: int = 30)` | 2436 | Remove archived sessions older than N days |
| `get_session_stats()` | `()` | 2451 | Return counts of sessions, messages, memories |
| `get_detailed_stats()` | `()` | 2463 | Stats + database file size in MB |
| `update_session_last_accessed()` | `(session_id: str)` | 2481 | Touch last_accessed timestamp |
| `get_session_mode()` | `(session_id: str)` | 2491 | Return a session's persisted mode (best-effort) |
| `set_session_mode()` | `(session_id: str, mode: str) -> bool` | 2504 | Persist a session's mode (best-effort) |
| `get_session_by_id()` | `(session_id: str)` | 2518 | Simple session lookup |
| `get_upcoming_events()` | `(owner, horizon_days=60, limit=40)` | 2523 | Upcoming calendar events as dicts |
| `archive_session()` | `(session_id: str)` | 2549 | Archive a session |

---

## 4. Authentication System

**File:** `/core/auth.py` (688 lines)

### 4.1 Architecture Overview

Authentication is a multi-layered system:

1. **Password storage**: `data/auth.json` (bcrypt-hashed, atomically written)
2. **Session tokens**: `data/sessions.json` (hex tokens, 7-day TTL)
3. **API tokens**: Database `api_tokens` table (bcrypt-hashed, `ody_` prefix, scoped)
4. **Two-factor**: TOTP via `pyotp` with backup codes
5. **Internal tool bypass**: Per-process secret token for in-process HTTP loopback

### 4.2 Password Handling

- **Hashing**: `bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())` (line 81)
- **Verification**: `bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))` (line 85)
- **Minimum length**: 8 characters (`PASSWORD_MIN_LENGTH`)

### 4.3 AuthManager Class

**`class AuthManager`** (line 97)

Constructor `__init__(self, auth_path: str = DEFAULT_AUTH_PATH)` (line 100):
- Loads auth config from `auth.json`
- Loads persisted session tokens from `sessions.json` (pruning expired ones)
- Runs migrations: single-user to multi-user format, reserved username cleanup, legacy admin role normalization
- Thread-safe via `_sessions_lock` (RLock), `_config_lock` (Lock), `_setup_lock` (Lock)

**Account management methods:**

| Method | Signature | Line | Purpose |
|---|---|---|---|
| `setup()` | `(username, password) -> bool` | 262 | First-run admin setup (only works if no users exist) |
| `create_user()` | `(username, password, is_admin=False) -> bool` | 269 | Create a new user account |
| `delete_user()` | `(username, requesting_user) -> bool` | 292 | Delete user (admin only, revokes sessions + API tokens) |
| `rename_user()` | `(old, new, requesting_user) -> bool` | 341 | Rename user (admin only, updates active sessions) |
| `change_password()` | `(username, current, new) -> bool` | 475 | Change password (requires current password verification) |
| `set_admin()` | `(username, is_admin, requesting_user) -> SetAdminResult` | 412 | Promote/demote admin (refuses to remove last admin) |
| `is_admin()` | `(username) -> bool` | 376 | Check admin status |
| `list_users()` | `() -> List[Dict]` | 379 | List all users with privileges |

**Session token methods:**

| Method | Signature | Line | Purpose |
|---|---|---|---|
| `create_session()` | `(username, password) -> Optional[str]` | 581 | Verify credentials and issue token |
| `create_session_trusted()` | `(username) -> Optional[str]` | 588 | Issue token for already-verified user |
| `validate_token()` | `(token) -> bool` | 605 | Check if token is valid (not expired, user exists) |
| `get_username_for_token()` | `(token) -> Optional[str]` | 630 | Get username from token |
| `revoke_token()` | `(token)` | 655 | Revoke a single token |
| `revoke_user_sessions()` | `(username, except_token=None) -> int` | 660 | Revoke all sessions for a user |

### 4.4 Privilege System

**Default privileges** (lines 25-41):
```python
DEFAULT_PRIVILEGES = {
    "can_use_agent": True,
    "can_use_browser": True,
    "can_use_bash": False,       # disabled by default
    "can_use_documents": True,
    "can_use_research": True,
    "can_generate_images": True,
    "can_manage_memory": True,
    "max_messages_per_day": 0,   # 0 = unlimited
    "allowed_models": [],
    "allowed_models_restricted": False,
    "block_all_models": False,
}
```

Admins always get `ADMIN_PRIVILEGES` (all booleans True, no restrictions). When promoting to admin, the pre-admin privilege map is stashed in `privileges_before_admin`; on demotion it is restored.

### 4.5 TOTP Two-Factor Authentication

| Method | Line | Purpose |
|---|---|---|
| `totp_enabled()` | 490 | Check if 2FA is enabled for a user |
| `totp_generate_secret()` | 495 | Generate new TOTP secret (pending until confirmed) |
| `totp_get_provisioning_uri()` | 506 | Get `otpauth://` URI for QR code generation |
| `totp_confirm_enable()` | 511 | Verify code against pending secret, enable 2FA, generate 8 backup codes |
| `totp_verify()` | 533 | Verify TOTP code for login (checks backup codes first, valid_window=1) |
| `totp_disable()` | 557 | Disable 2FA (requires password confirmation) |

### 4.6 Reserved Usernames

```python
RESERVED_USERNAMES = frozenset({"internal-tool", "api", "demo", "system"})
```

These are used as synthetic owner sentinels throughout the codebase. Creating or renaming into any of them is refused to prevent impersonation (e.g., `internal-tool` would bypass all admin checks).

### 4.7 Auth Middleware (in app.py)

**`class AuthMiddleware`** (app.py, line 356)

Authentication flow (in order):

1. **CORS preflight bypass**: OPTIONS + Access-Control-Request-Method passes through.
2. **Path exemption**: Static files, auth endpoints, health checks, webhook URLs (pattern-matched) are exempt.
3. **Internal tool token**: `X-Vaidyx-Internal-Token` header + trusted loopback = admin access. Supports `X-Vaidyx-Owner` header for user impersonation.
4. **Localhost bypass**: When `LOCALHOST_BYPASS=true`, direct loopback connections (no proxy forwarding headers) skip auth. Detects proxy headers: `cf-connecting-ip`, `cf-ray`, `cf-visitor`, `x-forwarded-for`, `x-forwarded-host`, `x-real-ip`, `forwarded`.
5. **Bearer token auth**: Tokens with `ody_` prefix. Token lookup uses an in-memory prefix cache (`_token_cache`) rebuilt from the DB on dirty flag. Each candidate is bcrypt-verified. Matched tokens set `request.state.current_user = "api"` with `api_token_owner`, `api_token_scopes`, and fire-and-forget `last_used_at` update.
6. **Cookie session auth**: Cookie named from `SESSION_COOKIE` validated via `auth_manager.validate_token()`. Sets `request.state.current_user` to the username.
7. **Unauthenticated**: API paths get 401 JSON; non-API paths get 302 redirect to `/login`.

### 4.8 Token Cache

**Location:** app.py, lines 291-329

An in-memory `dict` mapping token prefix (first 8 chars) to `list[(token_id, token_hash, owner, scopes)]`. The DB query (bcrypt-scanning linearly) only runs when the cache is marked dirty (token created/revoked). Invalidation is exposed via `app.state.invalidate_token_cache()`.

---

## 5. Middleware

### 5.1 SecurityHeadersMiddleware

**File:** `/core/middleware.py`, lines 59-126

**`class SecurityHeadersMiddleware(BaseHTTPMiddleware)`**

Generates a per-request CSP nonce (`secrets.token_hex(16)`) and sets comprehensive security headers on every response:

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: camera=(), microphone=(self), geolocation=()`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HTTPS only)
- `X-Frame-Options: DENY` (default) / `SAMEORIGIN` (PDF preview)
- `Content-Security-Policy`: Context-dependent:
  - **Default pages**: `script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'`
  - **Research reports**: Relaxed CSP with `'unsafe-inline'` scripts (self-contained HTML)
  - **Tool render endpoints**: No framing headers (tools render in iframes)
  - **Document PDF preview**: `default-src 'none'; frame-ancestors 'self'`

### 5.2 Internal Tool Token

**File:** `/core/middleware.py`, lines 16-19

```python
INTERNAL_TOOL_TOKEN = os.environ.get("VAIDYX_INTERNAL_TOKEN") or secrets.token_hex(32)
INTERNAL_TOOL_HEADER = "X-Vaidyx-Internal-Token"
INTERNAL_TOOL_USER = "internal-tool"
```

A per-process secret token generated at import time. Allows the in-app agent tool layer to hit admin-gated routes via HTTP loopback without a session cookie. Never persisted or exposed externally.

### 5.3 require_admin()

**File:** `/core/middleware.py`, lines 31-56

```python
def require_admin(request: Request):
```

Route-level guard that raises `HTTPException(403)` if the current user is not an admin. Allows access when:
- The request carries a valid `INTERNAL_TOOL_TOKEN` header
- `request.state.current_user == "internal-tool"` (set by AuthMiddleware)
- `AUTH_ENABLED=false`

### 5.4 is_cors_preflight()

**File:** `/core/middleware.py`, lines 22-28

```python
def is_cors_preflight(method: str, headers) -> bool:
```

Pure function (unit-testable) that returns True for a genuine CORS preflight: an OPTIONS request carrying the `Access-Control-Request-Method` header.

### 5.5 Request Timeout Middleware

**File:** `/app.py`, lines 187-198

**`class _RequestTimeoutMiddleware`**: Wraps non-streaming requests in `asyncio.wait_for()` with a configurable timeout (default 45s via `REQUEST_HARD_TIMEOUT` env var). Returns 504 on timeout.

**Exempt paths** (streaming/long-running):
`/api/chat`, `/api/shell/stream`, `/api/research`, `/api/model/download`, `/api/model/probe`, `/api/model-endpoints`, `/api/cookbook/setup`, `/api/upload`, `/api/image`, `/api/memory/audit`

### 5.6 Interactive Activity Middleware

**File:** `/app.py`, lines 201-215

**`class _InteractiveActivityMiddleware`**: Tracks foreground (interactive) requests and stops background tasks when a user is actively using the UI, preventing background jobs from competing with real-time interactions.

### 5.7 Slow Request Log Middleware

**File:** `/app.py`, lines 218-239

**`class _SlowRequestLogMiddleware`**: Logs a warning for any request that takes longer than the threshold (default 0.75s, configurable via `VAIDYX_SLOW_REQUEST_LOG_SECONDS`). Includes method, path, status, and elapsed time.

### 5.8 GZip Compression

**File:** `/app.py`, line 156

Starlette's `GZipMiddleware` with `minimum_size=1024` and `compresslevel=6`. Cuts CSS/JS/HTML transfer by ~75-85%. SSE streams (`text/event-stream`) are excluded by default.

### 5.9 CORS Configuration

**File:** `/app.py`, lines 128-146

- **Origins**: Configurable via `ALLOWED_ORIGINS` env var (default: `http://localhost,http://127.0.0.1`)
- **Methods**: GET, POST, PUT, PATCH, DELETE
- **Allowed headers**: Accept, Authorization, Content-Type, X-API-Key, X-Auth-Token, X-Vaidyx-Internal-Token, X-Vaidyx-Owner, X-Requested-With, X-TZ-Offset
- **Credentials**: Allowed

---

## 6. Models / Data Layer

### 6.1 In-Memory Data Models

**File:** `/core/models.py` (132 lines)

Pure dataclasses with no database dependencies.

**`class ChatMessage`** (line 35):
```python
@dataclass
class ChatMessage:
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
```
Methods: `to_dict()`, `get(key, default)` (dict-like access for backward compatibility).

**`class Session`** (line 53):
```python
@dataclass
class Session:
    id: str
    name: str
    endpoint_url: str
    model: str
    rag: bool = False
    archived: bool = False
    headers: Optional[Dict[str, str]] = None
    history: List[ChatMessage] = None
    owner: Optional[str] = None
    is_important: bool = False
    message_count: int = 0
```

Key behaviors:
- `__post_init__()` (line 78): Ensures each session gets its own history list (not the shared dataclass default).
- `_history` property (line 86): Backward-compatibility alias that resolves to `history`.
- `add_message()` (line 94): Appends to history, increments `message_count`, delegates to the global `SessionManager` singleton for persistence.
- `get_context_messages()` (line 109): Returns messages formatted for LLM API, excluding slash-command replies (messages with `metadata.source == "slash"`).
- `get()` / `__getitem__()` (lines 125-131): Dict-like access for compatibility.

### 6.2 Session Manager Singleton

**File:** `/core/models.py`, lines 14-31

```python
_SESSION_MANAGER_INSTANCE: Optional["SessionManager"] = None

def set_session_manager_instance(manager): ...
def get_session_manager_instance(): ...
```

Set during app initialization (`app.py`, line 579). Used by `Session.add_message()` to delegate persistence without circular imports.

### 6.3 Database Models

All database models are defined in `/core/database.py`. See [Section 3.4: Database Models](#34-database-models-tables) for the complete table listing.

**Key Session model fields** (database.py, line 175):
- `id` (String PK), `name`, `endpoint_url`, `model`, `owner` (nullable, indexed)
- `rag` (Boolean), `archived` (Boolean), `folder` (nullable String)
- `headers` (JSON), `mode` (nullable -- 'agent', 'chat', 'research')
- `is_important` (Boolean), `message_count` (Integer)
- `total_input_tokens`, `total_output_tokens` (Integer)
- `crew_member_id` (nullable -- links to crew_members)
- `last_accessed`, `last_message_at` (DateTime)
- `to_dict()` method for JSON serialization (line 233)

**Key ChatMessage model fields** (database.py, line 254):
- `id` (String PK), `session_id` (FK to sessions, CASCADE delete)
- `role` (String), `content` (Text), `meta_data` (Text -- JSON string)
- `timestamp` (DateTime)

---

## 7. Configuration

### 7.1 Constants

**File:** `/src/constants.py` (129 lines), re-exported via `/core/constants.py`

**Application version:**
```python
APP_VERSION = "1.0.2"
```

**Base paths:**
| Constant | Source | Default |
|---|---|---|
| `BASE_DIR` | `get_app_root()` | Application root directory |
| `STATIC_DIR` | `BASE_DIR/static` | Static file directory |
| `DATA_DIR` | `VAIDYX_DATA_DIR` env or `get_default_data_dir()` | Writable data directory |

**Data file paths** (all under `DATA_DIR`):
| Constant | Path | Purpose |
|---|---|---|
| `SESSIONS_FILE` | `sessions.json` | Session persistence |
| `MEMORY_FILE` | `memory.json` | Memory entries |
| `AUTH_FILE` | `auth.json` | User authentication |
| `SETTINGS_FILE` | `settings.json` | Application settings |
| `USER_PREFS_FILE` | `user_prefs.json` | Per-user preferences |
| `PRESETS_FILE` | `presets.json` | Chat presets |
| `INTEGRATIONS_FILE` | `integrations.json` | Integration configs |
| `CONTACTS_FILE` | `contacts.json` | CardDAV contacts |
| `APP_KEY_FILE` | `.app_key` | Fernet encryption key |
| `EMBEDDING_ENDPOINT_FILE` | `embedding_endpoint.json` | Embedding model config |
| `COOKBOOK_STATE_FILE` | `cookbook_state.json` | Cookbook download/serve state |
| `BG_JOBS_FILE` | `bg_jobs.json` | Background job tracking |
| `VAULT_FILE` | `vault.json` | Vault entries |
| `SKILLS_FILE` | `skills.json` | Skills metadata |
| `APP_DB` | `app.db` | Main SQLite database |
| `SCHEDULED_EMAILS_DB` | `scheduled_emails.db` | Scheduled email storage |
| `EMAIL_CACHE_DB` | `email_cache.db` | Email cache storage |

**Data subdirectories:**
`PERSONAL_DIR`, `PERSONAL_UPLOADS_DIR`, `UPLOAD_DIR`, `EMOJI_CACHE_DIR`, `RAG_DIR`, `CHROMA_DIR`, `BG_JOBS_DIR`, `DEEP_RESEARCH_DIR`, `MCP_OAUTH_DIR`, `GENERATED_IMAGES_DIR`, `TTS_CACHE_DIR`, `EMAIL_URGENCY_CACHE_DIR`, `SKILLS_DIR`, `GALLERY_DIR`, `GALLERY_UPLOADS_DIR`, `MEMORY_VECTORS_DIR`, `FASTEMBED_CACHE_DIR`, `MAIL_ATTACHMENTS_DIR`

### 7.2 Agent Tool Output Limits

```python
MAX_OUTPUT_CHARS = 10_000       # bash/python/web_search/web_fetch output cap
MAX_READ_CHARS = 20_000         # read_file / document preview cap
MAX_DIFF_LINES = 400            # edit_file unified-diff display cap
WEB_FETCH_SOFT_MAX_BYTES = 2_000_000    # default download budget (2 MB)
WEB_FETCH_HARD_MAX_BYTES = 20_000_000   # absolute ceiling (20 MB)
```

### 7.3 API Configuration

```python
MAX_CONTEXT_MESSAGES = 90
REQUEST_TIMEOUT = 20
OPENAI_COMPAT_PATH = "/v1/chat/completions"
DEFAULT_TEMPERATURE = 1.0
DEFAULT_MAX_TOKENS = 0
```

### 7.4 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VAIDYX_DATA_DIR` | Platform-dependent | Writable data directory |
| `DATABASE_URL` | `sqlite:///{DATA_DIR}/app.db` | Database connection URL |
| `AUTH_ENABLED` | `"true"` | Enable/disable authentication |
| `LOCALHOST_BYPASS` | `"false"` | Allow unauthenticated loopback requests |
| `ALLOWED_ORIGINS` | `"http://localhost,http://127.0.0.1"` | CORS allowed origins |
| `APP_BIND` | `"127.0.0.1"` | Server bind address |
| `APP_PORT` | `"7000"` | Server bind port |
| `REQUEST_HARD_TIMEOUT` | `"45"` | Hard request timeout in seconds |
| `VAIDYX_SLOW_REQUEST_LOG_SECONDS` | `"0.75"` | Slow request logging threshold |
| `VAIDYX_INTERNAL_BASE` | Auto-derived | Base URL for internal loopback calls |
| `VAIDYX_INTERNAL_TOKEN` | Auto-generated | Internal tool auth token |
| `VAIDYX_STARTUP_WARMUPS` | `""` (disabled) | Enable startup warmups |
| `VAIDYX_MODEL_KEEPALIVE` | `""` (disabled) | Enable periodic endpoint keepalive |
| `VAIDYX_INPROCESS_TASKS` | `"1"` (enabled) | Enable in-process task scheduler |
| `VAIDYX_ADMIN_USER` | `""` | Setup: admin username |
| `VAIDYX_ADMIN_PASSWORD` | `""` | Setup: admin password |
| `VAIDYX_SKIP_ADMIN_PROMPT` | Not set | Setup: skip interactive prompt |
| `VAIDYX_SKIP_RUN_HINT` | Not set | Setup: suppress "start the server" hint |
| `LLM_HOST` | `"localhost"` | Default LLM host |
| `LLM_HOSTS` | `""` | Comma-separated LLM hosts |
| `OPENAI_API_KEY` | None | OpenAI API key |
| `SEARXNG_INSTANCE` | `"http://localhost:8080"` | SearXNG search instance URL |
| `CLEANUP_ENABLED` | `"True"` | Enable automatic session cleanup |
| `CLEANUP_INTERVAL_HOURS` | `"24"` | Cleanup interval in hours |
| `HF_HUB_DISABLE_SYMLINKS` | `"1"` (Windows only) | Disable HuggingFace symlinks |
| `WEB_FETCH_USER_AGENT` | Chrome 148 UA string | User agent for web scraping |
| `FASTEMBED_CACHE_PATH` | `{DATA_DIR}/fastembed_cache` | FastEmbed model cache |
| `VAIDYX_MAIL_ATTACHMENTS_DIR` | `{DATA_DIR}/mail-attachments` | Email attachments directory |

### 7.5 internal_api_base()

**File:** `/src/constants.py`, line 112

```python
def internal_api_base() -> str:
```

Returns the base URL for in-process loopback calls. Resolution order:
1. `VAIDYX_INTERNAL_BASE` env var (explicit override)
2. `http://127.0.0.1:{APP_PORT}` (from env)
3. Fallback `http://127.0.0.1:7000`

Uses `127.0.0.1` (not `localhost`) to avoid IPv6/DNS ambiguity.

---

## 8. Dependencies

### 8.1 Core Dependencies (requirements.txt)

| Package | Purpose |
|---|---|
| `fastapi` | Web framework (ASGI) |
| `uvicorn` | ASGI server |
| `python-multipart` | Form/file upload parsing |
| `python-dotenv` | `.env` file loading |
| `httpx` | Async HTTP client (outbound LLM/API calls) |
| `httpcore>=1.0,<2.0` | HTTP transport layer |
| `pydantic>=2.13.4` | Data validation |
| `pydantic-settings>=2.14.1` | Settings management |
| `SQLAlchemy` | ORM / database abstraction |
| `pypdf` | PDF text extraction (MIT) |
| `beautifulsoup4` | HTML parsing |
| `charset-normalizer` | Character encoding detection |
| `numpy` | Numerical operations |
| `chromadb-client` | Lightweight ChromaDB HTTP client for RAG |
| `fastembed` | Local ONNX embeddings |
| `youtube-transcript-api` | YouTube transcript extraction |
| `markdown` | Markdown rendering for research reports |
| `nh3` | HTML sanitizer (allowlist-based) |
| `icalendar` | Calendar .ics import/export |
| `python-dateutil` | Recurrence rule expansion |
| `caldav` | CalDAV protocol client |
| `cryptography` | Fernet encryption |
| `bcrypt` | Password hashing |
| `mcp<2` | Model Context Protocol SDK (v1 API) |
| `pyotp` | TOTP two-factor authentication |
| `qrcode[pil]` | QR code generation for 2FA setup |
| `croniter` | Cron expression parsing for task scheduling |
| `pytest` / `pytest-asyncio` | Testing framework |
| `httpx2` | Starlette TestClient compatibility |

### 8.2 Optional Dependencies (requirements-optional.txt)

| Package | Purpose | License Note |
|---|---|---|
| `faster-whisper` | Local speech-to-text via CTranslate2 | -- |
| `ddgs` | DuckDuckGo search provider | -- |
| `PyMuPDF` | PDF form-filling (AcroForm) | AGPL-3.0 |
| `markitdown[docx,pptx,xlsx,xls]==0.1.6` | Office/EPUB document extraction | MIT (Microsoft) |

### 8.3 Frontend Dependencies (package.json)

```json
{
  "devDependencies": {
    "@antithesishq/bombadil": "^0.6.1"
  }
}
```

The only npm dependency is Bombadil (Antithesis), likely for deterministic testing infrastructure.

### 8.4 Test Configuration (pyproject.toml)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Test markers define a taxonomy: `area_security`, `area_routes`, `area_services`, `area_cli`, `area_js`, `area_helpers`, `area_unit`, `area_uncategorized`, plus `slow` for the fast-lane exclude.

---

## 9. Session Management

**File:** `/core/session_manager.py` (738 lines)

### 9.1 SessionManager Class

```python
class SessionManager:
    def __init__(self, sessions_file: str = None):
```

The single source of truth for session lifecycle, message persistence, and in-memory caching.

**State:**
- `self.sessions: Dict[str, Session]` -- in-memory session cache
- `self.upload_handler` -- set post-initialization for upload reference tracking

### 9.2 Loading Strategy

**Lazy hydration architecture:**

1. **Boot** (`load_sessions()`, line 84): Loads only the 100 most recent non-archived sessions with messages as *metadata-only* entries (empty history lists). This avoids loading thousands of message rows into RAM at startup.

2. **First access** (`get_session()`, line 400): When a session is accessed, if its history is empty but `message_count > 0`, messages are hydrated from the DB via `_load_session_from_db()`.

3. **Metadata sync** (`sync_session_metadata()`, line 423): On every `get_session()` call, non-message fields (name, model, endpoint, headers, etc.) are refreshed from the DB to keep the cache fresh.

**Helper functions for loading:**
- `_db_to_session_meta()` (line 117): Builds a `Session` with empty history from a DB row.
- `_db_to_session()` (line 141): Builds a `Session` with full message history from a DB row.
- `_parse_msg_content()` (line 37): Deserializes JSON arrays back to lists for multimodal content (images/audio). Only parses when every element has a recognized `type` field to avoid misinterpreting plain text that looks like JSON.

### 9.3 Message Operations

**`add_message(self, session_id: str, message: ChatMessage)`** (line 204):
1. Gets the session (hydrating if needed).
2. Appends to `session.history`.
3. Updates `session.message_count`.
4. Calls `_persist_message()` for database write.

**`_persist_message(self, session_id: str, message: ChatMessage)`** (line 223):
1. Validates the session still exists in the DB (dropped sessions are cleaned from cache).
2. Calls `reserve_message_upload_references()` to verify referenced uploads exist.
3. Calls `persistable_message_content()` to strip provider data URLs (keeps text + attachment refs only).
4. Creates a `DbChatMessage` row with UUID id and current timestamp.
5. Updates `message_count`, `last_accessed`, and `last_message_at` on the session.
6. Stores the DB ID in `message.metadata['_db_id']` for future edit/delete by ID.

**`truncate_messages(self, session_id: str, keep_count: int) -> bool`** (line 290): Keeps only the first N messages, deleting the rest from DB and in-memory.

**`replace_messages(self, session_id: str, messages: list) -> bool`** (line 332): Atomic replacement of all messages. Reserves all uploads first, then deletes old rows and inserts new ones in a single transaction.

### 9.4 Session CRUD

| Method | Signature | Line | Notes |
|---|---|---|---|
| `create_session()` | `(id, name, url, model, rag=False, owner=None) -> Session` | 496 | Creates DB row + in-memory entry |
| `delete_session()` | `(session_id) -> bool` | 542 | Cleans up images, detaches documents (SET NULL), deletes messages + session |
| `update_session_name()` | `(session_id, name)` | 590 | Updates DB + cache |
| `archive_session()` | `(session_id)` | 610 | Sets `archived=True` |
| `mark_important()` | `(session_id, important=True)` | 630 | Sets `is_important` flag |
| `ensure_task_session()` | `(id, name, url, model, owner, task) -> Session` | 667 | Idempotent creation for task scheduler |

### 9.5 Queries

**`get_sessions_for_user(username=None) -> Dict[str, Session]`** (line 655): Filters cached sessions by owner. Returns all if username is None.

### 9.6 Cleanup

**`cleanup_empty_sessions(auto_archive_days=30, min_age_hours=1) -> dict`** (line 686):
- Deletes empty sessions older than `min_age_hours` (prevents deleting just-created sessions).
- Archives non-important sessions with no activity for `auto_archive_days`.
- Returns stats: `{deleted_empty, archived_old, total_checked}`.

---

## 10. Error Handling

**File:** `/core/exceptions.py` (29 lines)

### 10.1 Custom Exception Classes

| Exception | Constructor | Context Fields | HTTP Code |
|---|---|---|---|
| `SessionNotFoundError` | `(session_id: str)` | `session_id` | 404 |
| `InvalidFileUploadError` | `(message: str, filename: str = None)` | `filename`, `message` | 400 |
| `LLMServiceError` | `(message: str, endpoint: str = None)` | `endpoint`, `message` | 502 |
| `WebSearchError` | `(message: str, query: str = None)` | `query`, `message` | 502 |

### 10.2 Exception Handlers (app.py, lines 603-617)

Each custom exception has a registered FastAPI exception handler that returns a structured JSON response:

```python
@app.exception_handler(SessionNotFoundError)
async def session_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={
        "error": "SESSION_NOT_FOUND",
        "message": str(exc)
    })

@app.exception_handler(InvalidFileUploadError)
async def invalid_file_upload_handler(request, exc):
    return JSONResponse(status_code=400, content={
        "error": "INVALID_FILE_UPLOAD",
        "message": str(exc)
    })

@app.exception_handler(LLMServiceError)
async def llm_service_error_handler(request, exc):
    return JSONResponse(status_code=502, content={
        "error": "LLM_SERVICE_ERROR",
        "message": str(exc)
    })

@app.exception_handler(WebSearchError)
async def web_search_error_handler(request, exc):
    return JSONResponse(status_code=502, content={
        "error": "WEB_SEARCH_ERROR",
        "message": str(exc)
    })
```

The error codes (`SESSION_NOT_FOUND`, `INVALID_FILE_UPLOAD`, `LLM_SERVICE_ERROR`, `WEB_SEARCH_ERROR`) are machine-readable identifiers for frontend error handling.

---

## 11. Platform Compatibility

**File:** `/core/platform_compat.py` (453 lines)

Design rules: stdlib + ctypes only (no psutil/pywinpty). POSIX behaviour is unchanged; Windows gets a faithful equivalent or a safe, documented no-op.

### 11.1 Platform Detection Constants

```python
IS_WINDOWS = os.name == "nt"                    # line 25
IS_POSIX = not IS_WINDOWS                       # line 26
IS_APPLE_SILICON = (                             # lines 28-36
    IS_POSIX
    and platform.system() == "Darwin"
    and platform.machine().lower() in {"arm64", "aarch64"}
)
```

### 11.2 File Permissions

**`safe_chmod(path, mode: int) -> bool`** (line 40): Applies `os.chmod` on POSIX, no-op on Windows (ACL-restricted profile dir). Used to lock secret files to `0o600`.

### 11.3 Process Management

| Function | Signature | Line | Purpose |
|---|---|---|---|
| `detached_popen_kwargs()` | `() -> dict` | 58 | Kwargs for `subprocess.Popen` to fully detach a child. POSIX: `start_new_session=True`. Windows: `CREATE_NEW_PROCESS_GROUP \| DETACHED_PROCESS`. |
| `pid_alive(pid)` | `(pid: Optional[int]) -> bool` | 75 | Check if a process is running. POSIX: `os.kill(pid, 0)`. Windows: `OpenProcess` + `GetExitCodeProcess` via ctypes (because `os.kill(pid, 0)` on Windows calls `TerminateProcess`). |
| `kill_process_tree(pid)` | `(pid: Optional[int]) -> None` | 112 | Kill process and all descendants. POSIX: `killpg(getpgid(pid), SIGTERM)`. Windows: `taskkill /F /T /PID`. |

### 11.4 Shell / Executable Resolution

| Function | Signature | Line | Purpose |
|---|---|---|---|
| `find_bash()` | `() -> Optional[str]` | 234 | Locate a real bash interpreter (cached). On Windows, probes Git Bash locations and skips the System32/WindowsApps bash stub. |
| `has_bash()` | `() -> bool` | 258 | Whether bash was found |
| `which_tool(name)` | `(name: str) -> Optional[str]` | 262 | Enhanced `shutil.which` that also tries `.cmd`, `.exe`, `.bat` suffixes on Windows |
| `run_script_argv(script_path)` | `(script_path) -> List[str]` | 280 | argv to execute a shell script file. Prefers bash, falls back to `cmd.exe /c` on Windows. |
| `git_bash_path(path)` | `(path: str\|Path) -> str` | 219 | Convert a path to POSIX style for Git Bash (e.g. `C:\path` -> `/c/path`) |

**Windows bash probe locations** (lines 148-162): Checks `ProgramFiles`, `ProgramW6432`, `ProgramFiles(x86)`, `LocalAppData` for Git installations, plus hardcoded `C:\Program Files\Git` and `C:\Program Files (x86)\Git`. Looks for both `bin/bash.exe` and `usr/bin/bash.exe` within each root.

### 11.5 WSL Support

| Function | Signature | Line | Purpose |
|---|---|---|---|
| `is_wsl()` | `() -> bool` | 298 | Detect WSL by checking `/proc/version` for "microsoft" |
| `translate_path(path_str)` | `(path_str: str) -> str` | 311 | Convert Windows paths to WSL format (`C:\foo` -> `/mnt/c/foo`) when running under WSL |
| `get_wsl_windows_user_profile()` | `() -> Optional[str]` | 338 | Get the Windows host user profile path from inside WSL (tries PowerShell, falls back to `/mnt/c/Users` scan) |

### 11.6 SSH / Remote Execution

| Function | Signature | Line | Purpose |
|---|---|---|---|
| `_ssh_exec_argv()` | `(remote, ssh_port, *, remote_cmd, connect_timeout, strict_host_key_checking) -> list[str]` | 362 | Build a consistent ssh argv. Validates remote host against injection. |
| `run_ssh_command()` | `(remote, ssh_port, remote_cmd, *, timeout, ...) -> CompletedProcess` | 395 | Execute an SSH command with centralized timeout and capture. |
| `_windows_powershell_argv()` | `(command, *, no_profile, non_interactive) -> List[str]` | 420 | Build PowerShell argv with `-NoProfile -NonInteractive` defaults. |
| `run_wsl_windows_powershell()` | `(command, *, timeout=5) -> CompletedProcess[str]` | 435 | Run a PowerShell command on the Windows host from inside WSL. |

**SSH PATH override** (lines 165-185): Adds `/usr/bin`, `/usr/local/bin`, `/usr/local/cuda/bin`, `/usr/lib/wsl/lib` to the remote PATH so tools like `nvidia-smi` can be found. `NVIDIA_PATH_CANDIDATES` lists fallback absolute paths.

---

## Appendix: File Summary

| File | Lines | Primary Purpose |
|---|---|---|
| `app.py` | 1282 | Main orchestrator: FastAPI app, middleware, routers, lifecycle |
| `launcher.py` | 143 | Windows portable launcher with splash screen and system tray |
| `setup.py` | 303 | First-time setup: directories, database, admin user |
| `core/__init__.py` | 53 | Package public API re-exports |
| `core/atomic_io.py` | 46 | Crash-safe JSON/text file writes |
| `core/auth.py` | 688 | Multi-user auth, TOTP 2FA, privilege management |
| `core/constants.py` | 12 | Shim re-exporting from src/constants.py |
| `core/database.py` | 2563 | SQLAlchemy ORM, 20+ models, 35+ migrations, FTS |
| `core/exceptions.py` | 29 | Custom exception classes |
| `core/log_safety.py` | 27 | URL redaction for safe logging |
| `core/middleware.py` | 127 | Security headers, internal tool token, admin guard |
| `core/models.py` | 132 | Pure data models (Session, ChatMessage dataclasses) |
| `core/platform_compat.py` | 453 | Cross-platform helpers (Windows, macOS, WSL, SSH) |
| `core/session_manager.py` | 738 | Session CRUD, lazy message hydration, cleanup |
| `src/constants.py` | 129 | All application constants, paths, env vars |
