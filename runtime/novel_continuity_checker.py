"""NovelContinuityChecker — Continuity Checker for novel mode.

Uses DeepSeekAdapter with thinking=high for detecting contradictions.
"""

from __future__ import annotations

from typing import Any

# Thinking configuration for detail-oriented reasoning
_THINKING_HIGH = {"thinking": {"type": "enabled", "reasoning_effort": "high"}}

# Continuity checker system prompt
CONTINUITY_CHECKER_PROMPT = """=== STABLE CONTINUITY CHECKER CONTRACT ===
你是长篇小说的连续性检查员。你的职责是检测已写章节中的问题。

=== 质量检查清单 ===

章节结构：
- 开头有钩子（不是天气/风景/日常开场）
- 中段有推进（有事件发生）
- 局势有变化（读完这章，世界跟之前不一样了）
- 结尾落在变化上（不是总结）

章尾：
- 结尾落在变化上
- 有危机/决定/发现/反转中的至少一个
- 不是总结式结尾
- 拉住读者翻下一页

语言：
- 没有空洞的抒情段落
- 没有连续多段同一情绪
- 对话符合人物身份
- 情绪通过动作落地

连载连续性：
- 没有遗忘之前的承诺/伏笔
- 没有突然塞入大量新设定
- 伏笔有推进

=== 水字数检测 ===
以下信号出现 = 可能水了：
- 全章对话没有任何新信息
- 同一个情绪写了 3 段以上
- 场景描写超过 500 字但不推进剧情
- 角色回忆之前发生的事但没有任何新视角
- 连续 2 章以上没有冲突

=== 小节密度诊断 ===
小节写完后偏短？按顺序检查：
1. 三维度都揉进了？只有动作没有感知和反应 → 揉进感官细节和身体动作
2. 对话只有1-2轮？缺少对话交锋 → 加一轮权力博弈对话
3. 有情绪词？用了抽象情绪词 → 替换为身体细节
4. 仍偏短？缺少对话或回忆 → 加一轮对话或简短回忆

子事件不够时怎么扩：
- 冲突/对抗 → 加「阻碍」
- 涉及配角 → 加「反应」
- 有空间移动 → 加「发现」
- 触发回忆 → 加「倒叙」
- 一连串动作 → 加「递进」
"""


class NovelContinuityChecker:
    """Continuity Checker for novel mode."""

    def __init__(self, registry, model: str = "deepseek-v4-flash"):
        self._registry = registry
        self._model = model

    def check_chapter(
        self,
        chapter_text: str,
        chapter_plan: Any,
        ledger_items: list,
        character_states: dict,
        previous_chapter_summary: str,
    ) -> dict:
        """Check a chapter for continuity issues.

        Returns dict with:
        - issues: list of issue descriptions
        - severity: "blocking" / "warning" / "info"
        - suggestions: list of fix suggestions
        """
        system_prompt, user_prompt = self._build_prompt(
            chapter_text, chapter_plan, ledger_items,
            character_states, previous_chapter_summary,
        )
        # Call LLM and parse JSON response
        from .novel_llm_factory import NovelLLMFactory
        import json
        factory = NovelLLMFactory.get_instance()
        adapter = factory.get_adapter("continuity_checker")
        thinking = factory.get_thinking_config("continuity_checker")
        model = factory.get_model("continuity_checker")
        max_tokens = factory.get_max_tokens("continuity_checker")

        try:
            text, receipt = adapter.generate_text(
                user_prompt,
                max_tokens=max_tokens,
                provider_role="novel_continuity_checker",
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
            return {"issues": [], "severity": "info", "suggestions": []}

    def _build_prompt(
        self, chapter_text, chapter_plan, ledger_items,
        character_states, previous_chapter_summary,
    ) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt)."""
        parts = []

        parts.append(f"\n=== CHAPTER TEXT ===\n{chapter_text[:3000]}")  # Truncate for prompt

        if chapter_plan:
            parts.append(f"\n=== CHAPTER PLAN ===\n{chapter_plan.to_dict() if hasattr(chapter_plan, 'to_dict') else chapter_plan}")

        if ledger_items:
            items_text = "\n".join(f"- [{i.section}] {i.entity}: {i.content}" for i in ledger_items[:10])
            parts.append(f"\n=== RELEVANT LEDGER ===\n{items_text}")

        if character_states:
            parts.append(f"\n=== CHARACTER STATES ===\n{character_states}")

        if previous_chapter_summary:
            parts.append(f"\n=== PREVIOUS CHAPTER ===\n{previous_chapter_summary}")

        parts.append("\n=== OUTPUT FORMAT ===\n"
                    "JSON: {\"issues\": [...], \"severity\": \"blocking|warning|info\", \"suggestions\": [...]}")

        return CONTINUITY_CHECKER_PROMPT, "\n".join(parts)
