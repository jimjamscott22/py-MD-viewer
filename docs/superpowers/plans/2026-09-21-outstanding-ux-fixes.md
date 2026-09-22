# Outstanding UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Note: this project's CLAUDE.md disables `superpowers:test-driven-development` — implement each step directly, then verify with the given test/command; do not write a failing test first.

**Goal:** Fix the outstanding UX recommendations from `docs/ui-design-review.md` — de-duplicated file tree and document header, a promoted Edit action with a consolidated Export dropdown, and two accessibility contrast fixes.

**Architecture:** All changes are template (Jinja), CSS custom-property, and small vanilla-JS edits to the existing Flask app — no new dependencies, no new routes, no data model changes. The file-tree macro is consolidated into one shared partial; the new Export dropdown reuses the theme-menu's existing click-toggle/outside-click-close JS pattern instead of introducing a new one.

**Tech Stack:** Flask, Jinja2 templates, vanilla JS, plain CSS custom properties, pytest.

**Spec:** [docs/superpowers/specs/2026-09-21-outstanding-ux-fixes-design.md](../specs/2026-09-21-outstanding-ux-fixes-design.md)

## Global Constraints

- No new runtime dependencies (`uv add`) — every change here is templates/CSS/JS only.
- The Export dropdown must reuse the existing theme-menu dropdown interaction pattern (`initTheme()` in `static/js/navigation.js`) rather than a new library or pattern.
- Every `--color-text-secondary` value changed for contrast must reach **≥4.5:1** against that theme's `--color-bg` (WCAG AA, normal text).
- Touch-target sizing for `.file-action-btn` (rename/delete) is **out of scope** for this plan — do not touch it.
- Sidebar "recents" (`#sidebar-quick-access`, already implemented in `static/js/file-operations.js`) is **out of scope** — do not modify it.
- Run `uv run pytest` after every task; all existing tests must keep passing in addition to any new ones.

---

### Task 1: Extract shared file-tree macro, remove home-page duplicate

The `render_tree` Jinja macro is currently defined three times: once in `templates/index.html` (called twice — sidebar and the `#file-library` main panel), and again, near-identically, in `templates/view.html`. This task consolidates it into one partial and drops the home page's duplicate main-panel tree per the review.

**Files:**
- Create: `src/md_preview_server/templates/_file_tree_macro.html`
- Modify: `src/md_preview_server/templates/index.html`
- Modify: `src/md_preview_server/templates/view.html`
- Modify: `src/md_preview_server/static/css/style.css:260-274,1434-1436` (remove now-dead `.section-heading`/`.file-list-main` rules)
- Test: `tests/test_app.py`

**Interfaces:**
- Produces: Jinja macro `render_tree(tree, prefix='', current=None)`, imported as `{% import "_file_tree_macro.html" as tree_macro %}` and called `tree_macro.render_tree(tree)` or `tree_macro.render_tree(tree, current=filepath)`. Both `index.html` and `view.html` (Task 2+ onward) consume this.

- [ ] **Step 1: Create the shared macro partial**

Create `src/md_preview_server/templates/_file_tree_macro.html`:

```jinja
{% macro render_tree(tree, prefix='', current=None) %}
<ul class="file-tree">
    {% for name in tree.keys()|sort %}
        {% set node = tree[name] %}
        {% if node is mapping %}
        <li class="directory">
            <span class="folder-toggle" onclick="this.parentElement.classList.toggle('collapsed')">
                <span class="icon folder-icon"></span>
                <span class="name">{{ name }}</span>
            </span>
            {{ render_tree(node, prefix ~ name ~ '/', current) }}
        </li>
        {% else %}
        <li class="file {% if node == current %}active{% endif %}" data-path="{{ node }}">
            <span class="icon file-icon"></span>
            <a href="{{ url_for('view_file', filepath=node) }}">{{ name }}</a>
            <span class="file-actions">
                <button class="file-action-btn" data-action="rename" data-path="{{ node }}" title="Rename">&#x270F;</button>
                <button class="file-action-btn" data-action="delete" data-path="{{ node }}" title="Delete">&#x2716;</button>
            </span>
        </li>
        {% endif %}
    {% endfor %}
</ul>
{% endmacro %}
```

This is the union of the two existing versions (the `view.html` copy's `current` param, defaulted to `None` instead of `''` — functionally identical since `node` is never an empty string).

- [ ] **Step 2: Update `index.html` — import the macro, drop the local one and the main-panel duplicate**

Replace the whole file's top (lines 1–29, extends + title block + local macro def) so it starts with:

```jinja
{% extends "base.html" %}
{% import "_file_tree_macro.html" as tree_macro %}

{% block title %}MD Preview - File Browser{% endblock %}
```

Update the sidebar block's call (was `{{ render_tree(tree) }}`) to:

```jinja
{% block sidebar %}
    <div class="sidebar-section">
        <h3>Files</h3>
        {% if tree %}
            {{ tree_macro.render_tree(tree) }}
        {% else %}
            <p class="empty-message">No markdown files found.</p>
        {% endif %}
    </div>
{% endblock %}
```

In the `content` block, remove the entire `#file-library` panel (the `{% if tree %} <div class="file-list-main" ...> ... {% else %} <div class="empty-state" ...> ... {% endif %}` block) along with the `<a class="btn btn-secondary" href="#file-library">Browse files</a>` hero link, since its target no longer exists. The `content` block becomes:

```jinja
{% block content %}
<div class="welcome">
    <section class="hero-panel">
        <p class="eyebrow">Markdown workspace</p>
        <h1>Preview, edit, and manage your notes from one place.</h1>
        <p>Select a markdown file from the sidebar to preview it, use live edit mode for quick changes, or drag and drop new files into the workspace.</p>
        <div class="hero-actions">
            <button class="btn btn-primary" id="hero-new-file-btn" type="button">Create a file</button>
        </div>
    </section>
</div>
{% endblock %}
```

(The `{% block scripts %}` at the bottom of the file is unchanged.)

- [ ] **Step 3: Update `view.html` — import the shared macro, drop the local copy**

Replace the local macro definition (the `{% macro render_tree(tree, prefix='', current='') %} ... {% endmacro %}` block, currently right after the `{% block extra_head %}` block) — delete it entirely, and add the import next to the `{% extends %}` line at the top of the file:

```jinja
{% extends "base.html" %}
{% import "_file_tree_macro.html" as tree_macro %}
```

Update the sidebar block's call (was `{{ render_tree(tree, current=filepath) }}`) to:

```jinja
{% block sidebar %}
    <div class="sidebar-section">
        <h3>Files</h3>
        {% if tree %}
            {{ tree_macro.render_tree(tree, current=filepath) }}
        {% endif %}
    </div>
{% endblock %}
```

- [ ] **Step 4: Remove now-dead CSS**

In `src/md_preview_server/static/css/style.css`, delete the `.file-list-main` rule (lines 1434–1436):

```css
.file-list-main {
    padding: 24px 28px;
}
```

Delete the `.section-heading` and `.section-heading h2` rules (lines 260–274):

```css
.section-heading {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 20px;
}

.section-heading h2 {
    font-family: var(--font-display);
    font-size: 1.4rem;
    line-height: 1.15;
    color: var(--color-accent);
    text-shadow: var(--glow-sm);
}
```

In the low-effects block (around line 2192), remove the now-dangling `.section-heading h2` selector from this rule (keep the rest of the selector list and declaration unchanged):

```css
:root[data-low-effects="true"] a:hover,
:root[data-low-effects="true"] .sidebar-header .logo,
:root[data-low-effects="true"] .sidebar-header .logo:hover,
:root[data-low-effects="true"] .doc-title,
:root[data-low-effects="true"] .markdown-body h1,
:root[data-low-effects="true"] .markdown-body h2,
:root[data-low-effects="true"] .markdown-body h3,
:root[data-low-effects="true"] .markdown-body h4,
:root[data-low-effects="true"] .markdown-body h5,
:root[data-low-effects="true"] .markdown-body h6,
:root[data-low-effects="true"] .hero-panel h1,
:root[data-low-effects="true"] .empty-state h2 {
    text-shadow: none;
}
```

- [ ] **Step 5: Add a regression test**

Add to `tests/test_app.py`:

```python
def test_index_file_tree_renders_once(client):
    response = client.get("/")
    data = response.data.decode("utf-8")
    assert data.count('id="file-library"') == 0
    # sample_dir has hello.md at root plus one nested "sub" folder,
    # so a single render produces two <ul class="file-tree"> (root + nested).
    assert data.count('class="file-tree"') == 2
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_app.py -v`
Expected: all tests pass, including the new `test_index_file_tree_renders_once` and the pre-existing `test_index_returns_200`, `test_index_lists_files`, `test_view_file_returns_200`, `test_view_file_renders_markdown`, `test_view_nested_file`.

- [ ] **Step 7: Commit**

```bash
git add src/md_preview_server/templates/_file_tree_macro.html src/md_preview_server/templates/index.html src/md_preview_server/templates/view.html src/md_preview_server/static/css/style.css tests/test_app.py
git commit -m "fix: de-duplicate file tree rendering across templates"
```

---

### Task 2: De-duplicate the document view header

`doc-overview` currently repeats the filename and full path that the breadcrumb directly above it already shows. Drop the path line; keep the title (it's the page's real `<h1>`) and the stat pills.

**Files:**
- Modify: `src/md_preview_server/templates/view.html` (the `doc-overview` header, inside the `content` block from Task 1)
- Modify: `src/md_preview_server/static/css/style.css:1048-1057` (remove now-dead `.doc-path` rules)
- Test: `tests/test_app.py`

**Interfaces:** none — this task only touches markup already present after Task 1; no new names are produced or consumed.

- [ ] **Step 1: Remove the duplicated path line**

In `view.html`, change:

```jinja
        <header class="surface-panel doc-overview">
            <div>
                <p class="eyebrow">Current document</p>
                <h1 class="doc-title">{{ filename }}</h1>
                <p class="doc-path">{{ filepath }}</p>
            </div>
```

to:

```jinja
        <header class="surface-panel doc-overview">
            <div>
                <p class="eyebrow">Current document</p>
                <h1 class="doc-title">{{ filename }}</h1>
            </div>
```

- [ ] **Step 2: Remove the now-dead `.doc-path` CSS**

In `style.css`, delete:

```css
.doc-path {
    font-size: 0.78rem;
    color: var(--color-text-secondary);
    font-family: var(--font-mono);
}

.doc-path::before {
    content: 'path: ';
    opacity: 0.5;
}
```

- [ ] **Step 3: Add a regression test**

Add to `tests/test_app.py`:

```python
def test_view_file_no_duplicate_path(client):
    response = client.get("/view/sub/nested.md")
    data = response.data.decode("utf-8")
    assert 'class="doc-path"' not in data
    assert 'class="doc-title"' in data
    assert 'class="breadcrumb"' in data
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_app.py -v`
Expected: all tests pass, including the new `test_view_file_no_duplicate_path`.

- [ ] **Step 5: Commit**

```bash
git add src/md_preview_server/templates/view.html src/md_preview_server/static/css/style.css tests/test_app.py
git commit -m "fix: remove duplicated file path from document header"
```

---

### Task 3: Promote Edit, consolidate Copy Path / Export HTML / Export PDF into one dropdown

The four breadcrumb buttons are currently the same size, so Edit doesn't stand out. Give Edit an accent fill by default, and collapse the other three into a single "Export" dropdown that reuses the theme-menu's existing toggle/outside-click-close JS pattern.

**Files:**
- Modify: `src/md_preview_server/templates/view.html` (the `breadcrumb-actions` div)
- Modify: `src/md_preview_server/static/css/style.css` (`.btn-edit-toggle`, new `.export-dropdown-container`/`.export-menu`/`.export-menu-item`, low-effects list)
- Modify: `src/md_preview_server/static/js/navigation.js` (new `initExportMenu()`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: the existing `initCopyPath()` (`navigation.js:454`, wired via `initDocumentTools()`) and `initExportButtons()` (`navigation.js:541`) handlers — both are ID-based (`copy-path-btn`, `export-html-btn`, `export-pdf-btn`) and need **no changes**, since those IDs are preserved, just moved inside the new dropdown markup.
- Produces: `initExportMenu()` in `navigation.js`, called from the top-level init list alongside the existing `initExportButtons()` call.

- [ ] **Step 1: Replace the breadcrumb-actions markup**

In `view.html`, change:

```jinja
    <div class="breadcrumb-actions">
        <button class="btn btn-sm btn-secondary" id="copy-path-btn" data-path="{{ filepath }}">Copy Path</button>
        <button class="btn btn-sm btn-secondary" id="export-html-btn" data-path="{{ filepath }}">Export HTML</button>
        <button class="btn btn-sm btn-secondary" id="export-pdf-btn">Export PDF</button>
        <button class="btn btn-sm btn-edit-toggle" id="edit-toggle-btn">Edit</button>
    </div>
```

to:

```jinja
    <div class="breadcrumb-actions">
        <div class="export-dropdown-container">
            <button class="btn btn-sm btn-secondary" id="export-menu-btn" aria-haspopup="true" aria-expanded="false">Export &#9662;</button>
            <div class="export-menu" id="export-menu" style="display: none;">
                <button class="export-menu-item" id="copy-path-btn" data-path="{{ filepath }}">Copy Path</button>
                <button class="export-menu-item" id="export-html-btn" data-path="{{ filepath }}">Export HTML</button>
                <button class="export-menu-item" id="export-pdf-btn">Export PDF</button>
            </div>
        </div>
        <button class="btn btn-sm btn-edit-toggle" id="edit-toggle-btn">Edit</button>
    </div>
```

- [ ] **Step 2: Give `.btn-edit-toggle` an accent fill by default, and a distinct look while actively editing**

`editor.js` (`static/js/editor.js:78-79,119-120`) already toggles `.active` on this button and swaps its text to "View" while editing. Since it will now be accent-filled by default (to read as the primary action), flip `.active` to an outlined look instead, so the two states stay visually distinct. In `style.css`, replace:

```css
.btn-edit-toggle {
    background: transparent;
    color: var(--color-accent);
    border: 1px solid var(--color-border-strong);
    padding: 5px 12px;
    font-size: 0.74rem;
    font-weight: 700;
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    cursor: pointer;
    border-radius: 2px;
    transition: background 0.1s, color 0.1s, box-shadow 0.1s;
}

.btn-edit-toggle:hover,
.btn-edit-toggle.active {
    background: var(--color-accent);
    color: #000;
    box-shadow: var(--glow-sm);
}
```

with:

```css
.btn-edit-toggle {
    background: var(--color-accent);
    color: #000;
    border: 1px solid var(--color-accent);
    padding: 5px 12px;
    font-size: 0.74rem;
    font-weight: 700;
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    cursor: pointer;
    border-radius: 2px;
    box-shadow: var(--glow-sm);
    transition: background 0.1s, color 0.1s, border-color 0.1s, box-shadow 0.1s;
}

.btn-edit-toggle:hover {
    background: var(--color-accent-strong);
    border-color: var(--color-accent-strong);
    box-shadow: var(--glow-md);
}

.btn-edit-toggle.active {
    background: transparent;
    color: var(--color-accent);
    border-color: var(--color-border-strong);
    box-shadow: none;
}

.btn-edit-toggle.active:hover {
    background: var(--color-accent);
    color: #000;
    box-shadow: var(--glow-sm);
}
```

In the low-effects block (around line 2205-2217, the selector list that strips `box-shadow`), add the bare `.btn-edit-toggle` selector since it now carries a shadow by default too:

```css
:root[data-low-effects="true"] .surface-panel,
:root[data-low-effects="true"] .theme-menu,
:root[data-low-effects="true"] .btn-primary,
:root[data-low-effects="true"] .btn-primary:hover,
:root[data-low-effects="true"] .btn-edit-toggle,
:root[data-low-effects="true"] .btn-edit-toggle:hover,
:root[data-low-effects="true"] .btn-edit-toggle.active,
:root[data-low-effects="true"] .reading-progress,
:root[data-low-effects="true"] .modal,
:root[data-low-effects="true"] .upload-overlay-content,
:root[data-low-effects="true"] .toast,
:root[data-low-effects="true"] .split-divider:hover {
    box-shadow: none;
}
```

- [ ] **Step 3: Add the Export dropdown CSS**

In `style.css`, add this block right after the `.breadcrumb-actions` rule (around line 987):

```css
.export-dropdown-container {
    position: relative;
    display: inline-block;
}

.export-menu {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 5px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 3px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5), var(--color-shadow);
    z-index: 1000;
    min-width: 160px;
    padding: 5px 0;
}

.export-menu-item {
    display: block;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    padding: 8px 16px;
    font-size: 0.78rem;
    font-family: var(--font-mono);
    color: var(--color-text);
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
}

.export-menu-item:hover {
    background: var(--color-border);
    color: var(--color-accent);
}
```

- [ ] **Step 4: Add `initExportMenu()` to `navigation.js`**

Add the function (near `initExportButtons`, e.g. directly above it):

```javascript
    function initExportMenu() {
        var menuBtn = document.getElementById("export-menu-btn");
        var menu = document.getElementById("export-menu");

        if (!menuBtn || !menu) {
            return;
        }

        menuBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            var isHidden = menu.style.display === "none" || menu.style.display === "";
            menu.style.display = isHidden ? "block" : "none";
            menuBtn.setAttribute("aria-expanded", isHidden ? "true" : "false");
        });

        document.addEventListener("click", function (e) {
            if (!menu.contains(e.target) && e.target !== menuBtn) {
                menu.style.display = "none";
                menuBtn.setAttribute("aria-expanded", "false");
            }
        });

        menu.querySelectorAll(".export-menu-item").forEach(function (item) {
            item.addEventListener("click", function () {
                menu.style.display = "none";
                menuBtn.setAttribute("aria-expanded", "false");
            });
        });
    }
```

Add the call to the top-level init list (`navigation.js:18-25`):

```javascript
    initTheme();
    initEffectsMode();
    initSearch();
    initTreeControls();
    initKeyboardShortcuts();
    initSidebarAutoClose();
    initDocumentTools();
    initExportButtons();
    initExportMenu();
```

- [ ] **Step 5: Add a regression test**

Add to `tests/test_app.py`:

```python
def test_view_file_export_dropdown(client):
    response = client.get("/view/hello.md")
    data = response.data.decode("utf-8")
    assert 'id="export-menu-btn"' in data
    assert 'id="export-menu"' in data
    assert 'id="copy-path-btn"' in data
    assert 'id="export-html-btn"' in data
    assert 'id="export-pdf-btn"' in data
    assert 'id="edit-toggle-btn"' in data
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_app.py -v`
Expected: all tests pass, including the new `test_view_file_export_dropdown`.

- [ ] **Step 7: Manual check**

Run `uv run md-preview` against a scratch directory with at least one `.md` file, open a document, and confirm:
- Edit button reads as visually primary (accent-filled) before editing, and switches to an outlined look with text "View" while editing.
- Clicking "Export ▾" opens the dropdown with Copy Path / Export HTML / Export PDF; clicking any item performs its existing action and closes the menu; clicking outside the menu also closes it.

- [ ] **Step 8: Commit**

```bash
git add src/md_preview_server/templates/view.html src/md_preview_server/static/css/style.css src/md_preview_server/static/js/navigation.js tests/test_app.py
git commit -m "feat: promote Edit action and consolidate export actions into a dropdown"
```

---

### Task 4: Fix dark-theme secondary-text contrast

`--color-text-secondary` fails WCAG AA (4.5:1 for normal text) against `--color-bg` on three of the four dark themes. Verified contrast ratios (relative-luminance method, WCAG formula):

| Theme | `--color-bg` | Current `--color-text-secondary` | Current ratio | New value | New ratio |
|---|---|---|---|---|---|
| Terminal | `#080d08` | `#4a7a4a` | ~3.90:1 (fail) | `#558a55` | ~4.81:1 |
| Amber | `#1a0f00` | `#997a00` | ~4.62:1 (**already passes**) | unchanged | — |
| Dracula | `#282a36` | `#6272a4` | ~3.03:1 (fail) | `#8e99bd` | ~5.05:1 |
| Nord | `#2e3440` | `#4c566a` | ~1.69:1 (fail) | `#9ea4af` | ~4.99:1 |
| Paper/light | `#fdfdfd` | `#555555` | ~7.33:1 (**already passes**) | unchanged | — |

Amber and Paper/light already meet AA once actually measured (the original review's "similar to Terminal" note for Amber undercounted it) — leave both unchanged.

**Files:**
- Modify: `src/md_preview_server/static/css/style.css:30,91,115` (Terminal, Dracula, Nord `--color-text-secondary` only)

**Interfaces:** none — single CSS custom-property value changes, consumed by the 50+ existing usages automatically.

- [ ] **Step 1: Update the three failing themes**

In `style.css`, change line 30 (inside the default `:root` block, Terminal theme):

```css
    --color-text-secondary: #4a7a4a;
```
to:
```css
    --color-text-secondary: #558a55;
```

Change line 91 (inside `:root[data-theme="dracula"]`):

```css
    --color-text-secondary: #6272a4;
```
to:
```css
    --color-text-secondary: #8e99bd;
```

Change line 115 (inside `:root[data-theme="nord"]`):

```css
    --color-text-secondary: #4c566a;
```
to:
```css
    --color-text-secondary: #9ea4af;
```

Leave the Amber (`#997a00`, line 67) and Paper/light (`#555555`, line 142) values unchanged.

- [ ] **Step 2: Verify the contrast ratios**

Run:

```bash
python3 -c "
def lum(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def rel_lum(hex_color):
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return 0.2126 * lum(r) + 0.7152 * lum(g) + 0.0722 * lum(b)

def contrast(fg, bg):
    l1, l2 = rel_lum(fg), rel_lum(bg)
    l1, l2 = max(l1, l2), min(l1, l2)
    return (l1 + 0.05) / (l2 + 0.05)

for name, fg, bg in [
    ('Terminal', '#558a55', '#080d08'),
    ('Dracula', '#8e99bd', '#282a36'),
    ('Nord', '#9ea4af', '#2e3440'),
]:
    ratio = contrast(fg, bg)
    print(f'{name}: {ratio:.2f}:1', 'OK' if ratio >= 4.5 else 'FAIL')
"
```

Expected: all three print `OK` with a ratio ≥ 4.5.

- [ ] **Step 3: Run the tests**

Run: `uv run pytest -v`
Expected: full suite passes (CSS-only change, no test should regress).

- [ ] **Step 4: Manual check**

Run `uv run md-preview`, switch through Terminal, Dracula, and Nord themes via the theme dropdown, and confirm secondary text (breadcrumb, file tree "no files" message, stat pills, etc.) is visibly more legible against the background.

- [ ] **Step 5: Commit**

```bash
git add src/md_preview_server/static/css/style.css
git commit -m "fix: lighten secondary text color on dark themes to meet WCAG AA contrast"
```

---

### Task 5: Add `prefers-contrast: more` support

Mirror the existing `@media (prefers-reduced-motion: reduce)` block (`style.css:2234-2263`) with an analogous `@media (prefers-contrast: more)` block that pushes secondary text further past the Task 4 AA baseline for each theme, for users whose OS requests higher contrast.

**Files:**
- Modify: `src/md_preview_server/static/css/style.css` (new block, added directly after the `prefers-reduced-motion` block)

**Interfaces:** none — pure CSS media-query addition, no JS or markup changes.

- [ ] **Step 1: Add the media query block**

In `style.css`, add this immediately after the closing `}` of the `@media (prefers-reduced-motion: reduce)` block (after line 2263, before the `RESPONSIVE` section comment):

```css
@media (prefers-contrast: more) {
    :root {
        --color-text-secondary: #7fc27f;
    }

    :root[data-theme="amber"] {
        --color-text-secondary: #c9a300;
    }

    :root[data-theme="dracula"] {
        --color-text-secondary: #aab4d6;
    }

    :root[data-theme="nord"] {
        --color-text-secondary: #c3c8d1;
    }

    :root[data-theme="light"] {
        --color-text-secondary: #333333;
    }
}
```

Each value here is a further lightening (dark themes) or darkening (Paper/light) beyond the Task 4 baseline — same custom property, same cascade, so every existing usage of `--color-text-secondary` picks it up automatically when the OS/browser requests more contrast.

- [ ] **Step 2: Run the tests**

Run: `uv run pytest -v`
Expected: full suite passes (CSS-only change).

- [ ] **Step 3: Manual check**

In Chrome or Firefox DevTools, open Rendering settings (Chrome: `Cmd/Ctrl+Shift+P` → "Show Rendering" → "Emulate CSS media feature prefers-contrast" → "more"; Firefox: `about:config` → toggle `ui.prefersReducedContrast` equivalent, or use the Accessibility panel). Confirm secondary text lightens/darkens further than the Task 4 baseline in each theme.

- [ ] **Step 4: Commit**

```bash
git add src/md_preview_server/static/css/style.css
git commit -m "feat: honor prefers-contrast: more for secondary text"
```

---

### Task 6 (optional): Improve the `cd` button's accessible label

**Files:**
- Modify: `src/md_preview_server/templates/base.html:28`
- Test: `tests/test_app.py`

**Context:** the review's suggested fix — spelling out the action in the `title` tooltip — is already done (`title="Change directory"`). The real remaining gap is that `title` tooltips aren't reachable on touch devices. Changing the *visible* button text to something like "cd → dir" was considered, but `.sidebar-header-buttons` is a tight, non-wrapping flex row (logo + theme button + "new" + "cd" + sidebar toggle, inside a ~300px sidebar) — a longer visible label risks crowding or overflow. Adding an explicit `aria-label` instead gets the same accessibility win (screen readers and other assistive tech read `aria-label` reliably, unlike `title`) with zero layout risk.

**Interfaces:** none.

- [ ] **Step 1: Add an explicit `aria-label`**

In `base.html`, change:

```html
                <button class="icon-btn" id="dir-picker-btn" title="Change directory">cd</button>
```

to:

```html
                <button class="icon-btn" id="dir-picker-btn" title="Change directory" aria-label="Change directory">cd</button>
```

- [ ] **Step 2: Add a regression test**

Add to `tests/test_app.py`:

```python
def test_index_dir_picker_has_aria_label(client):
    response = client.get("/")
    data = response.data.decode("utf-8")
    assert 'id="dir-picker-btn"' in data
    assert 'aria-label="Change directory"' in data
```

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/test_app.py -v`
Expected: all tests pass, including the new `test_index_dir_picker_has_aria_label`.

- [ ] **Step 4: Commit**

```bash
git add src/md_preview_server/templates/base.html tests/test_app.py
git commit -m "fix: add accessible label to the change-directory button"
```
