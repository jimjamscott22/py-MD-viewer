# Graph Report - .  (2026-08-13)

## Corpus Check
- Corpus is ~18,851 words - fits in a single context window. You may not need a graph.

## Summary
- 246 nodes · 309 edges · 16 communities detected
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output
- Edge kinds: contains: 148 · calls: 46 · rationale_for: 39 · references: 38 · implements: 17 · conceptually_related_to: 8 · imports_from: 6 · method: 4 · shares_data_with: 2 · inherits: 1


## Input Scope
- Requested: auto
- Resolved: committed (source: cli)
- Included files: 34 · Candidates: 46
- Excluded: 3 untracked · 3420 ignored · 0 sensitive · 0 missing committed
- Recommendation: Use --scope all or graphify.yaml inputs.corpus for a knowledge-base folder.

## Graph Freshness
- Built from Git commit: `5fcfdbb`
- Compare this hash to `git rev-parse HEAD` before trusting freshness-sensitive graph output.
## God Nodes (most connected - your core abstractions)
1. `MarkdownFileHandler` - 9 edges
2. `Markdown Rendering Pipeline` - 8 edges
3. `_scan_files()` - 6 edges
4. `render_markdown_with_meta()` - 6 edges
5. `renderQuickAccessSections()` - 6 edges
6. `REST API Surface` - 6 edges
7. `Full-Text Content Search` - 6 edges
8. `Base Layout Template` - 6 edges
9. `render_markdown()` - 5 edges
10. `render_markdown_cached_with_meta()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `File Tree Cache` --references--> `_scan_files()`  [EXTRACTED]
  CLAUDE.md → src/md_preview_server/app.py
- `Live Reload via SSE` --references--> `notify_clients()`  [EXTRACTED]
  CLAUDE.md → src/md_preview_server/app.py
- `Render Cache` --references--> `render_markdown_cached_with_meta()`  [EXTRACTED]
  docs/project-summary.md → src/md_preview_server/renderer.py
- `Search Mode Toggle` --references--> `initSearch()`  [EXTRACTED]
  docs/superpowers/specs/2026-06-05-full-text-search-design.md → src/md_preview_server/static/js/navigation.js
- `Search Snippet Results` --references--> `renderContentResults()`  [EXTRACTED]
  docs/superpowers/specs/2026-06-05-full-text-search-design.md → src/md_preview_server/static/js/navigation.js

## Hyperedges (group relationships)
- **Live Reload Flow** — watchdog_file_observer, live_reload_sse [EXTRACTED 1.00]
- **Content Search Flow** — full_text_content_search, search_mode_toggle, search_snippet_results [EXTRACTED 1.00]

## Communities

### Community 0 - "File API Tests"
Cohesion: 0.05
Nodes (5): client(), Tests for the API endpoints (Phases 1-4)., Create a temporary directory with sample markdown files., Create a Flask test client with the sample directory., sample_dir()

### Community 1 - "Flask Application Core"
Cohesion: 0.09
Nodes (31): File Tree Cache, Flask Web Application, Graph Quality Review Finding, Local Markdown Filesystem, MD Preview Server, build_file_tree(), _count_markdown_files(), create_app() (+23 more)

### Community 2 - "Markdown Rendering"
Cohesion: 0.12
Nodes (23): Example Markdown Corpus, Future Presentation Mode, Markdown Rendering Pipeline, _do_render(), extract_frontmatter(), invalidate_render_cache(), _preprocess_mermaid(), Markdown-to-HTML rendering pipeline with optional caching. (+15 more)

### Community 3 - "Navigation and Search"
Cohesion: 0.13
Nodes (17): applyEffectsMode(), applyTheme(), buildOutline(), createSlug(), escapeHtml(), fallbackCopy(), highlightActiveOutlineLink(), initCopyPath() (+9 more)

### Community 4 - "Product UI and APIs"
Cohesion: 0.15
Nodes (19): Base Layout Template, Content Search Implementation Plan, Document View Template, File Browser Template, Filename Search, Full-Text Content Search, Future Command Palette, Future PDF and Word Export (+11 more)

### Community 5 - "Live Reload Pipeline"
Cohesion: 0.14
Nodes (12): FileSystemEventHandler, Future Real-Time Collaboration, initLiveReload(), Live Reload via SSE, MarkdownFileHandler, File system watcher for markdown files., Watches for .md file changes with debounce., Start watching base_dir for .md file changes. Runs as a daemon thread. (+4 more)

### Community 6 - "Editor API Tests"
Cohesion: 0.13
Nodes (1): Tests for the editor API endpoints (Phase 5).

### Community 7 - "File Operations UI"
Cohesion: 0.29
Nodes (11): addToRecentFiles(), connectSSE(), escapeHtmlStr(), getFavorites(), getRecentFiles(), isFavorite(), refreshSidebar(), renderQuickAccessSections() (+3 more)

### Community 8 - "Page Route Tests"
Cohesion: 0.14
Nodes (5): client(), Tests for the Flask application., Create a temporary directory with sample markdown files., Create a Flask test client with the sample directory., sample_dir()

### Community 9 - "HTML Export Tests"
Cohesion: 0.14
Nodes (5): client(), Tests for the HTML export endpoint., Create a temporary directory with sample markdown files., Create a Flask test client with the sample directory., sample_dir()

### Community 10 - "Renderer Tests"
Cohesion: 0.17
Nodes (1): Tests for the markdown renderer.

### Community 11 - "CodeMirror Editor"
Cohesion: 0.40
Nodes (3): CodeMirror Editor, initEditor(), initSplitDivider()

### Community 12 - "AI Assistant UI"
Cohesion: 0.50
Nodes (2): appendMessage(), escapeHtml()

### Community 13 - "Directory Picker"
Cohesion: 0.83
Nodes (3): browseDirectory(), escapeAttr(), escapeHtml()

### Community 14 - "Startup Isolation Tests"
Cohesion: 0.67
Nodes (1): Tests for startup-time import behavior.

### Community 15 - "Package Initialization"
Cohesion: 1.00
Nodes (1): md-preview-server: A local Markdown preview server with live reload.

## Knowledge Gaps
- **49 isolated node(s):** `PyInstaller entry point.  PyInstaller freezes a single script, not a console_s`, `md-preview-server: A local Markdown preview server with live reload.`, `Flask application for the Markdown preview server.`, `Clear the cached file tree/list so the next access re-scans.`, `Push a change event to all SSE subscribers.` (+44 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Editor API Tests`** (1 nodes): `Tests for the editor API endpoints (Phase 5).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Renderer Tests`** (1 nodes): `Tests for the markdown renderer.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `AI Assistant UI`** (2 nodes): `appendMessage()`, `escapeHtml()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Startup Isolation Tests`** (1 nodes): `Tests for startup-time import behavior.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Initialization`** (1 nodes): `md-preview-server: A local Markdown preview server with live reload.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Document View Template` connect `Product UI and APIs` to `CodeMirror Editor`, `Markdown Rendering`?**
  _High betweenness centrality (0.293) - this node is a cross-community bridge._
- **Why does `Base Layout Template` connect `Product UI and APIs` to `File Operations UI`, `Navigation and Search`?**
  _High betweenness centrality (0.245) - this node is a cross-community bridge._
- **Why does `Markdown Rendering Pipeline` connect `Markdown Rendering` to `Product UI and APIs`?**
  _High betweenness centrality (0.239) - this node is a cross-community bridge._
- **What connects `PyInstaller entry point.  PyInstaller freezes a single script, not a console_s`, `md-preview-server: A local Markdown preview server with live reload.`, `Flask application for the Markdown preview server.` to the rest of the system?**
  _49 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `File API Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.05263157894736842 - nodes in this community are weakly interconnected._
- **Should `Flask Application Core` be split into smaller, more focused modules?**
  _Cohesion score 0.08522727272727272 - nodes in this community are weakly interconnected._
- **Should `Markdown Rendering` be split into smaller, more focused modules?**
  _Cohesion score 0.11594202898550725 - nodes in this community are weakly interconnected._