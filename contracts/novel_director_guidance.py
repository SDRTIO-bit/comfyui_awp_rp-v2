"""DirectorGuidance, OutlineEnhancement, ForeshadowingAction, CharacterArcBeat, SubplotStatus.

schemaId: awp.novel.director-guidance.v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_ID = "awp.novel.director-guidance.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class OutlineEnhancement:
    """大纲优化建议。"""
    target: str = ""             # "volume" / "chapter" / "scene_beat"
    target_id: str = ""
    enhancement_type: str = ""   # "add_beat" / "modify_beat" / "add_subplot" / "adjust_pacing" / "add_foreshadowing"
    description: str = ""
    reasoning: str = ""
    priority: str = "optional"   # "must_have" / "nice_to_have" / "optional"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "target_id": self.target_id,
            "enhancement_type": self.enhancement_type,
            "description": self.description,
            "reasoning": self.reasoning,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutlineEnhancement:
        return cls(
            target=data.get("target", ""),
            target_id=data.get("target_id", ""),
            enhancement_type=data.get("enhancement_type", ""),
            description=data.get("description", ""),
            reasoning=data.get("reasoning", ""),
            priority=data.get("priority", "optional"),
        )


@dataclass(frozen=True)
class ForeshadowingAction:
    """伏笔调度动作。"""
    foreshadowing_id: str = ""
    action: str = ""             # "plant" / "advance" / "payoff" / "red_herring"
    scene_context: str = ""
    subtlety: str = "implicit"   # "explicit" / "implicit" / "background"

    def to_dict(self) -> dict[str, Any]:
        return {
            "foreshadowing_id": self.foreshadowing_id,
            "action": self.action,
            "scene_context": self.scene_context,
            "subtlety": self.subtlety,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForeshadowingAction:
        return cls(
            foreshadowing_id=data.get("foreshadowing_id", ""),
            action=data.get("action", ""),
            scene_context=data.get("scene_context", ""),
            subtlety=data.get("subtlety", "implicit"),
        )


@dataclass(frozen=True)
class CharacterArcBeat:
    """角色弧光节拍。"""
    character_name: str = ""
    arc_phase: str = ""          # "setup" / "challenge" / "growth" / "crisis" / "transformation"
    beat_description: str = ""
    relationship_shifts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_name": self.character_name,
            "arc_phase": self.arc_phase,
            "beat_description": self.beat_description,
            "relationship_shifts": list(self.relationship_shifts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterArcBeat:
        return cls(
            character_name=data.get("character_name", ""),
            arc_phase=data.get("arc_phase", ""),
            beat_description=data.get("beat_description", ""),
            relationship_shifts=tuple(data.get("relationship_shifts", [])),
        )


@dataclass(frozen=True)
class SubplotStatus:
    """支线进度。"""
    subplot_name: str = ""
    status: str = "dormant"      # "dormant" / "advancing" / "climaxing" / "resolving" / "resolved"
    chapters_since_last_update: int = 0
    urgency: str = "can_wait"    # "needs_attention" / "on_track" / "can_wait"

    def to_dict(self) -> dict[str, Any]:
        return {
            "subplot_name": self.subplot_name,
            "status": self.status,
            "chapters_since_last_update": self.chapters_since_last_update,
            "urgency": self.urgency,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubplotStatus:
        return cls(
            subplot_name=data.get("subplot_name", ""),
            status=data.get("status", "dormant"),
            chapters_since_last_update=data.get("chapters_since_last_update", 0),
            urgency=data.get("urgency", "can_wait"),
        )


@dataclass(frozen=True)
class DirectorGuidance:
    """Director 的输出，包含当章方向 + 大纲优化建议 + 伏笔调度。"""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    guidance_id: str = ""

    # 当章方向
    chapter_direction: str = ""
    emotional_arc: str = ""
    pacing_strategy: str = ""
    key_scenes: tuple[str, ...] = ()
    dialogue_tone: str = ""

    # 大纲优化
    outline_enhancements: tuple[OutlineEnhancement, ...] = ()
    foreshadowing_schedule: tuple[ForeshadowingAction, ...] = ()
    character_arc_beats: tuple[CharacterArcBeat, ...] = ()
    reader_expectation_plan: str = ""

    # 全局视角
    subplot_status: tuple[SubplotStatus, ...] = ()
    risk_flags: tuple[str, ...] = ()
    opportunities: tuple[str, ...] = ()

    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "guidance_id": self.guidance_id,
            "chapter_direction": self.chapter_direction,
            "emotional_arc": self.emotional_arc,
            "pacing_strategy": self.pacing_strategy,
            "key_scenes": list(self.key_scenes),
            "dialogue_tone": self.dialogue_tone,
            "outline_enhancements": [e.to_dict() for e in self.outline_enhancements],
            "foreshadowing_schedule": [f.to_dict() for f in self.foreshadowing_schedule],
            "character_arc_beats": [c.to_dict() for c in self.character_arc_beats],
            "reader_expectation_plan": self.reader_expectation_plan,
            "subplot_status": [s.to_dict() for s in self.subplot_status],
            "risk_flags": list(self.risk_flags),
            "opportunities": list(self.opportunities),
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectorGuidance:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            guidance_id=data.get("guidance_id", ""),
            chapter_direction=data.get("chapter_direction", ""),
            emotional_arc=data.get("emotional_arc", ""),
            pacing_strategy=data.get("pacing_strategy", ""),
            key_scenes=tuple(data.get("key_scenes", [])),
            dialogue_tone=data.get("dialogue_tone", ""),
            outline_enhancements=tuple(OutlineEnhancement.from_dict(e) for e in data.get("outline_enhancements", [])),
            foreshadowing_schedule=tuple(ForeshadowingAction.from_dict(f) for f in data.get("foreshadowing_schedule", [])),
            character_arc_beats=tuple(CharacterArcBeat.from_dict(c) for c in data.get("character_arc_beats", [])),
            reader_expectation_plan=data.get("reader_expectation_plan", ""),
            subplot_status=tuple(SubplotStatus.from_dict(s) for s in data.get("subplot_status", [])),
            risk_flags=tuple(data.get("risk_flags", [])),
            opportunities=tuple(data.get("opportunities", [])),
            reasoning=data.get("reasoning", ""),
        )
