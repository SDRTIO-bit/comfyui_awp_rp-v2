"""ChapterDraft — novel chapter draft.

schemaId: awp.novel.chapter-draft.v1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_ID = "awp.novel.chapter-draft.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ChapterDraft:
    """A chapter draft with revision tracking."""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    draft_id: str = ""
    chapter_id: str = ""
    revision: int = 1
    source_plan_revision: int = 1
    text: str = ""
    char_count: int = 0
    status: str = "draft"       # draft / accepted / rejected / superseded
    quality_decision_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "draft_id": self.draft_id,
            "chapter_id": self.chapter_id,
            "revision": self.revision,
            "source_plan_revision": self.source_plan_revision,
            "text": self.text,
            "char_count": self.char_count,
            "status": self.status,
            "quality_decision_id": self.quality_decision_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChapterDraft:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            draft_id=data.get("draft_id", ""),
            chapter_id=data.get("chapter_id", ""),
            revision=data.get("revision", 1),
            source_plan_revision=data.get("source_plan_revision", 1),
            text=data.get("text", ""),
            char_count=data.get("char_count", 0),
            status=data.get("status", "draft"),
            quality_decision_id=data.get("quality_decision_id", ""),
            created_at=data.get("created_at", ""),
        )
