"""NovelArchitectAdapter — Architect LLM adapter for novel mode.

Uses DeepSeekAdapter with thinking=high for chapter planning.
"""

from __future__ import annotations

from typing import Any

from ..contracts.novel_chapter import ChapterPlan, BeatDetail

# Thinking configuration for structural planning
_THINKING_HIGH = {"thinking": {"type": "enabled", "reasoning_effort": "high"}}

# Architect system prompt (core rules from oh-story)
ARCHITECT_SYSTEM_PROMPT = """=== STABLE ARCHITECT CONTRACT ===
你是长篇网文的章节规划师。你负责生成详细的章节计划（细纲），供写手按此写作。

=== 核心风格认知 ===
本书采用"自然流动的口语化叙事"风格，参照以下参考作品的节奏特征：
- beat description 要包含对话提示和信息传递方式，给 Writer 明确"这段用什么方式讲"
- beat 之间需要"动→静→动"节奏，但过渡要自然，不要硬切
- 对话 beat 极简：只写关键台词，不写铺垫性对话
- 物证 beat 具体化：写出具体物件的尺寸、材质、颜色，而不是"发现了一个东西"
- 每个 beat 的 description 应该读起来像真人写的段落大纲，不像机器生成的清单

参考作品的节奏特征：
「林舟身体前倾，结果一只嫩白小手盖了过来，拍在了他的脸上。"看不见了——"林舟说着，白晚晚的小手冰冰凉凉的，还带着说不出的一点柔软。白晚晚把手放下，有点奇怪的看着林舟，"干嘛……开车。"」
——动作→对话→触感→对话，一个句子串联多个信息点，顺滑不堵塞。

=== 细纲模板 ===
每章必须包含以下维度：

1. 核心事件（一句话）
2. 字数目标
3. 目标情绪
4. 章节定位（高压/推进/修炼试错/关系回收/低压生活/信息整理）
5. 章首钩子（从7式中选择）
6. 爽点（低压章可写"无显性爽点，功能是…"）

7. 内容概括五段式：
   - 起因：本章事件为什么发生
   - 发展：冲突如何推进
   - 转折：信息/关系/局势哪里改变
   - 高潮：本章情绪或动作峰值
   - 结尾：收束到什么状态

8. 情节安排多线：
   - 主线推进
   - 辅线推进
   - 事件线/任务线
   - 感情线/关系线
   - 逻辑线：原因→行动→结果→后果

9. 人物关系和出场顺序：
   - 出场顺序
   - 人物关系变化
   - 视角/信息差

10. 情节细化（beat 预算）：
    - 每个情ポイント标 密/疏 并给字数预算
    - 密（爽点/打脸/反转/物证识破/身份反转）≥ 250 字
    - 疏（过场/赶路/安静呼吸）≈ 40 字
    - 铺垫/日常/内心吐槽 ≈ 120-150 字
    - 各点求和 Σ 落在 [章目标, 章目标×1.1]
    - 每点写清"谁做了什么+功能标签"
    - beat description 用短句风格写，这是给 Writer 的语气示范

11. 结尾设定和钩子：
    - 收束状态
    - 未解决问题
    - 下一章推动力
    - 章尾钩子（从13式中选择）

=== 大纲五检（每卷/每章设计前必答）===
1. 本卷交付什么情绪？什么剧情模式能可靠交付？
2. 本卷核心冲突是什么？
3. 卷节奏（起承转合）哪段加速哪段减速？
4. 本卷需要新埋设的伏笔有哪些？上一卷待回收的伏笔如何处理？
5. 章节定位分布是否有高低层次？低压+过场是否克制（合计不超约15%）？

=== 章节定位与张弛 ===
| 章节定位 | 钩子要求 | 爽点要求 | 功能 |
|----------|---------|---------|------|
| 高压章 | 必须强钩子 | 必须有爽点 | 释放 |
| 推进章 | 必须有钩子 | 必须有推进 | 前进 |
| 修炼试错章 | 可弱钩子 | 可无显性爽点 | 成长 |
| 关系回收章 | 可弱钩子 | 可无显性爽点 | 关系 |
| 低压生活章 | 可弱钩子 | 可无显性爽点 | 喘息 |
| 信息整理章 | 可弱钩子 | 可无显性爽点 | 铺垫 |

底线：每章都给读者一个往下看的理由，相邻章不情绪趋同。
"""


class NovelArchitectAdapter:
    """Architect LLM adapter for novel mode."""

    def __init__(self, registry, model: str = "deepseek-v4-pro"):
        self._registry = registry
        self._model = model

    def plan_chapter(
        self,
        project_id: str,
        chapter_index: int,
        volume_plan: Any,
        completed_chapters: list,
        ledger_items: list,
        character_states: dict,
        task_description: str = "",
    ) -> ChapterPlan:
        """Generate a chapter plan."""
        system_prompt, user_prompt = self._build_prompt(
            project_id, chapter_index, volume_plan,
            completed_chapters, ledger_items, character_states,
            task_description,
        )
        # Call LLM and parse JSON response
        from .novel_llm_factory import NovelLLMFactory
        import json
        factory = NovelLLMFactory.get_instance()
        adapter = factory.get_adapter("architect")
        thinking = factory.get_thinking_config("architect")
        model = factory.get_model("architect")
        max_tokens = factory.get_max_tokens("architect")

        try:
            text, receipt = adapter.generate_text(
                user_prompt,
                max_tokens=max_tokens,
                provider_role="novel_architect",
                model=model,
                extra_body=thinking,
                system_prompt=system_prompt,
            )
        except Exception:
            text = ""

        # Parse JSON response robustly (tolerate ```json fences, leading prose).
        import json
        extracted = self._extract_json_object(text)
        if extracted is None:
            # Parsing failed. Previously we silently returned an empty ChapterPlan
            # (no scene_beats), which made NovelEngine fall back to whole-chapter
            # naked generation — the opposite of the beat-by-beat design and a
            # token black hole. Now raise so batch_write can mark this chapter
            # failed and skip it instead of writing a meaningless draft.
            raise ValueError(
                f"Architect did not return JSON for chapter {chapter_index}. "
                f"Head of response: {text[:200]!r}"
            )

        try:
            data = json.loads(extracted)
            plan = ChapterPlan.from_dict(data)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise ValueError(
                f"Architect JSON parse failed for chapter {chapter_index}: {e}. "
                f"Head: {extracted[:200]!r}"
            )

        # Ensure scene_beats is non-empty (the whole point of the architect step).
        scene_beats = tuple(
            BeatDetail.from_dict(b) for b in data.get("scene_beats", [])
        )
        if not scene_beats:
            raise ValueError(
                f"Architect plan for chapter {chapter_index} has no scene_beats. "
                f"Beat-by-beat generation requires at least one beat."
            )

        # Override metadata to ensure consistency
        plan = ChapterPlan(
            schema_id=plan.schema_id,
            schema_version=plan.schema_version,
            chapter_id=plan.chapter_id or f"ch-{project_id}-{chapter_index}",
            project_id=project_id,
            volume_id=plan.volume_id,
            chapter_index=chapter_index,
            title=plan.title or f"第{chapter_index}章",
            target_chars=plan.target_chars or 3000,
            chapter_position=plan.chapter_position,
            target_emotion=plan.target_emotion,
            opening_hook=plan.opening_hook,
            main_payoff=plan.main_payoff,
            content_summary=plan.content_summary,
            plot_arrangement=plan.plot_arrangement,
            character_appearance=plan.character_appearance,
            scene_beats=scene_beats,
            ending_design=plan.ending_design,
            cost_and_reward=plan.cost_and_reward,
        )
        return plan

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        """Best-effort extract the first balanced top-level JSON object from text."""
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

    def _build_prompt(
        self, project_id, chapter_index, volume_plan,
        completed_chapters, ledger_items, character_states,
        task_description,
    ) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt).

        Optimized for DeepSeek prefix caching: stable rules first.
        """
        # Stable prefix — cacheable
        parts = [
            "=== OUTPUT FORMAT ===\n"
            "严格的 JSON 输出，符合 ChapterPlan schema。\n"
            "包含：chapter_id, project_id, chapter_index, title, target_chars, "
            "chapter_position, target_emotion, opening_hook, main_payoff, "
            "content_summary(五段式), plot_arrangement(多线), "
            "character_appearance(出场顺序), scene_beats(beat预算), "
            "ending_design(钩子), cost_and_reward。",
        ]

        # Varying context
        parts.append(f"\n=== TASK ===\n规划第 {chapter_index} 章\n项目ID: {project_id}")

        if task_description:
            parts.append(f"\n任务描述: {task_description}")

        if character_states:
            parts.append(f"\n角色状态:\n{character_states}")

        if volume_plan:
            parts.append(f"\n卷计划:\n{volume_plan.to_dict() if hasattr(volume_plan, 'to_dict') else volume_plan}")

        if completed_chapters:
            parts.append(f"\n已完成章节:\n{completed_chapters[-5:]}")

        if ledger_items:
            items_text = "\n".join(f"- [{i.section}] {i.entity}: {i.content}" for i in ledger_items[:15])
            parts.append(f"\n连续性账本:\n{items_text}")

        return ARCHITECT_SYSTEM_PROMPT, "\n".join(parts)
