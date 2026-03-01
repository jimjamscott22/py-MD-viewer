# Future Upgrades

## Features

### Mermaid Diagram Support
Render flowcharts, sequence diagrams, and other diagrams inline from ` ```mermaid ` code blocks using Mermaid.js loaded from CDN.

### Math/LaTeX Rendering (KaTeX)
Support `$inline$` and `$$block$$` math equations using KaTeX, enabling scientific and technical documentation.

### YAML Frontmatter Parsing
Parse and display metadata (title, author, date, tags) from YAML frontmatter blocks at the top of markdown files.

### Keyboard Shortcuts Toolbar
Add a formatting toolbar to the editor with buttons and keyboard shortcuts for bold, italic, headings, links, lists, and code blocks.

### Auto-Save with Undo History
Periodic auto-save with the ability to restore previous versions of a file, providing a safety net during editing.

### Vim/Emacs Keybinding Modes
Optional editor keybinding presets via CodeMirror extensions for users who prefer modal or Emacs-style editing.

### Tabbed Multi-File Editing
Open multiple files in tabs instead of navigating away, allowing side-by-side comparison and faster switching.

### Favorites/Pinned Files
Bookmark frequently accessed files so they appear at the top of the sidebar for quick access.

### Recent Files List
Track and display recently opened documents for easy navigation back to previous work.

### Breadcrumb Navigation
Show the current file path as clickable breadcrumbs for quick navigation up the directory tree.

### Print Stylesheet
Optimised CSS for printing directly from the browser with clean layout and no UI chrome.

---

## Performance Optimisations

### Markdown Render Caching
Cache rendered HTML keyed by file path and last-modified timestamp. Avoids re-rendering unchanged files on repeated views. The live preview endpoint (`/api/preview`) would continue rendering on each call since the content changes with every keystroke.

### SSE Connection Consolidation
Merge the two separate Server-Sent Events connections (`live-reload.js` and `file-operations.js`) into a single multiplexed connection. Halves server-side memory and connection overhead per client.

### AJAX Sidebar Updates Instead of Full Reload
Replace `location.reload()` after file operations (upload, create, rename, delete) and editor exit with targeted Fetch calls that update only the sidebar file tree via DOM manipulation. Eliminates 1-2 second full page reloads.

### Editor Preview Request Cancellation
Add `AbortController` to the editor's live preview fetch calls so that when a new preview request fires, any pending request is cancelled. Prevents request queuing during fast typing.

### Static Asset Cache Headers
Add `Cache-Control` and `ETag` headers for CSS, JS, and other static files so browsers cache them instead of re-downloading on every page load.

### Search Index
Pre-build a searchable index of file names and paths in memory (alongside the file tree cache) instead of scanning `get_file_list()` and doing linear string matching on every search query.
