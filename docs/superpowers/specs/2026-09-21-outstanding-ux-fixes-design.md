# Outstanding UX Fixes — Design

Source: "Recommendations still outstanding" in [docs/ui-design-review.md](../../ui-design-review.md).

## Context

The design review lists five groups of outstanding recommendations. Research into the
current codebase before this design was written surfaced that two of the five are
already substantially resolved, and the scope below reflects that:

- **Sidebar recents** (`#sidebar-quick-access`) is *not* empty as the review doc
  states — `static/js/file-operations.js` already renders "Recent" (viewed files,
  via `localStorage['mdv-recent-files']`) and "Favorites" sections into it. Per
  product decision, this is treated as already resolved; no new work is planned here.
- The `cd` toolbar button's `title` attribute already reads "Change directory," which
  covers the review's suggested fix. The only residual gap — tooltips aren't reachable
  on touch devices — gets a small optional visible-label tweak (see below).
- Touch-target sizing for the per-file rename/delete buttons (`.file-action-btn`) is
  explicitly **out of scope** for this round, per product decision.

## Goals

1. Remove the duplicated file tree from the home page.
2. Remove the duplicated filename/path in the document view header.
3. Promote the Edit action and consolidate the export/copy actions into one dropdown.
4. Fix dark-theme secondary-text contrast to meet WCAG AA.
5. Add `prefers-contrast: more` support alongside the existing reduced-motion handling.
6. (Optional, low priority) Clarify the `cd` button's visible label.

Non-goals: sidebar recents/favorites (already done), touch-target sizing (deferred).

## 1. Home page & sidebar — file tree de-duplication

**Current state:** the `render_tree(tree, prefix='')` Jinja macro is defined and called
independently in three places:
- `templates/index.html` line 5 (macro def) — called once for the sidebar (line 35,
  inside `{% block sidebar %}`) and again for the main-panel `#file-library` panel
  (line 63, inside `{% block content %}`).
- `templates/view.html` lines 42–66 — a near-duplicate copy of the same macro (adds a
  `current` param for active-file highlighting), used to render the sidebar tree on
  the document view page.

**Change:**
- Extract the macro into a shared partial, `templates/_file_tree_macro.html`, with the
  `current=None` param (a strict superset of both existing versions) so both
  `index.html` and `view.html` import the same implementation via `{% import
  "_file_tree_macro.html" as tree_macro %}`.
- Remove the second call site in `index.html`'s `#file-library` panel. Per the review,
  this panel is simply dropped — since sidebar quick-access already covers "recents"
  (goal, out of scope here), nothing new replaces it. Delete the surrounding
  `.file-list-main` markup and its now-unused hint text ("The sidebar search is
  faster for large folders...").
- Leave `#file-library`'s heading/search-hint copy removed along with it; if the home
  page's main content area reads as too sparse afterward, that's a follow-up layout
  concern, not part of this fix.

**Files:** `src/md_preview_server/templates/index.html`,
`src/md_preview_server/templates/view.html`, new
`src/md_preview_server/templates/_file_tree_macro.html`.

## 2. Document view — header de-duplication + button promotion

**Current state** (`templates/view.html`):
- Breadcrumb (lines 79–98) shows `Home / <path segments> / <filename>`.
- `doc-overview` header (lines 102–113) repeats the filename in `<h1 class="doc-title">`
  and the full path in `<p class="doc-path">{{ filepath }}</p>` (styled with a `path:
  ` `::before` in `style.css` lines 1054–1057), alongside the word-count /
  reading-time / heading-count stat pills.
- Breadcrumb actions (lines 92–97): four same-sized buttons — Copy Path, Export HTML,
  Export PDF, Edit (`.btn-edit-toggle`, which already has an accent-filled style but
  only applies it on hover/`.active` — see `style.css` lines 918–938).
- The only existing dropdown pattern in the app is the theme selector
  (`templates/base.html` lines 16–26; CSS `style.css` lines 372–420; JS
  `initTheme()` in `static/js/navigation.js` lines 27–58) — click-to-toggle display,
  outside-click to close.

**Change:**
- Remove `<p class="doc-path">{{ filepath }}</p>` from `doc-overview`; keep
  `doc-title` (it's the page's real `<h1>`) and all three stat pills.
- Give `.btn-edit-toggle` its accent fill by default (not just on hover/active), so it
  visually stands out as the primary action.
- Replace the three remaining buttons (Copy Path, Export HTML, Export PDF) with a
  single "Export" dropdown button, structurally mirroring the theme dropdown
  (`.export-dropdown-container` / `.export-menu` / `.export-menu-item`, reusing the
  same CSS shape and the same click-toggle + outside-click-to-close JS logic as
  `initTheme()`, factored into a small `initExportMenu()` in `navigation.js`). Menu
  items: Copy Path, Export HTML, Export PDF — wired to the existing handler logic in
  `initCopyPath()` / `initExportButtons()`, just triggered from menu items instead of
  standalone buttons.

**Files:** `src/md_preview_server/templates/view.html`, `static/css/style.css`,
`static/js/navigation.js`.

## 3. Accessibility

### Contrast
`--color-text-secondary` currently fails WCAG AA (4.5:1) against `--color-bg` on the
dark themes:

| Theme | `--color-bg` | `--color-text-secondary` (current) |
|---|---|---|
| Terminal | `#080d08` | `#4a7a4a` (~3:1) |
| Amber | `#1a0f00` | `#997a00` (~similar) |
| Dracula | `#282a36` | `#6272a4` |
| Nord | `#2e3440` | `#4c566a` |
| Paper/light | `#fdfdfd` | `#555555` |

**Change:** lighten `--color-text-secondary` per dark theme (Terminal, Amber, Dracula,
Nord) until each reaches ≥4.5:1 against that theme's `--color-bg`, verified with a
contrast-ratio tool during implementation (exact hex values are an implementation
detail, not fixed here). Paper/light is not confirmed failing and is checked but
likely needs no change. This is a single-variable change per theme, so it propagates
to every one of the 50+ existing usages automatically.

### `prefers-contrast: more`
**Current state:** `style.css` already has two mechanisms to mirror:
- A manual toggle, `:root[data-low-effects="true"]` (lines 2185–2232), driven by
  `initEffectsMode()` in `navigation.js` (lines 83–110) via a button in the theme
  dropdown.
- An OS-level media query, `@media (prefers-reduced-motion: reduce)` (lines
  2234–2257+), which zeroes shadow/glow custom properties and collapses animation/
  transition durations.

**Change:** add `@media (prefers-contrast: more)`, following the same structural
pattern as the reduced-motion block — strengthen `--color-text-secondary` further (on
top of the AA fix above) and thicken/darken-or-lighten border and focus-ring
declarations that currently rely on low-contrast defaults. No JS changes needed; this
is a pure CSS media query addition, same as reduced-motion.

### Touch targets
Out of scope for this round (product decision).

## 4. Iconography (optional, low priority)

**Current state:** `templates/base.html` line 28: `<button class="icon-btn"
id="dir-picker-btn" title="Change directory">cd</button>`. The `title` already spells
out the action; the review's concern is substantially addressed. The residual gap is
that `title` tooltips aren't reachable on touch devices.

**Change:** update the visible button text from `cd` to `cd → dir`, keeping the
existing `title` attribute as-is. Low priority — safe to drop from the plan without
affecting the rest of the work if deprioritized later.

**Files:** `src/md_preview_server/templates/base.html`.

## Testing

- `uv run pytest` — existing view-route tests should continue to pass; the macro
  extraction must not change rendered tree markup/IDs that `buildOutline()` or other
  JS relies on.
- Manual check: home page shows the tree once (sidebar only); document view header
  shows filename once; Export dropdown opens/closes like the theme menu and each item
  still performs its existing action; Edit button reads as visually primary.
- Manual contrast check per dark theme against the new `--color-text-secondary` values
  using a WCAG contrast checker.
