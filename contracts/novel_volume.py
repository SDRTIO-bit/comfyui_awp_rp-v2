"""VolumePlan — novel volume plan.

schemaId: awp.novel.volume-plan.v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_ID = "awp.novel.volume-plan.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VolumePlan:
    """A volume plan within a novel project."""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    volume_id: str = ""
    project_id: str = ""
    index: int = 0
    title: str = ""
    chapter_start: int = 0
    chapter_end: int = 0
    core_conflict: str = ""
    emotional_arc: str = ""
    major_payoffs: tuple[str, ...] = ()
    foreshadowing_plan: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "volume_id": self.volume_id,
            "project_id": self.project_id,
            "index": self.index,
            "title": self.title,
            "chapter_start": self.chapter_start,
            "chapter_end": self.chapter_end,
            "core_conflict": self.core_conflict,
            "emotional_arc": self.emotional_arc,
            "major_payoffs": list(self.major_payoffs),
            "foreshadowing_plan": list(self.foreshadowing_plan),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VolumePlan:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            volume_id=data.get("volume_id", ""),
            project_id=data.get("project_id", ""),
            index=data.get("index", 0),
            title=data.get("title", ""),
            chapter_start=data.get("chapter_start", 0),
            chapter_end=data.get("chapter_end", 0),
            core_conflict=data.get("core_conflict", ""),
            emotional_arc=data.get("emotional_arc", ""),
            major_payoffs=tuple(data.get("major_payoffs", [])),
            foreshadowing_plan=tuple(data.get("foreshadowing_plan", [])),
        )
