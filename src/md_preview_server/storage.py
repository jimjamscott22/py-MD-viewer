"""Stable file revision and atomic text storage helpers."""

import os
import stat
import tempfile
from pathlib import Path


class FileChangedDuringRead(OSError):
    """Raised when a file does not remain stable long enough to read."""


class FileRevisionMismatch(OSError):
    """Raised when a guarded write observes a newer file revision."""


def revision_from_stat(file_stat: os.stat_result) -> str:
    """Return the public revision token for a filesystem stat result."""
    return f"{file_stat.st_mtime_ns}:{file_stat.st_size}"


def get_file_revision(path: Path) -> str:
    """Return the current ``<mtime_ns>:<size>`` revision for a file."""
    return revision_from_stat(path.stat())


def read_text_stable(
    path: Path,
    *,
    encoding: str = "utf-8",
    max_attempts: int = 3,
) -> tuple[str, os.stat_result]:
    """Read text and a matching stat result, retrying concurrent changes."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for _ in range(max_attempts):
        before = path.stat()
        content = path.read_text(encoding=encoding)
        after = path.stat()
        if revision_from_stat(before) == revision_from_stat(after):
            return content, after

    raise FileChangedDuringRead(f"File changed while being read: {path}")


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    expected_revision: str | None = None,
) -> os.stat_result:
    """Atomically replace a text file, optionally guarding its revision."""
    original_mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.chmod(temp_path, original_mode)

        if expected_revision is not None and get_file_revision(path) != expected_revision:
            raise FileRevisionMismatch(f"File revision changed before save: {path}")

        os.replace(temp_path, path)
        return path.stat()
    except BaseException:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
