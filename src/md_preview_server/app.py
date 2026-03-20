"""Flask application for the Markdown preview server."""

import json
import os
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
import openai

from flask import Flask, Response, abort, jsonify, render_template, request
from werkzeug.utils import secure_filename

from .renderer import (
    render_markdown,
    render_markdown_cached,
    render_markdown_cached_with_meta,
    render_markdown_with_meta,
)
from .watcher import start_watcher, stop_watcher

_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()
_watcher_lock = threading.Lock()
_current_observer = None
_file_cache: dict | None = None
_file_cache_lock = threading.Lock()

EXCLUDED_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".tox", ".mypy_cache"}


def invalidate_file_cache() -> None:
    """Clear the cached file tree/list so the next access re-scans."""
    global _file_cache
    with _file_cache_lock:
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


def _scan_files(base_dir: Path) -> dict:
    """Scan the directory once and build both tree and file list."""
    global _file_cache
    with _file_cache_lock:
        if _file_cache is not None and _file_cache["base_dir"] == base_dir:
            return _file_cache

    tree: dict = {}
    files: list[dict] = []
    for md_file in sorted(base_dir.rglob("*.md")):
        rel = md_file.relative_to(base_dir)
        parts = rel.parts
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        # Build tree
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = rel.as_posix()
        # Build file list
        stat = md_file.stat()
        files.append({
            "path": rel.as_posix(),
            "name": md_file.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    cache = {"base_dir": base_dir, "tree": tree, "files": files}
    with _file_cache_lock:
        _file_cache = cache
    return cache


def build_file_tree(base_dir: Path) -> dict:
    """Build a nested dict representing the directory tree of .md files."""
    return _scan_files(base_dir)["tree"]


def get_file_list(base_dir: Path) -> list[dict]:
    """Get a flat list of .md files with metadata."""
    return _scan_files(base_dir)["files"]


def create_app(base_dir: Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent / "static"),
        template_folder=str(Path(__file__).parent / "templates"),
    )
    app.config["BASE_DIR"] = base_dir or Path.cwd()

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
            response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
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
        return jsonify({
            "tree": build_file_tree(base),
            "files": get_file_list(base),
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

        md_count = sum(1 for _ in browse_path.rglob("*.md")
                       if not any(p in EXCLUDED_DIRS for p in _.relative_to(browse_path).parts))

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
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            abort(400)
        stat = target.stat()
        return jsonify({
            "content": text,
            "path": filepath,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    @app.route("/api/save", methods=["PUT"])
    def api_save():
        base = app.config["BASE_DIR"]
        data = request.get_json(silent=True) or {}
        filepath = data.get("path", "").strip()
        content = data.get("content")
        last_modified = data.get("last_modified")

        if not filepath:
            return jsonify({"success": False, "error": "Path is required"}), 400
        if content is None:
            return jsonify({"success": False, "error": "Content is required"}), 400

        target = validate_path(base, filepath)
        if not target.exists():
            return jsonify({"success": False, "error": "File not found"}), 404

        # Conflict detection
        if last_modified:
            current_mtime = datetime.fromtimestamp(
                target.stat().st_mtime, tz=timezone.utc
            ).isoformat()
            if current_mtime != last_modified:
                return jsonify({
                    "success": False,
                    "error": "conflict",
                    "server_modified": current_mtime,
                    "server_content": target.read_text(encoding="utf-8"),
                }), 409

        target.write_text(content, encoding="utf-8")
        stat = target.stat()
        return jsonify({
            "success": True,
            "path": filepath,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
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
