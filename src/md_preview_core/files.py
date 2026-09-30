"""Framework-neutral Markdown file discovery, search, and path validation."""

import os
import threading
from datetime import datetime, timezone
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".tox",
    ".mypy_cache",
}


class PathOutsideBaseError(ValueError):
    """Raised when a path resolves outside the configured base directory."""


_file_cache: dict | None = None
_file_cache_lock = threading.Lock()
_scan_generation = 0


def invalidate_file_cache() -> None:
    """Clear the cached file tree/list so the next access re-scans."""
    global _file_cache, _scan_generation
    with _file_cache_lock:
        _scan_generation += 1
        _file_cache = None


def validate_path(base_dir: Path, rel_path: str) -> Path:
    """Resolve a relative path and require it to remain within ``base_dir``."""
    rel_path = rel_path.replace("\\", "/")
    resolved_base = base_dir.resolve()
    target = (resolved_base / rel_path).resolve()
    if not target.is_relative_to(resolved_base):
        raise PathOutsideBaseError(rel_path)
    return target


def _iter_markdown_files(base_dir: Path):
    """Yield Markdown files without descending into excluded directories."""
    stack = [base_dir.resolve()]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                sorted_entries = sorted(entries, key=lambda entry: entry.name.lower())
        except (OSError, PermissionError):
            continue

        directories = []
        for entry in sorted_entries:
            if entry.name in EXCLUDED_DIRS:
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    directories.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".md"):
                    yield Path(entry.path)
            except OSError:
                continue

        stack.extend(reversed(directories))


def count_markdown_files(base_dir: Path) -> int:
    """Count Markdown files using the same traversal as the file list."""
    return sum(1 for _ in _iter_markdown_files(base_dir))


def scan_files(base_dir: Path) -> dict:
    """Scan a directory once and return a nested tree and flat metadata list."""
    global _file_cache
    resolved_base = base_dir.resolve()
    while True:
        with _file_cache_lock:
            if _file_cache is not None and _file_cache["base_dir"] == resolved_base:
                return _file_cache
            entry_generation = _scan_generation

        tree: dict = {}
        files: list[dict] = []
        for md_file in _iter_markdown_files(resolved_base):
            try:
                relative = md_file.relative_to(resolved_base)
                file_stat = md_file.stat()
            except (OSError, ValueError):
                continue

            node = tree
            for part in relative.parts[:-1]:
                node = node.setdefault(part, {})
            node[relative.parts[-1]] = relative.as_posix()
            files.append(
                {
                    "path": relative.as_posix(),
                    "name": md_file.name,
                    "size": file_stat.st_size,
                    "modified": datetime.fromtimestamp(
                        file_stat.st_mtime,
                        tz=timezone.utc,
                    ).isoformat(),
                }
            )

        snapshot = {"base_dir": resolved_base, "tree": tree, "files": files}
        with _file_cache_lock:
            if _file_cache is not None and _file_cache["base_dir"] == resolved_base:
                return _file_cache
            if _scan_generation != entry_generation:
                continue
            _file_cache = snapshot
            return snapshot


def build_file_tree(base_dir: Path) -> dict:
    """Return a nested dictionary representing Markdown files."""
    return scan_files(base_dir)["tree"]


def get_file_list(base_dir: Path) -> list[dict]:
    """Return a flat list of Markdown files with metadata."""
    return scan_files(base_dir)["files"]


def search_markdown_file(
    base_dir: Path,
    rel_path: str,
    query_lower: str,
    result_limit: int,
    *,
    include_navigation: bool = False,
) -> list[dict]:
    """Return matching lines and context from one Markdown file."""
    target = validate_path(base_dir, rel_path)
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []

    matches = []
    occurrences: dict[str, int] = {}
    for index, line in enumerate(lines):
        if query_lower not in line.lower():
            continue
        start = max(0, index - 1)
        end = min(len(lines), index + 2)
        snippet = "\n".join(lines[start:end])
        if len(snippet) > 200:
            snippet = snippet[:200]
        matches.append(
            {
                "path": rel_path,
                "line_number": index + 1,
                "snippet": snippet,
            }
        )
        if include_navigation:
            key = line.strip().lower()
            occurrences[key] = occurrences.get(key, 0) + 1
            matches[-1].update(source_line=line, occurrence=occurrences[key])
        if len(matches) >= result_limit:
            break
    return matches


def search_content(base_dir: Path, query: str, *, limit: int = 50, cancelled=None) -> dict:
    """Search Markdown source deterministically, with one extra hit for truncation.

    ``cancelled`` is an optional callable checked between files by desktop workers.
    Navigation metadata leaves the existing web search response unchanged.
    """
    if len(query) < 2:
        return {"results": [], "truncated": False}
    if limit < 1:
        raise ValueError("limit must be positive")
    results = []
    for path in _iter_markdown_files(base_dir):
        if cancelled is not None and cancelled():
            break
        rel = path.relative_to(base_dir.resolve()).as_posix()
        try:
            results.extend(search_markdown_file(
                base_dir, rel, query.lower(), limit + 1 - len(results), include_navigation=True,
            ))
        except PathOutsideBaseError:
            continue  # A file may have been replaced with an escaping symlink.
        if len(results) > limit:
            break
    return {"results": results[:limit], "truncated": len(results) > limit}


__all__ = [
    "EXCLUDED_DIRS",
    "PathOutsideBaseError",
    "build_file_tree",
    "count_markdown_files",
    "get_file_list",
    "invalidate_file_cache",
    "scan_files",
    "search_markdown_file",
    "search_content",
    "validate_path",
]
