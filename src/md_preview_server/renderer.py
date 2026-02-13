"""Markdown-to-HTML rendering pipeline."""

import markdown


def render_markdown(text: str) -> str:
    """Convert markdown text to styled HTML."""
    extensions = [
        "fenced_code",
        "codehilite",
        "tables",
        "toc",
        "sane_lists",
        "smarty",
    ]
    extension_configs = {
        "codehilite": {
            "css_class": "codehilite",
            "linenums": False,
            "guess_lang": False,
        },
        "toc": {
            "permalink": True,
        },
    }
    return markdown.markdown(
        text,
        extensions=extensions,
        extension_configs=extension_configs,
    )
