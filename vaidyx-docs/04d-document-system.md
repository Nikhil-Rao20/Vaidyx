# Vaidyx Document System

The document system is a multi-document tabbed editor panel that runs alongside chat.
It spans three files totaling ~15,100 lines: `document.js` (11,200), `documentLibrary.js` (3,422),
and `fileHandler.js` (483).

---

## 1. Architecture Overview

### document.js -- Structure by Line Range

| Lines        | Subsystem                        | Description                                                |
|--------------|----------------------------------|------------------------------------------------------------|
| 1--120       | Module setup, imports, state     | Debounce timers, diff state, language detection config      |
| 120--200     | Multi-document state             | `docs` Map (docId -> metadata), session persistence keys    |
| 200--550     | Tab bar                          | Rendering, scroll arrows, drag-to-reorder, swipe-dismiss    |
| 550--930     | PDF form export modal            | AcroForm field rendering, signature/date helpers, download   |
| 930--1000    | Annotation serialization         | Markdown-embedded `<!-- annotation -->` comment format       |
| 1000--1970   | PDF annotation pane              | Page renderer, drag/resize/delete annotations, auto-save     |
| 1970--2050   | Header bar and action sync       | Toolbar visibility based on doc language                     |
| 2050--3800   | Email composer                   | Header parsing, rich body, recipient autocomplete, attachments|
| 3800--4070   | Email send/draft/discard         | SMTP send, draft save, discard cleanup                       |
| 4070--4460   | AI email reply and schedule-send | AI draft generation, scheduled send modal                    |
| 4465--4700   | Document switching and auto-create| `switchToDoc`, `closeTab`, `_autoCreateFromInput`           |
| 4700--5220   | Panel open/close                 | DOM construction, divider drag-to-resize, animation          |
| 5220--5780   | Language picker and font settings| Custom dropdown, monospace/proportional/serif font toggle     |
| 5780--5930   | Version history sidebar          | Fetch versions, build diff summaries                         |
| 5930--6110   | Find bar (Ctrl+F)                | In-document search with highlight overlays                   |
| 6110--6500   | Markdown formatting toolbar      | Bold, italic, headings, lists, links, code blocks            |
| 6500--6830   | Action overflow menu             | Context-sensitive actions, toolbar responsiveness             |
| 6830--6900   | Divider drag-to-resize           | Pointer-based panel width adjustment                         |
| 6900--7000   | closePanel / swapSide            | Panel teardown, left/right toggle                            |
| 7000--7100   | createDocument / newDocument     | POST to API, inject into tabs                                |
| 7100--7230   | Email reply body replacement     | Streaming AI reply into email draft                          |
| 7230--7420   | loadDocument / loadSessionDocs   | GET from API, populate editor, restore state                 |
| 7420--7800   | Syntax highlighting, line numbers| hljs integration, gutter rendering, resize observer           |
| 7800--7900   | Language auto-detection          | hljs auto-detect with relevance threshold (min 8)            |
| 7900--8200   | Selection state tracking         | Multi-cursor highlight overlays via mirror element            |
| 8200--8860   | Suggestion system and diff mode  | Inline suggestions, accept/dismiss, chunk-level diff viewer   |
| 8860--9160   | Run document, copy, tab menu     | Code execution, clipboard, per-tab dropdown menu              |
| 9160--9400   | Signed email reply               | Prepare + send PGP-signed reply via document content          |
| 9400--9530   | saveDocument                     | PUT to API with optional `force_version`                      |
| 9530--9700   | Export (raw, HTML, PDF, DOCX)    | Client-side export via html2pdf and docx libraries            |
| 9700--9870   | Import from device               | File picker, PDF vs text routing                              |
| 9870--10100  | Fullscreen, markdown preview     | Toggle fullscreen, markdown-to-HTML preview pane              |
| 10100--10300 | CSV preview and HTML preview     | Editable table view, sandboxed iframe for HTML/SVG            |
| 10300--10570 | Streaming (AI writes docs)       | `streamDocOpen`, `streamDocDelta`, `streamDocFinalize`        |
| 10570--10835 | handleDocUpdate                  | WebSocket-driven doc mutations from AI agent                  |
| 10835--11030 | Version history panel            | Load, preview, restore versions                               |
| 11030--11200 | Title/language update, exports   | PATCH title, PUT language, module export                       |

### Core Data Structure

```
docs: Map<docId, {
  id, title, language, content, version,
  sessionId, userSetLanguage,
  _composeAtts,              // email compose attachments
  sourceEmailUid,            // provenance for signed-reply flow
  sourceEmailFolder,
  sourceEmailAccountId,
  sourceEmailMessageId
}>
```

### Module Dependencies

```
document.js
  imports: ui, sessions, emojiPicker, markdown, codeRunner,
           langIcons, spinner, documentLibrary, signature,
           modalManager, escMenuStack

documentLibrary.js
  imports: toolWindowZOrder, ui, sessions, spinner, markdown,
           windowDrag, langIcons, escMenuStack

fileHandler.js
  imports: ui, spinner
```

---

## 2. Document Viewer/Editor

The editor is a dual-surface design:

- **Textarea** (`#doc-editor-textarea`) -- the editable input surface
- **Code overlay** (`#doc-editor-code`) -- an hljs-highlighted `<code>` element layered behind the textarea with transparent background, providing syntax coloring

### Editing Modes

| Mode              | Trigger                              | Surface                          |
|-------------------|--------------------------------------|----------------------------------|
| Code edit         | Default for code languages           | Textarea with syntax overlay     |
| Markdown edit     | language=markdown                    | Textarea with markdown highlighting |
| Markdown preview  | Toggle button or triple-click hint   | Rendered HTML in `#doc-md-preview` |
| CSV table         | language=csv, "View" toggle          | Editable HTML table synced to textarea |
| HTML/SVG preview  | language=html/svg, "Preview" toggle  | Sandboxed iframe                 |
| PDF form view     | Form-backed PDF documents            | Page images with overlay inputs  |
| Email compose     | language=email                       | Header fields + rich body editor |
| Diff mode         | AI suggestions or version compare    | Side-by-side chunk diff overlay  |

### Key Editor Features

- **Auto-save**: 2-second debounce after typing (line ~7066)
- **Auto-detect language**: Uses hljs with minimum relevance score of 8 (line ~7810)
- **Auto-title**: Derives title from first meaningful line of content (line ~11048)
- **Line numbers**: Custom gutter with resize-observer-driven re-measurement (line ~7752)
- **Find bar**: Ctrl+F in-document search with match highlighting (line ~5930)
- **Markdown toolbar**: Bold, italic, headings (H1-H4), lists, links, code (line ~6565)
- **Font toggle**: Monospace, proportional, or serif via `_applyDocFont` (line ~5722)

---

## 3. Document Types and Languages

### Supported Languages (Language Picker)

python, javascript, typescript, html, css, markdown, json, yaml, bash, sql,
rust, go, java, c, cpp, csv, ruby, php, xml, toml, ini, text, email, svg

### Special Document Types

| Type             | Detection                                   | Behavior                                      |
|------------------|---------------------------------------------|-----------------------------------------------|
| **PDF form**     | `<!-- pdf_form_source upload_id="..." -->`   | Renders page images with overlay inputs       |
| **Plain PDF**    | `<!-- pdf_source upload_id="..." -->`        | Renders page images, text extraction          |
| **Email**        | `language === 'email'`                      | Shows To/Cc/Bcc/Subject fields, rich body     |
| **CSV**          | `language === 'csv'`                        | Offers editable table "View" toggle           |
| **HTML/SVG/XML** | `_isRenderLang(lang)`                       | Offers sandboxed iframe "Preview" toggle      |
| **Runnable code**| Python, JS, Bash, etc.                      | "Run" button via codeRunner module            |

### File Import Extension Mapping

```
.py -> python    .js -> javascript    .ts -> typescript
.html -> html    .css -> css          .md -> markdown
.json -> json    .yml -> yaml         .sh -> bash
.sql -> sql      .rs -> rust          .go -> go
.java -> java    .c -> c              .cpp -> cpp
.rb -> ruby      .php -> php          .xml -> xml
.csv -> csv      .xlsx -> csv (per-sheet split)
.docx -> markdown (via mammoth)       .pdf -> dedicated import-pdf endpoint
```

---

## 4. Document Library (documentLibrary.js)

### Library Tabs

The library is a full-screen modal (`#doclib-modal`) with four tabs:

| Tab          | Content                              | Data Source                          |
|--------------|--------------------------------------|--------------------------------------|
| **Chats**    | All active chat sessions             | `GET /api/sessions`                  |
| **Documents**| All documents across sessions        | `GET /api/documents/library`         |
| **Research** | Deep-research reports                | `GET /api/research/library`          |
| **Archive**  | Archived chats + docs + research     | Multiple endpoints with `archived=true` |

### Documents Tab Features

- **Search**: Debounced text search across title and content
- **Language filter chips**: Click to filter by language
- **Sort**: Recent, oldest, alphabetical
- **Pagination**: 20-at-a-time reveal with infinite scroll and server pagination (limit=50)
- **Select mode**: Bulk operations on multiple documents
- **Bulk actions**: Delete, archive, clone, export as ZIP
- **Card preview**: Expand card inline to read document content
- **PDF card preview**: Renders PDF pages in an iframe within the card
- **Import**: File picker for importing from device

### Library State Variables

```
_libraryDocs       -- fetched document list
_libraryTotal      -- total count from server
_libraryOffset     -- pagination offset
_docsVisibleLimit  -- client-side chunked reveal (20 at a time)
_libraryLanguages  -- {language: count} map for filter chips
_librarySort       -- 'recent' | 'oldest' | 'alpha'
_librarySearch     -- current search query
_librarySelectMode -- bulk selection active
_librarySelectedIds -- Set of selected doc IDs
```

---

## 5. File Handling (fileHandler.js)

### Upload Flow

1. User adds files via picker (`openPicker`) or drag-drop
2. Files stored in `pendingFiles` array (max 10)
3. Mobile images offer a crop dialog (`_openMobileCropper`)
4. `renderAttachStrip()` shows chips (1-3 files) or collapsed badge (4+)
5. `uploadPending()` POSTs `FormData` to `/api/upload`
6. Per-chip spinner overlays during upload
7. Upload has 120-second timeout with AbortController
8. On success, returns array of file IDs; on failure, files remain for retry

### Key Functions

| Function             | Line | Purpose                                      |
|----------------------|------|----------------------------------------------|
| `init(apiBase)`      | 173  | Set API base URL                             |
| `openPicker()`       | 180  | Trigger hidden file input click              |
| `addFiles(files)`    | 359  | Add to pending with optional mobile crop     |
| `renderAttachStrip()`| 189  | Render attachment chips in strip             |
| `uploadPending()`    | 270  | POST files to server, return IDs             |
| `removePending(idx)` | 260  | Remove single pending file                   |
| `clearPending()`     | 436  | Remove all pending files                     |
| `cancelUpload()`     | 456  | Abort in-flight upload                       |
| `getPendingCount()`  | 407  | Return pending file count                    |
| `getPendingInfo()`   | 421  | Return file metadata with preview URLs       |
| `getLastUploadedMeta`| 444  | Full metadata including width/height         |

---

## 6. API Endpoints

### Document CRUD

| Method | Endpoint                                    | Used In           | Purpose                        |
|--------|---------------------------------------------|--------------------|--------------------------------|
| POST   | `/api/document`                             | createDocument     | Create new document            |
| GET    | `/api/document/{id}`                        | loadDocument       | Fetch single document          |
| PUT    | `/api/document/{id}`                        | saveDocument       | Update content (+ version)     |
| PATCH  | `/api/document/{id}`                        | updateTitle        | Update title or language       |
| DELETE | `/api/document/{id}`                        | deleteActiveDocument| Delete document               |
| GET    | `/api/documents/{sessionId}`                | loadSessionDocs    | All docs for a session         |

### Document Library

| Method | Endpoint                                    | Purpose                                |
|--------|---------------------------------------------|----------------------------------------|
| GET    | `/api/documents/library`                    | Paginated list with search/filter/sort |
| POST   | `/api/documents/import-pdf`                 | Import PDF (handles AcroForm)          |
| POST   | `/api/documents/export-zip`                 | Bulk export selected docs as ZIP       |

### Version History

| Method | Endpoint                                    | Purpose                         |
|--------|---------------------------------------------|---------------------------------|
| GET    | `/api/document/{id}/versions`               | List all versions               |
| GET    | `/api/document/{id}/version/{num}`          | Get specific version content    |
| POST   | `/api/document/{id}/restore/{num}`          | Restore old version (new ver)   |

### PDF Operations

| Method | Endpoint                                    | Purpose                              |
|--------|---------------------------------------------|--------------------------------------|
| GET    | `/api/document/{id}/render-pages`           | Get page data for PDF view           |
| GET    | `/api/document/{id}/page/{n}.png`           | Rendered page image                  |
| GET    | `/api/document/{id}/export-pdf`             | Download filled PDF (GET = direct)   |
| POST   | `/api/document/{id}/export-pdf`             | Download filled PDF with overrides   |
| POST   | `/api/document/{id}/export-pdf/preview`     | Preview field values before export   |
| POST   | `/api/document/{id}/extract-pdf-text`       | OCR/extract text from PDF            |
| POST   | `/api/document/{id}/ai-fill-annotations`    | AI-proposed annotations              |
| GET    | `/api/document/{id}/render-pdf`             | Render PDF for library card preview  |

### Document Archive

| Method | Endpoint                                    | Purpose                         |
|--------|---------------------------------------------|---------------------------------|
| POST   | `/api/document/{id}/archive?archived=bool`  | Archive or unarchive            |

### Email (used by document email composer)

| Method | Endpoint                                    | Purpose                             |
|--------|---------------------------------------------|-------------------------------------|
| GET    | `/api/email/accounts`                       | List configured email accounts      |
| POST   | `/api/email/send`                           | Send composed email                 |
| POST   | `/api/email/draft`                          | Save email as IMAP draft            |
| POST   | `/api/email/schedule`                       | Schedule email for later sending    |
| POST   | `/api/email/ai-reply`                       | Generate AI reply draft             |
| POST   | `/api/email/compose-upload`                 | Upload compose attachment           |
| DELETE | `/api/email/compose-upload/{token}`         | Remove compose attachment           |
| POST   | `/api/email/compose-from-attachment/{uid}/{idx}` | Stage forwarded attachment    |
| POST   | `/api/email/compose-from-vaidyx`          | Attach Vaidyx doc/gallery item    |
| POST   | `/api/email/compose-from-vaidyx-zip`      | Attach multiple items as ZIP        |
| POST   | `/api/email/mark-answered/{uid}`            | Mark original as answered           |
| POST   | `/api/email/mark-unread/{uid}`              | Mark email as unread                |
| GET    | `/api/email/attachment/{uid}/{idx}`         | Download email attachment           |
| POST   | `/api/email/attachment-as-doc/{uid}/{idx}`  | Convert attachment to document      |
| GET    | `/api/contacts/search`                      | Recipient autocomplete              |
| POST   | `/api/contacts/add`                         | Save new contact after send         |

### Other Endpoints Used

| Method | Endpoint                                    | Purpose                         |
|--------|---------------------------------------------|---------------------------------|
| POST   | `/api/upload`                               | File upload (fileHandler.js)    |
| POST   | `/api/session`                              | Auto-create chat session        |
| GET    | `/api/sessions`                             | List sessions (library chats)   |
| GET    | `/api/history/{sessionId}`                  | Chat history (library copy)     |
| GET    | `/api/signatures`                           | List saved signatures           |
| POST   | `/api/document/{id}/prepare-signed-reply`   | Prepare PGP-signed reply        |

---

## 7. Key Functions Reference

### document.js -- Core Lifecycle

| Function                  | Line  | Purpose                                          |
|---------------------------|-------|--------------------------------------------------|
| `init(apiBase)`           | 154   | Initialize module, wire library, hash listener   |
| `openPanel()`             | 4757  | Build and mount editor pane DOM                  |
| `closePanel(direction)`   | 6894  | Teardown pane with slide animation               |
| `createDocument(sid)`     | 7025  | POST new doc, add to tabs, open panel            |
| `newDocument()`           | 7014  | Create doc in current or new session             |
| `loadDocument(docId)`     | 7236  | GET doc by ID, add to tabs, switch               |
| `loadSessionDocs(sid)`    | 7321  | Load all docs for a session into tabs            |
| `switchToDoc(docId)`      | 4465  | Save current, populate editor with target doc    |
| `saveDocument(opts)`      | 9403  | PUT content to server, update version badge      |
| `addDocToTabs(doc, sid)`  | 7388  | Insert doc metadata into `docs` Map              |
| `populateEditor(doc)`     | 7409  | Set textarea, title, language, version badge     |
| `injectFreshDoc(doc)`     | 7084  | Insert doc from POST response without re-fetch   |
| `handleDocUpdate(data)`   | 10573 | Process AI-driven doc mutations via WebSocket    |
| `clearAll()`              | 11115 | Clear all docs and close panel                   |

### document.js -- Streaming

| Function                  | Line  | Purpose                                          |
|---------------------------|-------|--------------------------------------------------|
| `streamDocOpen(title,lang)` | 10302 | Open panel for incoming AI-streamed doc        |
| `streamDocDelta(content)` | 10478 | Append streamed content with cursor animation    |
| `streamDocFinalize()`     | 10514 | Finalize stream, persist to server               |

### document.js -- PDF System

| Function                  | Line  | Purpose                                          |
|---------------------------|-------|--------------------------------------------------|
| `_renderPdfPane()`        | 1149  | Fetch pages, render images + form field overlays |
| `_buildAnnotation()`      | 1390  | Create draggable/resizable annotation element    |
| `_savePdfPaneToMarkdown()`| 1879  | Sync form values + annotations back to markdown  |
| `_aiFillAnnotations()`    | 1781  | AI-proposed annotations via vision pipeline      |
| `_downloadFilledPdf()`    | 616   | Direct PDF export download                       |
| `_openExportPdfModal()`   | 672   | Modal with field review before export            |

### document.js -- Diff and Suggestions

| Function                  | Line  | Purpose                                          |
|---------------------------|-------|--------------------------------------------------|
| `enterDiffMode(old,new)`  | 8574  | Activate chunk-level diff overlay                |
| `exitDiffMode(discard)`   | 8853  | Leave diff mode, apply or discard changes        |
| `handleDocSuggestions()`  | 8250  | Process AI find-replace suggestions              |
| `acceptSuggestion(id)`    | 8971  | Apply a single suggestion                        |
| `dismissSuggestion(id)`   | 8999  | Reject a single suggestion                       |

### document.js -- Email Composer

| Function                  | Line  | Purpose                                          |
|---------------------------|-------|--------------------------------------------------|
| `_showEmailFields(doc)`   | 2897  | Render To/Cc/Bcc/Subject + rich body             |
| `_sendEmail()`            | 3853  | Validate, POST to /api/email/send                |
| `_saveDraft()`            | 4006  | Save as IMAP draft                               |
| `_aiReply(opts)`          | 4212  | Request AI-generated reply                       |
| `_scheduleSend()`         | 4309  | Schedule email for future delivery               |

### documentLibrary.js

| Function                  | Line  | Purpose                                          |
|---------------------------|-------|--------------------------------------------------|
| `openLibrary(opts)`       | 1573  | Build and show library modal                     |
| `closeLibrary()`          | exported | Remove modal from DOM                          |
| `libraryFetch(append)`    | 316   | GET /api/documents/library with params           |
| `libraryCreateCard(doc)`  | 519   | Build a document card element                    |
| `libraryExpandCard()`     | 874   | Inline content preview with reader view          |
| `libraryImportFiles()`    | 1478  | Import files (PDF, XLSX, text) into library      |
| `libraryDeleteSingle()`   | 1184  | DELETE single document                           |
| `libraryBulkDelete()`     | 1210  | DELETE multiple selected documents               |
| `libraryBulkArchive()`    | 1255  | Archive multiple selected documents              |
| `libraryBulkExport()`     | 1299  | Export selected as ZIP                           |
| `readFileContent(file)`   | 1443  | Read file as text/CSV/markdown (XLSX, DOCX)      |

---

## 8. Design Patterns

### State Persistence

- **Session-scoped tabs**: Documents filtered by current session ID; switching sessions clears other session's tabs
- **LocalStorage keys**: `vaidyx-doc-open-{sid}` and `vaidyx-doc-minimized-{sid}` track panel state per session
- **Email local drafts**: Reply drafts saved to localStorage under `vaidyx.email.replyDraft.v1:` prefix, restored on reopen

### Streaming Architecture

The AI agent can create/edit documents in real-time via three functions:
1. `streamDocOpen` -- creates a temporary doc with `_streaming_` prefix ID
2. `streamDocDelta` -- updates content progressively with cursor animation
3. `streamDocFinalize` -- persists the final content to the server, replaces temp ID with real ID

### PDF Annotation Storage

Annotations are embedded in the document's markdown content as HTML comments:
```markdown
## Annotations
- value text <!-- annotation id=ann-xxx page=1 x=10.00 y=20.00 w=8.00 h=2.50 kind=text lh=1.30 -->
```

Three annotation kinds: `text` (textarea), `check` (SVG checkmark), `signature` (signature picker).

### Auto-save Pipeline

1. User types in textarea -> `input` event fires
2. Debounce timer set to 2 seconds (`_autoSaveDebounce`)
3. On timer: `saveDocument({ silent: true })` -> PUT `/api/document/{id}`
4. PDF pane uses separate 600ms debounce (`_schedulePdfPaneSave`)
5. `beforeunload` event flushes any pending PDF pane save with `keepalive: true`
