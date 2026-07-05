"""NovelWritePacketBuilder — Build NovelWritePacket with oh-story's write-before-three-steps.

Implements: 状态筛选 → 模块召回 → 意图确认
"""

from __future__ import annotations

from typing import Any

from ..contracts.novel_write_packet import NovelWritePacket
from ..contracts.novel_chapter import ChapterPlan
from ..contracts.novel_ledger import LedgerItem
from ..contracts.novel_director_guidance import DirectorGuidance


class NovelWritePacketBuilder:
    """Build NovelWritePacket implementing oh-story's write-before-three-steps."""

    def __init__(self, registry):
        self._registry = registry

    def build(
        self,
        chapter_plan: ChapterPlan,
        ledger_items: list[LedgerItem],
        previous_chapter_summary: str,
        character_states: dict[str, Any],
        director_guidance: DirectorGuidance,
        reference_books: list[dict] | None = None,
    ) -> NovelWritePacket:
        """Build a NovelWritePacket with write-before-three-steps.

        Step 1: 状态筛选 — 只保留"不知道就会写错"的信息
        Step 2: 模块召回 — 从对标书找情绪/节奏/文风参考
        Step 3: 意图确认 — 一句话概括本章写作目标
        """
        # Step 1: 状态筛选
        relevant_items = self._filter_relevant_ledger(chapter_plan, ledger_items)
        relevant_characters = self._filter_relevant_characters(chapter_plan, character_states)

        # Step 2: 模块召回
        ref_books = reference_books or []
        emotion_module = self._recall_emotion_module(chapter_plan, ref_books)
        rhythm_reference = self._recall_rhythm(chapter_plan, ref_books)
        style_profile = self._recall_style(ref_books)

        # Step 3: 意图确认
        writing_intent = self._confirm_intent(
            chapter_plan, emotion_module, rhythm_reference, director_guidance
        )

        return NovelWritePacket(
            packet_id=f"pkt-{chapter_plan.chapter_id}",
            project_id=chapter_plan.project_id,
            chapter_id=chapter_plan.chapter_id,
            chapter_plan=chapter_plan,
            previous_chapter_summary=previous_chapter_summary,
            relevant_ledger_items=relevant_items,
            character_states=relevant_characters,
            director_guidance=director_guidance,
            writing_intent=writing_intent,
            emotion_module=emotion_module,
            rhythm_reference=rhythm_reference,
            style_profile=style_profile,
        )

    def build_beat_packet(
        self,
        beat: Any,
        accumulated_text: str,
        chapter_plan: ChapterPlan,
        director_guidance: DirectorGuidance,
        ledger_items: list[LedgerItem],
    ) -> NovelWritePacket:
        """Build a packet for a single beat."""
        relevant_items = self._filter_relevant_ledger(chapter_plan, ledger_items)

        return NovelWritePacket(
            packet_id=f"pkt-{chapter_plan.chapter_id}-{beat.beat_id}",
            project_id=chapter_plan.project_id,
            chapter_id=chapter_plan.chapter_id,
            chapter_plan=chapter_plan,
            relevant_ledger_items=relevant_items,
            director_guidance=director_guidance,
            current_scene_beat=beat,
            accumulated_text=accumulated_text,
        )

    def _filter_relevant_ledger(
        self, plan: ChapterPlan, items: list[LedgerItem]
    ) -> list[LedgerItem]:
        """只保留本章涉及的 ledger 条目。"""
        relevant = []
        plan_text = f"{plan.content_summary.cause} {plan.content_summary.development}"
        for item in items:
            # Include if entity mentioned in plan or status is active
            if item.entity in plan_text or item.status == "active":
                relevant.append(item)
        return relevant

    def _filter_relevant_characters(
        self, plan: ChapterPlan, character_states: dict[str, Any]
    ) -> dict[str, Any]:
        """只保留本章涉及的角色状态。"""
        if not character_states:
            return {}
        # Include all for now; could filter by appearance_order
        return character_states

    def _recall_emotion_module(
        self, plan: ChapterPlan, reference_books: list[dict]
    ) -> dict[str, Any]:
        """从对标书找情绪模块。"""
        if not reference_books:
            return {}
        # Simple implementation: find first matching emotion
        target_emotion = plan.target_emotion
        for book in reference_books:
            for module in book.get("emotion_modules", []):
                if target_emotion in str(module):
                    return module
        return {}

    def _recall_rhythm(
        self, plan: ChapterPlan, reference_books: list[dict]
    ) -> dict[str, Any]:
        """从对标书找节奏参考。"""
        if not reference_books:
            return {}
        # Return first book's rhythm profile
        for book in reference_books:
            if book.get("rhythm_profile"):
                return book["rhythm_profile"]
        return {}

    def _recall_style(
        self, reference_books: list[dict]
    ) -> dict[str, Any]:
        """从对标书找文风参考。"""
        if not reference_books:
            return {}
        # Return first book's style profile
        for book in reference_books:
            if book.get("style_profile"):
                return {"description": book["style_profile"]}
        return {}

    def _confirm_intent(
        self,
        plan: ChapterPlan,
        emotion_module: dict[str, Any],
        rhythm: dict[str, Any],
        guidance: DirectorGuidance,
    ) -> str:
        """一句话写作意图。"""
        parts = []
        parts.append(f"目标情绪: {plan.target_emotion}")
        parts.append(f"节奏: {guidance.pacing_strategy}")
        if emotion_module:
            parts.append(f"情绪模块: {emotion_module.get('name', '无')}")
        if rhythm:
            parts.append(f"节奏参考: {rhythm.get('name', '无')}")
        return " | ".join(parts)
