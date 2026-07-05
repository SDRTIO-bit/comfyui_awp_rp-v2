"""BatchProgress — novel batch generation progress tracking.

schemaId: awp.novel.batch-progress.v1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_ID = "awp.novel.batch-progress.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BatchProgress:
    """批量生成进度追踪。"""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    batch_id: str = ""
    project_id: str = ""
    chapter_start: int = 0
    chapter_end: int = 0
    chapter_index: int = 0       # 当前处理的章节
    status: str = "pending"      # pending / in_progress / completed / failed
    retry_count: int = 0
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "project_id": self.project_id,
            "chapter_start": self.chapter_start,
            "chapter_end": self.chapter_end,
            "chapter_index": self.chapter_index,
            "status": self.status,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchProgress:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            batch_id=data.get("batch_id", ""),
            project_id=data.get("project_id", ""),
            chapter_start=data.get("chapter_start", 0),
            chapter_end=data.get("chapter_end", 0),
            chapter_index=data.get("chapter_index", 0),
            status=data.get("status", "pending"),
            retry_count=data.get("retry_count", 0),
            error_message=data.get("error_message", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
