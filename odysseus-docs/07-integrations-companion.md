# Integrations and Companion System

This document covers the external agent integrations (Claude Code, Codex) and the companion LAN-pairing bridge that together form Odysseus's external-access surface.

---

## 1. Integrations Overview

Odysseus exposes a unified, scope-gated agent API under `/api/codex/*` that external AI coding agents use to read and write user data. Two integration bundles ship in the `integrations/` directory:

| Integration | Directory | Delivery | Runtime API |
|---|---|---|---|
| Claude Code | `integrations/claude/` | Skill bundle extracted to `~/.claude/skills/odysseus/` | `/api/codex/*` (shared) |
| Codex | `integrations/codex/` | Plugin bundle extracted to `~/plugins/odysseus/` | `/api/codex/*` (shared) |

Both integrations use the **same server-side routes** (`routes/codex_routes.py`). The `codex` path prefix is historic; all agent integrations share it. Authentication is via scoped `ody_`-prefixed Bearer tokens created through Odysseus Settings > Integrations.

### File inventory

```
integrations/
  claude/
    README.md                              # Setup instructions for Claude Code
    skills/odysseus/
      SKILL.md                             # Skill definition Claude Code reads at runtime
      scripts/odysseus_api.py              # CLI helper for calling scoped API endpoints
  codex/
    .codex-plugin/plugin.json              # Codex plugin manifest
    README.md                              # Setup instructions for Codex
    scripts/odysseus_api.py                # CLI helper (identical logic to Claude version)
    skills/odysseus/SKILL.md               # Skill definition Codex reads at runtime
```

### Environment variables (both integrations)

| Variable | Purpose | Example |
|---|---|---|
| `ODYSSEUS_URL` | Base URL for the Odysseus instance | `http://127.0.0.1:7000` |
| `ODYSSEUS_API_TOKEN` | Scoped API token (prefix `ody_`) | `ody_abc123...` |

### Scope system

Every API token carries a set of scopes. Server-side enforcement is in `routes/codex_routes.py` via `_scope_owner()` (line 85) and `_scope_owner_all()` (line 99). Defined scope sets:

| Scope constant | Value | Grants |
|---|---|---|
| `TODO_READ_SCOPES` | `{"todos:read", "todos:write"}` | List todos |
| `TODO_WRITE_SCOPES` | `{"todos:write"}` | Add/update/delete/toggle todos |
| `EMAIL_READ_SCOPES` | `{"email:read", "email:draft", "email:send"}` | List and read emails |
| `EMAIL_DRAFT_SCOPES` | `{"email:draft", "email:send"}` | Create draft documents/emails |
| `EMAIL_SEND_SCOPES` | `{"email:send"}` | Send email (requires explicit user instruction) |
| `MEMORY_READ_SCOPES` | `{"memory:read", "memory:write"}` | List memories |
| `MEMORY_WRITE_SCOPES` | `{"memory:write"}` | Add/delete memories |
| `CALENDAR_READ_SCOPES` | `{"calendar:read", "calendar:write"}` | List calendar events |
| `CALENDAR_WRITE_SCOPES` | `{"calendar:write"}` | Create/delete calendar events |
| `DOCS_READ_SCOPES` | `{"documents:read", "documents:write"}` | List and read documents |
| `DOCS_WRITE_SCOPES` | `{"documents:write"}` | Create/delete documents |
| `COOKBOOK_READ_SCOPES` | `{"cookbook:read", "cookbook:launch"}` | List tasks, servers, output, cached models, presets |
| `COOKBOOK_LAUNCH_SCOPES` | `{"cookbook:launch"}` | Start/stop serves, adopt sessions |

Write actions are determined by the `WRITE_ACTIONS` set (line 38): `{"add", "create", "new", "save", "remind", "update", "delete", "toggle_item", "remove", "remove_item"}`.

---

## 2. Claude Integration

### Setup flow

1. User opens Odysseus Settings > Integrations and adds a Claude Agent.
2. Odysseus generates a scoped `ody_` token and shows setup commands.
3. User exports `ODYSSEUS_URL` and `ODYSSEUS_API_TOKEN` in their terminal.
4. User downloads and extracts the skill bundle:

```bash
curl -fsSL -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  "$ODYSSEUS_URL/api/claude/plugin.zip" -o /tmp/odysseus-claude-skill.zip
python3 -m zipfile -e /tmp/odysseus-claude-skill.zip ~/.claude/
```

Claude Code auto-loads anything under `~/.claude/skills/`, so the `odysseus` skill becomes available in any session with the environment variables set.

### Skill bundle delivery

The zip is served by `setup_claude_routes()` in `routes/codex_routes.py` (line 882). It packages only the `skills/` subtree from `integrations/claude/skills/` to avoid dumping README.md into `~/.claude/`:

```python
def setup_claude_routes() -> APIRouter:                   # line 882
    router = APIRouter(prefix="/api/claude", tags=["claude"])

    @router.get("/plugin.zip")
    def plugin_zip(request: Request):                     # line 891
        # Only ships skills/ subtree
        skills_root = Path(__file__).resolve().parent.parent / "integrations" / "claude" / "skills"
```

### SKILL.md (`integrations/claude/skills/odysseus/SKILL.md`)

The skill definition is a frontmatter-annotated markdown file:

```yaml
---
name: odysseus
description: Use when the user asks Claude Code to read or write Odysseus data
  (todos, email, calendar, memory, documents) or to launch/monitor/stop a
  Cookbook model-serve task through the scoped Claude Agent API. Requires
  ODYSSEUS_URL and ODYSSEUS_API_TOKEN.
---
```

The file contains detailed instructions for Claude Code covering:

- **Configuration** (lines 8-17): Environment variable requirements and error handling.
- **Intent routing** (lines 19-27): Decision rules for reminders vs. calendar events vs. notes vs. memory. Key rule: "reminder" + a time defaults to a TODO with `due_date`, not a calendar event.
- **Safety rules** (lines 29-36): All data access must go through `/api/codex/*`. Direct imports, SSH, Docker, database queries, and MCP internals are forbidden.
- **Todos** (lines 38-61): `GET /api/codex/todos`, `POST /api/codex/todos`. Actions: `list`, `add`, `update`, `delete`, `toggle_item`. Reminders use natural language `due_date` field.
- **Email** (lines 63-77): `GET /api/codex/emails`, `GET /api/codex/emails/{uid}`. Read-only unless explicitly scoped.
- **Memory** (lines 79-89): `GET /api/codex/memory`, `POST /api/codex/memory`, `DELETE /api/codex/memory/{memory_id}`.
- **Calendar** (lines 91-95): `GET /api/codex/calendar/events`, `POST /api/codex/calendar/events`, `DELETE /api/codex/calendar/events/{uid}`.
- **Documents** (lines 97-102): Full CRUD via `/api/codex/documents`.
- **Email draft + send** (lines 104-108): Prefer `draft-document` (creates an editable document, no IMAP). `POST /api/codex/emails/draft` and `POST /api/codex/emails/send` for actual email.
- **Cookbook serve** (lines 110-151): Full model-server lifecycle management (tasks, servers, cached, presets, output, serve, preset, adopt, stop).
- **Forbidden bypass pattern** (lines 153-155): Explicit prohibition on bypassing the API.

### odysseus_api.py (`integrations/claude/skills/odysseus/scripts/odysseus_api.py`)

A standalone CLI helper with zero external dependencies beyond the Python standard library. Located at 219 lines total.

**Key functions:**

```python
def _usage() -> int                              # line 13 - Prints usage to stderr
def _config() -> tuple[str, str] | None          # line 38 - Reads ODYSSEUS_URL and ODYSSEUS_API_TOKEN
def main() -> int                                # line 52 - Main dispatch
```

**Command dispatch** (`main()`, line 52): Parses `sys.argv` and maps to HTTP method + path + body:

| CLI command | HTTP method | API path |
|---|---|---|
| `capabilities` | GET | `/api/codex/capabilities` |
| `todos list` | GET | `/api/codex/todos` |
| `todos add TITLE` | POST | `/api/codex/todos` |
| `emails list [limit]` | GET | `/api/codex/emails?folder=INBOX&limit={limit}&offset=0&filter=all` |
| `emails read UID` | GET | `/api/codex/emails/{uid}` |
| `emails draft-doc JSON` | POST | `/api/codex/emails/draft-document` |
| `documents list [limit]` | GET | `/api/codex/documents?limit={limit}` |
| `documents read DOC_ID` | GET | `/api/codex/documents/{doc_id}` |
| `documents create JSON` | POST | `/api/codex/documents` |
| `documents delete DOC_ID` | DELETE | `/api/codex/documents/{doc_id}` |
| `cookbook tasks` | GET | `/api/codex/cookbook/tasks` |
| `cookbook servers` | GET | `/api/codex/cookbook/servers` |
| `cookbook cached [HOST]` | GET | `/api/codex/cookbook/cached` |
| `cookbook presets` | GET | `/api/codex/cookbook/presets` |
| `cookbook output SID [tail]` | GET | `/api/codex/cookbook/output/{sid}?tail={tail}` |
| `cookbook serve REPO CMD [HOST]` | POST | `/api/codex/cookbook/serve` |
| `cookbook preset NAME` | POST | `/api/codex/cookbook/preset/{name}` |
| `cookbook adopt SID MODEL [HOST] [PORT]` | POST | `/api/codex/cookbook/adopt` |
| `cookbook stop SID` | POST | `/api/codex/cookbook/stop/{sid}` |
| `METHOD /api/codex/path [body]` | arbitrary | arbitrary (must start with `/api/codex/`) |

**Security enforcement** (line 178-181): Refuses any path not starting with `/api/codex/`:

```python
if not path.startswith("/api/codex/"):
    print("refusing non-/api/codex path; use scoped Odysseus integration endpoints only", file=sys.stderr)
    return 2
```

**HTTP execution** (line 189-214): Uses `urllib.request.Request` with Bearer token auth, 20-second timeout. JSON bodies are validated before sending.

---

## 3. Codex Integration

### Setup flow

1. User opens Odysseus Settings > Integrations and adds a Codex Agent.
2. User downloads the plugin bundle and registers it with Codex's plugin system:

```bash
curl -fsSL -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  "$ODYSSEUS_URL/api/codex/plugin.zip" -o /tmp/odysseus-codex-plugin.zip
python3 -m zipfile -e /tmp/odysseus-codex-plugin.zip ~/plugins
```

3. An inline Python script in the README writes a marketplace entry to `~/.agents/plugins/marketplace.json`.
4. User runs `codex plugin add odysseus@personal`.

### Plugin manifest (`.codex-plugin/plugin.json`)

```json
{
  "name": "odysseus",
  "version": "0.1.1",
  "description": "Connect Codex to a scoped Odysseus instance.",
  "skills": "./skills/",
  "interface": {
    "displayName": "Odysseus",
    "shortDescription": "Use scoped Odysseus tools from Codex.",
    "capabilities": ["todos", "email", "scoped-api"],
    "defaultPrompt": "Use Odysseus only through configured scoped access. Check capabilities before reading or writing data."
  }
}
```

### Plugin bundle delivery

Served by `setup_codex_routes()` in `routes/codex_routes.py` (line 218):

```python
@router.get("/plugin.zip")
def plugin_zip(request: Request):                         # line 219
    root = Path(__file__).resolve().parent.parent / "integrations" / "codex"
    # Packages entire codex directory under "odysseus/" prefix in zip
```

Unlike the Claude bundle (which only ships `skills/`), the Codex bundle ships the entire `integrations/codex/` directory.

### SKILL.md (`integrations/codex/skills/odysseus/SKILL.md`)

Structurally identical to the Claude SKILL.md but with Codex-specific naming. The content covers the same API surfaces with the same safety rules. Key differences from Claude SKILL.md:

- References "Codex Agent" instead of "Claude Agent" in user-facing instructions.
- Script paths reference `integrations/codex/scripts/odysseus_api.py` or `~/plugins/odysseus/scripts/odysseus_api.py`.

### odysseus_api.py (`integrations/codex/scripts/odysseus_api.py`)

Identical implementation to the Claude version. Both files are 219 lines, same functions, same dispatch logic. The docstring reads "Small Odysseus scoped API helper for Codex terminal sessions."

---

## 4. Server-Side Codex Routes (`routes/codex_routes.py`)

This is the single server-side module that backs both integrations. It is 911 lines and contains two factory functions:

### `setup_codex_routes()` (line 148)

```python
def setup_codex_routes(
    email_router: APIRouter | None = None,
    memory_router: APIRouter | None = None,
    calendar_router: APIRouter | None = None,
    document_router: APIRouter | None = None,
) -> APIRouter:
```

Accepts optional routers from which it resolves existing endpoint handlers via `_find_endpoint()` (line 127). This pattern lets the codex routes delegate to existing implementations without duplicating logic.

**Resolved endpoint handlers:**

| Handler variable | Source router | Original route |
|---|---|---|
| `email_list_endpoint` | `email_router` | `GET /api/email/list` |
| `email_read_endpoint` | `email_router` | `GET /api/email/read/{uid}` |
| `email_send_endpoint` | `email_router` | `POST /api/email/send` |
| `email_draft_endpoint` | `email_router` | `POST /api/email/draft` |
| `memory_list_endpoint` | `memory_router` | `GET /api/memory` |
| `memory_add_endpoint` | `memory_router` | `POST /api/memory/add` |
| `calendar_list_events` | `calendar_router` | `GET /api/calendar/events` |
| `calendar_create_event` | `calendar_router` | `POST /api/calendar/events` |
| `documents_library_endpoint` | `document_router` | `GET /api/documents/library` |
| `documents_get_endpoint` | `document_router` | `GET /api/document/{doc_id}` |
| `documents_create_endpoint` | `document_router` | `POST /api/document` |
| `memory_delete_endpoint` | `memory_router` | `DELETE /api/memory/{memory_id}` |
| `calendar_delete_event` | `calendar_router` | `DELETE /api/calendar/events/{uid}` |
| `documents_delete_endpoint` | `document_router` | `DELETE /api/document/{doc_id}` |

**Key internal helpers:**

```python
def _scope_owner(request, allowed: set[str]) -> str       # line 85
    # Returns data owner if caller has at least one scope in `allowed`

def _scope_owner_all(request, required: set[str]) -> str   # line 99
    # Returns owner only when token has ALL required scopes

def _require_cookbook_scope(request, allowed: set[str]) -> str  # line 113
    # Cookbook: API token uses scope set; cookie session requires admin

async def _as_owner(request, owner, fn, *args, **kwargs)   # line 60
    # Temporarily sets request.state.current_user to the token owner
    # so delegated handlers see the correct user context
```

**Registered routes (all under `/api/codex` prefix):**

| Method | Path | Handler | Line | Required scopes |
|---|---|---|---|---|
| GET | `/capabilities` | `capabilities()` | 167 | any (returns available scopes) |
| GET | `/plugin.zip` | `plugin_zip()` | 218 | authenticated |
| GET | `/todos` | `list_todos()` | 234 | `TODO_READ_SCOPES` |
| POST | `/todos` | `manage_todos()` | 242 | read or write depending on action |
| GET | `/emails` | `list_emails()` | 251 | `EMAIL_READ_SCOPES` |
| GET | `/emails/{uid}` | `read_email()` | 283 | `EMAIL_READ_SCOPES` |
| POST | `/emails/draft-document` | `codex_email_draft_document()` | 338 | `EMAIL_DRAFT_SCOPES` + `DOCS_WRITE_SCOPES` |
| POST | `/emails/draft` | `codex_email_draft()` | 363 | `EMAIL_DRAFT_SCOPES` |
| POST | `/emails/send` | `codex_email_send()` | 376 | `EMAIL_SEND_SCOPES` |
| GET | `/memory` | `codex_memory_list()` | 392 | `MEMORY_READ_SCOPES` |
| POST | `/memory` | `codex_memory_add()` | 398 | `MEMORY_WRITE_SCOPES` |
| DELETE | `/memory/{memory_id}` | `codex_memory_delete()` | 481 | `MEMORY_WRITE_SCOPES` |
| GET | `/calendar/events` | `codex_calendar_list()` | 420 | `CALENDAR_READ_SCOPES` |
| POST | `/calendar/events` | `codex_calendar_create()` | 427 | `CALENDAR_WRITE_SCOPES` |
| DELETE | `/calendar/events/{uid}` | `codex_calendar_delete()` | 488 | `CALENDAR_WRITE_SCOPES` |
| GET | `/documents` | `codex_documents_library()` | 442 | `DOCS_READ_SCOPES` |
| GET | `/documents/{doc_id}` | `codex_documents_get()` | 468 | `DOCS_READ_SCOPES` |
| POST | `/documents` | `codex_documents_create()` | 502 | `DOCS_WRITE_SCOPES` |
| DELETE | `/documents/{doc_id}` | `codex_documents_delete()` | 495 | `DOCS_WRITE_SCOPES` |
| GET | `/cookbook/tasks` | `codex_cookbook_tasks()` | 568 | `COOKBOOK_READ_SCOPES` |
| GET | `/cookbook/servers` | `codex_cookbook_servers()` | 575 | `COOKBOOK_READ_SCOPES` |
| GET | `/cookbook/output/{session_id}` | `codex_cookbook_output()` | 594 | `COOKBOOK_READ_SCOPES` |
| GET | `/cookbook/cached` | `codex_cookbook_cached()` | 692 | `COOKBOOK_READ_SCOPES` |
| GET | `/cookbook/presets` | `codex_cookbook_presets()` | 754 | `COOKBOOK_READ_SCOPES` |
| POST | `/cookbook/serve` | `codex_cookbook_serve()` | 636 | `COOKBOOK_LAUNCH_SCOPES` |
| POST | `/cookbook/preset/{name}` | `codex_cookbook_serve_preset()` | 776 | `COOKBOOK_LAUNCH_SCOPES` |
| POST | `/cookbook/stop/{session_id}` | `codex_cookbook_stop()` | 675 | `COOKBOOK_LAUNCH_SCOPES` |
| POST | `/cookbook/adopt` | `codex_cookbook_adopt()` | 825 | `COOKBOOK_LAUNCH_SCOPES` |

### `setup_claude_routes()` (line 882)

A minimal router under `/api/claude` with a single endpoint:

| Method | Path | Handler | Line |
|---|---|---|---|
| GET | `/plugin.zip` | `plugin_zip()` | 891 |

This only delivers the skill zip. Claude Code uses the same `/api/codex/*` endpoints as Codex at runtime.

---

## 5. Companion System

The companion system is a thin, additive LAN bridge that lets a mobile device (phone) discover and pair with an Odysseus server, then use it for chat via scoped API tokens.

### File inventory

```
companion/
  __init__.py       # Package init, exports setup_companion_routes
  pairing.py        # Token minting, LAN discovery, QR rendering
  routes.py         # FastAPI router with 5 endpoints
  README.md         # Architecture and CSRF documentation
```

### Registration in app.py

```python
from companion import setup_companion_routes          # app.py line 862
app.include_router(setup_companion_routes())          # app.py line 863
```

### `companion/__init__.py`

Exports the single public entry point:

```python
from companion.routes import setup_companion_routes
__all__ = ["setup_companion_routes"]
```

### `companion/pairing.py` -- Pairing helpers

Constants:

```python
PAIRING_VERSION = 1                                   # line 19
COMPANION_SCOPE = "chat"                              # line 20
```

**Functions:**

```python
def default_port() -> int                             # line 23
```
Returns the server port from `APP_PORT` env var, defaulting to `7000`.

```python
def lan_ip_candidates() -> list[str]                  # line 31
```
Discovers LAN IPv4 addresses using a UDP-connect trick (connect to `8.8.8.8:80` without sending data to discover the egress interface). Falls back to `socket.getaddrinfo()`. Drops loopback addresses. Returns best candidate first.

```python
def find_admin_user() -> str | None                   # line 63
```
Reads `data/auth.json` (via `AUTH_FILE` from `src.constants`) to find an admin user (`is_admin: true`). Falls back to the first user in the file.

```python
def mint_token(owner: str, name: str = "companion") -> tuple[str, str]  # line 83
```
Creates a chat-scoped API token:
1. Generates `ody_` + 32 bytes of URL-safe random data via `secrets.token_urlsafe`.
2. Hashes with bcrypt.
3. Creates an 8-char UUID token ID.
4. Persists an `ApiToken` row (from `core.database`) with: `id`, `owner`, `name`, `token_hash`, `token_prefix` (first 8 chars), `scopes="chat"`, `is_active=True`.
5. Returns `(token_id, raw_token)`. The raw token is shown once; only the hash is stored.

```python
def pairing_payload(host: str, port: int, token: str) -> dict  # line 109
```
Returns the JSON structure a client scans or accepts: `{"v": 1, "host": ..., "port": ..., "token": ...}`.

```python
def pairing_qr_png_data_uri(payload: dict) -> str | None  # line 114
```
Renders the pairing payload as a QR code `data:image/png;base64,...` URI using the optional `qrcode` library. Returns `None` if the library is unavailable.

### `companion/routes.py` -- Route handlers

**Helper functions:**

```python
def token_owner(request: Request) -> str | None       # line 31
```
Resolves the real owner of a request. For Bearer-token callers, reads `request.state.api_token_owner` (set by auth middleware). For cookie sessions, uses `get_current_user()`.

```python
def owner_can_see(row_owner, owner) -> bool            # line 44
```
Owner-scope predicate: a caller sees a row when it is their own or when it is a legacy null-owner (shared) row. Never reveals another owner's data.

```python
def require_models_scope(request: Request) -> None     # line 56
```
For Bearer-token callers, requires the `"chat"` scope (the `COMPANION_SCOPE`). Cookie sessions are exempt.

```python
def mint_pairing_token(owner: str, invalidate=None) -> tuple[str, str]  # line 68
```
Wraps `pairing.mint_token()` and additionally invalidates the auth middleware's in-memory token cache so the new token works immediately without a server restart.

### `setup_companion_routes()` (line 82)

Returns an `APIRouter` with prefix `/api/companion` and 5 endpoints:

#### GET `/api/companion/ping` (line 85)

Auth: session or token. Returns:

```json
{
  "ok": true,
  "name": "odysseus",
  "version": "<APP_VERSION>",
  "auth": "token" | "session"
}
```

Serves as a cheap health check confirming the host/port and credential are valid.

#### GET `/api/companion/info` (line 97)

Auth: session or token. Returns:

```json
{
  "name": "odysseus",
  "version": "<APP_VERSION>",
  "owner": "<resolved owner>",
  "capabilities": {"chat": true, "streaming": true}
}
```

#### GET `/api/companion/models` (line 109)

Auth: session or token (Bearer requires `chat` scope). Queries `ModelEndpoint` from `core.database` filtered by:
- `is_enabled == True`
- `model_type == "llm"` or `NULL`
- Owner-scoped via `owner_can_see()` predicate

Returns an array of endpoints with: `endpoint_id`, `name`, `endpoint_url` (via `build_chat_url()`), `models` (from `cached_models` minus `hidden_models`), `supports_tools`. Never exposes `api_key` material.

#### GET `/api/companion/pair` (line 162)

Auth: **admin cookie only** (enforced by `require_admin()`). Renders an HTML form page that POSTs to mint a code. A GET never mints a credential -- this is the CSRF-safe design: `SameSite=Lax` session cookies ride top-level GET navigations, so minting on GET would be triggerable by an `<img>` or link.

#### POST `/api/companion/pair` (line 189)

Auth: **admin cookie only**. Mints a one-time pairing token:

1. Calls `mint_pairing_token()` with the admin's username and the app's `invalidate_token_cache` callback.
2. Discovers LAN IP candidates via `pairing.lan_ip_candidates()`.
3. Determines port from the request URL or `default_port()`.
4. Builds the pairing payload via `pairing.pairing_payload()`.
5. Generates a QR code via `pairing.pairing_qr_png_data_uri()`.

If `?format=json` query parameter is present, returns JSON:

```json
{
  "host": "192.168.1.x",
  "port": 7000,
  "token": "ody_...",
  "token_id": "abcd1234",
  "hosts": ["192.168.1.x"],
  "payload": {"v": 1, "host": "...", "port": 7000, "token": "ody_..."},
  "qr": "data:image/png;base64,..." | null
}
```

Otherwise returns a styled HTML page displaying the QR code (or fallback text), host, port, token, and a warning that the code is shown once.

### CSRF posture

Documented in `companion/README.md`: minting happens only on POST. The session cookie is `SameSite=Lax` (set in `routes/auth_routes.py`), which browsers do not send on cross-site POSTs. This is the same CSRF protection that `POST /api/tokens` relies on. Minting on a GET would be unsafe because Lax cookies ride top-level GET navigations.

---

## 6. Integration Patterns

### Pattern 1: Scope-gated delegation

Both integrations follow the same pattern for data access:

1. **Client** sends request with `Authorization: Bearer ody_...` to `/api/codex/*`.
2. **`_scope_owner()`** extracts the token's scopes from `request.state.api_token_scopes` and the real owner from `request.state.api_token_owner`.
3. If the token lacks a required scope, the server returns `403`.
4. **`_as_owner()`** temporarily sets `request.state.current_user` to the token owner, then delegates to the existing internal endpoint handler. This avoids duplicating business logic.
5. Internal handlers (email, memory, calendar, documents, todos) see the correct user context and operate as if the token owner is logged in.

### Pattern 2: Endpoint discovery via `_find_endpoint()`

Rather than importing route handlers directly, `setup_codex_routes()` accepts optional `APIRouter` instances and resolves handlers by path and method at setup time:

```python
def _find_endpoint(router: APIRouter | None, method: str, path: str):
    if router is None:
        return None
    for route in getattr(router, "routes", []):
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route.endpoint
    return None
```

For cookbook routes where no router is passed, the code falls back to scanning `request.app.routes` at runtime.

### Pattern 3: Single CLI helper, identical across integrations

Both `integrations/claude/skills/odysseus/scripts/odysseus_api.py` and `integrations/codex/scripts/odysseus_api.py` contain identical Python code. The helper:

- Uses only the Python standard library (`json`, `os`, `sys`, `urllib`).
- Validates that all requests target `/api/codex/` paths (line 180-181).
- Uses Bearer token authentication with a 20-second timeout.
- Returns exit code 0 on success, 1 on HTTP errors, 2 on usage/config errors.

### Pattern 4: Skill definition as agent instructions

Each integration ships a `SKILL.md` file that the AI agent reads as runtime instructions. These files contain:

- Frontmatter with `name` and `description` for agent discovery.
- Decision rules (reminders vs. calendar vs. memory) so the agent makes correct data-model choices.
- Safety rules prohibiting direct database access, SSH, Docker, MCP internals.
- API reference with endpoints, methods, and example CLI invocations.
- The "Forbidden Bypass Pattern" section as a hard stop if the agent tries to circumvent scoping.

### Pattern 5: Companion owner-scoping

The companion routes use a layered scoping model:

1. **Auth middleware** validates the `ody_` token and stamps `api_token_owner` on the request.
2. **`token_owner()`** resolves the real owner (token owner for Bearer, logged-in user for cookies).
3. **`owner_can_see()`** is a pure predicate: `row_owner is None or row_owner == owner`.
4. **`require_models_scope()`** enforces the `"chat"` scope for Bearer callers viewing model inventory.
5. **`require_admin()`** gates pairing to admin cookie sessions only.

### Pattern 6: Token lifecycle

Tokens follow a consistent lifecycle across both companion pairing and integration setup:

1. **Generation**: `secrets.token_urlsafe(32)` prefixed with `ody_`.
2. **Hashing**: bcrypt hash stored in `ApiToken.token_hash`.
3. **Prefix storage**: First 8 characters stored in `ApiToken.token_prefix` for identification.
4. **Scope assignment**: Comma-separated string (e.g., `"chat"`, `"todos:read,email:read"`).
5. **Cache invalidation**: After minting, the auth middleware's in-memory token cache is invalidated.
6. **Display once**: The raw token is returned to the user exactly once; only the hash persists.

### Pattern 7: Cookbook debug loop

The Cookbook integration exposes a structured debug workflow for model-server management:

1. `cookbook tasks` -- survey running tasks.
2. `cookbook output SID 600` -- read persistent log (falls back to tmux pane if no log file).
3. `cookbook stop SID` -- kill previous attempt before relaunching.
4. `cookbook serve repo "cmd" [host]` -- relaunch with new flags.
5. Wait, then `cookbook output` on the new session ID.

Security: `serve` commands are validated against an allowlist of binaries (`vllm`, `python3`, `sglang`, `llama-server`, `ollama`, `node`, `npx`) and shell metacharacters are rejected. Session IDs are validated with `[a-zA-Z0-9_-]+`.

---

## 7. Cross-reference: How integrations connect to the main system

```
app.py
  line 862: from companion import setup_companion_routes
  line 863: app.include_router(setup_companion_routes())
  (codex/claude routes registered similarly via setup_codex_routes/setup_claude_routes)

routes/codex_routes.py
  line 148: setup_codex_routes() -- accepts email/memory/calendar/document routers
  line 882: setup_claude_routes() -- serves skill zip only

companion/__init__.py
  Exports: setup_companion_routes

companion/routes.py
  Imports: core.middleware.require_admin, src.auth_helpers.get_current_user
  Imports: companion.pairing (all helpers)
  Imports at runtime: core.constants.APP_VERSION, core.database.SessionLocal/ModelEndpoint

companion/pairing.py
  Imports: src.constants.AUTH_FILE, core.database.get_db_session/ApiToken, bcrypt

routes/codex_routes.py
  Imports: core.middleware.require_admin, src.auth_helpers.require_authenticated_request/require_user
  Imports: src.tool_implementations.do_manage_notes (for todos)
  Imports: src.constants.COOKBOOK_STATE_FILE
  Imports: routes._validators.validate_remote_host/validate_ssh_port
  Runtime imports: routes.email_helpers, routes.email_routes, routes.document_routes,
                   routes.calendar_routes, routes.cookbook_helpers, src.request_models,
                   core.atomic_io
```
