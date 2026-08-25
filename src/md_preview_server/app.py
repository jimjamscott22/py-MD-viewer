"""Flask application for the Markdown preview server."""

import json
import os
import queue
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request
from werkzeug.utils import secure_filename

from .renderer import (
    render_markdown,
    render_markdown_cached,
    render_markdown_cached_with_meta,
    render_markdown_with_meta,
)
from .storage import (
    FileRevisionMismatch,
    atomic_write_text,
    read_text_stable,
    revision_from_stat,
)
from .watcher import start_watcher, stop_watcher

_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()
_watcher_lock = threading.Lock()
_current_observer = None
_file_cache: dict | None = None
_file_cache_lock = threading.Lock()
# Monotonic counter bumped on every invalidation. _scan_files captures the
# value at entry and retries if it changes during the scan, preventing a
# request from receiving or publishing an invalidated snapshot.
_scan_generation: int = 0

EXCLUDED_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".tox", ".mypy_cache"}

_MAX_CONTENT_SEARCH_WORKERS = 8
_MAX_CONTENT_SEARCH_RESULTS = 50

# Pool used to parallelize per-file content search. Created once at
# import time; worker threads are daemons and exit with the process.
_search_executor = ThreadPoolExecutor(
    max_workers=_MAX_CONTENT_SEARCH_WORKERS,
    thread_name_prefix="search",
)


def invalidate_file_cache() -> None:
    """Clear the cached file tree/list so the next access re-scans."""
    global _file_cache, _scan_generation
    with _file_cache_lock:
        _scan_generation += 1
        _file_cache = None


def notify_clients(changed_path: str, event_type: str = "file_modified") -> None:
    """Push a change event to all SSE subscribers."""
    invalidate_file_cache()
    message = json.dumps({"type": event_type, "file": changed_path})
    with _subscribers_lock:
        for q in _subscribers:
            try:
                q.put_nowait(message)
            except queue.Full:
                pass


def notify_tree_changed() -> None:
    """Notify all clients that the file tree has changed and invalidate cache."""
    invalidate_file_cache()
    message = json.dumps({"type": "tree_changed"})
    with _subscribers_lock:
        for q in _subscribers:
            try:
                q.put_nowait(message)
            except queue.Full:
                pass


def validate_path(base_dir: Path, rel_path: str) -> Path:
    """Validate a relative path is within base_dir. Returns resolved Path or aborts."""
    rel_path = rel_path.replace("\\", "/")
    target = (base_dir / rel_path).resolve()
    if not target.is_relative_to(base_dir.resolve()):
        abort(403)
    return target


def _iter_markdown_files(base_dir: Path):
    """Yield markdown files under base_dir without descending excluded directories."""
    stack = [base_dir.resolve()]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                sorted_entries = sorted(entries, key=lambda entry: entry.name.lower())
        except (OSError, PermissionError):
            continue

        dirs = []
        for entry in sorted_entries:
            if entry.name in EXCLUDED_DIRS:
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".md"):
                    yield Path(entry.path)
            except OSError:
                continue

        stack.extend(reversed(dirs))


def _count_markdown_files(base_dir: Path) -> int:
    """Count markdown files using the same pruned traversal as the file list."""
    return sum(1 for _ in _iter_markdown_files(base_dir))


def _scan_files(base_dir: Path) -> dict:
    """Scan the directory once and build both tree and file list."""
    global _file_cache
    resolved_base = base_dir.resolve()
    while True:
        # Fast path: cache hit under lock, then release while scanning.
        with _file_cache_lock:
            if _file_cache is not None and _file_cache["base_dir"] == resolved_base:
                return _file_cache
            entry_generation = _scan_generation

        tree: dict = {}
        files: list[dict] = []
        for md_file in _iter_markdown_files(resolved_base):
            try:
                rel = md_file.relative_to(resolved_base)
                stat = md_file.stat()
            except (OSError, ValueError):
                # Files can disappear or be replaced between scandir and stat.
                # Exclude them from both views of this snapshot.
                continue

            parts = rel.parts
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = rel.as_posix()
            files.append({
                "path": rel.as_posix(),
                "name": md_file.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            })

        cache = {"base_dir": resolved_base, "tree": tree, "files": files}
        with _file_cache_lock:
            if _file_cache is not None and _file_cache["base_dir"] == resolved_base:
                # Another thread published a snapshot while this scan ran.
                return _file_cache
            if _scan_generation != entry_generation:
                # This result was invalidated while it was being built. Retry
                # so this request also receives a current, internally
                # consistent snapshot.
                continue
            _file_cache = cache
            return cache


def build_file_tree(base_dir: Path) -> dict:
    """Build a nested dict representing the directory tree of .md files."""
    return _scan_files(base_dir)["tree"]


def get_file_list(base_dir: Path) -> list[dict]:
    """Get a flat list of .md files with metadata."""
    return _scan_files(base_dir)["files"]


def _search_markdown_file(
    base_dir: Path,
    rel_path: str,
    query_lower: str,
    result_limit: int,
) -> list[dict]:
    """Return at most result_limit matching lines from one Markdown file."""
    target = validate_path(base_dir, rel_path)
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []

    matches = []
    for i, line in enumerate(lines):
        if query_lower not in line.lower():
            continue
        start = max(0, i - 1)
        end = min(len(lines), i + 2)
        snippet = "\n".join(lines[start:end])
        if len(snippet) > 200:
            snippet = snippet[:200]
        matches.append({
            "path": rel_path,
            "line_number": i + 1,
            "snippet": snippet,
        })
        if len(matches) >= result_limit:
            break
    return matches


def create_app(base_dir: Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent / "static"),
        template_folder=str(Path(__file__).parent / "templates"),
    )
    app.config["BASE_DIR"] = base_dir or Path.cwd()
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # Pre-load CSS for export (read once, reuse on every request)
    static_css = Path(__file__).parent / "static" / "css"
    app.config["EXPORT_CSS"] = (
        (static_css / "style.css").read_text(encoding="utf-8")
        + "\n"
        + (static_css / "codehilite.css").read_text(encoding="utf-8")
    )

    # --- Static asset cache headers ---
    @app.after_request
    def add_cache_headers(response):
        if request.path.startswith("/static/"):
            if request.query_string:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    # --- Page routes ---

    @app.route("/")
    def index():
        tree = build_file_tree(app.config["BASE_DIR"])
        return render_template("index.html", tree=tree)

    @app.route("/view/<path:filepath>")
    def view_file(filepath: str):
        base = app.config["BASE_DIR"]
        target = validate_path(base, filepath)
        if not target.exists() or not target.is_file():
            abort(404)
        try:
            content, metadata = render_markdown_cached_with_meta(target)
        except UnicodeDecodeError:
            abort(400)
        tree = build_file_tree(base)
        title = metadata.get("title") or target.name
        return render_template(
            "view.html",
            content=content,
            filename=title,
            filepath=filepath,
            tree=tree,
            metadata=metadata,
        )

    @app.route("/events")
    def events():
        def stream():
            q: queue.Queue = queue.Queue(maxsize=50)
            with _subscribers_lock:
                _subscribers.append(q)
            try:
                while True:
                    try:
                        message = q.get(timeout=30)
                        yield f"data: {message}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            except GeneratorExit:
                pass
            finally:
                with _subscribers_lock:
                    try:
                        _subscribers.remove(q)
                    except ValueError:
                        pass

        return Response(
            stream(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # --- Phase 1: File listing & search API ---

    @app.route("/api/files")
    def api_files():
        base = app.config["BASE_DIR"]
        snapshot = _scan_files(base)
        return jsonify({
            "tree": snapshot["tree"],
            "files": snapshot["files"],
            "base_dir": str(base),
        })

    @app.route("/api/search")
    def api_search():
        query = request.args.get("q", "").strip().lower()
        if not query:
            return jsonify({"results": []})
        base = app.config["BASE_DIR"]
        results = []
        for f in get_file_list(base):
            if query in f["name"].lower() or query in f["path"].lower():
                results.append(f)
        return jsonify({"results": results})

    @app.route("/api/search/content")
    def api_search_content():
        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify({"results": [], "truncated": False})
        query_lower = query.lower()
        base = app.config["BASE_DIR"]

        # Keep only a small ordered window of work in flight. Results remain
        # deterministic by sorted path, but a capped response no longer queues
        # or drains the entire workspace.
        paths = sorted(f["path"] for f in get_file_list(base))
        results: list[dict] = []
        truncated = False
        in_flight = deque()
        next_path = 0

        while next_path < min(len(paths), _MAX_CONTENT_SEARCH_WORKERS):
            path = paths[next_path]
            future = _search_executor.submit(
                _search_markdown_file,
                base,
                path,
                query_lower,
                _MAX_CONTENT_SEARCH_RESULTS + 1,
            )
            in_flight.append((path, future))
            next_path += 1

        while in_flight:
            _path, future = in_flight.popleft()
            batch = future.result()
            remaining = _MAX_CONTENT_SEARCH_RESULTS - len(results)
            results.extend(batch[:remaining])

            if len(batch) > remaining:
                truncated = True
                break
            if len(results) == _MAX_CONTENT_SEARCH_RESULTS:
                # More queued or unsubmitted files mean the search stopped
                # early even if the current file contained exactly the last
                # result included in the response.
                truncated = bool(in_flight) or next_path < len(paths)
                break

            if next_path < len(paths):
                path = paths[next_path]
                next_future = _search_executor.submit(
                    _search_markdown_file,
                    base,
                    path,
                    query_lower,
                    _MAX_CONTENT_SEARCH_RESULTS + 1,
                )
                in_flight.append((path, next_future))
                next_path += 1

        for _path, future in in_flight:
            future.cancel()
        return jsonify({"results": results, "truncated": truncated})

    # --- Phase 2: Upload & create ---

    @app.route("/api/upload", methods=["POST"])
    def api_upload():
        base = app.config["BASE_DIR"]
        dest = request.form.get("destination", "").strip()
        uploaded = []
        errors = []

        files = request.files.getlist("files")
        if not files:
            return jsonify({"success": False, "error": "No files provided"}), 400

        for f in files:
            if not f.filename:
                continue
            name = Path(f.filename).name
            if not name.lower().endswith(".md"):
                errors.append({"name": name, "error": "Only .md files allowed"})
                continue
            rel = os.path.join(dest, name) if dest else name
            target = validate_path(base, rel)
            if target.exists():
                errors.append({"name": name, "error": "File already exists"})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            f.save(str(target))
            uploaded.append({"path": Path(rel).as_posix(), "name": name})

        if uploaded:
            notify_tree_changed()
        return jsonify({"success": True, "uploaded": uploaded, "errors": errors})

    @app.route("/api/create", methods=["POST"])
    def api_create():
        base = app.config["BASE_DIR"]
        data = request.get_json(silent=True) or {}
        rel_path = data.get("path", "").strip()
        content = data.get("content", "")

        if not rel_path:
            return jsonify({"success": False, "error": "Path is required"}), 400
        if not rel_path.lower().endswith(".md"):
            rel_path += ".md"

        target = validate_path(base, rel_path)
        if target.exists():
            return jsonify({"success": False, "error": "File already exists"}), 409

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        notify_tree_changed()
        return jsonify({
            "success": True,
            "path": Path(rel_path).as_posix(),
        })

    # --- Phase 3: Rename & delete ---

    @app.route("/api/rename", methods=["PUT"])
    def api_rename():
        base = app.config["BASE_DIR"]
        data = request.get_json(silent=True) or {}
        old_path = data.get("old_path", "").strip()
        new_path = data.get("new_path", "").strip()

        if not old_path or not new_path:
            return jsonify({"success": False, "error": "Both old_path and new_path required"}), 400
        if not new_path.lower().endswith(".md"):
            new_path += ".md"

        old_target = validate_path(base, old_path)
        new_target = validate_path(base, new_path)

        if not old_target.exists():
            return jsonify({"success": False, "error": "Source file not found"}), 404
        if new_target.exists():
            return jsonify({"success": False, "error": "Destination already exists"}), 409

        new_target.parent.mkdir(parents=True, exist_ok=True)
        old_target.rename(new_target)
        notify_tree_changed()
        return jsonify({
            "success": True,
            "old_path": old_path,
            "new_path": Path(new_path).as_posix(),
        })

    @app.route("/api/delete", methods=["DELETE"])
    def api_delete():
        base = app.config["BASE_DIR"]
        data = request.get_json(silent=True) or {}
        paths = data.get("paths", [])
        confirm = data.get("confirm", False)

        if not confirm:
            return jsonify({"success": False, "error": "Confirmation required"}), 400
        if not paths:
            return jsonify({"success": False, "error": "No paths provided"}), 400

        deleted = []
        errors = []
        for p in paths:
            target = validate_path(base, p)
            if not target.exists():
                errors.append({"path": p, "error": "File not found"})
                continue
            if not target.is_file():
                errors.append({"path": p, "error": "Not a file"})
                continue
            target.unlink()
            deleted.append(p)

        if deleted:
            notify_tree_changed()
        return jsonify({"success": True, "deleted": deleted, "errors": errors})

    # --- Phase 4: Directory picker ---

    @app.route("/api/directories")
    def api_directories():
        path_str = request.args.get("path", "")
        if path_str:
            browse_path = Path(path_str).resolve()
        else:
            browse_path = app.config["BASE_DIR"].resolve()

        if not browse_path.is_dir():
            return jsonify({"success": False, "error": "Not a directory"}), 400

        parent = str(browse_path.parent) if browse_path.parent != browse_path else None
        dirs = []
        try:
            for entry in sorted(browse_path.iterdir()):
                if entry.is_dir() and entry.name not in EXCLUDED_DIRS and not entry.name.startswith("."):
                    dirs.append({"name": entry.name, "path": str(entry)})
        except PermissionError:
            return jsonify({"success": False, "error": "Permission denied"}), 403

        md_count = _count_markdown_files(browse_path)

        return jsonify({
            "current": str(browse_path),
            "parent": parent,
            "directories": dirs,
            "md_count": md_count,
        })

    @app.route("/api/set-base-directory", methods=["POST"])
    def api_set_base_directory():
        global _current_observer
        data = request.get_json(silent=True) or {}
        path_str = data.get("path", "").strip()

        if not path_str:
            return jsonify({"success": False, "error": "Path is required"}), 400

        new_base = Path(path_str).resolve()
        if not new_base.is_dir():
            return jsonify({"success": False, "error": "Not a valid directory"}), 400

        app.config["BASE_DIR"] = new_base

        # Restart watcher
        with _watcher_lock:
            if _current_observer:
                stop_watcher(_current_observer)
            _current_observer = start_watcher(new_base, notify_clients)

        notify_tree_changed()
        files = get_file_list(new_base)
        return jsonify({
            "success": True,
            "base_dir": str(new_base),
            "file_count": len(files),
        })

    # --- Phase 5: Editor API ---

    @app.route("/api/content/<path:filepath>")
    def api_content(filepath: str):
        base = app.config["BASE_DIR"]
        target = validate_path(base, filepath)
        if not target.exists() or not target.is_file():
            abort(404)
        try:
            text, file_stat = read_text_stable(target)
        except UnicodeDecodeError:
            abort(400)
        except OSError:
            return jsonify({
                "success": False,
                "error": "File changed while it was being read. Try again.",
            }), 409
        return jsonify({
            "content": text,
            "path": filepath,
            "modified": datetime.fromtimestamp(
                file_stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            "revision": revision_from_stat(file_stat),
        })

    @app.route("/api/save", methods=["PUT"])
    def api_save():
        base = app.config["BASE_DIR"]
        data = request.get_json(silent=True) or {}
        filepath = data.get("path", "").strip()
        content = data.get("content")
        revision = data.get("revision")
        last_modified = data.get("last_modified")

        if not filepath:
            return jsonify({"success": False, "error": "Path is required"}), 400
        if content is None:
            return jsonify({"success": False, "error": "Content is required"}), 400
        if not isinstance(content, str):
            return jsonify({"success": False, "error": "Content must be text"}), 400

        target = validate_path(base, filepath)
        if not target.exists() or not target.is_file():
            return jsonify({"success": False, "error": "File not found"}), 404
        if target.suffix.lower() != ".md":
            return jsonify({"success": False, "error": "Only .md files can be saved"}), 400

        def conflict_response():
            try:
                server_content, server_stat = read_text_stable(target)
            except OSError:
                return jsonify({
                    "success": False,
                    "error": "File is changing on disk. Try again.",
                }), 409
            return jsonify({
                "success": False,
                "error": "conflict",
                "server_modified": datetime.fromtimestamp(
                    server_stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "server_revision": revision_from_stat(server_stat),
                "server_content": server_content,
            }), 409

        # Conflict detection
        try:
            current_stat = target.stat()
        except OSError:
            return jsonify({"success": False, "error": "File not found"}), 404
        current_revision = revision_from_stat(current_stat)
        expected_revision = None
        if revision:
            if current_revision != revision:
                return conflict_response()
            expected_revision = revision
        elif last_modified:
            current_mtime = datetime.fromtimestamp(
                current_stat.st_mtime, tz=timezone.utc
            ).isoformat()
            if current_mtime != last_modified:
                return conflict_response()
            expected_revision = current_revision

        try:
            saved_stat = atomic_write_text(
                target,
                content,
                expected_revision=expected_revision,
            )
        except FileRevisionMismatch:
            return conflict_response()
        except OSError as exc:
            return jsonify({"success": False, "error": f"Save failed: {exc}"}), 500

        invalidate_file_cache()
        return jsonify({
            "success": True,
            "path": filepath,
            "modified": datetime.fromtimestamp(
                saved_stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            "revision": revision_from_stat(saved_stat),
        })

    @app.route("/api/preview", methods=["POST"])
    def api_preview():
        data = request.get_json(silent=True) or {}
        content = data.get("content", "")
        html, metadata = render_markdown_with_meta(content)
        return jsonify({"html": html, "metadata": metadata})

    @app.route("/api/ai/ask", methods=["POST"])
    def api_ai_ask():
        data = request.get_json(silent=True) or {}
        prompt = data.get("prompt", "").strip()
        doc_content = data.get("document_content", "")

        if not prompt:
            return jsonify({"success": False, "error": "Prompt is required"}), 400

        api_key = os.environ.get("OPENAI_API_KEY", "local-key")
        base_url = os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1")
        model = os.environ.get("LLM_MODEL", "local-model")

        try:
            import openai
        except ImportError:
            return jsonify({
                "success": False,
                "error": (
                    "AI support requires the 'openai' package. "
                    "Install with: uv sync --extra ai"
                ),
            }), 501

        try:
            client = openai.OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful Markdown document assistant. The user will provide the current content of their document for context. Provide helpful answers, summaries, grammar fixes, or markdown formatting suggestions based on their prompt."},
                    {"role": "user", "content": f"Here is the current document content:\\n\\n{doc_content}\\n\\n---\\n\\nMy prompt: {prompt}"}
                ],
                max_tokens=600,
            )
            reply = response.choices[0].message.content
            return jsonify({"success": True, "response": reply})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # --- Phase 6: Export ---

    @app.route("/api/export/html/<path:filepath>")
    def api_export_html(filepath: str):
        base = app.config["BASE_DIR"]
        target = validate_path(base, filepath)
        if not target.exists() or not target.is_file():
            abort(404)
        try:
            html_body = render_markdown_cached(target)
        except UnicodeDecodeError:
            abort(400)
        export_css = app.config["EXPORT_CSS"]

        standalone = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"<title>{target.stem}</title>\n"
            f"<style>{export_css}</style>\n"
            "<style>body{max-width:800px;margin:2rem auto;padding:0 1rem;}</style>\n"
            "</head>\n<body>\n"
            f'<article class="markdown-body">{html_body}</article>\n'
            "</body>\n</html>"
        )

        filename = secure_filename(target.stem) + ".html"
        return Response(
            standalone,
            mimetype="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


def main() -> None:
    """Entry point for the md-preview command."""
    global _current_observer
    base_dir = Path.cwd()
    app = create_app(base_dir)

    with _watcher_lock:
        _current_observer = start_watcher(base_dir, notify_clients)

    print(f"Serving markdown files from: {base_dir}")
    print("Open http://localhost:8000 in your browser")
    print("Press Ctrl+C to stop\n")

    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
