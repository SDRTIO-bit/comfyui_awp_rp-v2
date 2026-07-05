"""NovelCharacter, CharacterRelationship — novel character management.

schemaId: awp.novel.character.v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_ID = "awp.novel.character.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CharacterRelationship:
    """角色关系。"""
    target_character_id: str = ""
    target_name: str = ""
    relation_type: str = ""     # 恋人/仇人/师徒/父子/对手/盟友/暗恋...
    description: str = ""
    tension: str = "none"       # high / medium / low / none

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_character_id": self.target_character_id,
            "target_name": self.target_name,
            "relation_type": self.relation_type,
            "description": self.description,
            "tension": self.tension,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterRelationship:
        return cls(
            target_character_id=data.get("target_character_id", ""),
            target_name=data.get("target_name", ""),
            relation_type=data.get("relation_type", ""),
            description=data.get("description", ""),
            tension=data.get("tension", "none"),
        )


@dataclass(frozen=True)
class NovelCharacter:
    """小说角色。多角色管理、关系图、语言风格、POV 资格。"""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    character_id: str = ""
    project_id: str = ""
    name: str = ""
    aliases: tuple[str, ...] = ()
    role: str = "supporting"    # protagonist / antagonist / supporting / minor
    personality: str = ""
    voice_style: str = ""       # 口语化/书面腔/方言/特殊口癖
    pov_eligible: bool = False
    core_motivation: str = ""
    weakness: str = ""
    relationships: tuple[CharacterRelationship, ...] = ()
    current_state: dict[str, Any] = field(default_factory=dict)
    arc_phase: str = "setup"    # setup / challenge / growth / crisis / transformation
    first_appearance: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "project_id": self.project_id,
            "name": self.name,
            "aliases": list(self.aliases),
            "role": self.role,
            "personality": self.personality,
            "voice_style": self.voice_style,
            "pov_eligible": self.pov_eligible,
            "core_motivation": self.core_motivation,
            "weakness": self.weakness,
            "relationships": [r.to_dict() for r in self.relationships],
            "current_state": self.current_state,
            "arc_phase": self.arc_phase,
            "first_appearance": self.first_appearance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NovelCharacter:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            character_id=data.get("character_id", ""),
            project_id=data.get("project_id", ""),
            name=data.get("name", ""),
            aliases=tuple(data.get("aliases", [])),
            role=data.get("role", "supporting"),
            personality=data.get("personality", ""),
            voice_style=data.get("voice_style", ""),
            pov_eligible=data.get("pov_eligible", False),
            core_motivation=data.get("core_motivation", ""),
            weakness=data.get("weakness", ""),
            relationships=tuple(CharacterRelationship.from_dict(r) for r in data.get("relationships", [])),
            current_state=dict(data.get("current_state", {})),
            arc_phase=data.get("arc_phase", "setup"),
            first_appearance=data.get("first_appearance", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
