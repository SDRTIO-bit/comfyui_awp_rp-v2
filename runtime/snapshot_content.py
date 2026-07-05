"""Helpers for reading normalized content from RoundSnapshot dictionaries."""

from __future__ import annotations

from typing import Any


def worldbook_entry_excerpt(entry: dict[str, Any], limit: int | None = None) -> str:
    """Return the usable text for a worldbook entry from old or new snapshots."""
    raw = (
        entry.get("content_excerpt")
        or entry.get("content")
        or entry.get("summary")
        or ""
    )
    text = str(raw)
    if limit is None:
        return text
    return text[:limit]
