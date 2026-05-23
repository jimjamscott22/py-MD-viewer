# Tables and Lists

[TOC]

Tables

### Basic Table

| Feature           | Status      | Notes                     |
|:------------------|:-----------:|:--------------------------|
| File browser      | Complete    | Recursive directory tree  |
| Live reload       | Complete    | SSE-based auto-refresh    |
| Syntax highlight  | Complete    | Pygments integration      |
| Dark mode         | Planned     | Future enhancement        |

### Alignment

| Left Aligned | Center Aligned | Right Aligned |
|:-------------|:--------------:|--------------:|
| Row 1        | Data           |          1.00 |
| Row 2        | Data           |         12.50 |
| Row 3        | Data           |        100.00 |

## Nested Lists

- **Web Frameworks**
  - Flask
    - Lightweight
    - Jinja2 templating
    - Large ecosystem
  - FastAPI
    - Async-first
    - Auto-generated docs
- **Markdown Libraries**
  - Python-Markdown
    - Extensible
    - Well-documented
  - mistune
    - Fast parsing

## Mixed Content

Here is a paragraph followed by a list, a table, and a code block all together.

1. First, we configure the server
2. Then, we start watching for changes
3. Finally, we open the browser

| Step | Action              | Command            |
|-----:|:--------------------|:-------------------|
|    1 | Install deps        | `uv sync`          |
|    2 | Start server        | `uv run md-preview`|
|    3 | Open browser        | Navigate to :8000  |

```python
# All three steps in code
import subprocess
subprocess.run(["uv", "sync"])
subprocess.run(["uv", "run", "md-preview"])
```

## Blockquote with Code

> To install the preview server, run:
>
> ```bash
> uv sync
> ```
>
> Then start it with `uv run md-preview`.
