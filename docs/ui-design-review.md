# UI Design Review & Changelog

A record of the design critique of the markdown previewer, the changes made so far,
and the recommendations still outstanding.

## Changes made

### 1. Body prose off monospace
Long-form markdown was rendering in JetBrains Mono, which is ~15% wider and tiring to
read across paragraphs. Added a `--font-prose` variable scoped to `.markdown-body`.

- Dark themes (Terminal, Amber, Dracula, Nord) use a readable system sans stack.
- The Paper / light theme overrides `--font-prose` with a serif stack (Georgia and
  fallbacks), which reads best on a light background.
- Headings (`--font-display`) and `code` / `pre` (`--font-mono`) still force monospace,
  so the terminal character is preserved everywhere it matters — only running prose,
  lists, tables and blockquotes changed.

Files: `static/css/style.css`.

### 2. Tabbed right rail (outline + AI assistant)
The document side panel previously stacked the table of contents and the AI assistant
in one ~280px column split by an `<hr>`. Both are primary, so they competed for vertical
space and the outline got buried once a chat grew.

They are now two tabs — "On this page" and "Assistant" — that swap the panel content, so
the outline stays fully visible regardless of chat length. A small `railShow()` toggle
handles switching and focuses the chat input when the Assistant tab is selected. Styling
(`.rail-tabs`, `.rail-tab`, `.rail-panel`) uses the theme accent color and glow.

Files: `src/md_preview_server/templates/view.html`, `static/css/style.css`.

Verified: the view route renders HTTP 200 with the tab markup present; the existing
`buildOutline()` and AI assistant init still work because their element IDs remain in the
DOM inside the tab panels.

## Recommendations still outstanding

Listed roughly by impact.

### Home page & sidebar
- **De-duplicate the file tree.** The tree renders twice on the home page — once in the
  sidebar and again in the main `#file-library` panel. Drop it from the main panel.
- **Use the freed space for recents.** Wire the currently-empty `#sidebar-quick-access`
  div to show recently-edited files so the reclaimed space earns its keep.

### Document view
- **De-duplicate the document header.** `doc-overview` repeats the filename and full path
  that the breadcrumb directly above already shows. Drop the path (or the title) from the
  header; keep the word-count / reading-time pills, which are the unique value.
- **Promote the primary action.** The four breadcrumb buttons (Copy Path, Export HTML,
  Export PDF, Edit) are all the same size, so Edit doesn't stand out. Give Edit the accent
  fill and collapse the three export/copy buttons into a single "Export" dropdown.

### Accessibility
- **Contrast.** `--color-text-secondary` fails WCAG AA on the dark themes (Terminal
  `#4a7a4a` on `#080d08` is ~3:1; Amber `#997a00` is similar). Lighten the secondaries or
  reserve them for large text only.
- **Touch targets.** The per-file rename/delete buttons (`file-action-btn`) are tiny and
  only appear on hover — unreachable on touch. Give them a 44x44px minimum tap area or a
  persistent "..." menu.
- Consider honoring `prefers-contrast: more` in addition to the existing low-effects
  toggle and `prefers-reduced-motion` handling.

### Iconography
- The `new` / `cd` toolbar labels are charming but `cd` is opaque to non-shell users.
  Keep the terminal label but make the `title` spell it out, or render it as `cd → dir`.

## What already works well
- Theming via CSS custom properties swapped by `data-theme`, with a single low-effects
  override — clean architecture, trivial to add a theme.
- Lazy-loading Mermaid and KaTeX only when a document actually contains diagrams or math.
- Breadcrumb, reading-progress bar, and live word count — thoughtful reading-oriented
  touches.
