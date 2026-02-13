"""Flask application for the Markdown preview server."""

import json
import queue
import threading
from pathlib import Path

from flask import Flask, Response, abort, render_template, request

from .renderer import render_markdown
from .watcher import start_watcher

_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()

EXCLUDED_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".tox", ".mypy_cache"}


def notify_clients(changed_path: str) -> None:
    """Push a change event to all SSE subscribers."""
    message = json.dumps({"file": changed_path})
    with _subscribers_lock:
        for q in _subscribers:
            try:
                q.put_nowait(message)
            except queue.Full:
                pass


def build_file_tree(base_dir: Path) -> dict:
    """Build a nested dict representing the directory tree of .md files."""
    tree: dict = {}
    for md_file in sorted(base_dir.rglob("*.md")):
        rel = md_file.relative_to(base_dir)
        parts = rel.parts
        # Skip files inside excluded directories
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = rel.as_posix()
    return tree


def create_app(base_dir: Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent / "static"),
        template_folder=str(Path(__file__).parent / "templates"),
    )
    app.config["BASE_DIR"] = base_dir or Path.cwd()

    @app.route("/")
    def index():
        tree = build_file_tree(app.config["BASE_DIR"])
        return render_template("index.html", tree=tree)

    @app.route("/view/<path:filepath>")
    def view_file(filepath: str):
        base = app.config["BASE_DIR"]
        target = (base / filepath).resolve()
        # Security: prevent path traversal
        if not target.is_relative_to(base.resolve()):
            abort(403)
        if not target.exists() or not target.is_file():
            abort(404)
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            abort(400)
        content = render_markdown(text)
        tree = build_file_tree(base)
        return render_template(
            "view.html",
            content=content,
            filename=target.name,
            filepath=filepath,
            tree=tree,
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

    return app


def main() -> None:
    """Entry point for the md-preview command."""
    base_dir = Path.cwd()
    app = create_app(base_dir)

    # Start the file watcher
    start_watcher(base_dir, notify_clients)

    print(f"Serving markdown files from: {base_dir}")
    print("Open http://localhost:8000 in your browser")
    print("Press Ctrl+C to stop\n")

    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
