"""NovelDirectorAdapter — Director LLM adapter for novel mode.

Uses DeepSeekAdapter with thinking=high for global story optimization.
"""

from __future__ import annotations

from typing import Any

from ..contracts.novel_director_guidance import DirectorGuidance

# Thinking configuration for deep reasoning
_THINKING_HIGH = {"thinking": {"type": "enabled", "reasoning_effort": "high"}}

# Director system prompt (core rules from oh-story)
DIRECTOR_SYSTEM_PROMPT = """=== STABLE DIRECTOR CONTRACT ===
你是长篇网文的大纲优化导演。你的核心职责是**编排故事**，不是编排句式。

你不是写手，你不出正文。你是"总编辑 + 导演"的结合体。
你的任务是告诉 Writer：这个场景讲什么、用什么方式讲、信息怎么分配。句式、分段、用词是 Writer 的职责，你不要管。

=== 第一原则：对话驱动 ===
读者是为了看"故事内容"来的，不是看作者主观臆想的。故事内容 = 人物的行为和语言。

你的 chapter_direction 和 pacing_strategy 必须明确：
- 哪些信息通过**对话**传递（人物之间的交流、冲突、试探）
- 哪些情绪通过**行为**展现（动作、反应、选择）
- 哪些背景通过**叙述**交代（点到即止，不铺开）
- 对话占比目标：30-40%。如果某个 beat 没有对话对象，要设计自言自语、回忆别人的话、打电话等方式

=== 第二原则：钩子编排 ===
每个场景必须有钩子。钩子类型：
- 悬念钩：留下未解的问题（"谁画的这幅画？"）
- 情绪钩：制造情绪缺口（压抑→期待释放）
- 反转钩：颠覆预期（"招租电话是我自己的"）
- 信息差：读者知道角色不知道，或反过来

你的 key_scenes 必须标记每个场景的钩子类型。

=== 第三原则：期待感管理 ===
- 每章结束时，读者必须有一个想看下一章的理由
- "不存在过渡章"——每个场景都是下一个期待感的铺垫
- 节奏慢的时候加钩子，节奏快的时候加情绪

=== chapter_direction 编写规范 ===
不要写"用短句""用长句""内心独白密度25%"这种句式指导。
要写：
- 本章的核心冲突是什么
- 哪些场景用对话推进（具体到哪个人物说哪类话）
- 哪些场景用行为推进（具体到什么动作展现什么情绪）
- 信息如何分层释放（先给什么线索，后揭什么真相）

=== pacing_strategy 编写规范 ===
不要写"短句密集事件""动后必静"这种节奏配方。
要写：
- 每个 beat 的信息类型（对话/行为/叙述/内心推断）
- beat 之间的信息递进关系（A beat 给线索 → B beat 通过对话确认 → C beat 行动验证）
- 哪里需要"慢下来"（通过对话深挖情绪），哪里需要"快起来"（通过行为推进剧情）

=== key_scenes 编写规范 ===
每个 scene 必须包含：
1. 场景内容（一句话）
2. 钩子类型（悬念/情绪/反转/信息差）
3. 信息传递方式（对话/行为/叙述）
4. 涉及人物

示例：
"袁护士交接钥匙并送安神香 | 钩子：悬念（为什么送香？）| 方式：对话为主（袁护士简短交代+林知夏追问+袁护士回避）| 人物：林知夏、袁护士"

=== OUTPUT FORMAT（必须严格遵守）===
只输出一个 JSON 对象，不要任何 markdown、不要 ``` 代码块、不要前后解释文字。
JSON 必须能直接被 json.loads 解析。字段如下（除标注外都是 string，缺失字段用空字符串）：

{
  "guidance_id": "string",
  "chapter_direction": "string — 本章叙事方向（核心冲突+信息分配方式，不要写句式指导）",
  "emotional_arc": "string — 本章情绪弧线 开头→中间→结尾",
  "pacing_strategy": "string — 节奏策略（每个beat的信息类型和递进关系，不要写句式配方）",
  "key_scenes": ["string — 格式：内容|钩子类型|传递方式|人物", "..."],
  "dialogue_tone": "string — 对话基调（每个主要人物的说话风格和对话中的潜台词）",
  "reader_expectation_plan": "string — 读者预期操控（每章结束时读者想知道什么）",
  "reasoning": "string — 推理过程（供审查）"
}

若你不确定某个字段，写空字符串或空数组，但不要省略字段，不要输出 JSON 以外的内容。
"""


class NovelDirectorAdapter:
    """Director LLM adapter for novel mode."""

    def __init__(self, registry, model: str = "deepseek-v4-pro"):
        self._registry = registry
        self._model = model

    def generate_guidance(
        self,
        project_id: str,
        chapter_plan: Any,
        completed_chapters_summary: str,
        ledger_items: list,
        character_states: dict,
        foreshadowing_list: list,
        subplot_status: list,
        previous_chapter_ending: str,
    ) -> DirectorGuidance:
        """Generate Director guidance for a chapter."""
        system_prompt, user_prompt = self._build_prompt(
            project_id, chapter_plan, completed_chapters_summary,
            ledger_items, character_states, foreshadowing_list,
            subplot_status, previous_chapter_ending,
        )
        # Call LLM and parse JSON response
        from .novel_llm_factory import NovelLLMFactory
        factory = NovelLLMFactory.get_instance()
        adapter = factory.get_adapter("director")
        thinking = factory.get_thinking_config("director")
        model = factory.get_model("director")
        max_tokens = factory.get_max_tokens("director")

        try:
            text, receipt = adapter.generate_text(
                user_prompt,
                max_tokens=max_tokens,
                provider_role="novel_director",
                model=model,
                extra_body=thinking,
                system_prompt=system_prompt,
            )
        except Exception:
            text = ""

        # Parse JSON response robustly: tolerate ```json fences and leading prose.
        import json
        extracted = self._extract_json_object(text)
        if extracted is not None:
            try:
                data = json.loads(extracted)
                return DirectorGuidance.from_dict(data)
            except (json.JSONDecodeError, TypeError):
                pass

        # Last resort: keep only a short chapter_direction, drop the long reasoning
        # (previously we leaked the full reasoning text into the packet, wasting
        #  tens of thousands of tokens downstream for no value).
        cleaned = text.strip()
        if len(cleaned) > 400:
            cleaned = cleaned[:400]
        return DirectorGuidance(
            guidance_id=f"guid-{chapter_plan.chapter_id}",
            chapter_direction=cleaned or "推进主线",
        )

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        """Best-effort extract the first balanced top-level JSON object from text.

        Strips ```json fences, then scans for the outermost {...}. Returns the
        substring or None if no brace pair is found.
        """
        if not text:
            return None
        t = text.strip()
        # Strip markdown code fences
        if t.startswith("```"):
            # remove opening fence (with optional language tag)
            first_newline = t.find("\n")
            if first_newline != -1:
                t = t[first_newline + 1:]
            # remove closing fence if present
            if t.endswith("```"):
                t = t[:-3]
            t = t.strip()
        # Find outermost brace pair
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
        self, project_id, chapter_plan, completed_chapters_summary,
        ledger_items, character_states, foreshadowing_list,
        subplot_status, previous_chapter_ending,
    ) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt).

        Optimized for DeepSeek prefix caching: stable rules first.
        """
        # Stable prefix — cacheable
        parts = [
            "=== THINKING WORKFLOW ===\n"
            "1. 先审视全书结构：当前处于什么阶段？节奏是否合理？\n"
            "2. 检查伏笔：有哪些需要推进？有哪些需要埋设？\n"
            "3. 检查角色弧光：主要角色在本章应该有什么成长？\n"
            "4. 检查支线：哪些支线需要推进？哪些可以暂缓？\n"
            "5. 设计读者预期：本章应该给读者什么期待？如何误导或满足？\n"
            "6. 最后：为 Writer 提供精确的本章方向",
        ]

        # Varying context
        parts.append(f"\n=== CURRENT TASK ===\n当前要写第 {chapter_plan.chapter_index} 章")
        parts.append(f"\n章节计划:\n{chapter_plan.to_dict()}")
        parts.append(f"\n前一章结尾:\n{previous_chapter_ending}")

        if character_states:
            parts.append(f"\n角色状态:\n{character_states}")

        if foreshadowing_list:
            parts.append(f"\n伏笔清单:\n{foreshadowing_list}")

        if subplot_status:
            parts.append(f"\n支线进度:\n{subplot_status}")

        if ledger_items:
            items_text = "\n".join(f"- [{i.section}] {i.entity}: {i.content}" for i in ledger_items[:20])
            parts.append(f"\n连续性账本:\n{items_text}")

        parts.append(f"\n已完成章节摘要:\n{completed_chapters_summary}")

        parts.append(
            "\n=== FINAL REMINDER ===\n"
            "按 OUTPUT FORMAT 只输出一个 JSON 对象。不要 markdown，不要解释。"
        )

        return DIRECTOR_SYSTEM_PROMPT, "\n".join(parts)
