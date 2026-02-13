# Code Examples

This file demonstrates syntax highlighting for various programming languages.

## Python

```python
from pathlib import Path


def find_markdown_files(directory: Path) -> list[Path]:
    """Recursively find all markdown files in a directory."""
    return sorted(directory.rglob("*.md"))


if __name__ == "__main__":
    files = find_markdown_files(Path.cwd())
    for f in files:
        print(f"Found: {f.name}")
```

## JavaScript

```javascript
async function fetchMarkdown(filepath) {
    const response = await fetch(`/view/${filepath}`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response.text();
}

document.addEventListener("DOMContentLoaded", () => {
    console.log("Page loaded");
});
```

## HTML

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hello World</title>
</head>
<body>
    <h1>Hello, World!</h1>
    <p>This is a paragraph.</p>
</body>
</html>
```

## JSON

```json
{
    "name": "md-preview-server",
    "version": "0.1.0",
    "dependencies": {
        "flask": ">=3.0",
        "markdown": ">=3.5"
    }
}
```

## Bash

```bash
#!/bin/bash
echo "Installing dependencies..."
uv sync
echo "Starting server..."
uv run md-preview
```

## Plain Code Block (no language)

```
This is a plain code block without a language specified.
It should render as monospace text without syntax highlighting.
```

## Inline Code

You can also use inline code like `print("hello")` or reference variables like `my_variable` within a sentence.
