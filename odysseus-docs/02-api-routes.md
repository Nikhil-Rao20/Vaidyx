# Odysseus API Routes Reference

Comprehensive documentation of every API endpoint in the `routes/` directory.

Each subdirectory under `routes/` is a self-contained domain package. Top-level
files at `routes/<name>_routes.py` are backward-compatibility shims that
re-export from the corresponding `routes/<name>/<name>_routes.py` package.

---

## Table of Contents

1. [Route Overview](#1-route-overview)
2. [Admin / Wipe Routes](#2-admin--wipe-routes)
3. [Cleanup Routes](#3-cleanup-routes)
4. [Compare Routes](#4-compare-routes)
5. [Contacts Routes](#5-contacts-routes)
6. [Document Routes](#6-document-routes)
7. [Gallery Routes](#7-gallery-routes)
8. [History Routes](#8-history-routes)
9. [Memory Routes](#9-memory-routes)
10. [Note Routes](#10-note-routes)
11. [Research Routes](#11-research-routes)
12. [Search Routes](#12-search-routes)
13. [Vault Routes](#13-vault-routes)
14. [Webhook Routes](#14-webhook-routes)

---

## 1. Route Overview

| # | HTTP Method | URL Pattern | Domain | Auth | Summary |
|---|-------------|-------------|--------|------|---------|
| 1 | `DELETE` | `/api/admin/wipe/{kind}` | Admin | Admin | Wipe a data category |
| 2 | `GET` | `/api/cleanup/preview` | Cleanup | User | Preview cleanup candidates |
| 3 | `POST` | `/api/cleanup` | Cleanup | User | Run cleanup operations |
| 4 | `POST` | `/api/compare/start` | Compare | User | Start A/B model comparison |
| 5 | `POST` | `/api/compare/{comp_id}/vote` | Compare | User | Vote on comparison winner |
| 6 | `POST` | `/api/compare/record` | Compare | User | Record a lightweight vote |
| 7 | `GET` | `/api/compare/history` | Compare | User | List past comparisons |
| 8 | `DELETE` | `/api/compare/{comp_id}` | Compare | User | Delete a comparison |
| 9 | `GET` | `/api/contacts/list` | Contacts | Admin | List all contacts |
| 10 | `GET` | `/api/contacts/search` | Contacts | Admin | Search contacts |
| 11 | `POST` | `/api/contacts/add` | Contacts | Admin | Add new contact |
| 12 | `POST` | `/api/contacts/import` | Contacts | Admin | Import VCF/CSV contacts |
| 13 | `GET` | `/api/contacts/export` | Contacts | Admin | Export contacts as VCF/CSV |
| 14 | `GET` | `/api/contacts/config` | Contacts | Admin | Get CardDAV config |
| 15 | `PUT` | `/api/contacts/config` | Contacts | Admin | Update CardDAV config |
| 16 | `DELETE` | `/api/contacts/clear` | Contacts | Admin | Clear local contacts |
| 17 | `PUT` | `/api/contacts/{uid}` | Contacts | Admin | Edit a contact |
| 18 | `DELETE` | `/api/contacts/{uid}` | Contacts | Admin | Delete a contact |
| 19 | `POST` | `/api/document` | Document | Privilege | Create a document |
| 20 | `POST` | `/api/documents/import-pdf` | Document | Privilege | Import PDF as document |
| 21 | `GET` | `/api/documents/library` | Document | User | Browse document library |
| 22 | `GET` | `/api/documents/{session_id}` | Document | User | List docs for session |
| 23 | `GET` | `/api/document/{doc_id}` | Document | User | Get single document |
| 24 | `PUT` | `/api/document/{doc_id}` | Document | User | Update document content |
| 25 | `PATCH` | `/api/document/{doc_id}` | Document | User | Patch document metadata |
| 26 | `DELETE` | `/api/document/{doc_id}` | Document | User | Soft-delete document |
| 27 | `POST` | `/api/document/{doc_id}/archive` | Document | User | Archive/restore document |
| 28 | `POST` | `/api/document/{doc_id}/extract-pdf-text` | Document | User | Re-extract PDF text |
| 29 | `GET` | `/api/document/{doc_id}/versions` | Document | User | List version history |
| 30 | `GET` | `/api/document/{doc_id}/version/{num}` | Document | User | Get specific version |
| 31 | `POST` | `/api/document/{doc_id}/restore/{num}` | Document | User | Restore old version |
| 32 | `POST` | `/api/documents/tidy` | Document | User | Clean junk documents |
| 33 | `POST` | `/api/documents/ai-tidy` | Document | User | AI-powered junk cleanup |
| 34 | `POST` | `/api/documents/export-zip` | Document | User | Export docs as ZIP |
| 35 | `POST` | `/api/document/{doc_id}/export-pdf/preview` | Document | User | Preview PDF field mapping |
| 36 | `GET` | `/api/document/{doc_id}/render-pages` | Document | User | PDF page metadata + fields |
| 37 | `GET` | `/api/document/{doc_id}/page/{n}.png` | Document | User | Render PDF page as PNG |
| 38 | `POST` | `/api/document/{doc_id}/ai-fill-annotations` | Document | User | AI-fill PDF annotations |
| 39 | `GET` | `/api/document/{doc_id}/render-pdf` | Document | User | Inline PDF preview |
| 40 | `GET` | `/api/document/{doc_id}/export-pdf` | Document | User | Download filled PDF |
| 41 | `POST` | `/api/document/{doc_id}/prepare-signed-reply` | Document | User | Prepare signed PDF email reply |
| 42 | `POST` | `/api/gallery/upload` | Gallery | User | Upload image to gallery |
| 43 | `POST` | `/api/gallery/{image_id}/replace` | Gallery | User | Replace gallery image file |
| 44 | `POST` | `/api/gallery/{image_id}/rename` | Gallery | User | Rename gallery image |
| 45 | `POST` | `/api/gallery/{image_id}/rotate` | Gallery | User | Rotate image |
| 46 | `POST` | `/api/gallery/ai-upscale` | Gallery | Privilege | AI upscale via diffusion |
| 47 | `POST` | `/api/gallery/style-transfer` | Gallery | Privilege | Style transfer via img2img |
| 48 | `GET` | `/api/gallery/tags` | Gallery | User | List distinct tags |
| 49 | `GET` | `/api/gallery/library` | Gallery | User | Browse gallery library |
| 50 | `GET` | `/api/gallery/albums` | Gallery | User | List albums |
| 51 | `POST` | `/api/gallery/albums` | Gallery | User | Create album |
| 52 | `GET` | `/api/gallery/stats` | Gallery | User | Gallery statistics |
| 53 | `POST` | `/api/gallery/ai-tag-batch` | Gallery | User | Batch AI tag untagged images |
| 54 | `GET` | `/api/gallery/{image_id}` | Gallery | User | Get single image metadata |
| 55 | `PATCH` | `/api/gallery/{image_id}` | Gallery | User | Patch image tags/favorite/album |
| 56 | `DELETE` | `/api/gallery/{image_id}` | Gallery | User | Soft-delete image |
| 57 | `POST` | `/api/gallery/download-zip` | Gallery | User | Bulk download as ZIP |
| 58 | `POST` | `/api/gallery/clear-user-tags` | Gallery | User | Wipe user tags |
| 59 | `POST` | `/api/gallery/clear-ai-tags` | Gallery | User | Wipe AI tags |
| 60 | `POST` | `/api/gallery/dedupe-tags` | Gallery | User | Deduplicate user vs AI tags |
| 61 | `POST` | `/api/image/inpaint` | Gallery | Privilege | Inpaint proxy (OpenAI/SD) |
| 62 | `POST` | `/api/image/harmonize` | Gallery | Privilege | Harmonize via img2img |
| 63 | `POST` | `/api/image/sharpen` | Gallery | Privilege | Unsharp-mask sharpening |
| 64 | `POST` | `/api/image/denoise` | Gallery | Privilege | AI denoise via Real-ESRGAN |
| 65 | `POST` | `/api/image/upscale-local` | Gallery | Privilege | Local Real-ESRGAN upscale |
| 66 | `POST` | `/api/image/mask` | Gallery | Privilege | SAM segmentation mask |
| 67 | `POST` | `/api/image/remove-bg` | Gallery | Privilege | Background removal |
| 68 | `POST` | `/api/image/enhance-face` | Gallery | Privilege | Face enhancement (GFPGAN) |
| 69 | `PUT` | `/api/gallery/albums/{album_id}` | Gallery | User | Update album |
| 70 | `DELETE` | `/api/gallery/albums/{album_id}` | Gallery | User | Delete album |
| 71 | `POST` | `/api/gallery/albums/{album_id}/add` | Gallery | User | Add images to album |
| 72 | `POST` | `/api/gallery/albums/{album_id}/remove` | Gallery | User | Remove images from album |
| 73 | `POST` | `/api/gallery/{image_id}/favorite` | Gallery | User | Toggle favorite |
| 74 | `POST` | `/api/gallery/{image_id}/ai-tag` | Gallery | User | AI-tag single image |
| 75 | `GET` | `/api/history/{session_id}` | History | User | Get session history |
| 76 | `POST` | `/api/session/{session_id}/truncate` | History | User | Truncate messages |
| 77 | `POST` | `/api/session/{session_id}/message` | History | User | Add message to session |
| 78 | `POST` | `/api/session/{session_id}/delete-messages` | History | User | Delete specific messages |
| 79 | `POST` | `/api/session/{session_id}/edit-message` | History | User | Edit message content |
| 80 | `POST` | `/api/session/{session_id}/mark-stopped` | History | User | Mark last reply as stopped |
| 81 | `POST` | `/api/session/{session_id}/update-last-meta` | History | User | Merge metadata into last reply |
| 82 | `POST` | `/api/session/{session_id}/merge-last-assistant` | History | User | Merge continue fragments |
| 83 | `POST` | `/api/session/{session_id}/fork` | History | User | Fork session |
| 84 | `GET` | `/api/conversations/topics` | History | User | Analyze conversation topics |
| 85 | `GET` | `/api/session/{session_id}/context` | History | User | Context usage estimate |
| 86 | `POST` | `/api/session/{session_id}/compact` | History | User | Manual context compaction |
| 87 | `POST` | `/api/memory/debug` | Memory | User | Debug memory relevance |
| 88 | `POST` | `/api/memory/add` | Memory | Privilege | Add memory entry |
| 89 | `GET` | `/api/memory` | Memory | User | List all memories |
| 90 | `POST` | `/api/memory/search` | Memory | User | Search memories |
| 91 | `GET` | `/api/memory/timeline` | Memory | User | Chronological memory timeline |
| 92 | `GET` | `/api/memory/by-session/{session_id}` | Memory | User | Memories by session |
| 93 | `POST` | `/api/memory/extract` | Memory | User | Extract memories from chat |
| 94 | `POST` | `/api/memory/audit` | Memory | User | Deduplicate/consolidate memories |
| 95 | `POST` | `/api/memory/import` | Memory | Privilege | Import memories from file |
| 96 | `POST` | `/api/memory/{memory_id}/pin` | Memory | User | Pin/unpin memory |
| 97 | `GET` | `/api/memory/{memory_id}` | Memory | User | Get single memory |
| 98 | `PUT` | `/api/memory/{memory_id}` | Memory | User | Update memory text |
| 99 | `DELETE` | `/api/memory/{memory_id}` | Memory | User | Delete memory |
| 100 | `GET` | `/api/notes` | Note | User | List notes |
| 101 | `POST` | `/api/notes` | Note | User | Create note |
| 102 | `GET` | `/api/notes/{note_id}` | Note | User | Get single note |
| 103 | `PUT` | `/api/notes/{note_id}` | Note | User | Update note |
| 104 | `DELETE` | `/api/notes/{note_id}` | Note | User | Delete note |
| 105 | `POST` | `/api/notes/{note_id}/pin` | Note | User | Toggle pin |
| 106 | `POST` | `/api/notes/{note_id}/archive` | Note | User | Toggle archive |
| 107 | `POST` | `/api/notes/{note_id}/items/{index}/toggle` | Note | User | Toggle checklist item |
| 108 | `POST` | `/api/notes/fire-reminder` | Note | User | Dispatch reminder |
| 109 | `POST` | `/api/notes/reorder` | Note | User | Reorder notes |
| 110 | `GET` | `/api/research/active` | Research | User | List running research |
| 111 | `GET` | `/api/research/status/{session_id}` | Research | User | Research status |
| 112 | `POST` | `/api/research/cancel/{session_id}` | Research | User | Cancel research |
| 113 | `POST` | `/api/research/result/{session_id}` | Research | User | Get and clear result |
| 114 | `GET` | `/api/research/report/{session_id}` | Research | User | Visual HTML report |
| 115 | `POST` | `/api/research/{session_id}/hide-image` | Research | User | Hide report image |
| 116 | `POST` | `/api/research/{session_id}/unhide-images` | Research | User | Unhide all images |
| 117 | `GET` | `/api/research/library` | Research | User | Library of research reports |
| 118 | `GET` | `/api/research/detail/{session_id}` | Research | User | Full research JSON |
| 119 | `POST` | `/api/research/{session_id}/archive` | Research | User | Archive/restore research |
| 120 | `DELETE` | `/api/research/{session_id}` | Research | User | Delete research |
| 121 | `POST` | `/api/research/start` | Research | Privilege | Launch research job |
| 122 | `GET` | `/api/research/stream/{session_id}` | Research | User | SSE progress stream |
| 123 | `POST` | `/api/research/result-peek/{session_id}` | Research | User | Peek result (no clear) |
| 124 | `POST` | `/api/research/spinoff/{session_id}` | Research | User | Spin off into chat session |
| 125 | `GET` | `/api/search/config` | Search | None | Get search config |
| 126 | `POST` | `/api/search` | Search | None | Standalone web search |
| 127 | `GET` | `/api/search/providers` | Search | None | List search providers |
| 128 | `POST` | `/api/search/query` | Search | None | Search with specific provider |
| 129 | `GET` | `/api/vault/config` | Vault | Admin | Get vault config |
| 130 | `POST` | `/api/vault/config` | Vault | Admin | Save vault config |
| 131 | `POST` | `/api/vault/login` | Vault | Admin | Login to Vaultwarden |
| 132 | `POST` | `/api/vault/unlock` | Vault | Admin | Unlock vault |
| 133 | `POST` | `/api/vault/lock` | Vault | Admin | Lock vault |
| 134 | `POST` | `/api/vault/logout` | Vault | Admin | Logout from vault |
| 135 | `GET` | `/api/webhooks` | Webhook | Admin | List webhooks |
| 136 | `POST` | `/api/webhooks` | Webhook | Admin | Create webhook |
| 137 | `POST` | `/api/webhooks/{webhook_id}/test` | Webhook | Admin | Test webhook |
| 138 | `PATCH` | `/api/webhooks/{webhook_id}` | Webhook | Admin | Toggle webhook active |
| 139 | `DELETE` | `/api/webhooks/{webhook_id}` | Webhook | Admin | Delete webhook |
| 140 | `POST` | `/api/v1/chat` | Webhook | API Token | Sync chat (external tools) |

---

## 2. Admin / Wipe Routes

**Source:** `routes/admin_wipe/admin_wipe_routes.py`
**Factory:** `setup_admin_wipe_routes(session_manager)` (line 65)
**Router prefix:** `/api/admin`

These endpoints are for the admin "Danger Zone" panel. Each truncates exactly
one data domain so the user can selectively reset without nuking everything.

### DELETE `/api/admin/wipe/{kind}`

**Function:** `wipe()` (line 72)
**Auth:** `require_admin(request)` -- admin-only
**Path parameter:** `kind` -- one of: `chats`, `memory`, `skills`, `notes`, `tasks`, `documents`, `gallery`, `calendar`

**Behavior by kind:**

| Kind | What is deleted | Details |
|------|----------------|---------|
| `chats` | All sessions and chat messages | Clears DB tables `Session`, `ChatMessage`. Also clears `session_manager.sessions` in-memory cache. |
| `memory` | All memory entries | Clears DB `Memory` table, blanks `memory.json`, removes `memory_tidy_state.json`, clears the ChromaDB vector store. |
| `skills` | All skill files | Removes the `data/skills/` directory tree and legacy `skills.json`. Counts SKILL.md files. |
| `notes` | All notes | Clears DB `Note` table. |
| `tasks` | All scheduled tasks and runs | Clears DB `TaskRun` (FK first), then `ScheduledTask`. |
| `documents` | All documents and versions | Clears DB `DocumentVersion` (FK first), then `Document`. |
| `gallery` | All gallery images and albums | Clears DB `GalleryImage` and `GalleryAlbum`. Removes `GALLERY_DIR` and `GALLERY_UPLOADS_DIR` from disk. |
| `calendar` | All calendar events and calendars | Clears DB `CalendarEvent` (FK first), then `CalendarCal`. |

**Response:**
```json
{"status": "deleted", "kind": "chats", "count": 42}
```

**Error:** 400 for unknown kind, 500 on failure.

---

## 3. Cleanup Routes

**Source:** `routes/cleanup/cleanup_routes.py`
**Factory:** `setup_cleanup_routes(session_manager)` (line 10)
**Router prefix:** `/api/cleanup`

### GET `/api/cleanup/preview`

**Function:** `cleanup_preview()` (line 23)
**Auth:** `get_current_user(request)` -- requires authenticated user
**Parameters:** None

Returns a preview of what would be cleaned without making changes. Delegates
to `src.cleanup_service.get_cleanup_preview()`.

**Response:** JSON with lists of sessions that would be archived/deleted and estimated space savings.

### POST `/api/cleanup`

**Function:** `cleanup_endpoint()` (line 38)
**Auth:** `get_current_user(request)` -- requires authenticated user
**Parameters:** None (body not required)

Performs two cleanup operations:
1. Archives sessions not accessed for 7 days.
2. Deletes old archived sessions (not important, not accessed for 14+ days, fewer than 10 messages).

**Response:**
```json
{
  "archived_count": 5,
  "deleted_count": 3,
  "space_freed_mb": 12.45
}
```

---

## 4. Compare Routes

**Source:** `routes/compare/compare_routes.py`
**Factory:** `setup_compare_routes(session_manager)` (line 67)
**Router prefix:** `/api/compare`

Model A/B comparison system. Supports blind comparisons where model identities
are hidden until after voting.

### POST `/api/compare/start`

**Function:** `start_comparison()` (line 70)
**Auth:** User from `request.state.current_user`
**Parameters (form data):**
- `prompt` (required) -- the prompt to compare
- `model_a` (required) -- first model name
- `model_b` (required) -- second model name
- `endpoint_a` -- endpoint URL for model A
- `endpoint_b` -- endpoint URL for model B
- `endpoint_a_id` -- registered endpoint ID for model A (preferred)
- `endpoint_b_id` -- registered endpoint ID for model B (preferred)
- `is_blind` -- `"true"` (default) for blind comparison

Creates two ephemeral `[CMP]` sessions and a `Comparison` DB record. In blind
mode, left/right assignment is randomized and model names are hidden.

**Security:** Both endpoints are validated for ownership before any session is
created. Non-admin users cannot use raw (unregistered) endpoint URLs.

**Response:**
```json
{
  "id": "uuid",
  "session_left": "sid-uuid",
  "session_right": "sid-uuid",
  "model_left": null,
  "model_right": null,
  "is_blind": true,
  "mapping": null
}
```

### POST `/api/compare/{comp_id}/vote`

**Function:** `vote_comparison()` (line 237)
**Auth:** `get_current_user(request)` with strict ownership
**Parameters (form data):**
- `winner` (required) -- `"left"`, `"right"`, or `"tie"`

Records the user's vote. Reveals model names after voting in blind mode.
Cannot vote twice on the same comparison.

**Response:**
```json
{
  "winner": "a",
  "model_a": "gpt-4",
  "model_b": "claude-3",
  "revealed": {"left": "claude-3", "right": "gpt-4"}
}
```

### POST `/api/compare/record`

**Function:** `record_comparison()` (line 283)
**Auth:** `get_current_user(request)`
**Body (JSON):** `RecordVoteRequest` with fields: `prompt`, `models` (list), `winner`, `is_blind`

Lightweight endpoint to record a comparison vote from the frontend without
creating full sessions. Supports N > 2 models.

**Response:** `{"status": "ok", "id": "uuid"}`

### GET `/api/compare/history`

**Function:** `list_comparisons()` (line 320)
**Auth:** `get_current_user(request)` -- owner-filtered
**Parameters:** None

Returns up to 50 past comparisons, newest first.

**Response:** Array of comparison summaries with prompt preview (100 chars), models, winner, timestamps.

### DELETE `/api/compare/{comp_id}`

**Function:** `delete_comparison()` (line 346)
**Auth:** `get_current_user(request)` with strict ownership

Deletes a comparison record. Returns `{"status": "deleted"}`.

---

## 5. Contacts Routes

**Source:** `routes/contacts/contacts_routes.py`
**Factory:** `setup_contacts_routes()` (line 738)
**Router prefix:** `/api/contacts`

CardDAV-compatible contacts integration. Reads from local Radicale or a local
JSON fallback. Supports vCard import/export and CSV import/export.

### GET `/api/contacts/list`

**Function:** `list_contacts()` (line 741)
**Auth:** `require_admin` -- admin-only
**Response:** `{"contacts": [...], "count": N}`

### GET `/api/contacts/search`

**Function:** `search_contacts()` (line 748)
**Auth:** `require_admin`
**Query params:** `q` -- search string
**Response:** `{"results": [...]}` (up to 10 matches by name or email)

### POST `/api/contacts/add`

**Function:** `add_contact()` (line 765)
**Auth:** `require_admin`
**Body (JSON):** `name`, `email`, `phone`, `phones` (list), `address`
**Behavior:** Creates via CardDAV PUT or appends to local JSON. De-duplicates by email/phone.
**Response:** `{"success": true}` or `{"success": true, "message": "Already exists", "contact": {...}}`

### POST `/api/contacts/import`

**Function:** `import_vcf()` (line 812)
**Auth:** `require_admin`
**Body (JSON):** `{"vcf": "..."}` or `{"csv": "..."}`
**Behavior:** Imports .vcf (vCard) or CSV contacts. Each card is PUT individually, preserving original content.
**Response:** `{"imported": N, "failed": M, "total": T, "success": true}`

### GET `/api/contacts/export`

**Function:** `export_contacts()` (line 831)
**Auth:** `require_admin`
**Query params:** `format` -- `vcf` (default) or `csv`
**Response:** File download (`text/vcard` or `text/csv`)

### GET `/api/contacts/config`

**Function:** `get_config()` (line 852)
**Auth:** `require_admin`
**Response:** CardDAV URL, username, password (masked as `***`)

### PUT `/api/contacts/config`

**Function:** `update_config()` (line 860)
**Auth:** `require_admin`
**Body (JSON):** `carddav_url`, `carddav_username`, `carddav_password`
**Behavior:** Passwords are encrypted at rest via `src.secret_storage`. URLs are validated against SSRF.

### DELETE `/api/contacts/clear`

**Function:** `clear_contacts()` (line 881)
**Auth:** `require_admin`
**Behavior:** Clears local contacts JSON. If CardDAV is configured, only clears the local fallback.

### PUT `/api/contacts/{uid}`

**Function:** `edit_contact()` (line 890)
**Auth:** `require_admin`
**Body (JSON):** `name`, `emails` (list), `phones` (list), `address`

### DELETE `/api/contacts/{uid}`

**Function:** `delete_contact()` (line 908)
**Auth:** `require_admin`
**Behavior:** Deletes via CardDAV DELETE or removes from local JSON. Verifies deletion by re-fetching.

---

## 6. Document Routes

**Source:** `routes/document/document_routes.py`, `routes/document/document_helpers.py`
**Factory:** `setup_document_routes(session_manager, upload_handler=None)` (line 79)
**Router:** No prefix (paths include `/api/document` or `/api/documents`)

Living documents with full version history, PDF form filling, and AI-powered
cleanup. Documents can be session-bound or standalone library entries.

### POST `/api/document`

**Function:** `create_document()` (line 105)
**Auth:** `require_privilege(request, "can_use_documents")`
**Body (JSON):** `DocumentCreate` -- `session_id` (optional), `title`, `language`, `content`
**Behavior:**
- Auto-detects language if not supplied (email, markdown, etc.)
- For email documents: deduplicates by source UID, merging into existing draft
- Stamps owner directly on the document
- Fires `document_created` event

**Response:** Document dict with id, title, language, content, version_count, timestamps.

### POST `/api/documents/import-pdf`

**Function:** `import_pdf()` (line 221)
**Auth:** `require_privilege(request, "can_use_documents")`
**Parameters (multipart form):** `file` (PDF upload), `session_id` (optional)
**Behavior:**
- Saves the PDF via upload handler
- Detects AcroForm fields -- if present, creates a form-backed markdown doc with interactive inputs
- Otherwise creates a plain PDF doc with extracted text
- Fires OCR/VL text extraction

**Response:** Document dict.

### GET `/api/documents/library`

**Function:** `documents_library()` (line 323)
**Auth:** `get_current_user(request)` -- owner-filtered
**Query params:**
- `search` -- full-text search (title + content, per-term AND)
- `language` -- filter by language (including virtual "pdf" type)
- `sort` -- `recent` (default), `oldest`, `edits`, `alpha`
- `offset`, `limit` (max 50)
- `archived` -- show archived docs only

**Response:**
```json
{
  "documents": [...],
  "total": 42,
  "languages": {"markdown": 10, "pdf": 5, "email": 3},
  "session_count": 8
}
```

### GET `/api/documents/{session_id}`

**Function:** `list_documents()` (line 445)
**Auth:** `get_current_user(request)` -- session ownership verified
**Response:** Array of document dicts for the given session.

### GET `/api/document/{doc_id}`

**Function:** `get_document()` (line 469)
**Auth:** Owner-verified via `_verify_doc_owner()`
**Response:** Full document dict.

### PUT `/api/document/{doc_id}`

**Function:** `update_document()` (line 623)
**Auth:** Owner-verified
**Body (JSON):** `DocumentUpdate` -- `content`, `summary` (optional), `force_version` (bool)
**Behavior:**
- Version coalescing: if last user version < 60 seconds old, updates in-place
- Otherwise creates a new version
- Skips if content is identical (unless `force_version`)
- Validates upload references and PDF marker ownership

### PATCH `/api/document/{doc_id}`

**Function:** `patch_document()` (line 698)
**Auth:** Owner-verified
**Body (JSON):** `DocumentPatch` -- `title`, `language`, `session_id` (link/unlink)

### DELETE `/api/document/{doc_id}`

**Function:** `delete_document()` (line 737)
**Auth:** Owner-verified
**Behavior:** Soft-delete (sets `is_active = False`). Clears active-document pointer.

### POST `/api/document/{doc_id}/archive`

**Function:** `archive_document()` (line 483)
**Auth:** Owner-verified
**Query params:** `archived` (default true)

### POST `/api/document/{doc_id}/extract-pdf-text`

**Function:** `extract_pdf_text()` (line 499)
**Auth:** Owner-verified
**Behavior:** Re-runs pypdf + VL text extraction against the linked PDF. Creates a new version.
**Response:** `{"ok": true, "id": "...", "extracted": true, "chars": 5000}`

### GET `/api/document/{doc_id}/versions`

**Function:** `list_versions()` (line 765)
**Response:** Array of version dicts (id, version_number, content, summary, source, created_at).

### GET `/api/document/{doc_id}/version/{num}`

**Function:** `get_version()` (line 789)
**Response:** Single version dict.

### POST `/api/document/{doc_id}/restore/{num}`

**Function:** `restore_version()` (line 811)
**Behavior:** Creates a new version with the old version's content. Updates current_content.

### POST `/api/documents/tidy`

**Function:** `tidy_documents()` (line 852)
**Behavior:**
- Fixes empty/placeholder titles by deriving from content
- Hard-deletes empty, junk-titled, and email-stub documents (skips docs < 15 min old)
- Also cleans up inactive empty docs

**Response:** `{"fixed_titles": 3, "deleted": 5, "message": "..."}`

### POST `/api/documents/ai-tidy`

**Function:** `ai_tidy_documents()` (line 967)
**Behavior:** Sends batches of up to 30 documents to an LLM for junk/keep classification.
Caches verdicts so reviewed docs are skipped on subsequent runs.

### POST `/api/documents/export-zip`

**Function:** `documents_export_zip()` (line 559)
**Body (JSON):** `{"ids": ["doc-id-1", "doc-id-2"]}`
**Response:** ZIP file download containing each document as a text file with appropriate extension.

### POST `/api/document/{doc_id}/export-pdf/preview`

**Function:** `export_pdf_preview()` (line 1064)
**Response:** Field-value mapping preview for PDF form export confirmation.

### GET `/api/document/{doc_id}/render-pages`

**Function:** `render_pages()` (line 1126)
**Response:** Per-page metadata with image dimensions and form field rects in pixel coordinates.

### GET `/api/document/{doc_id}/page/{page_no}.png`

**Function:** `render_page_png()` (line 1197)
**Response:** PNG image of the rendered PDF page (no form values stamped).

### POST `/api/document/{doc_id}/ai-fill-annotations`

**Function:** `ai_fill_annotations()` (line 1238)
**Body (JSON):** `{"instruction": "Fill with my info..."}`
**Behavior:** Sends each PDF page to a vision LLM to locate fillable areas and propose values.
**Response:** `{"annotations": [{"page": 1, "x": 10.5, "y": 20.3, "w": 30, "h": 5, "value": "John Doe"}]}`

### GET `/api/document/{doc_id}/render-pdf`

**Function:** `render_pdf()` (line 1378)
**Response:** Inline PDF with form fields filled + annotations stamped (no signatures).

### GET `/api/document/{doc_id}/export-pdf`

**Function:** `export_pdf()` (line 1478)
**Response:** Downloadable PDF with form fields filled, signatures stamped, and annotations burned in.

### POST `/api/document/{doc_id}/prepare-signed-reply`

**Function:** `prepare_signed_reply()` (line 1614)
**Behavior:** Bakes filled PDF into a flattened attachment, fetches source email headers for reply context.
**Response:** Attachment token + reply metadata (to, subject, in-reply-to, references).

---

## 7. Gallery Routes

**Source:** `routes/gallery/gallery_routes.py`, `routes/gallery/gallery_helpers.py`
**Factory:** `setup_gallery_routes()` (line 332)
**Router:** No prefix (paths include `/api/gallery` and `/api/image`)

Browsable photo library with AI-powered image editing tools, album management,
EXIF extraction, and integration with diffusion servers.

### POST `/api/gallery/upload`

**Function:** `gallery_upload()` (line 336)
**Auth:** `get_current_user(request)`
**Parameters (multipart form):** `file`, `album_id` (optional)
**Behavior:**
- Supports images (png, jpg, jpeg, webp, gif) and video (mp4, mov, webm, mkv, m4v)
- SHA-256 dedup (owner-scoped)
- Extracts EXIF metadata (camera, GPS, taken_at, dimensions)

**Response:** `{"ok": true, "filename": "abc123.png", "id": "uuid"}`

### POST `/api/gallery/{image_id}/replace`

**Function:** `gallery_replace()` (line 418)
**Auth:** Owner check
**Parameters (multipart form):** `image`
**Behavior:** Replaces the image file on disk. Updates width/height in DB.

### POST `/api/gallery/{image_id}/rename`

**Function:** `gallery_rename()` (line 461)
**Body (JSON):** `{"name": "New Name"}`
**Behavior:** Updates the `prompt` column (used as display label for uploads).

### POST `/api/gallery/{image_id}/rotate`

**Function:** `gallery_rotate()` (line 487)
**Body (JSON):** `{"angle": 90}` (accepts 90, -90, 180, 270)
**Behavior:** Rotates image file on disk. Updates hash, dimensions.

### POST `/api/gallery/ai-upscale`

**Function:** `gallery_ai_upscale()` (line 544)
**Auth:** `require_privilege(request, "can_generate_images")`
**Parameters (multipart form):** `image`, `scale` (default 2)
**Behavior:** Sends to diffusion server's `/v1/images/upscale` endpoint.

### POST `/api/gallery/style-transfer`

**Function:** `gallery_style_transfer()` (line 588)
**Auth:** `require_privilege(request, "can_generate_images")`
**Parameters (multipart form):** `image`, `prompt`, `strength` (default 0.55)

### GET `/api/gallery/tags`

**Function:** `gallery_tags()` (line 635)
**Response:** `{"tags": ["landscape", "portrait", ...]}`

### GET `/api/gallery/library`

**Function:** `gallery_library()` (line 657)
**Query params:** `search`, `tag`, `model`, `album`, `favorites`, `sort` (`recent`/`oldest`/`shuffle`), `seed`, `offset`, `limit` (max 100)
**Response:** Items, total, total_tagged, tags, models.

### Album CRUD

- **GET** `/api/gallery/albums` -- `list_albums()` (line 796)
- **POST** `/api/gallery/albums` -- `create_album()` (line 834) -- body: `{"name": "...", "description": "..."}`
- **PUT** `/api/gallery/albums/{album_id}` -- `update_album()` (line 2127) -- body: `name`, `description`, `cover_id`
- **DELETE** `/api/gallery/albums/{album_id}` -- `delete_album()` (line 2148)
- **POST** `/api/gallery/albums/{album_id}/add` -- `add_to_album()` (line 2164) -- body: `{"image_ids": [...]}`
- **POST** `/api/gallery/albums/{album_id}/remove` -- `remove_from_album()` (line 2182) -- body: `{"image_ids": [...]}`

### GET `/api/gallery/stats`

**Function:** `gallery_stats()` (line 855)
**Response:** `{"total_photos": N, "total_size": bytes, "total_size_human": "1.2 GB", "favorites": N, "albums": N}`

### Image Editing Tools

#### POST `/api/image/inpaint`

**Function:** `inpaint_proxy()` (line 1241)
**Auth:** `require_privilege(request, "can_generate_images")`
**Body (JSON):** `image` (base64), `mask` (base64), `prompt`, `width`, `height`, `_endpoint`, `_model`
**Behavior:**
- OpenAI path: converts mask to alpha-channel format, uses `/v1/images/edits`, composites result
- Self-hosted path: tries `/v1/images/edits` (multipart), falls back to `/v1/images/inpaint` (JSON)
- Endpoint must be a registered visible endpoint (no raw URLs)

#### POST `/api/image/harmonize`

**Function:** `harmonize_image()` (line 1499)
**Body (JSON):** `image`, `prompt`, `strength`/`color_match`/`seam_fix`, `body_mask`, `seam_mask`, `_endpoint`, `_model`
**Behavior:** Real img2img -- tries `/v1/images/harmonize`, `/v1/images/img2img`, `/v1/images/variations`, `/sdapi/v1/img2img` in order. Refuses OpenAI (no img2img support).

#### POST `/api/image/sharpen`

**Function:** `sharpen_image()` (line 1699)
**Body (JSON):** `image` (base64), `amount` (0-100)
**Behavior:** PIL UnsharpMask filter. Returns `{"image": "base64..."}`

#### POST `/api/image/denoise`

**Function:** `denoise_image()` (line 1724)
**Body (JSON):** `image` (base64), `strength` (0.0-1.0)
**Behavior:** Real-ESRGAN `realesr-general-x4v3` at outscale=1.

#### POST `/api/image/upscale-local`

**Function:** `upscale_image_local()` (line 1775)
**Body (JSON):** `image` (base64), `scale` (2 or 4)
**Behavior:** Local Real-ESRGAN `RealESRGAN_x4plus` upscale. No diffusion server needed.

#### POST `/api/image/mask`

**Function:** `smart_mask()` (line 1821)
**Body (JSON):** `image` (base64), `points` (list of {x,y,label}), `box` ([x1,y1,x2,y2]), `text`/`query`
**Behavior:** SAM segmentation. If only text provided, first grounds via OWL-ViT to get bounding box.
**Response:** `{"mask": "base64...", "bbox": [x1,y1,x2,y2], "model": "...", "device": "..."}`

#### POST `/api/image/remove-bg`

**Function:** `remove_background()` (line 1950)
**Body (JSON):** `image` (base64), `hint_mask` (optional base64)
**Behavior:** Uses `rembg` or `briaai/RMBG-1.4` transformer pipeline. If hint_mask provided, crops to mask bbox first and constrains output.

#### POST `/api/image/enhance-face`

**Function:** `enhance_face()` (line 2043)
**Body (JSON):** `image` (base64)
**Behavior:** GFPGAN face restoration. Falls back to PIL-based enhancement (median filter + unsharp mask + contrast/color/brightness boost).

### POST `/api/gallery/{image_id}/favorite`

**Function:** `toggle_favorite()` (line 2203)
**Response:** `{"ok": true, "favorite": true}`

### POST `/api/gallery/{image_id}/ai-tag`

**Function:** `ai_tag_image()` (line 2217)
**Behavior:** Sends image to configured vision model for auto-tagging. Supports both Anthropic and OpenAI providers.
**Response:** `{"ok": true, "ai_tags": "landscape, sunset, mountains, ..."}`

### Tag Management

- **POST** `/api/gallery/clear-user-tags` (line 1032) -- wipes `tags` field on all user's images
- **POST** `/api/gallery/clear-ai-tags` (line 1053) -- wipes `ai_tags` field (optional `image_id` query param for single photo)
- **POST** `/api/gallery/dedupe-tags` (line 1084) -- removes user tags that duplicate AI tags

### POST `/api/gallery/download-zip`

**Function:** `gallery_download_zip()` (line 977)
**Body (JSON):** `{"ids": ["id1", "id2"]}`
**Response:** ZIP file download.

---

## 8. History Routes

**Source:** `routes/history/history_routes.py`
**Factory:** `setup_history_routes(session_manager, upload_handler=None)` (line 103)
**Router:** No prefix (paths include `/api/history` and `/api/session`)

Session history management -- pagination, message editing, forking, compaction.

### GET `/api/history/{session_id}`

**Function:** `get_session_history()` (line 178)
**Auth:** `_verify_session_owner(request, session_id)`
**Query params:** `limit` (1-100), `offset`
**Behavior:**
- With `limit`: paged DB query with total count, has_more_before/after
- Without `limit`: returns full in-memory history (falls back to DB if empty)
- Strips inline base64 images from display content
- Filters out hidden messages (compaction summaries)
- Hydrates in-memory session from DB if stale

**Response:**
```json
{
  "history": [...],
  "model": "gpt-4",
  "endpoint_url": "...",
  "name": "Session Name",
  "offset": 0,
  "limit": 50,
  "total": 200,
  "has_more_before": false,
  "has_more_after": true
}
```

### POST `/api/session/{session_id}/truncate`

**Function:** `truncate_session()` (line 295)
**Body (JSON):** `{"keep_count": 10}`
**Response:** `{"status": "ok", "kept": 10, "truncated": N}`

### POST `/api/session/{session_id}/message`

**Function:** `add_message()` (line 309)
**Body (JSON):** `role`, `content`, `metadata`
**Behavior:** Adds a message to the session. Used for slash command persistence.

### POST `/api/session/{session_id}/delete-messages`

**Function:** `delete_messages()` (line 327)
**Body (JSON):** `{"msg_ids": ["db-id-1", "db-id-2"]}` or `{"indices": [0, 1]}` (legacy)
**Behavior:** Deletes by DB ID (preferred) or by positional index (legacy). Updates in-memory and DB.

### POST `/api/session/{session_id}/edit-message`

**Function:** `edit_message()` (line 390)
**Body (JSON):** `{"msg_id": "db-id", "content": "new text"}`
**Behavior:** Edits content in DB and in-memory. Sets `edited: true` in metadata.

### POST `/api/session/{session_id}/mark-stopped`

**Function:** `mark_stopped()` (line 445)
**Behavior:** Adds `stopped: true` metadata to the last assistant message (in-memory + DB).

### POST `/api/session/{session_id}/update-last-meta`

**Function:** `update_last_meta()` (line 500)
**Body (JSON):** `{"metadata": {"key": "value"}}`
**Behavior:** Merges metadata into the last assistant message.

### POST `/api/session/{session_id}/merge-last-assistant`

**Function:** `merge_last_assistant()` (line 551)
**Body (JSON):** `{"separator": "\n\n"}`
**Behavior:** Merges the last two assistant messages into one (for "continue" flow). Removes the intervening "continue" user message. Updates both in-memory history and DB.

### POST `/api/session/{session_id}/fork`

**Function:** `fork_session()` (line 640)
**Body (JSON):** `{"keep_count": 10}`
**Behavior:** Creates a new session with messages copied up to `keep_count`. Inherits endpoint/model from source. Name prefix: `"⫝ "` (fork symbol).
**Response:** `{"status": "ok", "id": "new-uuid", "name": "...", "kept": 10}`

### GET `/api/conversations/topics`

**Function:** `get_conversation_topics()` (line 693)
**Auth:** `require_user(request)` -- owner-scoped
**Behavior:** Analyzes all sessions to extract conversation topics.

### GET `/api/session/{session_id}/context`

**Function:** `get_session_context_usage()` (line 702)
**Response:**
```json
{
  "session_id": "...",
  "model": "gpt-4",
  "used_tokens": 5000,
  "context_length": 128000,
  "context_percent": 3.9,
  "messages": 20,
  "context_messages": 22,
  "compacted_messages": 2,
  "can_compact": true,
  "should_compact": false,
  "auto_compact_threshold": 85
}
```

### POST `/api/session/{session_id}/compact`

**Function:** `compact_session()` (line 751)
**Behavior:**
- Requires at least 6 messages
- Keeps last 4 messages
- Summarizes older messages via utility/default LLM
- Inserts hidden system summary + visible "compacted" assistant message
- Updates DB accordingly

**Response:** `{"status": "ok", "message": "...", "before": 85.0, "after": 12.3}`

---

## 9. Memory Routes

**Source:** `routes/memory/memory_routes.py`
**Factory:** `setup_memory_routes(memory_manager, session_manager, memory_vector=None)` (line 54)
**Router prefix:** `/api/memory`

Personal knowledge base -- stores facts, preferences, contacts extracted from
conversations. Supports vector search via ChromaDB.

### POST `/api/memory/debug`

**Function:** `debug_memory_relevance()` (line 85)
**Parameters (form):** `query`
**Response:** Matching memories with relevance scores (threshold 0.05).

### POST `/api/memory/add`

**Function:** `api_add_memory()` (line 100)
**Auth:** `require_privilege(request, "can_manage_memory")`
**Body (JSON or form):** `text`, `category` (default "fact"), `source` (default "user"), `session_id` (optional)
**Behavior:** Deduplicates against existing memories. Syncs to vector index. Fires `memory_added` event.
**Response:** `{"ok": true, "count": N}`

### GET `/api/memory`

**Function:** `api_get_memory()` (line 148)
**Response:** `{"memory": [...]}`

### POST `/api/memory/search`

**Function:** `search_memories()` (line 154)
**Parameters (form):** `query`, `session_id` (optional), `category` (optional)
**Response:** `{"memories": [...], "total": N, "query": "..."}`

### GET `/api/memory/timeline`

**Function:** `memory_timeline()` (line 170)
**Response:** `{"timeline": [...], "total": N}` -- chronological with session names.

### GET `/api/memory/by-session/{session_id}`

**Function:** `get_memory_by_session()` (line 208)
**Auth:** Session ownership verified.
**Response:** Memories associated with a specific session.

### POST `/api/memory/extract`

**Function:** `extract_memory()` (line 238)
**Auth:** `require_user(request)`
**Parameters (form):** `session` (session ID)
**Behavior:** Sends full chat history to LLM for memory extraction.
**Response:** `{"suggestions": ["Alice lives at 123 Main St", ...]}`

### POST `/api/memory/audit`

**Function:** `api_audit_memories()` (line 288)
**Parameters (form):** `session` (optional)
**Behavior:** Deduplicates and consolidates memories via LLM. Caches tidy state so unchanged stores are skipped.
**Response:** `{"ok": true, "before": 50, "after": 42, "removed": 8, "already_tidy": false}`

### POST `/api/memory/import`

**Function:** `import_memories_from_file()` (line 339)
**Auth:** `require_privilege(request, "can_manage_memory")`
**Parameters (multipart form):** `file` (PDF, TXT, MD, CSV, etc.), `session` (optional)
**Behavior:**
- Supported types: .txt, .md, .pdf, .csv, .log, .json, .py, .js, .html
- .json files that look like a memories export round-trip without LLM
- Other files are sent to LLM for extraction
**Response:** `{"suggestions": [{"text": "...", "category": "fact"}, ...], "filename": "..."}`

### POST `/api/memory/{memory_id}/pin`

**Function:** `pin_memory()` (line 502)
**Parameters (form):** `pinned` (default true)
**Behavior:** Pinned memories are always included in context.

### GET `/api/memory/{memory_id}`

**Function:** `get_memory_item()` (line 516)
**Response:** `{"memory": {...}}`

### PUT `/api/memory/{memory_id}`

**Function:** `update_memory()` (line 527)
**Parameters (form):** `text`, `category` (optional)
**Behavior:** Updates text and timestamp. Syncs vector index (remove + re-add).

### DELETE `/api/memory/{memory_id}`

**Function:** `delete_memory()` (line 549)
**Behavior:** Removes from store and vector index.

---

## 10. Note Routes

**Source:** `routes/note/note_routes.py`
**Factory:** `setup_note_routes(task_scheduler=None, upload_handler=None)` (line 578)
**Router prefix:** `/api/notes`

Google Keep-style notes and checklists with reminders, labels, colors, and
sorting. Includes a multi-channel reminder dispatch system (browser, email,
ntfy, webhook).

### GET `/api/notes`

**Function:** `list_notes()` (line 623)
**Auth:** `require_user(request)` -- owner-scoped
**Query params:** `archived` (bool, optional), `label` (string, optional)
**Behavior:** Default: non-archived, sorted by pinned desc, sort_order asc, updated_at desc. Archived: sorted by updated_at desc.

### POST `/api/notes`

**Function:** `create_note()` (line 651)
**Body (JSON):** `NoteCreate` with fields: `title`, `content`, `items` (list), `note_type` ("note"/"checklist"), `color`, `label`, `pinned`, `due_date`, `source`, `session_id`, `image_url`, `repeat`, `sort_order`

### GET `/api/notes/{note_id}`

**Function:** `get_note()` (line 688)

### PUT `/api/notes/{note_id}`

**Function:** `update_note()` (line 705)
**Body (JSON):** `NoteUpdate` -- all fields optional. Includes `agent_session_id` for AI agent integration.

### DELETE `/api/notes/{note_id}`

**Function:** `delete_note()` (line 760)
**Behavior:** Hard delete from DB.

### POST `/api/notes/{note_id}/pin`

**Function:** `toggle_pin()` (line 779)
**Behavior:** Toggles `pinned` boolean.

### POST `/api/notes/{note_id}/archive`

**Function:** `toggle_archive()` (line 798)
**Behavior:** Toggles `archived` boolean.

### POST `/api/notes/{note_id}/items/{index}/toggle`

**Function:** `toggle_item()` (line 817)
**Behavior:** Toggles the `done` state of a checklist item at the given index.

### POST `/api/notes/fire-reminder`

**Function:** `fire_reminder()` (line 843)
**Auth:** `require_user(request)` -- gates against anonymous (LLM synthesis burns tokens)
**Body (JSON):** `note_id` (required); for test reminders (admin only): `title`, `body`, `channel`, `webhook_integration_id`, `webhook_payload_template`, `llm_synthesis`, `llm_persona`

**Behavior:** Calls `dispatch_reminder()` which:
1. Optionally generates an LLM synthesis line (warm sentence) using utility model
2. Sends via configured channel: browser (in-app notification queue), email (SMTP), ntfy, or webhook (Discord, etc.)
3. Deduplicates within 25-minute windows per note/channel

**Response:**
```json
{
  "channel": "email",
  "synthesis": "Time to check on that report!",
  "email_sent": true,
  "email_error": "",
  "ntfy_sent": false,
  "ntfy_error": "",
  "webhook_sent": false,
  "webhook_error": "",
  "browser_sent": true
}
```

### POST `/api/notes/reorder`

**Function:** `reorder_notes()` (line 901)
**Body (JSON):** `{"ids": ["note-id-1", "note-id-2", ...]}`
**Behavior:** Updates `sort_order` for each note in the order provided. Owner-scoped.

---

## 11. Research Routes

**Source:** `routes/research/research_routes.py`
**Factory:** `setup_research_routes(research_handler, session_manager=None)` (line 209)
**Router:** No prefix (paths include `/api/research`)

Deep research / multi-round web investigation system. Runs background tasks
that iteratively search, extract, and synthesize. Results are persisted as
JSON files in the `DEEP_RESEARCH_DIR`.

### POST `/api/research/start`

**Function:** `research_start()` (line 492)
**Auth:** `require_privilege(request, "can_use_research")`
**Body (JSON):** `ResearchStartRequest`:
- `query` (required)
- `max_rounds` (0 = auto, up to 20)
- `search_provider` (optional)
- `endpoint_id` (optional -- specific registered endpoint)
- `model` (optional)
- `max_time` (60-1800, default 300)
- `extraction_timeout` (15-3600, optional)
- `extraction_concurrency` (1-12, optional)
- `category` (optional)

**Behavior:** Launches async research job. Endpoint resolution chain: explicit endpoint_id > research > utility > default > chat > first enabled.
**Response:** `{"session_id": "rp-abc123", "status": "running", "query": "..."}`

### GET `/api/research/active`

**Function:** `research_active()` (line 259)
**Response:** List of currently running research tasks (owner-filtered).

### GET `/api/research/status/{session_id}`

**Function:** `research_status()` (line 278)
**Response:** Current status and progress of a research task.

### POST `/api/research/cancel/{session_id}`

**Function:** `research_cancel()` (line 289)
**Response:** `{"cancelled": true}`

### POST `/api/research/result/{session_id}`

**Function:** `research_result()` (line 298)
**Behavior:** Returns result and clears it from in-memory state.
**Response:** `{"result": "...", "sources": [...], "raw_findings": [...]}`

### POST `/api/research/result-peek/{session_id}`

**Function:** `research_result_peek()` (line 613)
**Behavior:** Returns result without clearing (for panel use). Falls back to disk.

### GET `/api/research/report/{session_id}`

**Function:** `research_report()` (line 323)
**Response:** Full HTML visual report (HTMLResponse).

### POST `/api/research/{session_id}/hide-image`

**Function:** `research_hide_image()` (line 343)
**Body (JSON):** `{"url": "https://..."}`
**Behavior:** Marks an image URL as hidden in the visual report.

### POST `/api/research/{session_id}/unhide-images`

**Function:** `research_unhide_images()` (line 355)
**Behavior:** Clears all hidden images.

### GET `/api/research/library`

**Function:** `research_library()` (line 366)
**Query params:** `search`, `sort` (`recent`/`oldest`/`most-messages`/`alpha`), `limit` (default 50), `archived`
**Response:** `{"research": [...], "total": N}`

### GET `/api/research/detail/{session_id}`

**Function:** `research_detail()` (line 421)
**Response:** Full JSON of a single research result.

### POST `/api/research/{session_id}/archive`

**Function:** `research_archive()` (line 437)
**Query params:** `archived` (default true)

### DELETE `/api/research/{session_id}`

**Function:** `research_delete()` (line 455)
**Behavior:** Deletes the research JSON file from disk.

### GET `/api/research/stream/{session_id}`

**Function:** `research_stream()` (line 579)
**Response:** Server-Sent Events (SSE) stream of progress updates. Polls every 1.5s. Final event includes `{"status": "done", "final": true}` or error.

### POST `/api/research/spinoff/{session_id}`

**Function:** `research_spinoff()` (line 635)
**Behavior:** Creates a new chat session pre-seeded with the research report as system context. Inherits endpoint/model from the research or resolves through the chain.
**Response:** `{"session_id": "uuid", "name": "Follow-up: ...", "source_count": N}`

---

## 12. Search Routes

**Source:** `routes/search/search_routes.py`
**Factory:** `setup_search_routes(config)` (line 39)
**Router:** No prefix (paths include `/api/search`)

Web search integration supporting multiple providers (SearXNG, DuckDuckGo,
Brave, Google, Bing, etc.).

### GET `/api/search/config`

**Function:** `get_search_settings()` (line 42)
**Auth:** None
**Response:** Current search configuration.

### POST `/api/search`

**Function:** `do_web_search()` (line 46)
**Auth:** None
**Parameters (JSON, form, or query params):** `query`/`q`, `time_filter`/`freshness` (optional)
**Behavior:** Comprehensive web search using the configured provider. Returns context string + source list.
**Response:** `{"context": "...", "sources": [...]}`

### GET `/api/search/providers`

**Function:** `list_search_providers()` (line 68)
**Auth:** None
**Response:** Array of provider objects with id, label, and availability status.

### POST `/api/search/query`

**Function:** `search_with_provider()` (line 87)
**Parameters (JSON, form, or query params):** `query`/`q`, `provider`, `count`/`limit` (max 20)
**Response:** `{"results": [...], "provider": "searxng", "time": 0.45}`

---

## 13. Vault Routes

**Source:** `routes/vault/vault_routes.py`
**Factory:** `setup_vault_routes()` (line 126)
**Router prefix:** `/api/vault`

Vaultwarden / Bitwarden CLI integration for password management. Stores
the BW_SESSION key in `data/vault.json` with restrictive file permissions
(0600 on POSIX).

### GET `/api/vault/config`

**Function:** `get_config()` (line 129)
**Auth:** `require_admin(request)`
**Response:**
```json
{
  "server_url": "https://vault.example.com",
  "email": "user@example.com",
  "unlocked": true,
  "unlocked_at": "2024-01-15T10:30:00",
  "bw_installed": true
}
```

### POST `/api/vault/config`

**Function:** `save_config()` (line 143)
**Auth:** `require_admin(request)`
**Body (JSON):** `server_url`, `email`
**Behavior:** Saves URL/email and runs `bw config server` to point at the Vaultwarden instance.

### POST `/api/vault/login`

**Function:** `login()` (line 159)
**Auth:** `require_admin(request)`
**Body (JSON):** `email`, `master_password`
**Behavior:** Runs `bw login <email> --raw` with master password on stdin. Saves session key on success.
**Security:** Master password is passed via stdin, not argv (argv is visible via `ps`/`/proc`).

### POST `/api/vault/unlock`

**Function:** `unlock()` (line 183)
**Auth:** `require_admin(request)`
**Body (JSON):** `master_password`
**Behavior:** Runs `bw unlock --raw` with master password on stdin. Saves session key.
**Response:** `{"ok": true, "message": "Vault unlocked"}`

### POST `/api/vault/lock`

**Function:** `lock()` (line 205)
**Auth:** `require_admin(request)`
**Behavior:** Clears session from config, runs `bw lock`.

### POST `/api/vault/logout`

**Function:** `logout()` (line 217)
**Auth:** `require_admin(request)`
**Behavior:** Runs `bw logout`, clears session/email/unlocked_at from config.

---

## 14. Webhook Routes

**Source:** `routes/webhook/webhook_routes.py`
**Factory:** `setup_webhook_routes(webhook_manager, auth_manager, session_manager=None, api_key_manager=None)` (line 64)
**Router prefix:** `/api`

Webhook management and a synchronous chat API endpoint for external
integrations (n8n, Make, Activepieces).

### GET `/api/webhooks`

**Function:** `list_webhooks()` (line 71)
**Auth:** `require_admin(request)`
**Response:** Array of webhook objects with id, name, url, events, status, last trigger info.

### POST `/api/webhooks`

**Function:** `create_webhook()` (line 95)
**Auth:** `require_admin(request)`
**Parameters (form):** `name` (max 100), `url` (max 2048, validated), `secret` (max 256, encrypted at rest), `events` (comma-separated)
**Response:** `{"id": "abc12345", "name": "My Webhook"}`

### POST `/api/webhooks/{webhook_id}/test`

**Function:** `test_webhook()` (line 141)
**Auth:** `require_admin(request)`
**Behavior:** Sends a test delivery via the webhook manager.

### PATCH `/api/webhooks/{webhook_id}`

**Function:** `toggle_webhook()` (line 156)
**Auth:** `require_admin(request)`
**Behavior:** Toggles `is_active` boolean.
**Response:** `{"id": "abc12345", "is_active": false}`

### DELETE `/api/webhooks/{webhook_id}`

**Function:** `delete_webhook()` (line 170)
**Auth:** `require_admin(request)`

### POST `/api/v1/chat`

**Function:** `sync_chat()` (line 237)
**Auth:** API Token required (`request.state.api_token`), must have `chat` scope
**Body (JSON):** `SyncChatRequest`:
- `message` (required, max 32000 chars)
- `model` (optional, max 200)
- `session` (optional, max 100 -- resume existing session)
- `api_key` (optional, max 256 -- direct provider key)
- `base_url` (optional, max 2048 -- direct provider URL)
- `provider` (optional, max 50 -- auto-resolve URL)

**Behavior -- three resolution paths:**

1. **Resume session:** If `session` ID provided, gets existing session. Strict ownership verification.
2. **Direct API key:** If `api_key` provided, creates ephemeral session. Auto-resolves provider URL from model name or explicit `provider`/`base_url`. Validates base_url against SSRF.
3. **Fallback endpoint:** Uses first enabled `ModelEndpoint` from DB (owner-scoped). Auto-discovers model list if `model` is "auto".

After resolution, sends the message via `llm_call_async()`, stores in session, and fires `chat.completed` webhook.

**Known provider auto-resolution:**
deepseek, openai, mistral, groq, together, openrouter, ollama, fireworks, venice, kimi-code

**Response:**
```json
{
  "response": "The assistant's reply...",
  "session_id": "uuid",
  "model": "deepseek-chat"
}
```

---

## Security Notes

All routes follow these security patterns:

1. **Owner scoping:** Queries filter by `owner` to prevent cross-tenant data access. Null-owner rows from legacy/migration are handled explicitly.
2. **404 not 403:** Ownership failures return 404 ("not found") instead of 403 to avoid leaking resource existence.
3. **SSRF protection:** Outbound URLs are validated via `src.url_safety.check_outbound_url()`. Cloud metadata addresses (169.254.x.x) are always blocked.
4. **Upload path traversal:** Upload paths are resolved and checked to stay within allowed directories via `os.path.commonpath()`.
5. **Secret encryption:** Passwords, API keys, and webhook secrets are encrypted at rest via `src.secret_storage` / Fernet.
6. **Input limits:** Upload sizes, string lengths, and pagination limits are bounded.
