"""Compatibility exports for :mod:`md_preview_core.storage`."""

from md_preview_core.storage import (
    FileChangedDuringRead,
    FileRevisionMismatch,
    atomic_write_text,
    get_file_revision,
    read_text_stable,
    revision_from_stat,
)

__all__ = [
    "FileChangedDuringRead",
    "FileRevisionMismatch",
    "atomic_write_text",
    "get_file_revision",
    "read_text_stable",
    "revision_from_stat",
]
