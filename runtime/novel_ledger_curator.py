"""NovelLedgerCurator — Ledger Curator for novel mode.

Uses DeepSeekAdapter with thinking=medium for extracting continuity information.
"""

from __future__ import annotations

from typing import Any

# Thinking configuration for extraction
_THINKING_MEDIUM = {"thinking": {"type": "enabled", "reasoning_effort": "medium"}}

# Ledger curator system prompt
LEDGER_CURATOR_PROMPT = """=== STABLE LEDGER CURATOR CONTRACT ===
你负责维护长篇小说的连续性账本。分析已接受的章节正文，更新追踪信息。

=== 分析维度 ===
1. 角色状态变化：身份、能力、位置、情绪、关系
2. 伏笔推进：新埋设、推进、回收、矛盾
3. 时间线更新：时间流逝、事件顺序
4. 世界规则：新设定、规则变化
5. 开放线索：新出现的未解决问题

=== 伏笔状态机 ===
- planted → active（已埋设）
- advanced → active（已推进）
- paid_off → resolved（已回收）
- stale → stale（过期未回收）
- contradicted → contradicted（被矛盾）

=== 角色状态快照格式 ===
## {name}
- 身份: {identity}
- 能力: {ability}
- 关系: {relationships}
- 公众形象: {public_image}
- 最近变化: {recent_changes}
"""


class NovelLedgerCurator:
    """Ledger Curator for novel mode."""

    def __init__(self, registry, model: str = "deepseek-v4-flash"):
        self._registry = registry
        self._model = model

    def curate(
        self,
        chapter_text: str,
        chapter_plan: Any,
        current_ledger_items: list,
    ) -> dict:
        """Analyze accepted chapter and propose ledger updates.

        Returns dict with:
        - ledger_updates: list of new/modified ledger items
        - ledger_resolves: list of item_ids to mark as resolved
        - chapter_summary: one-line summary for next chapter
        - foreshadowing_changes: list of foreshadowing status changes
        """
        system_prompt, user_prompt = self._build_prompt(chapter_text, chapter_plan, current_ledger_items)
        # Call LLM and parse JSON response
        from .novel_llm_factory import NovelLLMFactory
        import json
        factory = NovelLLMFactory.get_instance()
        adapter = factory.get_adapter("ledger_curator")
        thinking = factory.get_thinking_config("ledger_curator")
        model = factory.get_model("ledger_curator")
        max_tokens = factory.get_max_tokens("ledger_curator")

        try:
            text, receipt = adapter.generate_text(
                user_prompt,
                max_tokens=max_tokens,
                provider_role="novel_ledger_curator",
                model=model,
                extra_body=thinking,
                system_prompt=system_prompt,
            )
        except Exception:
            text = ""

        # Parse JSON response
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return {
                "ledger_updates": [],
                "ledger_resolves": [],
                "chapter_summary": text[:100] if text else "",
                "foreshadowing_changes": [],
            }

    def _build_prompt(self, chapter_text, chapter_plan, current_ledger_items) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt)."""
        parts = []

        if chapter_plan:
            parts.append(f"\n=== CHAPTER PLAN ===\n{chapter_plan.to_dict() if hasattr(chapter_plan, 'to_dict') else chapter_plan}")

        parts.append(f"\n=== ACCEPTED CHAPTER TEXT ===\n{chapter_text[:3000]}")

        if current_ledger_items:
            items_text = "\n".join(
                f"- [{i.status}] [{i.section}] {i.entity}: {i.content}"
                for i in current_ledger_items[:20]
            )
            parts.append(f"\n=== CURRENT LEDGER ===\n{items_text}")

        parts.append("\n=== OUTPUT FORMAT ===\n"
                    "JSON: {\n"
                    "  \"ledger_updates\": [...],\n"
                    "  \"ledger_resolves\": [...],\n"
                    "  \"chapter_summary\": \"...\",\n"
                    "  \"foreshadowing_changes\": [...]\n"
                    "}")

        return LEDGER_CURATOR_PROMPT, "\n".join(parts)
