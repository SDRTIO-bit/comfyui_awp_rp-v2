"""NovelPlannerAdapter — Project-level novel planner.

Takes a brief concept from the user and generates a full novel plan:
core outline, world settings, characters, volume plans (OKR), first volume chapter breakdown.

Independent from Architect (chapter-level) and Director (chapter guidance).
"""

from __future__ import annotations

from typing import Any

from ..contracts.novel_plan import (
    NovelPlan, CoreOutline, WorldSetting, UpgradeSystem, ResourceSystem,
    CharacterBlueprint, VolumeOKR, ChapterOKR,
)

PLANNER_SYSTEM_PROMPT = """=== NOVEL PLANNER CONTRACT ===
你是小说大纲规划师。用户只会给你一点思路（可能是一句话、一个设定、一个角色、一个桥段），你需要把它扩展成完整的小说大纲。

你的输出必须覆盖以下所有维度，不能遗漏。

=== 一、核心纲（必填）===
用 OKR 方法构建：
- O（Objective）：整本书的目标——读者看完应该感受到什么
- KR（Key Results）：完成目标的途径——3-5个关键剧情节点
- 表层大纲：开篇→过程→结尾，主角目标+驱动力，200字以内
- 里层大纲：核心卖点，读者安利时怎么总结这本书
- 一句话大纲

=== 二、世界观（必须扩展，不能只写用户给的）===
用户可能只给了一个模糊的设定，你必须扩展出完整的框架：

**基础设定：**
- 时代背景、地理/空间结构、社会结构/势力分布、核心规则/禁忌
- 关键地点（3-5个）

**升级体系（如果有成长线）：**
- 底层能源：角色凭什么变强（只选1主+1次）
- 大阶：4-7个，每阶描述质变内容（不是数值变高，是本质变了）
- 每阶的输入→过程→输出→代价
- 例外机制：主角的特殊之处（来源/优势/代价/边界）

**资源体系：**
- 关键资源的稀缺度、获取渠道、使用门槛
- 高阶资源被谁掌握
- 普通人能升到哪一步
- 升级后社会地位如何改变

**禁忌和边界：**
- 不可违反的规则（死亡不可逆/时间不可回溯等）
- 能力的副作用和限制

=== 三、角色蓝图（3-6个）===
每个角色包含：
- 名字、角色定位（主角/反派/辅助/导师）
- 核心特质（一句话）
- 动机
- 角色弧光概述（从A到B的变化）
- 与主角的关系

**角色设计要点：**
- 人设要有反差点（表面X实际Y）
- 每个角色都要有"不能退让的理由"
- 关系是推动故事的情感引擎

=== 四、卷计划（OKR，3-5卷）===
每卷包含：
- O：本卷目标（读者应该感受到什么）
- KR：3-5个关键剧情节点
- 核心冲突
- 情绪弧线
- 主要爽点/高潮
- 伏笔计划（新埋+回收）

**卷节奏：**
- 大高潮周期7-10章
- 小高潮周期3章左右
- 高潮后加1-2章过渡
- 相邻卷不情绪趋同

=== 五、第一卷章节拆解（OKR，10-15章）===
每章包含：
- O：本章目标
- KR：2-3个关键剧情节点
- 钩子类型（悬念/情绪/反转/信息差）
- 钩子内容

**章节设计要点：**
- 每章结束时读者必须有一个想看下一章的理由
- "不存在过渡章"——每个场景都是下一个期待感的铺垫
- 前100字必须包含≥3个事件
- 对话驱动剧情，不是描写驱动

=== 六、钩子设计（贯穿全书）===
- 开篇钩：第一句话/第一个场景就要抓住读者
- 章末钩：每章结尾留下悬念
- 卷末钩：每卷结尾留下大悬念
- 钩子类型：硬悬疑/人设式/思路式/复仇式/反转钩/情绪钩

=== 输出格式 ===
只输出一个 JSON 对象，不要 markdown、不要代码块、不要解释。
JSON 必须能直接被 json.loads 解析。

{
  "title": "string",
  "genre": "string",
  "target_platform": "string",
  "target_reader": "string",
  "core_emotion": "string",
  "one_sentence_pitch": "string",
  "core_outline": {
    "surface": "string — 表层大纲200字",
    "inner": "string — 里层卖点",
    "one_sentence": "string — 一句话大纲"
  },
  "world_setting": {
    "era": "string",
    "geography": "string",
    "social_structure": "string",
    "core_rules": "string",
    "upgrade_system": {
      "energy_source": "string",
      "secondary_source": "string",
      "tiers": ["string — 每阶质变描述"],
      "tier_details": [{"input": "", "process": "", "output": "", "cost": ""}],
      "exception_mechanism": "string — 主角特殊机制"
    },
    "resource_system": {
      "description": "string",
      "low_tier_resources": "string",
      "mid_tier_resources": "string",
      "high_tier_resources": "string",
      "resource_flow": "string"
    },
    "key_locations": ["string"]
  },
  "characters": [
    {
      "name": "string",
      "role": "string — protagonist/antagonist/supporting/mentor",
      "core_trait": "string",
      "motivation": "string",
      "arc_summary": "string",
      "relationship_to_protagonist": "string"
    }
  ],
  "volumes": [
    {
      "volume_index": 1,
      "title": "string",
      "objective": "string — 本卷O",
      "key_results": ["string — KR1", "KR2", ...],
      "chapter_count": 10,
      "core_conflict": "string",
      "emotional_arc": "string",
      "major_payoffs": ["string"],
      "foreshadowing_plan": ["string"]
    }
  ],
  "first_volume_chapters": [
    {
      "chapter_index": 1,
      "objective": "string — 本章O",
      "key_results": ["string"],
      "hook_type": "string — 悬念/情绪/反转/信息差",
      "hook_detail": "string"
    }
  ],
  "tags": ["string"]
}

缺失字段用空字符串或空数组，不要省略字段。
"""


class NovelPlannerAdapter:
    """Project-level novel planner. Takes a brief concept, generates full plan."""

    def __init__(self, registry):
        self._registry = registry

    def plan_novel(
        self,
        concept: str,
        title: str = "",
        genre: str = "",
        target_platform: str = "",
        additional_requirements: str = "",
    ) -> NovelPlan:
        """Generate a full novel plan from a brief concept.

        Args:
            concept: User's brief idea (can be just one sentence)
            title: Optional title (if not provided, LLM generates one)
            genre: Optional genre hint
            target_platform: Optional platform (番茄/起点/etc)
            additional_requirements: Any extra requirements from user
        """
        system_prompt = PLANNER_SYSTEM_PROMPT
        user_prompt = self._build_user_prompt(
            concept, title, genre, target_platform, additional_requirements
        )

        from .novel_llm_factory import NovelLLMFactory
        import json
        factory = NovelLLMFactory.get_instance()
        adapter = factory.get_adapter("architect")  # Use architect adapter (high thinking)
        thinking = factory.get_thinking_config("architect")
        model = factory.get_model("architect")
        max_tokens = 12000  # Planner needs more tokens for full plan

        try:
            text, receipt = adapter.generate_text(
                user_prompt,
                max_tokens=max_tokens,
                provider_role="novel_planner",
                model=model,
                extra_body=thinking,
                system_prompt=system_prompt,
            )
        except Exception:
            text = ""

        # Parse JSON response
        extracted = self._extract_json_object(text)
        if extracted is None:
            raise ValueError(
                f"Planner did not return JSON. Head: {text[:300]!r}"
            )

        try:
            data = json.loads(extracted)
            plan = NovelPlan.from_dict(data)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise ValueError(
                f"Planner JSON parse failed: {e}. Head: {extracted[:300]!r}"
            )

        # Persist if registry available
        if self._registry and plan.title:
            self._persist_plan(plan)

        return plan

    def _build_user_prompt(
        self, concept: str, title: str, genre: str,
        target_platform: str, additional_requirements: str,
    ) -> str:
        parts = [f"=== 用户思路 ===\n{concept}"]

        if title:
            parts.append(f"\n=== 书名 ===\n{title}")
        if genre:
            parts.append(f"\n=== 题材 ===\n{genre}")
        if target_platform:
            parts.append(f"\n=== 目标平台 ===\n{target_platform}")
        if additional_requirements:
            parts.append(f"\n=== 额外要求 ===\n{additional_requirements}")

        parts.append(
            "\n=== 任务 ===\n"
            "将上述思路扩展成完整的小说大纲。包含：核心纲、世界观（必须扩展升级体系和资源体系）、"
            "角色蓝图（3-6个）、卷计划（OKR，3-5卷）、第一卷章节拆解（OKR，10-15章）、钩子设计。\n"
            "按 OUTPUT FORMAT 输出 JSON。"
        )

        return "\n".join(parts)

    def _persist_plan(self, plan: NovelPlan) -> None:
        """Persist plan components to stores."""
        try:
            from ..contracts.novel_project import NovelProject
            project = NovelProject(
                project_id=f"novel-{plan.title}",
                title=plan.title,
                genre=plan.genre,
                target_platform=plan.target_platform,
                target_reader=plan.target_reader,
                core_emotion=plan.core_emotion,
                one_sentence_pitch=plan.one_sentence_pitch,
                status="planning",
            )
            self._registry.novel_project_store.create(project)

            from ..contracts.novel_character import NovelCharacter
            for char in plan.characters:
                nc = NovelCharacter(
                    character_id=f"char-{plan.title}-{char.name}",
                    project_id=project.project_id,
                    name=char.name,
                    role=char.role,
                    personality=char.core_trait,
                    core_motivation=char.motivation,
                    current_state={"arc": char.arc_summary},
                )
                self._registry.novel_character_store.save(nc)

            from ..contracts.novel_volume import VolumePlan
            for vol in plan.volumes:
                vp = VolumePlan(
                    volume_id=f"vol-{plan.title}-{vol.volume_index}",
                    project_id=project.project_id,
                    index=vol.volume_index,
                    title=vol.title,
                    chapter_count=vol.chapter_count,
                    core_conflict=vol.core_conflict,
                    emotional_arc=vol.emotional_arc,
                    major_payoffs=vol.major_payoffs,
                    foreshadowing_plan=vol.foreshadowing_plan,
                )
                self._registry.novel_volume_store.save(vp)

        except Exception:
            pass  # Don't fail planning if persistence fails

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        """Extract first balanced JSON object from text."""
        if not text:
            return None
        t = text.strip()
        if t.startswith("```"):
            first_newline = t.find("\n")
            if first_newline != -1:
                t = t[first_newline + 1:]
            if t.endswith("```"):
                t = t[:-3]
            t = t.strip()
        start = t.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(t)):
            ch = t[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return t[start:i + 1]
        return None
