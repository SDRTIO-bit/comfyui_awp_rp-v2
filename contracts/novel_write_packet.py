"""NovelWritePacket — Writer input packet for novel chapter writing.

schemaId: awp.novel.write-packet.v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .novel_chapter import ChapterPlan, BeatDetail
from .novel_ledger import LedgerItem
from .novel_director_guidance import DirectorGuidance

SCHEMA_ID = "awp.novel.write-packet.v1"
SCHEMA_VERSION = 1


@dataclass
class NovelWritePacket:
    """Writer 的输入包，对应 RP 的 WriterInputBundle。"""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    packet_id: str = ""
    project_id: str = ""
    chapter_id: str = ""
    chapter_plan: ChapterPlan = field(default_factory=ChapterPlan)
    previous_chapter_summary: str = ""
    relevant_ledger_items: list[LedgerItem] = field(default_factory=list)
    character_states: dict[str, Any] = field(default_factory=dict)
    world_constraints: list[str] = field(default_factory=list)
    style_profile: dict[str, Any] = field(default_factory=dict)
    benchmark_snippets: list[str] = field(default_factory=list)
    director_guidance: DirectorGuidance = field(default_factory=DirectorGuidance)

    # 分 beat 模式
    current_scene_beat: BeatDetail | None = None
    accumulated_text: str = ""

    # 写前三步（从 oh-story 吸收）
    writing_intent: str = ""
    emotion_module: dict[str, Any] = field(default_factory=dict)
    rhythm_reference: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "project_id": self.project_id,
            "chapter_id": self.chapter_id,
            "chapter_plan": self.chapter_plan.to_dict(),
            "previous_chapter_summary": self.previous_chapter_summary,
            "relevant_ledger_items": [i.to_dict() for i in self.relevant_ledger_items],
            "character_states": self.character_states,
            "world_constraints": self.world_constraints,
            "style_profile": self.style_profile,
            "benchmark_snippets": self.benchmark_snippets,
            "director_guidance": self.director_guidance.to_dict(),
            "current_scene_beat": self.current_scene_beat.to_dict() if self.current_scene_beat else None,
            "accumulated_text": self.accumulated_text,
            "writing_intent": self.writing_intent,
            "emotion_module": self.emotion_module,
            "rhythm_reference": self.rhythm_reference,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NovelWritePacket:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            packet_id=data.get("packet_id", ""),
            project_id=data.get("project_id", ""),
            chapter_id=data.get("chapter_id", ""),
            chapter_plan=ChapterPlan.from_dict(data.get("chapter_plan", {})),
            previous_chapter_summary=data.get("previous_chapter_summary", ""),
            relevant_ledger_items=[LedgerItem.from_dict(i) for i in data.get("relevant_ledger_items", [])],
            character_states=dict(data.get("character_states", {})),
            world_constraints=list(data.get("world_constraints", [])),
            style_profile=dict(data.get("style_profile", {})),
            benchmark_snippets=list(data.get("benchmark_snippets", [])),
            director_guidance=DirectorGuidance.from_dict(data.get("director_guidance", {})),
            current_scene_beat=BeatDetail.from_dict(data["current_scene_beat"]) if data.get("current_scene_beat") is not None else None,
            accumulated_text=data.get("accumulated_text", ""),
            writing_intent=data.get("writing_intent", ""),
            emotion_module=dict(data.get("emotion_module", {})),
            rhythm_reference=dict(data.get("rhythm_reference", {})),
        )
