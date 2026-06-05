# Full-Text Search — Design Spec

**Date:** 2026-06-05  
**Status:** Approved  

---

## Overview

Extend the existing filename search with a dedicated **content search mode** that scans `.md` file bodies for keyword matches and returns results with contextual snippets. The two modes coexist — filename search is unchanged; content search is an opt-in toggle.

---

## Goals

- Allow users to find text *inside* documents, not just by filename
- Keep the UI familiar — same search bar, mode toggle switches behaviour
- Plain keyword matching only (case-insensitive); no operators in this iteration
- Fast enough for real-time (as-you-type) use on typical local workspaces

---

## Non-Goals

- Full-text indexing / inverted index (future upgrade path)
- Regex, quoted-phrase, or case-sensitive operators (future upgrade path)
- Searching non-`.md` files

---

## Architecture

### Backend — `app.py`

New route added in Phase 1 (alongside the existing `/api/search`):

```
GET /api/search/content?q=<query>
```

**Behaviour:**
- Returns `{"results": []}` immediately if `len(q) < 2`
- Iterates all `.md` files via the existing `get_file_list(base)` helper
- Opens each file with UTF-8 encoding; silently skips files that raise `UnicodeDecodeError`
- Scans line-by-line with a case-insensitive `str.lower()` contains-check
- For each matching line, collects a snippet: lines `[n-1, n, n+1]` joined and capped at ~200 characters
- Returns at most **50 results** total, ordered by file path
- Response shape:

```json
{
  "results": [
    {
      "path": "notes/project.md",
      "line_number": 14,
      "snippet": "...surrounding context with the match inline..."
    }
  ]
}
```

No new imports required beyond what `app.py` already uses (`pathlib`, `os`).

---

### Frontend

#### `base.html` — sidebar search area

Add a mode-toggle icon button adjacent to `#search-input`. The button carries a `data-mode` attribute (`filename` | `content`) and a visual active state. Toggling clears the current results and re-runs the search if the input is non-empty.

#### `navigation.js` — `initSearch()` extension

- Tracks current mode (`filename` or `content`) in a local variable
- In `content` mode, calls `/api/search/content?q=` instead of `/api/search?q=`
- Debounce stays at ~300ms; skips the call if `q.length < 2`
- New `renderContentResults(results, query)` function:
  - Builds result items: **filename** (clickable → navigates to `/<path>`) + **snippet block**
  - Wraps keyword occurrences in the snippet with `<mark>` using a case-insensitive regex replace
  - Renders into the existing `#search-results` panel
- Existing `renderFileResults()` is untouched

#### `style.css`

A few targeted additions:
- `.search-snippet` — monospace font, muted colour, small font size, `white-space: pre-wrap`, max-height truncated
- `mark` — highlight colour that respects the active theme (CSS variable)
- `.search-mode-toggle` — active state styling for the toggle button

---

## Data Flow

```
User types (content mode) 
  → 300ms debounce 
  → skip if len < 2
  → GET /api/search/content?q=<query>
  → backend scans files line-by-line
  → returns [{path, line_number, snippet}] (max 50)
  → renderContentResults() highlights keyword in snippet
  → results appear in #search-results panel
  → user clicks filename → navigates to document
```

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Non-UTF-8 file | Silently skipped (no error to user) |
| Query < 2 chars | Returns empty immediately, no file I/O |
| 0 results | Renders "No results found" message |
| Very long lines | Snippet capped at ~200 chars |
| >50 matches | Truncated with a "Showing first 50 results" note |

---

## Files to Change

| File | Change |
|---|---|
| `src/md_preview_server/app.py` | Add `GET /api/search/content` route |
| `src/md_preview_server/templates/base.html` | Add mode-toggle button to sidebar search area |
| `src/md_preview_server/static/js/navigation.js` | Extend `initSearch()` with mode toggle + `renderContentResults()` |
| `src/md_preview_server/static/css/style.css` | Add `.search-snippet`, `mark`, `.search-mode-toggle` styles |

No new files. No new dependencies.

---

## Future Upgrade Path

The dedicated `/api/search/content` endpoint is a natural place to later:
- Add a file-content cache keyed by `(path, mtime)` to avoid re-reading unchanged files
- Support `?case_sensitive=true`, `?regex=true` query parameters
- Replace line scanning with an in-memory inverted index built on startup
