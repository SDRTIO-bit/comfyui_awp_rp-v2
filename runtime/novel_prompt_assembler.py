"""NovelPromptAssembler — Assemble prompts for novel mode agents.

Combines system prompts, context, and instructions for each agent role.
"""

from __future__ import annotations

from typing import Any

from ..contracts.novel_write_packet import NovelWritePacket
from ..contracts.novel_director_guidance import DirectorGuidance
from ..contracts.novel_chapter import ChapterPlan


class NovelPromptAssembler:
    """Assemble prompts for novel mode agents."""

    def __init__(self, registry):
        self._registry = registry

    def assemble_writer_prompt(self, packet: NovelWritePacket) -> str:
        """Assemble the full prompt for Chapter Writer."""
        from .novel_writer_adapter import WRITER_SYSTEM_PROMPT

        parts = [WRITER_SYSTEM_PROMPT]

        # Chapter plan
        parts.append(f"\n=== CHAPTER PLAN ===\n{packet.chapter_plan.to_dict()}")

        # Previous chapter
        if packet.previous_chapter_summary:
            parts.append(f"\n=== PREVIOUS CHAPTER ===\n{packet.previous_chapter_summary}")

        # Continuity context
        if packet.relevant_ledger_items:
            items_text = "\n".join(
                f"- [{i.section}] {i.entity}: {i.content}"
                for i in packet.relevant_ledger_items
            )
            parts.append(f"\n=== CONTINUITY CONTEXT ===\n{items_text}")

        # Character states
        if packet.character_states:
            parts.append(f"\n=== CHARACTER STATES ===\n{packet.character_states}")

        # Director guidance
        if packet.director_guidance.guidance_id:
            parts.append(f"\n=== DIRECTOR GUIDANCE ===\n"
                        f"方向: {packet.director_guidance.chapter_direction}\n"
                        f"情绪弧线: {packet.director_guidance.emotional_arc}\n"
                        f"节奏策略: {packet.director_guidance.pacing_strategy}\n"
                        f"对话基调: {packet.director_guidance.dialogue_tone}")

        # Writing intent
        if packet.writing_intent:
            parts.append(f"\n=== WRITING INTENT ===\n{packet.writing_intent}")

        # Output rules
        parts.append(f"\n=== OUTPUT RULES ===\n"
                    f"- 只输出正文，无标签、无 JSON、无元信息\n"
                    f"- 目标 {packet.chapter_plan.target_chars} 字\n"
                    f"- 结尾必须留悬念/钩子\n"
                    f"- 不复述上一章结尾")

        return "\n".join(parts)

    def assemble_director_prompt(
        self,
        chapter_plan: ChapterPlan,
        completed_chapters_summary: str,
        ledger_items: list,
        character_states: dict,
        foreshadowing_list: list,
        subplot_status: list,
        previous_chapter_ending: str,
    ) -> str:
        """Assemble the full prompt for Director."""
        from .novel_director_adapter import DIRECTOR_SYSTEM_PROMPT

        parts = [DIRECTOR_SYSTEM_PROMPT]

        parts.append(f"\n=== PROJECT CONTEXT ===")
        parts.append(f"\n已完成章节摘要:\n{completed_chapters_summary}")

        if ledger_items:
            items_text = "\n".join(
                f"- [{i.section}] {i.entity}: {i.content}"
                for i in ledger_items[:20]
            )
            parts.append(f"\n连续性账本:\n{items_text}")

        if character_states:
            parts.append(f"\n角色状态:\n{character_states}")

        if foreshadowing_list:
            parts.append(f"\n伏笔清单:\n{foreshadowing_list}")

        if subplot_status:
            parts.append(f"\n支线进度:\n{subplot_status}")

        parts.append(f"\n=== CURRENT TASK ===\n当前要写第 {chapter_plan.chapter_index} 章")
        parts.append(f"\n章节计划:\n{chapter_plan.to_dict()}")
        parts.append(f"\n前一章结尾:\n{previous_chapter_ending}")

        parts.append("\n=== THINKING WORKFLOW ===\n"
                    "1. 先审视全书结构：当前处于什么阶段？节奏是否合理？\n"
                    "2. 检查伏笔：有哪些需要推进？有哪些需要埋设？\n"
                    "3. 检查角色弧光：主要角色在本章应该有什么成长？\n"
                    "4. 检查支线：哪些支线需要推进？哪些可以暂缓？\n"
                    "5. 设计读者预期：本章应该给读者什么期待？如何误导或满足？\n"
                    "6. 最后：为 Writer 提供精确的本章方向")

        return "\n".join(parts)

    def assemble_architect_prompt(
        self,
        project_id: str,
        chapter_index: int,
        volume_plan: Any,
        completed_chapters: list,
        ledger_items: list,
        character_states: dict,
    ) -> str:
        """Assemble the full prompt for Architect."""
        from .novel_architect_adapter import ARCHITECT_SYSTEM_PROMPT

        parts = [ARCHITECT_SYSTEM_PROMPT]

        parts.append(f"\n=== PROJECT ===\n项目ID: {project_id}")
        parts.append(f"\n=== TASK ===\n规划第 {chapter_index} 章")

        if volume_plan:
            parts.append(f"\n卷计划:\n{volume_plan.to_dict() if hasattr(volume_plan, 'to_dict') else volume_plan}")

        if completed_chapters:
            parts.append(f"\n已完成章节:\n{completed_chapters[-5:]}")

        if ledger_items:
            items_text = "\n".join(
                f"- [{i.section}] {i.entity}: {i.content}"
                for i in ledger_items[:15]
            )
            parts.append(f"\n连续性账本:\n{items_text}")

        if character_states:
            parts.append(f"\n角色状态:\n{character_states}")

        parts.append("\n=== OUTPUT FORMAT ===\n"
                    "严格的 JSON 输出，符合 ChapterPlan schema。")

        return "\n".join(parts)
