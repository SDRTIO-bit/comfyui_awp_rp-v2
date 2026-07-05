"""NovelPlan — full novel plan generated from a brief concept.

schemaId: awp.novel.plan.v1

Covers: core outline, world settings, characters, volume plans.
Based on OKR outline method: O (objective) + KR (key results).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_ID = "awp.novel.plan.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CoreOutline:
    """核心纲：表层（故事骨架）+ 里层（核心卖点）。"""
    surface: str = ""      # 表层：开篇→过程→结尾，主角目标+驱动力
    inner: str = ""        # 里层：核心卖点，读者安利时怎么总结
    one_sentence: str = "" # 一句话大纲

    def to_dict(self) -> dict[str, Any]:
        return {"surface": self.surface, "inner": self.inner, "one_sentence": self.one_sentence}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoreOutline:
        data = data if isinstance(data, dict) else {}
        return cls(
            surface=str(data.get("surface", "") or ""),
            inner=str(data.get("inner", "") or ""),
            one_sentence=str(data.get("one_sentence", "") or ""),
        )


@dataclass(frozen=True)
class UpgradeSystem:
    """升级体系：角色凭什么变强、阶梯、质变、代价。"""
    energy_source: str = ""         # 底层能源（灵气/血脉/科技/信仰/法则领悟）
    secondary_source: str = ""      # 次要来源（悟性/天赋/心境）
    tiers: tuple[str, ...] = ()     # 大阶列表（4-7个），每阶描述质变内容
    tier_details: tuple[dict[str, Any], ...] = ()  # 每阶的输入/过程/输出/代价
    exception_mechanism: str = ""   # 主角的例外机制（来源/优势/代价/边界）

    def to_dict(self) -> dict[str, Any]:
        return {
            "energy_source": self.energy_source,
            "secondary_source": self.secondary_source,
            "tiers": list(self.tiers),
            "tier_details": [dict(d) for d in self.tier_details],
            "exception_mechanism": self.exception_mechanism,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UpgradeSystem:
        data = data if isinstance(data, dict) else {}
        tiers = data.get("tiers", [])
        tiers = tuple(tiers) if isinstance(tiers, (list, tuple)) else ()
        td = data.get("tier_details", [])
        td = tuple(td) if isinstance(td, (list, tuple)) else ()
        return cls(
            energy_source=str(data.get("energy_source", "") or ""),
            secondary_source=str(data.get("secondary_source", "") or ""),
            tiers=tiers,
            tier_details=td,
            exception_mechanism=str(data.get("exception_mechanism", "") or ""),
        )


@dataclass(frozen=True)
class ResourceSystem:
    """资源体系：稀缺度、获取渠道、使用门槛。"""
    description: str = ""
    low_tier_resources: str = ""
    mid_tier_resources: str = ""
    high_tier_resources: str = ""
    resource_flow: str = ""  # 资源如何在社会中流通

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "low_tier_resources": self.low_tier_resources,
            "mid_tier_resources": self.mid_tier_resources,
            "high_tier_resources": self.high_tier_resources,
            "resource_flow": self.resource_flow,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceSystem:
        data = data if isinstance(data, dict) else {}
        return cls(
            description=str(data.get("description", "") or ""),
            low_tier_resources=str(data.get("low_tier_resources", "") or ""),
            mid_tier_resources=str(data.get("mid_tier_resources", "") or ""),
            high_tier_resources=str(data.get("high_tier_resources", "") or ""),
            resource_flow=str(data.get("resource_flow", "") or ""),
        )


@dataclass(frozen=True)
class WorldSetting:
    """世界观设定。"""
    era: str = ""               # 时代背景
    geography: str = ""         # 地理/空间结构
    social_structure: str = ""  # 社会结构/势力分布
    core_rules: str = ""        # 核心规则/禁忌
    upgrade_system: UpgradeSystem = field(default_factory=UpgradeSystem)
    resource_system: ResourceSystem = field(default_factory=ResourceSystem)
    key_locations: tuple[str, ...] = ()  # 关键地点

    def to_dict(self) -> dict[str, Any]:
        return {
            "era": self.era,
            "geography": self.geography,
            "social_structure": self.social_structure,
            "core_rules": self.core_rules,
            "upgrade_system": self.upgrade_system.to_dict(),
            "resource_system": self.resource_system.to_dict(),
            "key_locations": list(self.key_locations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldSetting:
        data = data if isinstance(data, dict) else {}
        kl = data.get("key_locations", [])
        kl = tuple(kl) if isinstance(kl, (list, tuple)) else ()
        return cls(
            era=str(data.get("era", "") or ""),
            geography=str(data.get("geography", "") or ""),
            social_structure=str(data.get("social_structure", "") or ""),
            core_rules=str(data.get("core_rules", "") or ""),
            upgrade_system=UpgradeSystem.from_dict(data.get("upgrade_system", {})),
            resource_system=ResourceSystem.from_dict(data.get("resource_system", {})),
            key_locations=kl,
        )


@dataclass(frozen=True)
class CharacterBlueprint:
    """角色蓝图（大纲级别，非详细设定）。"""
    name: str = ""
    role: str = ""              # protagonist / antagonist / supporting / mentor
    core_trait: str = ""        # 核心特质（一句话）
    motivation: str = ""        # 动机
    arc_summary: str = ""       # 角色弧光概述
    relationship_to_protagonist: str = ""  # 与主角的关系

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "core_trait": self.core_trait,
            "motivation": self.motivation,
            "arc_summary": self.arc_summary,
            "relationship_to_protagonist": self.relationship_to_protagonist,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterBlueprint:
        data = data if isinstance(data, dict) else {}
        return cls(
            name=str(data.get("name", "") or ""),
            role=str(data.get("role", "") or ""),
            core_trait=str(data.get("core_trait", "") or ""),
            motivation=str(data.get("motivation", "") or ""),
            arc_summary=str(data.get("arc_summary", "") or ""),
            relationship_to_protagonist=str(data.get("relationship_to_protagonist", "") or ""),
        )


@dataclass(frozen=True)
class VolumeOKR:
    """卷级 OKR：O（目标）+ KR（关键结果/剧情节点）。"""
    volume_index: int = 0
    title: str = ""
    objective: str = ""              # 本卷目标（读者在本卷结束时应该感受到什么）
    key_results: tuple[str, ...] = ()  # KR 列表（完成目标的途径/关键剧情节点）
    chapter_count: int = 0
    core_conflict: str = ""
    emotional_arc: str = ""
    major_payoffs: tuple[str, ...] = ()
    foreshadowing_plan: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_index": self.volume_index,
            "title": self.title,
            "objective": self.objective,
            "key_results": list(self.key_results),
            "chapter_count": self.chapter_count,
            "core_conflict": self.core_conflict,
            "emotional_arc": self.emotional_arc,
            "major_payoffs": list(self.major_payoffs),
            "foreshadowing_plan": list(self.foreshadowing_plan),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VolumeOKR:
        data = data if isinstance(data, dict) else {}
        kr = data.get("key_results", [])
        kr = tuple(kr) if isinstance(kr, (list, tuple)) else ()
        mp = data.get("major_payoffs", [])
        mp = tuple(mp) if isinstance(mp, (list, tuple)) else ()
        fp = data.get("foreshadowing_plan", [])
        fp = tuple(fp) if isinstance(fp, (list, tuple)) else ()
        return cls(
            volume_index=int(data.get("volume_index", 0) or 0),
            title=str(data.get("title", "") or ""),
            objective=str(data.get("objective", "") or ""),
            key_results=kr,
            chapter_count=int(data.get("chapter_count", 0) or 0),
            core_conflict=str(data.get("core_conflict", "") or ""),
            emotional_arc=str(data.get("emotional_arc", "") or ""),
            major_payoffs=mp,
            foreshadowing_plan=fp,
        )


@dataclass(frozen=True)
class ChapterOKR:
    """章节级 OKR（第一卷的章节拆解）。"""
    chapter_index: int = 0
    objective: str = ""          # 本章目标
    key_results: tuple[str, ...] = ()  # 本章的关键剧情节点
    hook_type: str = ""          # 钩子类型
    hook_detail: str = ""        # 钩子内容

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_index": self.chapter_index,
            "objective": self.objective,
            "key_results": list(self.key_results),
            "hook_type": self.hook_type,
            "hook_detail": self.hook_detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChapterOKR:
        data = data if isinstance(data, dict) else {}
        kr = data.get("key_results", [])
        kr = tuple(kr) if isinstance(kr, (list, tuple)) else ()
        return cls(
            chapter_index=int(data.get("chapter_index", 0) or 0),
            objective=str(data.get("objective", "") or ""),
            key_results=kr,
            hook_type=str(data.get("hook_type", "") or ""),
            hook_detail=str(data.get("hook_detail", "") or ""),
        )


@dataclass(frozen=True)
class NovelPlan:
    """完整小说大纲：核心纲 + 世界观 + 角色 + 卷计划 + 章节拆解。"""
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    # 基本信息
    title: str = ""
    genre: str = ""
    target_platform: str = ""
    target_reader: str = ""
    core_emotion: str = ""
    one_sentence_pitch: str = ""

    # 核心纲
    core_outline: CoreOutline = field(default_factory=CoreOutline)

    # 世界观
    world_setting: WorldSetting = field(default_factory=WorldSetting)

    # 角色蓝图
    characters: tuple[CharacterBlueprint, ...] = ()

    # 卷计划（OKR）
    volumes: tuple[VolumeOKR, ...] = ()

    # 第一卷章节拆解（OKR）
    first_volume_chapters: tuple[ChapterOKR, ...] = ()

    # 标签
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "title": self.title,
            "genre": self.genre,
            "target_platform": self.target_platform,
            "target_reader": self.target_reader,
            "core_emotion": self.core_emotion,
            "one_sentence_pitch": self.one_sentence_pitch,
            "core_outline": self.core_outline.to_dict(),
            "world_setting": self.world_setting.to_dict(),
            "characters": [c.to_dict() for c in self.characters],
            "volumes": [v.to_dict() for v in self.volumes],
            "first_volume_chapters": [c.to_dict() for c in self.first_volume_chapters],
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NovelPlan:
        data = data if isinstance(data, dict) else {}
        chars = data.get("characters", [])
        chars = tuple(CharacterBlueprint.from_dict(c) for c in chars) if isinstance(chars, list) else ()
        vols = data.get("volumes", [])
        vols = tuple(VolumeOKR.from_dict(v) for v in vols) if isinstance(vols, list) else ()
        chs = data.get("first_volume_chapters", [])
        chs = tuple(ChapterOKR.from_dict(c) for c in chs) if isinstance(chs, list) else ()
        tags = data.get("tags", [])
        tags = tuple(tags) if isinstance(tags, (list, tuple)) else ()
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            title=str(data.get("title", "") or ""),
            genre=str(data.get("genre", "") or ""),
            target_platform=str(data.get("target_platform", "") or ""),
            target_reader=str(data.get("target_reader", "") or ""),
            core_emotion=str(data.get("core_emotion", "") or ""),
            one_sentence_pitch=str(data.get("one_sentence_pitch", "") or ""),
            core_outline=CoreOutline.from_dict(data.get("core_outline", {})),
            world_setting=WorldSetting.from_dict(data.get("world_setting", {})),
            characters=chars,
            volumes=vols,
            first_volume_chapters=chs,
            tags=tags,
        )
