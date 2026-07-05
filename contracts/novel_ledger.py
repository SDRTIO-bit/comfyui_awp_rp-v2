"""LedgerItem — novel continuity ledger item.

schemaId: awp.novel.ledger-item.v1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_ID = "awp.novel.ledger-item.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LedgerItem:
    """A continuity ledger item tracking facts, foreshadowing, timelines, etc."""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    item_id: str = ""
    project_id: str = ""
    section: str = ""       # character_state / timeline / foreshadowing / world_rules / relationship / open_threads
    entity: str = ""        # 关联实体名
    content: str = ""       # 条目内容
    status: str = "active"  # active / resolved / contradicted / stale
    source_chapter: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "item_id": self.item_id,
            "project_id": self.project_id,
            "section": self.section,
            "entity": self.entity,
            "content": self.content,
            "status": self.status,
            "source_chapter": self.source_chapter,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LedgerItem:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            item_id=data.get("item_id", ""),
            project_id=data.get("project_id", ""),
            section=data.get("section", ""),
            entity=data.get("entity", ""),
            content=data.get("content", ""),
            status=data.get("status", "active"),
            source_chapter=data.get("source_chapter", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
