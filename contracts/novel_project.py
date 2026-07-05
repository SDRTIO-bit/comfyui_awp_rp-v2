"""NovelProject — novel project metadata.

schemaId: awp.novel.project.v1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_ID = "awp.novel.project.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class NovelProject:
    """A novel project with metadata and status."""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    project_id: str = ""
    title: str = ""
    genre: str = ""              # 都市/玄幻/悬疑/言情/科幻...
    target_platform: str = ""    # 起点/番茄/自定义
    target_reader: str = ""      # 目标读者画像
    core_emotion: str = ""       # 全书核心情绪
    one_sentence_pitch: str = ""
    status: str = "planning"     # planning / writing / paused / completed
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "title": self.title,
            "genre": self.genre,
            "target_platform": self.target_platform,
            "target_reader": self.target_reader,
            "core_emotion": self.core_emotion,
            "one_sentence_pitch": self.one_sentence_pitch,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NovelProject:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            project_id=data.get("project_id", ""),
            title=data.get("title", ""),
            genre=data.get("genre", ""),
            target_platform=data.get("target_platform", ""),
            target_reader=data.get("target_reader", ""),
            core_emotion=data.get("core_emotion", ""),
            one_sentence_pitch=data.get("one_sentence_pitch", ""),
            status=data.get("status", "planning"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
