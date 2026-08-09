# Odysseus Email System

Deep-dive into the client-side email subsystem: library popup, sidebar inbox,
reply recipients, signature folding, state management, and all API endpoints.

Source files (all under `static/js/`):

| File | Lines | Role |
|------|-------|------|
| `emailLibrary.js` | 8504 | Full email library popup modal |
| `emailInbox.js` | 1417 | Sidebar inbox list |
| `emailShared.js` | 19 | Shared URL helpers |
| `emailLibrary/replyRecipients.js` | 27 | Reply-all CC builder |
| `emailLibrary/signatureFold.js` | 340 | Signature and quote folding |
| `emailLibrary/state.js` | 35 | Shared mutable state object |
| `emailLibrary/utils.js` | 249 | Pure helpers (sanitizer, formatters) |
| `signature.js` | 524 | Drawing-pad signature capture |

---

## 1. Email System Architecture

The email frontend is split into two views that share state and utilities:

```
emailShared.js          -- emailApiUrl(), emailAccountQuery()
       |
       +----> emailInbox.js       (sidebar list)
       +----> emailLibrary.js     (popup modal)
                |
                +-- emailLibrary/state.js           (shared state object)
                +-- emailLibrary/utils.js            (sanitizer, formatters)
                +-- emailLibrary/signatureFold.js    (quote & sig folding)
                +-- emailLibrary/replyRecipients.js  (reply-all CC logic)
```

**emailInbox.js** renders a compact email list in the sidebar. Clicking the
section header or an email opens the full **emailLibrary.js** popup modal.
The inbox handles reply drafts, AI replies, archive, delete, and reminders.

**emailLibrary.js** is the primary email interface -- an 8500-line modal that
provides email reading, composing, searching, filtering, multi-account
management, settings, unsubscribe tooling, attachment viewing, AI
summarization, translation, and bulk operations.

### Multi-Account Support

Accounts are loaded from `/api/email/accounts`. The active account ID is
stored in `state._libAccountId` and published globally via
`window.__odysseusActiveEmailAccount`. Every API call appends
`&account_id=...` through the `_acct()` helper or `emailApiUrl()`.

### Desktop/Mobile Layout

On desktop (>768px), when a reply draft opens, the email modal docks to the
left edge with the document editor beside it (`email-doc-split-active` class,
CSS custom properties `--email-doc-split-*`). On mobile, the document panel
slides over the email; swiping it down reveals the email underneath.

---

## 2. Email Library (emailLibrary.js)

### Initialization and Lifecycle

- `initEmailLibrary(config)` (line 2287) -- stores `documentModule` and
  `onEmailClick` callback in shared state.
- `openEmailLibrary(opts)` (line 2294) -- creates the modal DOM, loads
  accounts, folders, and emails. Supports deep-linking via `opts.folder`
  and `opts.uid`.
- `closeEmailLibrary()` (line 3123) -- removes modal, clears split layout,
  restores sidebar.
- `prewarmEmailLibrary({ delay })` (line 2091) -- background prewarm that
  fetches accounts, folders, and the first page of INBOX for each account
  before the user opens the library.
- `prewarmUnreadEmails({ limit, maxUid })` (line 2129) -- lighter prewarm
  that caches only unread emails.

### Email Loading and Caching (SWR Pattern)

`_loadEmails()` (line 4471) implements stale-while-revalidate:

1. Check client-side cache (`_libCacheGet`) for the current
   account+folder+filter combo.
2. If cached, paint immediately and optionally refetch in background.
3. If not cached, try a fast `cached_only=1` request (450ms timeout).
4. Fall back to the full IMAP fetch.
5. Cache key: `email:${accountId}:${folder}:${filter}:${hasAttachments}`.

### Email Body Rendering

`_renderEmailBody(data)` (line 5481) renders email content through multiple
strategies in priority order:

1. **Sent/self messages** -- plaintext thread parse, then linkify.
2. **Server thread turns** -- `data.thread_turns` rendered as chat bubbles
   (currently disabled; `_bubblesDisabled()` returns `true`).
3. **Cached boundaries** -- `data.boundaries` with `sig_start`/`quote_start`
   offsets split the body into head/signature/quote sections.
4. **Client-side parse** -- HTML sanitized via `_sanitizeHtml()`, then
   threaded via `_renderThreadStructure()` or `_foldQuotedReplies()`.

`_safeRenderEmailBody(data)` (line 5573) wraps the above with error recovery.

### Email Card Grid

`_renderGrid()` (line 4738) renders email cards with date-bucket headers.
`_createCard(em)` (line 4832) builds individual card DOM elements with
sender avatar, subject, date, tags, done-check, star, and action buttons.
`_toggleCardPreview(card, em)` (line 5157) expands a card inline to show the
full email body with attachments.

### Search and Filtering

Search uses a pill-based architecture (`_libSearchPills` on state):
- `_addSearchPill(pill)` / `_removeSearchPillAt(idx)` manage filter pills.
- `_doSearch()` (line 4066) fires parallel local and full-text search
  requests.
- `_applyTagFilterFromPill(tag)` creates `filter:tag:*` pills.
- Filter modes: `all`, `unread`, `unanswered`, `reminders`, `favorites`.
- Sort modes: `recent`, `unread`, `favorites`.

### Email Settings

`_showEmailSettingsPage()` (line 234) renders three settings sections:
1. **Newsletter Unsubscribe** -- scan and one-click unsubscribe.
2. **Auto Reply** -- holiday/away replies with start/end dates, cooldown,
   scope, and pause-notifications toggle.
3. **Writing Style** -- free-text style prompt for AI replies, with an
   "Extract" button that analyzes sent emails.

### Unsubscribe Tooling

- `_openUnsubscribeReviewModal()` (line 1524) scans for newsletter senders.
- Supports three unsubscribe methods: `mailto`, `url` (link), and agent-
  assisted (sends prompt to chat).
- After unsubscribing, offers bulk cleanup (mark spam or delete).

### Email Actions Menu

`_showReaderMoreMenu()` (line 7391) and `_showCardMenu()` (line 7667)
provide context menus with: Reply, Reply All, Forward, AI Reply (with
optional user hint), Mark Read/Unread, Star/Unstar, Mark Done, Archive,
Add to Contacts, Mark Spam, Delete, Delete Permanently, Summarize,
Translate, and Copy Email Address.

### Bulk Operations

`_bulkAction(action)` (line 7939) handles multi-select operations: archive,
delete, mark-done, mark-read, mark-unread.

---

## 3. Email Inbox (emailInbox.js)

The sidebar inbox is a lighter view that delegates to the library for the
full reading experience.

### Initialization

`init(documentModule)` (line 156) wires click handlers, initializes the
email library, starts the unread badge poller, and triggers background
prewarming.

### Email List

- `loadEmails(append)` (line 384) fetches emails from `/api/email/list`
  with optional sender filter. Uses a fast `cached_only=1` prefetch.
- `_renderList()` (line 515) renders email items with sender avatar
  (deterministic HSL color from name hash), date, subject, unread dot,
  attachment icon, and tag pills.
- `_createEmailItem(em)` (line 560) builds each list row.

### Reply Flow

`_openEmail(em, itemEl, preloadedData, mode, noteHint, prefilledBody)`
(line 754) handles the full reply lifecycle:

1. Fetch email body from `/api/email/read/{uid}`.
2. For AI Reply mode, call `/api/email/ai-reply` to generate a draft.
3. Build reply headers (To, Cc, In-Reply-To, References, X-Source-UID).
4. Handle reply-all by calling `buildReplyAllCc()` to compute CC list.
5. Create or reuse a document via `/api/document` POST.
6. On desktop, dock the email modal left; on mobile, slide the draft panel
   over the email.

### Folder Management

- `loadFolders()` (line 437) fetches from `/api/email/folders`.
- `sortedFolders(folders)` (line 450) orders folders: INBOX, Sent, Starred,
  Archive, Junk, Trash, Drafts, then alphabetical others.
- `folderDisplayName(folder)` (line 473) maps raw IMAP names to friendly
  display names.

### Swipe and Touch

On mobile, email items support swipe-left-to-archive with a 70px threshold
and red gradient background indicator (line 691).

### Unread Badge

`_refreshUnreadCount()` (line 314) polls `/api/email/unread-state` every 60s
and compares `max_uid` against a localStorage threshold
(`odysseus-email-last-seen-uid`). The dot color reflects urgency state from
`/api/email/urgency-state` (red for score>=3, orange for score=2).

### Deep Linking

Hash format `#email=FOLDER:UID` opens the library to a specific email.

---

## 4. Reply Recipients (replyRecipients.js)

Pure functions for building reply-all recipient lists.

- `extractEmail(addr)` (line 7) -- extracts bare email from
  `"Name <email@x>"` format.
- `buildReplyAllCc(data, mine)` (line 20) -- constructs the CC list for
  reply-all by combining original To and Cc addresses, excluding the user's
  own addresses. Compares by exact extracted email to avoid the bug where
  an empty self-address matched everything (issue #360).

---

## 5. Signature System

### Signature Folding (signatureFold.js)

Heuristic engine that collapses quoted email history and corporate signatures
into `<details>` folds.

**`_foldSignature(html, hintSig)`** (line 285) -- top-level entry point.
Detection strategies in priority order:

1. **Hint signature** -- per-sender cached signature from
   `learn_sender_signatures` action via `_tryFoldHintSig()` (line 231).
2. **Gmail signature class** -- `gmail_signature` or
   `data-smartmail="gmail_signature"` divs.
3. **ID-based** -- `id="Signature"` or `id="divRplyFwdMsg"`.
4. **RFC delimiter** -- `\n--\n` line.
5. **Closing phrase** -- "Best regards", "Cheers", "Thanks", etc. followed
   by bloated content. `_peelSigNameLine()` (line 183) keeps the signer's
   name visible above the fold.
6. **Mobile tag** -- "Sent from my iPhone/Android/...".
7. **Disclaimer** -- "CONFIDENTIALITY NOTICE", "This email is confidential".

**`_looksLikeSignature(html)`** (line 35) -- heuristic scoring: 9 signature
tells (legal entity names, phone numbers, confidentiality notices) vs 4
conversational tells (greetings, questions). Score >= 3 with <= 1
conversational hit = signature.

**`_isBloatedSig(htmlFragment)`** (line 214) -- only folds signatures whose
plain text exceeds `_SIG_BLOAT_MIN_CHARS` (200 characters).

### Quote Folding

- `_harvestAttribution(container)` (line 66) -- extracts "On date, X wrote:"
  attribution lines from the end of a fragment.
- `_extractQuoteMeta(html)` (line 135) -- parses Outlook-style
  "From: X / Sent: Y" headers and Gmail-style "On date, X wrote:" in 15+
  languages. Returns `"Sender Name / Date"` for fold headers.
- `_foldSummary(label, iconSvg, meta)` (line 100) -- builds the
  `<summary>` element with sender name, metadata, and chevron.

### Drawing Signature (signature.js)

Canvas-based signature drawing pad using Catmull-Rom cubic curves with
variable stroke width derived from pointer velocity.

- `capture(opts)` (line 379) -- opens a modal with a drawing canvas,
  smoothness slider (0-10, persisted in localStorage), name input, and
  undo support. Returns `{ id, dataUrl, width, height, name }`.
- `pick(opts)` (line 460) -- shows saved signatures in a 3-column grid
  with a "Draw new" button. Delegates to `capture()` for new signatures.
- `SmoothPad` class (line 38) -- implements the drawing engine with EMA
  smoothing on input points, Chaikin corner-cutting passes (up to 6), and
  Catmull-Rom cubic interpolation.
- `toTrimmedDataUrl(padding)` (line 272) -- crops empty border and replaces
  white pixels with transparency for PDF stamping.

---

## 6. State Management (state.js)

Single exported `state` object shared across all emailLibrary modules:

| Property | Default | Purpose |
|----------|---------|---------|
| `_libOpen` | `false` | Whether the library modal is visible |
| `_libEmails` | `[]` | Current page of email objects |
| `_libTotal` | `0` | Total emails in current view |
| `_libOffset` | `0` | Pagination offset |
| `_libFolder` | `'INBOX'` | Active IMAP folder |
| `_libFolders` | `[]` | Available folder list |
| `_libAccountId` | `null` | Active email account ID |
| `_libAccounts` | `[]` | All configured accounts |
| `_libSearch` | `''` | Current search query |
| `_libFilter` | `'all'` | Filter mode (all/unread/unanswered) |
| `_libSort` | `'recent'` | Sort mode (recent/unread/favorites) |
| `_libHasAttachments` | `false` | Attachment filter toggle |
| `_libShowTags` | from localStorage | Tag pill visibility |
| `_libLoading` | `false` | Loading indicator flag |
| `_selectMode` | `false` | Bulk selection mode |
| `_selectedUids` | `new Set()` | Selected email UIDs |

---

## 7. API Calls

### Email CRUD

| Method | Endpoint | Used In |
|--------|----------|---------|
| GET | `/api/email/list` | emailLibrary (line 4584), emailInbox (line 421) |
| GET | `/api/email/read/{uid}` | emailLibrary (line 5243), emailInbox (line 783) |
| DELETE | `/api/email/delete/{uid}` | emailLibrary (line 1168), emailInbox (line 1232) |
| DELETE | `/api/email/delete-permanent/{uid}` | emailLibrary (line 7608) |
| POST | `/api/email/archive/{uid}` | emailLibrary (line 7530), emailInbox (line 1215) |
| POST | `/api/email/move/{uid}` | emailLibrary (line 7571) |
| POST | `/api/email/flag/{uid}` | emailLibrary (line 7495) |
| GET | `/api/email/scheduled` | emailLibrary (line 4614) |
| DELETE | `/api/email/scheduled/{id}` | emailLibrary (line 4669) |

### Read/Answered State

| Method | Endpoint | Used In |
|--------|----------|---------|
| POST | `/api/email/mark-read/{uid}` | emailLibrary (line 7475), emailInbox (line 1285) |
| POST | `/api/email/mark-unread/{uid}` | emailLibrary (line 7477) |
| POST | `/api/email/mark-answered/{uid}` | emailLibrary (line 7516), emailInbox (line 1284) |
| POST | `/api/email/clear-answered/{uid}` | emailLibrary (line 7519), emailInbox (line 1287) |
| GET | `/api/email/unread-state` | emailLibrary (line 3101), emailInbox (line 323) |
| POST | `/api/email/{uid}/unflag-spam` | emailInbox (line 673) |

### Accounts and Folders

| Method | Endpoint | Used In |
|--------|----------|---------|
| GET | `/api/email/accounts` | emailLibrary (line 2957) |
| POST | `/api/email/accounts/{id}/set-default` | emailLibrary (line 3031) |
| GET | `/api/email/folders` | emailLibrary (line 3256), emailInbox (line 440) |
| GET | `/api/email/urgency-state` | emailInbox (line 324) |

### AI Features

| Method | Endpoint | Used In |
|--------|----------|---------|
| POST | `/api/email/ai-reply` | emailInbox (line 826) |
| POST | `/api/email/summarize` | emailLibrary (line 7236) |
| POST | `/api/email/translate` | emailLibrary (line 7320) |

### Settings and Style

| Method | Endpoint | Used In |
|--------|----------|---------|
| GET | `/api/email/config` | emailLibrary (line 81) |
| PUT | `/api/email/config` | emailLibrary (line 327) |
| GET | `/api/email/style` | emailLibrary (line 89) |
| PUT | `/api/email/style` | emailLibrary (line 363) |
| POST | `/api/email/extract-style` | emailLibrary (line 402) |

### Unsubscribe

| Method | Endpoint | Used In |
|--------|----------|---------|
| POST | `/api/email/unsubscribe/scan` | emailLibrary (line 1589) |
| POST | `/api/email/unsubscribe/execute` | emailLibrary (line 1655, 1713) |
| POST | `/api/email/unsubscribe/cleanup` | emailLibrary (line 1448) |

### Attachments

| Method | Endpoint | Used In |
|--------|----------|---------|
| GET | `/api/email/attachments/{uid}` | emailLibrary (line 6599) |

### Other

| Method | Endpoint | Used In |
|--------|----------|---------|
| GET | `/api/email/odysseus/reminders` | emailLibrary (line 2624) |
| POST | `/api/notes` | emailInbox (line 1194), emailLibrary (line 8469) |
| POST | `/api/document` | emailInbox (line 1004, 1365) |
| POST | `/api/session` | emailInbox (line 1332) |
| GET | `/api/default-chat` | emailInbox (line 1318) |
| GET | `/api/contacts/list` | emailLibrary (line 3426) |
| POST | `/api/contacts/add` | emailLibrary (line 7548) |
| GET | `/api/auth/settings` | emailLibrary (line 965) |
| GET/POST | `/api/signatures` | signature.js (line 329, 336) |
| DELETE | `/api/signatures/{id}` | signature.js (line 349) |

---

## 8. Key Functions

### emailLibrary.js

| Line | Function | Purpose |
|------|----------|---------|
| 2287 | `initEmailLibrary(config)` | Store documentModule and onEmailClick |
| 2294 | `openEmailLibrary(opts)` | Create and open the library modal |
| 3123 | `closeEmailLibrary()` | Tear down the modal and clear layout |
| 2091 | `prewarmEmailLibrary()` | Background-fetch accounts/folders/emails |
| 4471 | `_loadEmails()` | SWR email loading with client cache |
| 4738 | `_renderGrid()` | Render email cards with date headers |
| 4832 | `_createCard(em)` | Build an email card DOM element |
| 5157 | `_toggleCardPreview(card, em)` | Expand card to show full email |
| 5481 | `_renderEmailBody(data)` | Multi-strategy body rendering |
| 4066 | `_doSearch()` | Parallel local + full-text search |
| 7391 | `_showReaderMoreMenu()` | Email reader context menu |
| 7939 | `_bulkAction(action)` | Multi-select operations |
| 234 | `_showEmailSettingsPage()` | Email settings UI |
| 1524 | `_openUnsubscribeReviewModal()` | Newsletter unsubscribe scanner |
| 6752 | `_openEmailAsTab(em, folder)` | Pop email out to its own tab |
| 840 | `_syncEmailReadState(uid)` | Sync read state across all views |

### emailInbox.js

| Line | Function | Purpose |
|------|----------|---------|
| 156 | `init(documentModule)` | Wire events and initialize library |
| 384 | `loadEmails(append)` | Fetch and render sidebar email list |
| 754 | `_openEmail(em, ...)` | Full reply/forward/AI-reply flow |
| 1351 | `_composeNew()` | Create a new blank email draft |
| 1294 | `_createEmailChat(emailData)` | Create or reuse a chat session for email |
| 314 | `_refreshUnreadCount()` | Poll unread badge with urgency colors |
| 560 | `_createEmailItem(em)` | Build a sidebar email list row |
| 1064 | `_showEmailMenu(em, anchor)` | Sidebar email context menu |

### emailLibrary/utils.js

| Line | Function | Purpose |
|------|----------|---------|
| 177 | `_sanitizeHtml(html)` | Multi-pass HTML sanitizer for email bodies |
| 75 | `_escLinkify(text)` | Escape and auto-link URLs/emails |
| 90 | `_extractName(addr)` | Pull display name from email address |
| 132 | `_formatRecipients(raw)` | Short readable recipient list |
| 150 | `_senderColor(name)` | Deterministic HSL color from sender name |
| 162 | `_initials(s)` | 1-2 letter avatar initials |

### emailLibrary/signatureFold.js

| Line | Function | Purpose |
|------|----------|---------|
| 285 | `_foldSignature(html, hintSig)` | Top-level signature fold dispatcher |
| 35 | `_looksLikeSignature(html)` | Heuristic signature detection |
| 135 | `_extractQuoteMeta(html)` | Parse multilingual quote attribution |
| 231 | `_tryFoldHintSig(html, hintSig)` | Fold using cached per-sender signature |
| 183 | `_peelSigNameLine(html)` | Keep signer name visible above fold |
