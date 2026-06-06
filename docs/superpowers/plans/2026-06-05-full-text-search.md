# Full-Text Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content-search mode to the sidebar that scans `.md` file bodies for keyword matches and shows results with contextual snippets.

**Architecture:** A new `GET /api/search/content?q=` route scans files line-by-line and returns `{path, line_number, snippet}` results (max 50). The existing sidebar search input gains a mode-toggle button; when in content mode `navigation.js` calls the new endpoint and renders snippet results into the existing `#search-results` panel.

**Tech Stack:** Python/Flask (backend), plain ES5 JavaScript (frontend), Jinja2 HTML templates, CSS custom properties.

---

## File Map

| File | Change |
|---|---|
| `src/md_preview_server/app.py` | Add `GET /api/search/content` route after line 250 |
| `src/md_preview_server/templates/base.html` | Wrap search input in a flex row; add mode-toggle button |
| `src/md_preview_server/static/js/navigation.js` | Add mode state + `renderContentResults()` to `initSearch()` |
| `src/md_preview_server/static/css/style.css` | Add `.search-mode-toggle`, `.search-snippet`, `mark` styles |
| `tests/test_api.py` | Add tests for the new content search endpoint |

---

## Task 1: Backend — `/api/search/content` route

**Files:**
- Modify: `src/md_preview_server/app.py:250`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_api.py`:

```python
# --- Content search ---

def test_api_search_content_returns_empty_for_short_query(client):
    response = client.get("/api/search/content?q=a")
    assert response.status_code == 200
    data = response.get_json()
    assert data["results"] == []


def test_api_search_content_finds_match(client):
    response = client.get("/api/search/content?q=test file")
    data = response.get_json()
    assert any(r["path"] == "hello.md" for r in data["results"])


def test_api_search_content_returns_snippet(client):
    response = client.get("/api/search/content?q=test file")
    data = response.get_json()
    result = next(r for r in data["results"] if r["path"] == "hello.md")
    assert "test file" in result["snippet"].lower()
    assert "line_number" in result


def test_api_search_content_no_match_returns_empty(client):
    response = client.get("/api/search/content?q=zzznomatch")
    data = response.get_json()
    assert data["results"] == []


def test_api_search_content_case_insensitive(client):
    response = client.get("/api/search/content?q=HELLO")
    data = response.get_json()
    assert any(r["path"] == "hello.md" for r in data["results"])


def test_api_search_content_skips_excluded_dirs(client):
    response = client.get("/api/search/content?q=ignore")
    data = response.get_json()
    assert not any(".venv" in r["path"] for r in data["results"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_api.py::test_api_search_content_finds_match -v
```

Expected output: `FAILED` with `404` or `AttributeError` (route doesn't exist yet).

- [ ] **Step 3: Implement the route**

In `src/md_preview_server/app.py`, insert the following block directly after the closing of `api_search()` (after line 250, before `# --- Phase 2`):

```python
    @app.route("/api/search/content")
    def api_search_content():
        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify({"results": []})
        query_lower = query.lower()
        base = app.config["BASE_DIR"]
        results = []
        for f in get_file_list(base):
            if len(results) >= 50:
                break
            target = validate_path(base, f["path"])
            if not target.exists():
                continue
            try:
                lines = target.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    start = max(0, i - 1)
                    end = min(len(lines), i + 2)
                    snippet = "\n".join(lines[start:end])
                    if len(snippet) > 200:
                        snippet = snippet[:200]
                    results.append({
                        "path": f["path"],
                        "line_number": i + 1,
                        "snippet": snippet,
                    })
                    if len(results) >= 50:
                        break
        return jsonify({"results": results, "truncated": len(results) >= 50})
```

- [ ] **Step 4: Run all content search tests to verify they pass**

```bash
uv run pytest tests/test_api.py -k "content" -v
```

Expected output: all 6 tests `PASSED`.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
uv run pytest -v
```

Expected output: all tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add src/md_preview_server/app.py tests/test_api.py
git commit -m "feat: add /api/search/content endpoint for full-text search"
```

---

## Task 2: Frontend HTML — mode toggle button

**Files:**
- Modify: `src/md_preview_server/templates/base.html:34-36`

- [ ] **Step 1: Replace the `.sidebar-search` block**

Find this block in `base.html` (lines 34–36):

```html
        <div class="sidebar-search">
            <input type="text" id="search-input" placeholder="Search files or press /" autocomplete="off">
        </div>
```

Replace it with:

```html
        <div class="sidebar-search">
            <div class="search-bar-row">
                <input type="text" id="search-input" placeholder="Search files or press /" autocomplete="off">
                <button class="search-mode-toggle" id="search-mode-toggle" title="Switch to content search" aria-pressed="false">
                    <span class="search-mode-label">name</span>
                </button>
            </div>
        </div>
```

- [ ] **Step 2: Commit**

```bash
git add src/md_preview_server/templates/base.html
git commit -m "feat: add content search mode toggle button to sidebar"
```

---

## Task 3: Frontend CSS — snippet and toggle styles

**Files:**
- Modify: `src/md_preview_server/static/css/style.css` (after line 749, after the `.search-no-results` block)

- [ ] **Step 1: Add the new styles**

Insert the following CSS block after the `.search-no-results` rule (after line 749):

```css
.search-bar-row {
    display: flex;
    gap: 6px;
    align-items: center;
}

.search-bar-row input {
    flex: 1;
    min-width: 0;
}

.search-mode-toggle {
    flex-shrink: 0;
    padding: 6px 8px;
    border: 1px solid var(--color-border);
    border-radius: 2px;
    background: var(--color-surface-strong);
    color: var(--color-text-secondary);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    cursor: pointer;
    transition: border-color 0.12s, color 0.12s;
    white-space: nowrap;
}

.search-mode-toggle:hover {
    border-color: var(--color-accent);
    color: var(--color-text);
}

.search-mode-toggle.is-active {
    border-color: var(--color-accent);
    color: var(--color-accent);
    box-shadow: var(--glow-sm);
}

.search-content-result {
    padding: 6px 18px;
    border-bottom: 1px solid var(--color-border);
}

.search-content-result:last-child {
    border-bottom: none;
}

.search-content-result a {
    display: block;
    font-size: 0.84rem;
    color: var(--color-accent);
    margin-bottom: 4px;
}

.search-content-result a:hover {
    text-decoration: underline;
}

.search-snippet {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
    max-height: 4.5em;
    overflow: hidden;
}

mark {
    background: transparent;
    color: var(--color-accent);
    font-weight: 700;
    text-shadow: var(--glow-sm);
}

.search-truncated-notice {
    padding: 6px 18px;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    font-style: italic;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/md_preview_server/static/css/style.css
git commit -m "feat: add content search snippet and toggle styles"
```

---

## Task 4: Frontend JS — content search mode in `initSearch()`

**Files:**
- Modify: `src/md_preview_server/static/js/navigation.js:112-160`

- [ ] **Step 1: Replace `initSearch()` with the mode-aware version**

Find the entire `initSearch` function (lines 112–160) and replace it with:

```javascript
    function initSearch() {
        if (!searchInput) {
            return;
        }

        var searchMode = "filename"; // "filename" | "content"
        var modeToggleBtn = document.getElementById("search-mode-toggle");
        var modeLabelEl = modeToggleBtn ? modeToggleBtn.querySelector(".search-mode-label") : null;

        function setSearchMode(mode) {
            searchMode = mode;
            var isContent = mode === "content";
            if (modeToggleBtn) {
                modeToggleBtn.classList.toggle("is-active", isContent);
                modeToggleBtn.setAttribute("aria-pressed", isContent ? "true" : "false");
                modeToggleBtn.setAttribute("title", isContent ? "Switch to filename search" : "Switch to content search");
            }
            if (modeLabelEl) {
                modeLabelEl.textContent = isContent ? "text" : "name";
            }
            searchInput.placeholder = isContent ? "Search file content..." : "Search files or press /";
            var query = searchInput.value.trim();
            if (query) {
                runSearch(query);
            } else {
                resetSearch();
            }
        }

        if (modeToggleBtn) {
            modeToggleBtn.addEventListener("click", function () {
                setSearchMode(searchMode === "filename" ? "content" : "filename");
            });
        }

        searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            var query = searchInput.value.trim();
            if (!query) {
                resetSearch();
                return;
            }
            debounceTimer = setTimeout(function () {
                runSearch(query);
            }, 220);
        });

        searchInput.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                searchInput.value = "";
                resetSearch();
                searchInput.blur();
            }
        });

        function runSearch(query) {
            if (searchMode === "content") {
                if (query.length < 2) {
                    resetSearch();
                    return;
                }
                fetch("/api/search/content?q=" + encodeURIComponent(query))
                    .then(function (response) { return response.json(); })
                    .then(function (data) {
                        sidebarTree.style.display = "none";
                        searchResults.style.display = "";
                        renderContentResults(data.results || [], query, data.truncated);
                    });
            } else {
                fetch("/api/search?q=" + encodeURIComponent(query))
                    .then(function (response) { return response.json(); })
                    .then(function (data) {
                        sidebarTree.style.display = "none";
                        searchResults.style.display = "";

                        if (!data.results || data.results.length === 0) {
                            searchResults.innerHTML = '<p class="empty-message">No results found.</p>';
                            return;
                        }

                        var html = '<ul class="file-tree">';
                        data.results.forEach(function (file) {
                            var size = formatSize(file.size);
                            var modified = formatDate(file.modified);
                            html += '<li class="file">';
                            html += '<span class="icon file-icon"></span>';
                            html += '<a href="/view/' + encodeURI(file.path) + '">' + escapeHtml(file.name) + '</a>';
                            html += '<span class="file-meta" title="' + size + ' | ' + modified + '">' + size + '</span>';
                            html += "</li>";
                        });
                        html += "</ul>";
                        searchResults.innerHTML = html;
                    });
            }
        }
    }

    function renderContentResults(results, query, truncated) {
        if (!results || results.length === 0) {
            searchResults.innerHTML = '<p class="empty-message">No results found.</p>';
            return;
        }

        var escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        var highlightRe = new RegExp("(" + escapedQuery + ")", "gi");

        var html = "";
        results.forEach(function (result) {
            var snippetHtml = escapeHtml(result.snippet)
                .replace(highlightRe, "<mark>$1</mark>");
            html += '<div class="search-content-result">';
            html += '<a href="/view/' + encodeURI(result.path) + '">'
                + escapeHtml(result.path) + ':' + result.line_number + '</a>';
            html += '<div class="search-snippet">' + snippetHtml + '</div>';
            html += '</div>';
        });

        if (truncated) {
            html += '<p class="search-truncated-notice">Showing first 50 results.</p>';
        }

        searchResults.innerHTML = html;
    }
```

- [ ] **Step 2: Verify the server starts without errors**

```bash
uv run md-preview --help
```

Expected: help text printed, no import errors.

- [ ] **Step 3: Commit**

```bash
git add src/md_preview_server/static/js/navigation.js
git commit -m "feat: add content search mode to sidebar navigation"
```

---

## Task 5: Manual smoke test

- [ ] **Step 1: Start the server**

```bash
uv run md-preview
```

Open `http://localhost:5000` in a browser.

- [ ] **Step 2: Verify filename search still works**

Type a filename fragment into the search bar. Confirm file results appear as before.

- [ ] **Step 3: Toggle to content mode**

Click the `name` button next to the search input. Confirm:
- Button turns accent-coloured and reads `text`
- Input placeholder changes to "Search file content..."

- [ ] **Step 4: Verify content search returns snippets**

Type a word you know exists inside one of the `.md` files. Confirm:
- Results show `path:line_number` as a clickable link
- A snippet appears below with the keyword highlighted in accent colour
- Clicking the link navigates to the document

- [ ] **Step 5: Verify edge cases**

- Type a single character in content mode — confirm no results are fetched (no network request)
- Type a string that matches nothing — confirm "No results found." message
- Toggle back to filename mode — confirm filename search works normally again

- [ ] **Step 6: Run full test suite one final time**

```bash
uv run pytest -v
```

Expected: all tests `PASSED`.
