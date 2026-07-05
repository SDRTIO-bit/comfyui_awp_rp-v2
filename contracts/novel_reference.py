"""ReferenceBook — novel reference book for benchmarking.

schemaId: awp.novel.reference-book.v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_ID = "awp.novel.reference-book.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReferenceBook:
    """对标书。"""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    book_id: str = ""
    project_id: str = ""
    name: str = ""
    role: str = "benchmark"       # "primary" / "secondary" / "benchmark"
    genre: str = ""
    total_chapters: int = 0
    style_profile: str = ""
    emotion_modules: tuple[dict[str, Any], ...] = ()
    rhythm_profile: dict[str, Any] = field(default_factory=dict)
    chapter_summaries: tuple[dict[str, Any], ...] = ()
    deconstruction_report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "book_id": self.book_id,
            "project_id": self.project_id,
            "name": self.name,
            "role": self.role,
            "genre": self.genre,
            "total_chapters": self.total_chapters,
            "style_profile": self.style_profile,
            "emotion_modules": list(self.emotion_modules),
            "rhythm_profile": self.rhythm_profile,
            "chapter_summaries": list(self.chapter_summaries),
            "deconstruction_report": self.deconstruction_report,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceBook:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            book_id=data.get("book_id", ""),
            project_id=data.get("project_id", ""),
            name=data.get("name", ""),
            role=data.get("role", "benchmark"),
            genre=data.get("genre", ""),
            total_chapters=data.get("total_chapters", 0),
            style_profile=data.get("style_profile", ""),
            emotion_modules=tuple(data.get("emotion_modules", [])),
            rhythm_profile=dict(data.get("rhythm_profile", {})),
            chapter_summaries=tuple(data.get("chapter_summaries", [])),
            deconstruction_report=data.get("deconstruction_report", ""),
        )
