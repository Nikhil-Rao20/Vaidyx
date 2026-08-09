# Feature UIs: Gallery, Notes, Calendar, Tasks, Memory

Covers the five major feature modules rendered as tool windows / side panels.

---

## 1. Gallery (`static/js/gallery.js`, 2958 lines)

Photo backup and AI-generated image library.  Opens as a draggable modal with
three tabs: **Photos**, **Albums**, and **Edit** (image editor landing).

### Core Capabilities

| Area | Details |
|------|---------|
| Photo grid | Paginated thumbnail grid with skeleton loading, stale-while-revalidate caching, and domino-in cascade animation on first open. Page size auto-computed from viewport dimensions (capped at 100). |
| Sorting/filtering | Sort by recent/shuffle; filter by search, tags (AND-stacked), model, album, favorites. |
| Albums | CRUD for albums with cover thumbnails. Folder drag-and-drop auto-creates albums. Bulk select/delete. |
| Upload | Drag-and-drop or file picker. Concurrent 4-worker upload pool. Duplicate detection. Supports images and videos. Recursive directory walk for folder drops. |
| Detail overlay | Full metadata display (EXIF, dimensions, file size, dates). Inline tag editing, AI auto-tagging, rename, rotate, favorite, album assignment, delete. Color picker for event backgrounds. |
| Editor drafts | Persisted canvas projects (list/search/select/bulk-delete). Resume drafts with preset sizes (Square HD, Widescreen, A4, etc.). |
| Bulk operations | Multi-select mode with select-all, bulk delete, bulk download (ZIP), bulk favorite toggle, bulk tag assignment. |
| Video support | `<video>` elements for .mp4/.mov/.webm/.mkv/.m4v with play overlay badge. |

### State (line 15-71)

`_open`, `_items[]`, `_total`, `_search`, `_activeTags[]`, `_activeModel`,
`_activeAlbum`, `_favoritesOnly`, `_sort`, `_shuffleSeed`, `_offset`,
`_limit`, `_albums[]`, `_albumSelectMode`, `_draftsCache[]`.

---

## 2. Notes (`static/js/notes.js`, 5365 lines)

Google Keep-style notes and todos.  Renders as a side panel (right-docked on
desktop, full-screen bottom sheet on mobile).

### Core Capabilities

| Area | Details |
|------|---------|
| Note types | Plain text, todo/checklist (with checkbox items), goal (with progress tracking and AI step breakdown). |
| Views | List or grid (masonry layout). Persisted in localStorage. |
| Colors | Preset palette (red/orange/yellow/green/blue/purple) plus custom background image upload. |
| Reminders | Due-date scheduling with presets (Later today 6pm, Tomorrow 8am, Next Monday 8am, custom datetime). Recurring reminders (daily, weekly, monthly with nth-weekday/last-weekday variants, yearly). Browser Notification API integration. 30-second poll loop. |
| Reminder glow | Fired reminders get sticky card glow and pending-highlight queue for offline firing. Rail badge shows unfired count. |
| Archiving | Archive/unarchive with undo stack (Ctrl+Z). Confetti animation on completing all checklist items. |
| Drag reorder | Long-press enters drag mode; reorder persisted via `/api/notes/reorder`. |
| Select mode | Multi-select with bulk archive and bulk delete. |
| Search | Inline search filters displayed notes. |
| Labels | Filter by label (e.g., "calendar" label for reminders created from calendar events). |
| Undo | In-memory stack (max 20 entries). Ctrl/Cmd+Z pops last action. Toast shows "Undo" button. |
| Mobile | Full-screen bottom sheet with swipe-to-dismiss gesture, mobile-specific fullscreen edit overlay. |

### State (line 17-51)

`_open`, `_notes[]`, `_editingId`, `_selectedIds`, `_activeLabel`,
`_activeFilter`, `_searchQuery`, `_viewMode` (list/grid),
`_showingArchived`, `_selectMode`, `_reminderTimer`.

### Reminder System (lines 660-1046)

- Presets: `_laterTodayDate()` (6pm or +3h), `_tomorrowDate()` (8am), `_nextWeekDate()` (next Mon 8am)
- Recurring: normalized format `weekly:W`, `monthly:day:D`, `monthly:nth:N:W`, `monthly:last:W`, `daily`, `yearly`
- `_advanceRecurring()` computes the next occurrence (catches up past-due with 5000-iteration guard)
- `_checkReminders()` runs every 30s, fires browser notifications and server-side dispatch
- `_fireReminder()` calls `/api/notes/fire-reminder` for email/synthesis, shows local Notification + toast

---

## 3. Calendar (`static/js/calendar.js`, 3722 lines)

CalDAV-backed calendar with month/week/year/agenda views.

### Supporting Modules

- **`calendar/utils.js`** (181 lines) -- Pure constants and helpers: `WEEKDAYS`, `MONTHS`, `CAL_COLORS` (9 preset colors + custom bg-image), `_TYPE_PALETTE` (per-event-type accent colors), date formatters (`_ds`, `_addDays`, `_shiftDT`, `_tzOffset`, `_localDateOf`), CSS helpers for background images, WCAG contrast color picker.
- **`calendar/reminders.js`** (114 lines) -- Browser-notification poller. Polls `/api/notes?label=calendar` every 60s. Fires Notification + toast for notes whose `due_date` is past but within 5-minute staleness window. Persists fired IDs to localStorage (last 200).

### Core Capabilities

| Area | Details |
|------|---------|
| Views | Month (6-week grid with multi-day overlay bars), Week (hour-grid with zoomable 28-120px/hour), Year (12 mini-month grids with dot indicators), Agenda (upcoming events list). |
| Event CRUD | Create, update, delete with optimistic UI. Temp UIDs replaced on server confirmation. Rollback on server error. |
| Recurring events | Compound UIDs (`base::date`). Delete scope choice: single occurrence or full series. Cache invalidation on recurring-event mutations. |
| Quick-add | Natural-language input parsed via `/api/calendar/quick-parse`. Cycling placeholder examples. |
| CalDAV sync | Background sync on first open via `/api/calendar/sync`. Manual sync button. Calendar CRUD (create, rename, delete). |
| Import/Export | `.ics` file import, per-calendar `.ics` export download. |
| Drag and drop | Month grid: drag events between days. Week grid: drag to reschedule (time + day) and bottom-edge resize to change duration. |
| Filters | Per-calendar visibility toggle, per-event-type category chips (work/personal/health/travel/meal/social/admin/other), "! important" filter for high/critical events. Collapsible filter row. |
| Week-start | Configurable Monday-first (default) or Sunday-first. |
| Color | Per-event color override from 9-color palette plus custom background image. WCAG-aware text color auto-selection. |
| Reminders | "Set reminder" from event detail creates a note with `label=calendar` and `event_dtstart` for live time computation. |
| Caching | Event pool in `_allEvents{}` keyed by UID. Range tracking via `_fetchedRanges[]`. LocalStorage persistence. Prefetch adjacent months/years. |
| Navigation | Prev/next with slide animation. Today button. View toggle (Week/Month/Year/Agenda). Pinch zoom between views. |
| Undo | Event moves and deletes support undo via toast + Ctrl/Cmd+Z. |

### State (line 50-78)

`_open`, `_currentDate`, `_events[]`, `_allEvents{}`, `_fetchedRanges[]`,
`_calendars[]`, `_hiddenCals`, `_hiddenTypes`, `_onlyImportant`,
`_weekStartSun`, `_selectedDay`, `_view`, `_searchQuery`, `_dragUid`.

---

## 4. Tasks (`static/js/tasks.js`, 3187 lines)

Scheduled recurring LLM prompts and built-in maintenance actions.

### Core Capabilities

| Area | Details |
|------|---------|
| Task types | LLM prompt, Research, Action (built-in maintenance). |
| Trigger types | Schedule (daily/weekly/monthly/once/cron), Event (every N sessions/messages), Webhook (external HTTP). |
| Schedule | Custom time picker (hour/minute selects), day-of-week for weekly, day-of-month for monthly, full date picker for once, cron expression input. Times converted UTC<->local. |
| Actions | Built-in actions: tidy_sessions, tidy_documents, consolidate_memory, tidy_research, tidy_calendar, summarize_emails, draft_email_replies, email_auto_translate, extract_email_events, classify_events, check_email_urgency, test_skills, audit_skills, daily_brief, ssh_command, run_script, cookbook_serve. |
| Output targets | Session, email (with account selection), MCP endpoints. |
| Run control | Run now, pause, resume, stop. Force-run option. |
| Run history | Per-task run log with status (success/error), timing, result preview. Recent activity feed across all tasks. |
| Categories | Auto-categorized (Cookbook/Calendar/Email/Chats/Documents/Memory/Research/Skills/Assistant/System/Other). Category filter chips. |
| Bulk operations | Multi-select with bulk delete (concurrent deletion with per-card busy indicator and progress counter). |
| AI drafting | Describe a task in plain language, AI parses it into structured task via `/api/tasks/parse`. |
| Built-in badge | Tasks marked `is_builtin` show a badge; modified built-ins can be reverted to default. |
| Notifications | Per-task notification toggle. Failure/completion pending indicators on sidebar buttons. |
| Card UI | Expandable detail cards with schedule label, next-run countdown, run count, last-run result preview, kebab menu. Long-press opens menu on mobile. |

### State (line 15-25)

`_open`, `_tasks[]`, `_tasksFetched`, `_viewingRuns`, `_clockInterval`,
`_taskFailurePending`, `_taskCompletionPending`.

---

## 5. Memory (`static/js/memory.js`, 1550 lines)

AI memory system UI for managing facts the assistant remembers across sessions.

### Core Capabilities

| Area | Details |
|------|---------|
| Categories | fact, identity, preference, contact, project, goal, task. Chip filters with counts. |
| CRUD | Add (with category select), inline edit (double-click text, category dropdown), delete with confirmation. |
| Pin/Unpin | Pinned memories always injected into context; unpinned use RAG only. Bookmark icon in dropdown menu. |
| Sort | Newest, Oldest, A-Z, Most used. Custom icon-labeled sort picker. |
| Search | Text filter across memory content. |
| Bulk select | Select mode with select-all, bulk delete with animated removal. |
| Tidy (audit) | POST to `/api/memory/audit`. Animated diff: edits show text morphing, removals get strikethrough fade-out. |
| Import | File upload to `/api/memory/import` (FormData). Returns suggestions for review. Save-all or per-item save/delete. |
| Export | Download memories as JSON file. |
| Extract | From chat session via `/api/memory/extract`. Shows suggestion cards with save buttons. |
| Settings | Toggles for memory_enabled, auto_memory, skills_enabled, auto_skills, auto_approve_skills. Confidence slider for skill injection. Max-injected-skills number input. All backed by `/api/prefs/{key}`. |
| Usage tracking | Per-memory `uses` count with injection-count display. |

### State (line 13-18)

`memories[]`, `activeCategory`, `sortOrder`, `selectMode`, `selectedIds`, `memoriesLoading`.

---

## 6. API Endpoints

### Gallery
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/gallery/library` | Fetch paginated photo list (sort, search, tag, model, album, favorites) |
| GET | `/api/gallery/{id}` | Fetch single image metadata |
| PATCH | `/api/gallery/{id}` | Update image metadata (tags, caption, album) |
| DELETE | `/api/gallery/{id}` | Delete image |
| POST | `/api/gallery/upload` | Upload single image/video |
| POST | `/api/gallery/{id}/favorite` | Toggle favorite |
| POST | `/api/gallery/{id}/ai-tag` | AI auto-tag single image |
| POST | `/api/gallery/{id}/rotate` | Rotate image |
| POST | `/api/gallery/{id}/rename` | Rename image |
| GET | `/api/gallery/ai-tag-batch` | Batch AI-tag multiple images |
| POST | `/api/gallery/clear-ai-tags` | Clear AI tags (single or all) |
| POST | `/api/gallery/download-zip` | Bulk download as ZIP |
| GET | `/api/gallery/albums` | List albums |
| POST | `/api/gallery/albums` | Create album |
| PUT | `/api/gallery/albums/{id}` | Rename album |
| DELETE | `/api/gallery/albums/{id}` | Delete album |
| GET | `/api/editor-drafts` | List editor drafts |
| DELETE | `/api/editor-drafts/{id}` | Delete editor draft |

### Notes
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/notes` | Fetch notes (optional `?archived=true`, `?label=`) |
| POST | `/api/notes` | Create note |
| PUT | `/api/notes/{id}` | Update note |
| DELETE | `/api/notes/{id}` | Delete note |
| POST | `/api/notes/reorder` | Persist drag-reorder |
| POST | `/api/notes/fire-reminder` | Server-side reminder dispatch (email/synthesis) |
| POST | `/api/upload` | Upload background image for note color |

### Calendar
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/calendar/events` | Fetch events for date range |
| POST | `/api/calendar/events` | Create event |
| PUT | `/api/calendar/events/{uid}` | Update event |
| DELETE | `/api/calendar/events/{uid}` | Delete event (optional `?scope=occurrence`) |
| POST | `/api/calendar/quick-parse` | NLP quick-add parsing |
| GET | `/api/calendar/calendars` | List calendars |
| POST | `/api/calendar/calendars` | Create calendar |
| PUT | `/api/calendar/calendars/{id}` | Update calendar |
| DELETE | `/api/calendar/calendars/{id}` | Delete calendar |
| POST | `/api/calendar/sync` | Trigger CalDAV sync |
| POST | `/api/calendar/import` | Import .ics file |
| GET | `/api/calendar/export/{id}` | Export calendar as .ics |

### Tasks
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Create task |
| PUT | `/api/tasks/{id}` | Update task |
| DELETE | `/api/tasks/{id}` | Delete task |
| POST | `/api/tasks/{id}/pause` | Pause task |
| POST | `/api/tasks/{id}/resume` | Resume task |
| POST | `/api/tasks/{id}/run` | Trigger immediate run (optional `?force=true`) |
| POST | `/api/tasks/{id}/stop` | Stop running task |
| POST | `/api/tasks/{id}/revert` | Revert built-in task to defaults |
| POST | `/api/tasks/{id}/clear-cache` | Clear task action cache |
| GET | `/api/tasks/{id}/runs` | Fetch run history |
| GET | `/api/tasks/runs/recent` | Recent runs across all tasks |
| GET | `/api/tasks/meta/output-targets` | Available output targets |
| GET | `/api/tasks/meta/actions` | Available built-in actions |
| GET | `/api/tasks/meta/events` | Available trigger events |
| GET | `/api/tasks/onboarding` | Check onboarding state |
| POST | `/api/tasks/onboarding` | Mark onboarding complete |
| POST | `/api/tasks/parse` | AI-draft task from description |
| GET | `/api/tasks/notifications` | Fetch task notifications |
| GET | `/api/models` | Available models for task config |
| GET | `/api/email/accounts` | Email accounts for email actions |

### Memory
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/memory` | Fetch all memories |
| POST | `/api/memory/add` | Add memory |
| PUT | `/api/memory/{id}` | Update memory text/category |
| DELETE | `/api/memory/{id}` | Delete memory |
| POST | `/api/memory/{id}/pin` | Pin/unpin memory |
| POST | `/api/memory/audit` | Tidy/deduplicate memories |
| POST | `/api/memory/extract` | Extract suggestions from session |
| POST | `/api/memory/import` | Import memories from file |
| GET/PUT | `/api/prefs/{key}` | Read/write user preferences |

---

## 7. Key Functions (with line numbers)

### Gallery (`gallery.js`)
| Line | Function | Purpose |
|------|----------|---------|
| 75 | `_fetchLibrary(append)` | Paginated photo fetch with filter params |
| 132 | `_fetchAlbums()` | Load album list |
| 147 | `_patchImage(id, patch)` | PATCH image metadata |
| 165 | `_deleteImage(id)` | DELETE image |
| 186 | `_bulkUpload(filesOrItems, albumId)` | Concurrent 4-worker upload |
| 286 | `_handleGalleryDrop(e)` | Native drop handler (folder/file split) |
| 529 | `_renderAlbumsGrid()` | Album card grid with cover thumbnails |
| 808 | `_bulkDeleteAlbums(ids)` | Bulk album deletion |
| 873 | `_renderEditorDrafts()` | Fetch and render canvas project drafts |
| 1182 | `_renderGrid()` | Main photo grid renderer |
| 1319 | `_openDetail(img)` | Photo detail overlay |
| 1944 | `openGallery()` | Public: open gallery modal |
| 2635 | `_bulkDelete(ids)` | Bulk photo deletion |
| 2659 | `_bulkDownload(ids)` | ZIP download of selected photos |
| 2919 | `closeGallery()` | Public: close gallery modal |

### Notes (`notes.js`)
| Line | Function | Purpose |
|------|----------|---------|
| 447 | `_fetchNotes()` | Fetch notes from API |
| 463 | `_saveNote(note)` | Create or update note |
| 482 | `_patchNote(id, patch)` | Partial update |
| 858 | `_advanceRecurring(dateStr, repeat)` | Compute next recurring date |
| 925 | `_checkReminders()` | 30s poll loop for due reminders |
| 969 | `_fireReminder(note)` | Dispatch notification + server call |
| 1042 | `_startReminderLoop()` | Start 30s interval |
| 1145 | `openPanel()` | Public: open notes side panel |
| 1631 | `closePanel(direction)` | Public: close panel |

### Calendar (`calendar.js`)
| Line | Function | Purpose |
|------|----------|---------|
| 115 | `_fetchEvents(start, end, force)` | Fetch events for date range with pool caching |
| 182 | `_fetchCalendars()` | Load calendar list + trigger first CalDAV sync |
| 206 | `_syncCaldav(interactive)` | CalDAV pull (background or interactive) |
| 251 | `_createEvent(data)` | Optimistic event creation |
| 275 | `_updateEvent(uid, data)` | Optimistic event update |
| 304 | `_deleteEvent(uid, opts)` | Optimistic event deletion (series/occurrence) |
| 569 | `_createEventReminder(ev, dueDate)` | Create reminder note from calendar event |
| 803 | `_render()` | View dispatch (month/week/year/agenda) |
| 1006 | `_renderMonth()` | Month grid with multi-day overlay bars |
| 1255 | `_renderWeek()` | Hour-grid week view |
| 3480 | `openCalendar()` | Public: open calendar modal |
| 3605 | `closeCalendar()` | Public: close calendar modal |

### Tasks (`tasks.js`)
| Line | Function | Purpose |
|------|----------|---------|
| 42 | `_fetchTasks()` | Fetch task list |
| 72 | `_createTask(data)` | Create new task |
| 83 | `_updateTask(id, data)` | Update task |
| 94 | `_deleteTask(id)` | Delete task |
| 135 | `_pauseTask(id)` | Pause scheduled task |
| 142 | `_resumeTask(id)` | Resume paused task |
| 149 | `_runNow(id, force)` | Trigger immediate execution |
| 167 | `_stopTask(id)` | Stop running task |
| 182 | `_fetchRuns(taskId, limit)` | Fetch run history |
| 800 | `_renderList()` | Render task card list |
| 1206 | `_showForm(existing, type, trigger)` | Task create/edit form |
| 2935 | `openTasks(focusId, opts)` | Public: open tasks modal |
| 3087 | `closeTasks()` | Public: close tasks modal |

### Memory (`memory.js`)
| Line | Function | Purpose |
|------|----------|---------|
| 372 | `loadMemories()` | Fetch and render all memories |
| 476 | `bulkDelete()` | Bulk delete selected memories |
| 503 | `tidyMemories()` | Audit/deduplicate via API |
| 685 | `renderMemoryList()` | Render filtered/sorted memory list |
| 1044 | `saveInlineEdit(id, text, category)` | Save inline text/category edit |
| 1106 | `addNewMemory()` | Add memory from input field |
| 1153 | `togglePin(id, pinned)` | Pin/unpin memory |
| 1171 | `deleteMemory(id)` | Delete single memory with confirmation |
| 1194 | `extractMemory(sessionId)` | Extract suggestions from chat session |
| 1266 | `exportMemories()` | Download memories as JSON |
| 1284 | `importMemories()` | Trigger file import flow |

### Calendar Utilities (`calendar/utils.js`)
| Line | Function | Purpose |
|------|----------|---------|
| 60 | `_isCalBgImage(c)` | Check if color is bg-image sentinel |
| 83 | `_calBgCss(c, fallback)` | CSS background value for event color |
| 118 | `_calReadableTextColor(bg)` | WCAG-aware text color for background |
| 131 | `_ds(d)` | Date to YYYY-MM-DD string |
| 152 | `_tzOffset()` | UTC offset as +/-HH:MM |
| 167 | `_localDateOf(isoStr)` | Extract local date from ISO string |

### Calendar Reminders (`calendar/reminders.js`)
| Line | Function | Purpose |
|------|----------|---------|
| 57 | `_pollReminders()` | Poll calendar-label notes for due reminders |
| 106 | `startReminderPoll()` | Start 60s poll loop + request Notification permission |
