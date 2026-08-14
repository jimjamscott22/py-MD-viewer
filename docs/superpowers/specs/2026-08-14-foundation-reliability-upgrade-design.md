# Foundation Reliability Upgrade — Design Spec

**Date:** 2026-08-14
**Status:** Approved direction; pending written-spec review

---

## Overview

Strengthen the local, single-user Markdown app before adding broader performance or product features. This release fixes the delayed live-reload connection, makes external file changes complete and predictable, prevents avoidable editor data loss, ensures AI actions use the document actually being edited, and aligns the supported Python and Windows launcher contracts with reality.

The implementation remains a local Flask application with a browser UI. It does not introduce accounts, collaboration, a database, a native shell, or a frontend framework.

---

## Product Boundary

The app is designed for one trusted user working with local Markdown files. It binds to `127.0.0.1`, may open multiple browser tabs, and must remain responsive and reliable when files are also changed by an external editor.

This boundary permits local filesystem access and does not require hostile multi-user isolation. It still requires path validation, conflict detection, durable writes, clear error handling, and no silent loss of edits.

---

## Goals

- Complete the SSE connection immediately instead of waiting for the first event or 30-second keepalive.
- Detect Markdown create, modify, delete, and move events made outside the app.
- Avoid false “changed on disk” warnings for the app’s own successful saves.
- Replace direct overwrites with atomic UTF-8 saves.
- Use a high-resolution file revision token for editor conflict detection while retaining temporary compatibility with the existing timestamp field.
- Give the AI assistant the active editor tab’s current unsaved content and path.
- Set the package’s minimum Python version to one the source actually supports.
- Make the Windows launcher portable within the repository instead of embedding machine-specific paths.
- Add regression coverage after the implementation changes are made.

---

## Non-Goals

- Full-text search indexing or cache-performance work.
- Bundling CodeMirror, Mermaid, KaTeX, or fonts for offline use.
- Command palette, backlinks, tag navigation, Git integration, or new exports.
- Streaming AI responses, diff/apply AI editing, model discovery, or provider settings UI.
- Visual redesign or accessibility remediation.
- Multi-user access, authentication, network hosting, or real-time collaboration.
- A native desktop wrapper, installer, or system-tray process.
- A general refactor of `app.py`, the CSS, or frontend modules unrelated to this release.

---

## Architecture

### 1. Server-Sent Events handshake and event schema

`GET /events` will yield an SSE comment immediately after registering its subscriber:

```text
: connected

```

The existing 30-second keepalive remains. This lets the WSGI server send response headers immediately and makes the endpoint test complete without waiting 30 seconds.

File events retain the existing JSON envelope and may add a revision:

```json
{
  "type": "file_modified",
  "file": "notes/example.md",
  "revision": "1723581123456789000:4182"
}
```

Tree-changing events use:

```json
{
  "type": "tree_changed",
  "file": "notes/example.md"
}
```

Existing clients remain compatible because they already ignore unknown JSON fields.

### 2. Watcher event classification

`MarkdownFileHandler` will classify events instead of treating create and modify identically:

| Filesystem event | App event | Handling |
| --- | --- | --- |
| Existing `.md` content modified | `file_modified` | Notify viewers with the current revision |
| `.md` created | `tree_changed` | Refresh the file tree |
| `.md` deleted | `tree_changed` | Refresh the file tree |
| `.md` moved or renamed | `tree_changed` | Refresh the file tree using the destination path when available |
| Atomic temporary file moved over an existing `.md` | `file_modified` | Notify viewers with the destination revision |
| Non-Markdown event | none | Ignore |

The watcher callback changes from a one-argument callback to a small explicit event interface:

```python
Callable[[str, str, str | None], None]
```

Arguments are relative path, event type, and optional revision. The handler continues to reject paths outside the active base directory.

The debounce map will remove expired entries during event handling so a long-running session does not retain one timestamp for every file ever touched.

### 3. File revision and atomic storage helper

A focused `storage.py` module will own the file-state mechanics used by editor routes:

```python
def get_file_revision(path: Path) -> str:
    """Return '<mtime_ns>:<size>' for the current file state."""

def atomic_write_text(path: Path, content: str) -> os.stat_result:
    """Write UTF-8 content beside the target and atomically replace it."""
```

`atomic_write_text` will:

1. Create a temporary file in the target directory.
2. Preserve the target's existing file mode when the platform exposes it.
3. Write UTF-8 content, flush it, and call `os.fsync`.
4. Replace the target with `os.replace`.
5. Remove the temporary file if an error occurs before replacement.

Creating the temporary file beside the target keeps replacement on the same filesystem. The helper will not create backup files or version-control commits.

The revision token uses nanosecond modification time plus byte size. It is inexpensive, JSON-safe, and materially stronger than the existing microsecond timestamp string. It is an optimistic concurrency token, not a cryptographic content identity.

### 4. Editor API contract

`GET /api/content/<path>` adds `revision` while retaining existing fields:

```json
{
  "content": "# Example",
  "path": "example.md",
  "modified": "2026-08-14T12:00:00+00:00",
  "revision": "1723581123456789000:10"
}
```

`PUT /api/save` accepts:

```json
{
  "path": "example.md",
  "content": "# Updated",
  "revision": "1723581123456789000:10",
  "last_modified": "2026-08-14T12:00:00+00:00"
}
```

Conflict rules are:

1. If `revision` is supplied, compare it with the current server revision.
2. Otherwise, if `last_modified` is supplied, use the existing timestamp comparison for compatibility with a previously cached client.
3. If neither is supplied, preserve the current API behavior and allow the save.

A successful response includes both `modified` and the new `revision`. A `409` conflict includes `server_modified`, `server_revision`, and `server_content` so the browser preserves the user’s work and can support a later merge UI.

The route continues to validate the path against the base directory. It will also require the target to be an existing regular `.md` file before saving.

### 5. Browser editor state

`editor.js` will track `revision` per tab alongside `lastModified`. Save and autosave requests send the active tab’s revision and update it only after a successful response.

The editor exposes one small read-only integration surface:

```javascript
window.mdEditor = {
    isActive: function () {},
    getActivePath: function () {},
    getActiveContent: function () {},
    getActiveRevision: function () {},
    handleFileModified: function (path, revision) {}
};
```

This replaces the unused `window._cmEditor` assumption in `ai-assistant.js`. When edit mode is active, the AI request uses the active tab’s path and unsaved CodeMirror content. Outside edit mode, the existing content API remains the source.

`live-reload.js` delegates active-editor events to `handleFileModified`. A matching revision is the app’s already-acknowledged save and produces no warning. A different revision is external and keeps the existing warning behavior.

The editor marks a save as in flight before sending it. If a watcher event arrives before that save response, `handleFileModified` queues the event instead of warning immediately. When the save settles, the editor compares the queued revision with the server response:

- Matching successful revision: treat it as the app’s own save and ignore it.
- Different successful revision: treat it as an external change and warn.
- Failed save: treat the queued event as external and warn.

This ordering rule avoids relying on timing assumptions between the save response and the independent SSE connection. In view mode, a matching current document still reloads normally.

### 6. Local history behavior

This release retains browser-local snapshots but removes silent truncation. A snapshot is stored in full only when the document is at or below 200 KiB. For a larger document, history storage is skipped and the user receives one non-repeating notice for that editing session.

The limit prevents localStorage exhaustion while ensuring that a visible history entry is always a complete restorable document. History keys will use a `v2` prefix. Existing entries from the truncating format are left untouched in localStorage but are no longer displayed or restored because their missing content cannot be recovered safely.

### 7. Python and launcher contract

`requires-python` will become `>=3.10`, matching the source syntax and the current upstream OpenAI Python major version's minimum supported version. The lockfile will be regenerated from that declared floor.

`launch-md-viewer.bat` will:

- Derive `PROJECT_DIR` from `%~dp0`.
- Use the first argument as `SERVE_DIR` when provided.
- Default `SERVE_DIR` to the launcher directory.
- Preserve the existing delayed browser opening and visible server console.
- Quote all paths so directories containing spaces work.

The executable entry point remains unchanged.

### 8. Documentation alignment

Documentation will be updated only where this release changes facts:

- Supported Python version.
- SSE and watcher event behavior.
- Editor save revision contract.
- Portable launcher usage.
- Removal of already-completed AI integration from the future-upgrades list.

The previously identified offline, accessibility, duplicate-tree, export, Git, and command-palette work remains documented as future work.

---

## Data Flows

### Save flow

```text
User edits active CodeMirror tab
  -> browser marks that tab dirty
  -> save sends path + content + revision
  -> server validates path and current revision
  -> server atomically replaces the file
  -> response returns new modified timestamp + revision
  -> tab records the new revision and clears dirty state
  -> watcher emits file_modified with that revision
  -> editor recognizes its acknowledged revision and suppresses a false warning
     even if the SSE event arrived before the save response
```

### External change flow

```text
External editor changes a Markdown file
  -> watchdog classifies the filesystem event
  -> file_modified includes the new revision
  -> view mode reloads the matching document
  -> edit mode compares revisions
     -> same revision: ignore
     -> different revision: warn and preserve unsaved editor content
```

### AI context flow

```text
User submits an AI prompt
  -> if editor active: read active tab path + unsaved content from window.mdEditor
  -> otherwise: fetch current document content from the server
  -> send prompt and selected document context to /api/ai/ask
  -> render the existing assistant response or error state
```

---

## Error Handling

- Atomic-write failures return a JSON error without replacing the original file.
- A failed temporary-file cleanup does not mask the original write error.
- Missing, non-file, non-Markdown, and path-traversal save targets are rejected.
- Revision conflicts return `409` and never overwrite server content.
- Watcher stat failures omit the revision but still send the appropriate event.
- Watcher events received during an in-flight save are queued until the save result establishes whether they are local or external.
- An unavailable editor integration falls back to the server content API for AI context.
- localStorage quota or serialization failures do not block editing or saving; history becomes unavailable for that snapshot and the user is notified once.

---

## Files to Change

| File | Change |
| --- | --- |
| `src/md_preview_server/app.py` | Immediate SSE handshake, revision fields, atomic-save integration, stricter save target checks |
| `src/md_preview_server/storage.py` | New focused revision and atomic-write helpers |
| `src/md_preview_server/watcher.py` | Complete event classification, revision payloads, bounded debounce state |
| `src/md_preview_server/static/js/editor.js` | Per-tab revisions, public editor context API, complete snapshot behavior |
| `src/md_preview_server/static/js/live-reload.js` | Revision-aware own-save suppression and external-change warning |
| `src/md_preview_server/static/js/ai-assistant.js` | Use active editor path and unsaved content |
| `src/md_preview_server/templates/view.html` | Bump editor asset version if needed to avoid stale immutable caching |
| `pyproject.toml` | Raise minimum Python to 3.10 |
| `uv.lock` | Regenerate for the supported Python floor |
| `launch-md-viewer.bat` | Remove absolute paths and accept an optional served-directory argument |
| `tests/test_app.py` | Verify immediate SSE output |
| `tests/test_editor.py` | Verify revision responses, conflicts, atomic-save outcomes, and target restrictions |
| `tests/test_watcher.py` | New watcher event-classification regression coverage |
| `tests/test_storage.py` | New storage-helper regression coverage |
| `README.md` | Supported Python and launcher usage |
| `CLAUDE.md` | Updated API and watcher contracts |
| `docs/project-summary.md` | Updated data flow and API schemas |
| `future_upgrades.md` | Remove completed AI integration entry and retain deferred work |

---

## Verification Strategy

Tests are added after the implementation changes, in accordance with the repository workflow.

### Automated checks

```powershell
uv sync --extra dev --locked
uv run pytest -q --durations=10
```

Required coverage:

- `/events` returns its initial comment without a 30-second wait.
- Existing SSE subscriber cleanup still works.
- Watcher create, modify, delete, rename, and atomic-replace cases emit the intended event type and path.
- The debounce structure removes expired entries.
- Content responses include a revision.
- Saves with the current revision succeed and return a new revision.
- Saves with a stale revision return `409` without changing the file.
- The legacy `last_modified` path remains temporarily compatible.
- Save rejects directories, non-Markdown files, missing targets, and path traversal.
- Atomic-write failure leaves the original file intact and cleans up its temporary file when possible.
- Existing renderer, export, file-operation, and search tests remain green.

### Manual checks

The flow under test is: app loads -> Markdown file opens -> edit and save -> live preview remains stable -> external edit produces a warning -> AI sees unsaved active-tab content.

Verify on Windows:

1. Launch from a repository path containing spaces.
2. Launch with and without an explicit served-directory argument.
3. Open two documents in editor tabs and confirm AI context follows the active tab.
4. Save a document and confirm no false external-change warning appears.
5. Modify, create, rename, and delete Markdown files in an external editor or File Explorer and confirm the UI reacts correctly.
6. Force a conflict and confirm unsaved browser content is preserved.
7. Confirm a document larger than 200 KiB remains editable and receives a clear history-limit notice.
8. Check browser console errors and the primary desktop and mobile layouts; this release should not introduce visual changes.

---

## Acceptance Criteria

- The full test suite passes and no individual SSE test waits for the 30-second keepalive.
- A browser receives the SSE connection immediately.
- External Markdown create, modify, delete, and move operations update the correct UI surface.
- Successful app saves do not trigger a false external-change warning.
- A stale editor revision cannot overwrite newer file content.
- A failed save cannot leave a partially written target file.
- AI requests use the active tab’s unsaved content while editing.
- Every visible history entry contains a complete restorable document.
- Package metadata and code agree on Python 3.10+.
- The batch launcher contains no machine-specific absolute path.
- Existing local single-user behavior remains intact.
- No offline asset pipeline, search index, new product feature, or broad refactor enters this release.

---

## Deferred Follow-Up Releases

1. **Offline and performance:** bundle browser dependencies, separate tree/content cache invalidation, benchmark large workspaces, and add an incremental content index if justified.
2. **UX and accessibility:** remove the duplicate homepage tree, improve contrast and touch targets, consolidate document actions, and add a command palette.
3. **Workspace and AI features:** backlinks, tags, Git awareness, streaming provider adapters, selected-text actions, and diff-before-apply editing.
