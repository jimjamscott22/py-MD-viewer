# Complete P2 and Reliability Findings Implementation Plan

> **For agentic workers:** Execute this plan inline and sequentially in the current workspace. Repository instructions prohibit worktrees, parallel subagents, test-first loops, and automatic execution without user approval.

**Goal:** Close the final explicitly tagged P2 finding and the remaining broader reliability findings without reopening the completed P1, scan/search-bounding, SSE, watcher, or revision-aware live-reload work.

**Architecture:** Keep the existing local Flask and browser-JavaScript architecture. Make direct, narrowly scoped changes at the packaging, editor integration, browser state, metadata, launcher, and documentation boundaries; each task ends with focused verification and its own commit gate.

**Tech Stack:** Python 3.10+, Flask, vanilla JavaScript, CodeMirror, watchdog, Server-Sent Events, uv, pytest, PyInstaller, Windows batch scripts.

**Spec:** `docs/superpowers/specs/2026-08-14-foundation-reliability-upgrade-design.md`

## Global Constraints

- Work only in the current checkout; do not create a worktree or dispatch subagents.
- Present each task for approval before implementation and execute tasks sequentially.
- Implement first, then add or run regression coverage; do not use a test-driven loop.
- Preserve unrelated working-tree changes and stage only the files named by the active task.
- Keep the product a trusted, local, single-user Flask application bound to `127.0.0.1`.
- Do not introduce a frontend framework, database, authentication, native shell, or broad `app.py` refactor.
- Set the supported Python floor to exactly `>=3.10`.
- Store history snapshots completely only when their UTF-8 size is at most `200 * 1024` bytes.
- Do not push, publish, or combine task commits unless the user explicitly requests it.
- Use a repository-local uv cache such as `.cache/uv` if the global Windows uv cache is inaccessible.

## Current Baseline

- `de5c072` completed both P1 data-loss findings: stable content/revision snapshots and tab-safe revision-aware atomic saves.
- `f9090fe` completed three P2 findings: retry invalidated scans, skip disappearing files, and bound content-search work.
- `115c241` completed the SSE handshake, watcher classification, revision-bearing file events, and active-editor live-reload behavior.
- One explicitly tagged P2 remains: the standalone executable declares `openai` as a hidden import without installing the `ai` extra.
- Broader findings remain in AI active-tab context, complete local history, stale search response invalidation, background-tab external-change notices, Python metadata, launcher portability, and documentation alignment.

---

### Task 1: Include AI Support in the Standalone Executable (Remaining P2)

**Files:**

- Modify: `build-exe.bat:16-26`
- Modify: `README.md` standalone-build instructions, added beside the usage/development guidance

**Interfaces:**

- Consumes: optional dependency group `ai = ["openai>=1.0.0"]` from `pyproject.toml`.
- Produces: a PyInstaller invocation whose isolated environment contains both `PyInstaller` and `openai`; the existing `--hidden-import openai` remains valid.

- [ ] **Step 1: Update the isolated build command**

  Change the command prefix in `build-exe.bat` to install the project AI extra while retaining the temporary PyInstaller tool dependency:

  ```bat
  uv run --extra ai --with pyinstaller pyinstaller ^
  ```

  Keep the existing `--onefile`, template/static data, Markdown extension collections, and `--hidden-import openai` arguments unchanged.

- [ ] **Step 2: Document the executable contract**

  Add a concise README subsection that states:

  - `build-exe.bat` creates `dist\md-viewer.exe`.
  - The executable includes the OpenAI client used for OpenAI-compatible local or remote endpoints.
  - Runtime configuration still comes from `OPENAI_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`.

- [ ] **Step 3: Verify dependency availability before the full build**

  Run:

  ```powershell
  $env:UV_CACHE_DIR = '.cache\uv'
  uv run --extra ai --with pyinstaller python -c "import openai, PyInstaller; print(openai.__version__)"
  ```

  Expected: exit code `0`; neither import raises `ImportError`.

- [ ] **Step 4: Build and smoke-test the executable**

  Run `build-exe.bat`, confirm `dist\md-viewer.exe` exists, launch it from a temporary directory containing one Markdown file, and request `/` plus `/api/ai/ask`.

  Acceptance:

  - `/` returns HTTP `200`.
  - `/api/ai/ask` may return a provider connection/configuration error when no model endpoint is running, but it must not return the `501` missing-OpenAI error.
  - Stop the temporary executable process after the probe; do not commit `dist/` or other build output.

- [ ] **Step 5: Run repository checks**

  ```powershell
  $env:UV_CACHE_DIR = '.cache\uv'
  uv run pytest tests/test_startup.py -v
  git diff --check
  ```

- [ ] **Step 6: Review and commit this task**

  Stage only `build-exe.bat` and `README.md` after user approval.

  Suggested commit: `fix: include AI support in standalone build`

---

### Task 2: Use the Active Editor Tab for AI Context

**Files:**

- Modify: `src/md_preview_server/static/js/ai-assistant.js:7-70`
- Modify: `src/md_preview_server/static/js/editor.js:43-110`
- Modify: `src/md_preview_server/static/css/style.css:1009-1025`
- Modify: `src/md_preview_server/templates/view.html:251`

**Interfaces:**

- Consumes: `window.mdEditor.isActive()`, `getActivePath()`, and `getActiveContent()` from `editor.js`.
- Produces: `/api/ai/ask` request bodies whose `document_content` is the active tab's current unsaved content; view mode continues to use `/api/content/<path>`.

- [ ] **Step 1: Replace the obsolete editor lookup**

  In the submit handler, make `filepath` mutable and select context with this precedence:

  ```javascript
  let filepath = docPathEl ? docPathEl.textContent.trim() : "";
  let documentContent = "";
  const editor = window.mdEditor;

  if (editor && editor.isActive()) {
      filepath = editor.getActivePath();
      documentContent = editor.getActiveContent();
  } else {
      // Preserve the existing /api/content fallback and rendered-text fallback.
  }
  ```

  Remove the unused `window._cmEditor` branch. Validate `filepath` after active-editor selection so a secondary editor tab can supply its own path.

- [ ] **Step 2: Keep failure behavior bounded**

  If `window.mdEditor` is absent or reports inactive, retain the current server-content lookup. If active editor access returns an empty path, show the existing “No document is currently open” message and do not send an AI request.

- [ ] **Step 3: Keep the Assistant available during editing**

  When entering edit mode, keep `#doc-shell` visible, move `#editor-container` into the shell's main grid column, hide only `.doc-main`, and leave `#doc-sidebar-panel` interactive. Restore `.doc-main` when exiting edit mode. Add a narrow `.editor-mode` layout class so the editor can shrink inside the grid without overflowing.

- [ ] **Step 4: Bust the changed asset caches**

  Change the template includes to:

  ```html
  <script src="{{ url_for('static', filename='js/editor.js') }}?v=7"></script>
  <script src="{{ url_for('static', filename='js/ai-assistant.js') }}?v=2"></script>
  ```

- [ ] **Step 5: Run static and backend checks**

  ```powershell
  node --check src/md_preview_server/static/js/ai-assistant.js
  node --check src/md_preview_server/static/js/editor.js
  $env:UV_CACHE_DIR = '.cache\uv'
  uv run pytest tests/test_app.py tests/test_editor.py -q
  git diff --check
  ```

- [ ] **Step 6: Verify active-tab behavior in a browser**

  Intercept `/api/ai/ask` or point it at a controlled local endpoint, then:

  1. Open document A and document B as editor tabs.
  2. Add distinct unsaved text to both tabs.
  3. Confirm the Assistant sidebar remains visible in edit mode, then submit from document B and confirm the request contains B's path/content.
  4. Switch to A, submit again, and confirm the request contains A's path/content.
  5. Exit edit mode and confirm view mode obtains context from `/api/content`.
  6. Confirm the browser console has no errors.

- [ ] **Step 7: Review and commit this task**

  Stage the four Task 2 source files and this amended plan after user approval.

  Suggested commit: `fix: use active editor content for AI context`

---

### Task 3: Store Only Complete Local-History Snapshots

**Files:**

- Modify: `src/md_preview_server/static/js/editor.js:301-347`
- Modify: `src/md_preview_server/templates/view.html:250`

**Interfaces:**

- Consumes: `window.showToast(message, type)` and browser `TextEncoder`/`localStorage`.
- Produces: history keys prefixed with `mdv-history-v2-`; every displayed v2 entry contains the full restorable document.

- [ ] **Step 1: Introduce explicit history constants and notice state**

  Add near the current autosave/history state:

  ```javascript
  var HISTORY_MAX_BYTES = 200 * 1024;
  var HISTORY_KEY_PREFIX = "mdv-history-v2-";
  var _historyNoticeShown = false;

  function _historyKey(path) {
      return HISTORY_KEY_PREFIX + encodeURIComponent(path);
  }
  ```

  The v2 key deliberately leaves legacy truncated `mdv-history-...` entries untouched and invisible.

- [ ] **Step 2: Replace truncation with an all-or-nothing write**

  Compute the UTF-8 byte count with `new TextEncoder().encode(content).length`. If it exceeds `HISTORY_MAX_BYTES`, return without calling `localStorage.setItem` and show this notice once per editor session:

  ```text
  History snapshot skipped because this document is larger than 200 KiB.
  ```

  Otherwise store `content` unchanged, retain at most ten snapshots, and keep the existing timestamp/label fields.

- [ ] **Step 3: Surface storage failures once without blocking editing**

  Replace the empty `catch` with a one-time informational toast such as:

  ```text
  Local history is unavailable for this editing session.
  ```

  `saveSnapshot` must not throw into open/save/autosave flows.

- [ ] **Step 4: Bump the editor asset version**

  Change `editor.js?v=7` to `editor.js?v=8` in `view.html`.

- [ ] **Step 5: Run static and backend regression checks**

  ```powershell
  node --check src/md_preview_server/static/js/editor.js
  $env:UV_CACHE_DIR = '.cache\uv'
  uv run pytest tests/test_editor.py -q
  git diff --check
  ```

- [ ] **Step 6: Verify history boundaries in a browser**

  Use controlled documents and inspect localStorage:

  - A document at or below `204800` UTF-8 bytes creates a v2 entry with byte-for-byte complete content.
  - A document above `204800` UTF-8 bytes creates no entry and shows one notice even after repeated save/autosave attempts.
  - A multi-byte UTF-8 document is measured by bytes, not JavaScript character count.
  - A pre-existing `mdv-history-...` entry is neither listed nor restored.
  - A forced `localStorage.setItem` failure does not interrupt editing or saving and produces only one notice.

- [ ] **Step 7: Review and commit this task**

  Stage only `editor.js` and `view.html` after user approval.

  Suggested commit: `fix: keep editor history snapshots complete`

---

### Task 4: Invalidate Search Responses When Search Is Cleared

**Files:**

- Modify: `src/md_preview_server/static/js/navigation.js:120-252`
- Modify: `src/md_preview_server/templates/base.html:153`

**Interfaces:**

- Consumes: the existing `currentRequestId` response guard inside `initSearch()`.
- Produces: a `resetSearch()` closure that invalidates every outstanding filename/content response before restoring the tree.

- [ ] **Step 1: Move reset logic into the search closure**

  Define `resetSearch` inside `initSearch`, after `currentRequestId`, so it can increment the guard:

  ```javascript
  function resetSearch() {
      currentRequestId += 1;
      if (!sidebarTree || !searchResults) return;
      sidebarTree.style.display = "";
      searchResults.style.display = "none";
      searchResults.innerHTML = "";
  }
  ```

  Remove the outer sibling `resetSearch` function. Keep every existing caller—empty input, Escape, short content queries, mode changes, and fetch errors—using the new closure.

- [ ] **Step 2: Preserve response ordering**

  Keep `var requestId = ++currentRequestId` at the start of `runSearch` and retain all `requestId !== currentRequestId` guards. Do not introduce a new search API or change result rendering.

- [ ] **Step 3: Bust the navigation asset cache**

  Change the base template include to:

  ```html
  <script src="{{ url_for('static', filename='js/navigation.js') }}?v=2"></script>
  ```

- [ ] **Step 4: Run static and API checks**

  ```powershell
  node --check src/md_preview_server/static/js/navigation.js
  $env:UV_CACHE_DIR = '.cache\uv'
  uv run pytest tests/test_api.py -q
  git diff --check
  ```

- [ ] **Step 5: Verify delayed responses in a browser**

  Delay `/api/search` and `/api/search/content` responses, clear the input before each response completes, and confirm:

  - The file tree remains visible.
  - Search results remain hidden and empty.
  - Escape behaves the same way.
  - Starting a second query prevents the first response from replacing the second result set.

- [ ] **Step 6: Review and commit this task**

  Stage only `navigation.js` and `base.html` after user approval.

  Suggested commit: `fix: invalidate cleared search requests`

---

### Task 5: Defer External-Change Warnings for Background Editor Tabs

**Files:**

- Modify: `src/md_preview_server/static/js/editor.js:140-177, 464-540`
- Modify: `src/md_preview_server/templates/view.html:250`

**Interfaces:**

- Consumes: revision-bearing `file_modified` events and the existing per-tab `revision`, `saveInFlight`, `pendingFileEvent`, and `pendingFileRevision` fields.
- Produces: per-tab `externalChangePending` and `externalChangeNotified` state; changing a background tab never reloads the page and warns when that tab becomes active.

- [ ] **Step 1: Track external-change state per tab**

  Add these fields when creating each tab:

  ```javascript
  externalChangePending: false,
  externalChangeNotified: false
  ```

  Add a helper that marks a tab external, refreshes the tab bar, and immediately calls `showExternalChange(tab)` only when the tab is active.

- [ ] **Step 2: Match file events against every open tab**

  Change `handleFileModified(path, revision)` to find the tab whose normalized `filePath` matches `path`, not only `_activeTabId`.

  Preserve these rules:

  - Matching acknowledged revision: consume without warning.
  - Save in flight: continue using `pendingFileEvent`/`pendingFileRevision` until the save response resolves ownership.
  - Different or missing revision: mark that matching tab as externally changed.
  - No matching open tab: return `false` without changing editor state.

- [ ] **Step 3: Warn once when a changed background tab activates**

  In `_activateTab`, after synchronizing active state:

  - If `externalChangePending` is true, set the status to `Changed on disk`.
  - Show the existing toast only if `externalChangeNotified` is false, then set it true.
  - Keep `externalChangePending` until the tab is reloaded/reopened or a successful, revision-valid save establishes a new accepted revision.

  Optionally append a non-interactive marker to the existing tab label, but do not add new controls or a merge UI.

- [ ] **Step 4: Clear state only on accepted state transitions**

  Clear both external flags when a fresh tab load succeeds and when a successful save is known to represent the accepted latest revision. Do not clear them on a `409` conflict or network failure.

- [ ] **Step 5: Bump the editor asset version**

  Increment the editor query version from `v=8` to `v=9` after Task 3 has landed. If Task 3 has not landed, increment the current version once and record the actual value in the commit.

- [ ] **Step 6: Run static and backend regression checks**

  ```powershell
  node --check src/md_preview_server/static/js/editor.js
  $env:UV_CACHE_DIR = '.cache\uv'
  uv run pytest tests/test_editor.py tests/test_watcher.py tests/test_app.py -q
  git diff --check
  ```

- [ ] **Step 7: Verify tab/event ordering in a browser**

  Cover all four sequences:

  1. Modify background tab B externally while A is active; A stays stable, then B warns when activated.
  2. Activate B repeatedly; the toast appears once while the status still reflects the external change.
  3. Save A normally; A receives no false warning.
  4. Deliver B's watcher event before B's save response; a matching save revision is suppressed, while a different revision warns.

- [ ] **Step 8: Review and commit this task**

  Stage only `editor.js` and `view.html` after user approval.

  Suggested commit: `fix: retain background tab change warnings`

---

### Task 6: Align the Supported Python Floor

**Files:**

- Modify: `pyproject.toml:6`
- Modify: `uv.lock:3`
- Modify: `README.md:20-24`

**Interfaces:**

- Consumes: source syntax already requiring Python 3.10 or newer.
- Produces: package metadata, lock metadata, and user documentation that consistently state Python `>=3.10`.

- [ ] **Step 1: Update package metadata**

  Change:

  ```toml
  requires-python = ">=3.10"
  ```

- [ ] **Step 2: Regenerate the lockfile**

  Run:

  ```powershell
  $env:UV_CACHE_DIR = '.cache\uv'
  uv lock
  ```

  Confirm `uv.lock` records `requires-python = ">=3.10"` and review dependency changes so the task does not silently upgrade unrelated packages beyond what regeneration requires.

- [ ] **Step 3: Update the README requirement**

  Replace `Python 3.9+` with `Python 3.10+`. Keep the optional Python 3.11 virtual-environment example as an example, not the minimum.

- [ ] **Step 4: Verify the declared floor**

  ```powershell
  $env:UV_CACHE_DIR = '.cache\uv'
  uv lock --check
  uv run --python 3.10 --extra dev pytest -q
  git diff --check
  ```

  Expected: the complete suite passes under Python 3.10. If uv must download Python 3.10, request network approval rather than substituting a later interpreter and claiming floor compatibility.

- [ ] **Step 5: Review and commit this task**

  Stage only `pyproject.toml`, `uv.lock`, and `README.md` after user approval.

  Suggested commit: `chore: require Python 3.10 or newer`

---

### Task 7: Make the Windows Launcher Portable

**Files:**

- Modify: `launch-md-viewer.bat:1-29`
- Modify: `README.md` usage section

**Interfaces:**

- Consumes: `md-preview` console script and uv's `--project <path>` option.
- Produces: a launcher that derives the repository from `%~dp0`, serves its own directory by default, and accepts the first argument as the served directory.

- [ ] **Step 1: Replace hard-coded paths**

  Use this path contract:

  ```bat
  set "PROJECT_DIR=%~dp0"
  if "%~1"=="" (
    set "SERVE_DIR=%~dp0"
  ) else (
    set "SERVE_DIR=%~1"
  )
  ```

  Keep every use quoted. Preserve the delayed browser open, visible server console, `cd /d "%SERVE_DIR%"`, and `uv run --project "%PROJECT_DIR%" md-preview` behavior.

- [ ] **Step 2: Add a clear invalid-directory failure**

  Before opening the browser, check `if not exist "%SERVE_DIR%\."` and print the resolved input plus a non-zero exit. Do not create missing directories.

- [ ] **Step 3: Update launcher documentation**

  Add README examples for:

  ```bat
  launch-md-viewer.bat
  launch-md-viewer.bat "D:\Markdown Notes"
  ```

  State that the default is the launcher/repository directory and paths containing spaces are supported.

- [ ] **Step 4: Verify batch parsing and launch behavior on Windows**

  Run from a repository path containing spaces and with a served-directory path containing spaces:

  - No argument: `/api/files` lists Markdown files from the launcher directory.
  - Explicit argument: `/api/files` lists Markdown files from the supplied directory.
  - Missing argument path: launcher exits non-zero before opening a browser.
  - The server window stays visible and Ctrl+C still stops it.

- [ ] **Step 5: Run repository checks**

  ```powershell
  $env:UV_CACHE_DIR = '.cache\uv'
  uv run pytest tests/test_startup.py tests/test_app.py -q
  git diff --check
  ```

- [ ] **Step 6: Review and commit this task**

  Stage only `launch-md-viewer.bat` and `README.md` after user approval.

  Suggested commit: `fix: make Windows launcher path portable`

---

### Task 8: Align Documentation and Run the Final Reliability Gate

**Files:**

- Modify: `CLAUDE.md:37-62`
- Modify: `docs/project-summary.md` architecture, SSE/watcher, editor, AI, dependency, and launcher sections
- Modify: `future_upgrades.md:19-25`
- Review: `README.md`

**Interfaces:**

- Consumes: the final contracts delivered by Tasks 1-7 and the already completed commits `de5c072`, `f9090fe`, and `115c241`.
- Produces: documentation that describes current behavior and a final evidence-backed completion report.

- [ ] **Step 1: Update maintainer guidance**

  In `CLAUDE.md`, document:

  - The immediate SSE handshake and `file_modified`/`tree_changed` schema.
  - Watcher modify/create/delete/move/atomic-replace classification.
  - Revision-aware atomic save and conflict behavior.
  - `window.mdEditor` as the AI/live-reload integration boundary.
  - Python 3.10+ and the portable launcher contract.

- [ ] **Step 2: Update the project summary**

  Align `docs/project-summary.md` with the same contracts. Do not redesign its diagrams unless a diagram contains a now-false statement; make the smallest factual edits required.

- [ ] **Step 3: Remove the completed generic AI future item**

  Delete `### AI Assistant Integration` from `future_upgrades.md` because the assistant already exists. If future AI work remains useful, replace it with a narrowly future-facing item such as streaming responses, selected-text actions, provider settings, or diff-before-apply editing—features not claimed as complete by this plan.

- [ ] **Step 4: Audit for stale claims**

  Run targeted searches and resolve every false hit:

  ```powershell
  rg -n "Python 3\.9|window\._cmEditor|content\.slice\(0, 51200\)|D:\\Code\\Python\\PythonApps\\py-MD-viewer|AI Assistant Integration" README.md CLAUDE.md future_upgrades.md docs src build-exe.bat launch-md-viewer.bat pyproject.toml uv.lock
  ```

  Expected: no stale Python floor, obsolete AI editor integration, truncated-history implementation, machine-specific launcher path, or already-completed generic AI future item remains.

- [ ] **Step 5: Run the full automated verification gate**

  ```powershell
  $env:UV_CACHE_DIR = '.cache\uv'
  uv sync --extra dev --locked
  uv run pytest -q --durations=10
  uv run python -m compileall -q src tests
  node --check src/md_preview_server/static/js/editor.js
  node --check src/md_preview_server/static/js/ai-assistant.js
  node --check src/md_preview_server/static/js/navigation.js
  node --check src/md_preview_server/static/js/live-reload.js
  uv lock --check
  git diff --check
  ```

- [ ] **Step 6: Run consolidated Windows/browser acceptance checks**

  Verify:

  1. Launcher works with default and explicit spaced paths.
  2. The standalone executable starts and contains the OpenAI client.
  3. AI requests follow the active editor tab and include unsaved content.
  4. History stores complete documents through 200 KiB and skips larger documents with one notice.
  5. Cleared or superseded searches cannot repaint stale results.
  6. Background-tab external edits warn when that tab activates.
  7. Normal saves do not produce false external-change warnings.
  8. External create, modify, rename, and delete operations update the correct UI surface.
  9. Browser console contains no new errors or warnings.

- [ ] **Step 7: Reconcile the original finding ledger**

  Report each original P1/P2 and broader finding as `fixed`, `deferred by explicit scope`, or `not verified`. Do not use “all findings complete” unless every item has current code evidence and its specified verification passed.

- [ ] **Step 8: Review and commit documentation**

  Stage only the documentation files changed by this task after user approval.

  Suggested commit: `docs: align reliability and portability contracts`

---

## Final Acceptance Criteria

- All two P1 and four P2 findings are fixed; the standalone build no longer returns the missing-OpenAI `501` caused by an absent bundled client.
- AI requests use the active editor tab's path and unsaved content.
- Every visible history snapshot is complete, and documents above 200 KiB do not create misleading entries.
- Clearing or replacing a search invalidates older responses.
- External changes to background tabs are retained and surfaced on activation without reloading under the editor.
- Package metadata, lock metadata, and documentation agree on Python 3.10+.
- `launch-md-viewer.bat` contains no machine-specific absolute path and accepts an optional served-directory argument.
- The full Python suite, JavaScript syntax checks, Python compilation, lock check, and diff check pass from a clean verification run.
- Windows build, launcher, and browser checks are reported as verified only when actually performed.
- Each task remains a separate review and commit boundary; no push occurs without explicit user instruction.

## Scope Deliberately Deferred

- Offline bundling of CodeMirror, Mermaid, KaTeX, or fonts.
- Search indexing or broader performance redesign beyond the completed bounded-search work.
- Accessibility/visual redesign, duplicate-tree removal, and command palette work.
- Streaming AI, provider UI, selected-text actions, and diff/apply editing.
- Authentication, collaboration, public hosting, native desktop wrappers, installers, or tray behavior.
