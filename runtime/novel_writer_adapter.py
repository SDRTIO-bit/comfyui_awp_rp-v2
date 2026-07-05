"""NovelWriterAdapter — Chapter Writer LLM adapter for novel mode.

Uses DeepSeekAdapter with thinking=medium for creative writing.
"""

from __future__ import annotations

from typing import Any

from ..contracts.novel_write_packet import NovelWritePacket
from ..contracts.novel_chapter import ChapterPlan, BeatDetail

# Thinking configuration for creative writing
_THINKING_MEDIUM = {"thinking": {"type": "enabled", "reasoning_effort": "medium"}}

# Writer system prompt (core rules from oh-story)
WRITER_SYSTEM_PROMPT = """=== STABLE WRITING CONTRACT ===
你是长篇网文的章节写手。你只输出正文，不出标签、无JSON、无元信息。

=== 一、句式规则 ===
1. 一句话不超过50个字。按动作变化、视线变化、情绪变化断句。
2. 一句话只说一件事。先写最重要的动作，再补心理、原因、状态。
3. 用动作和画面表达情绪，不用情绪词直述。不写"她很难过"，写"她捏着手机，半天没说话，最后把脸埋进了膝盖里"。
4. 不写抽象概括，写具体细节。不写"很破旧"，写"墙皮一块块往下掉，窗框发黑，桌角缺了口"。
5. 同一个意思只说一遍，不重复铺垫。

=== 二、对话规则（目标占正文 30-40%）===
对话是推进剧情的主要手段。独处场景也要有对话（自言自语、回忆别人说过的话、打电话）。

**互动感：**
- 不是轮流发言，要有打断、反问、吐槽、接话、抢话、答非所问。
- 错误：「"你来了。""是的。""走吧。""好的。」
- 正确：「"你再晚五分钟，我都准备给你立碑了。""少来，堵了一路，我能活着到这儿已经算命大。"」

**功能性：**
- 每段对话至少承担一项：给新信息、造冲突、做决定、改关系、推行动。
- 对话结束时局面要发生一点变化，哪怕只是人物态度变了。

**潜台词：**
- 不直说情绪，藏在反话、停顿、答非所问、刻意平静里。
- 嘴上抱怨实际关心，嘴上说无所谓实际试探。
- 越重要的情绪，越不要第一句就说破。

**人物辨识度：**
- 不同人说话方式不同。身份、年龄、脾气、关系远近影响措辞。
- 亲近关系不代表说话温柔，亲情常常藏在责备、打断、嘴硬里。
- 敌对关系不是句句大吼，用嘲讽、轻视、故意戳痛点体现。

**写法：**
- 对话和动作、心理、叙述混在一起写，不独立成段。
- 对话标签<50%，用动作代替"XX说"。

=== 三、描写规则（点到即止，不要铺开）===
描写是为对话和行为服务的背景板，不是正文主体。

**情绪：** 禁用情绪词。用1个身体反应替代（掐掌心、吞口水、手指蜷了一下）。不要把"脸"拆开写5个细节，挑1个就够。
**动作：** 重要动作拆2-3个小动作，不要拆5个。加入"二次动作"（伸到一半停住）。
**场景：** 跟着对话和动作一起出现，不要集中堆砌。五感挑1-2种，不要5种全写。
**细节：** 给人物1-2个专属小动作/口头禅。穿插小阻碍打破平淡。

**核心原则：描写占正文不超过40%。如果一章里描写超过40%，说明你在用描写代替对话推进剧情。**

=== 四、叙述姿态：深度限知 ===
锁死主视角角色的"此刻感知"。读者与角色同步获知。主观偏差代替客观叙述。

=== 五、格式规则 ===
禁用省略号和破折号。段落参差不齐。大白话，不用华丽辞藻。

=== 六、底线 ===
- 对话+行为占正文60%以上
- 描写不超过40%
- 每个场景必须有对话（独处场景用自言自语/回忆/打电话）
- 大白话，不用华丽辞藻
- 字数：默认最低3000字/章
"""


class NovelWriterAdapter:
    """Chapter Writer LLM adapter for novel mode."""

    def __init__(self, registry, model: str = "deepseek-v4-pro"):
        self._registry = registry
        self._model = model

    def generate_chapter(self, packet: NovelWritePacket) -> str:
        """Generate full chapter text from a write packet."""
        system_prompt, user_prompt = self._build_prompt(packet)
        return self._call_llm(user_prompt, system_prompt)

    def generate_beat(self, packet: NovelWritePacket) -> str:
        """Generate a single beat's text."""
        system_prompt, user_prompt = self._build_beat_prompt(packet)
        return self._call_llm(user_prompt, system_prompt)

    def _build_prompt(self, packet: NovelWritePacket) -> tuple[str, str]:
        """Build the full chapter generation prompt. Returns (system_prompt, user_prompt).

        Prompt structure optimized for DeepSeek prefix caching:
        - Stable rules first (cacheable prefix)
        - Varying context after
        """
        # Stable prefix — same every call, maximizes cache hits
        parts = [
            "=== OUTPUT RULES ===\n"
            "- 只输出正文，无标签、无 JSON、无元信息\n"
            "- 结尾必须留悬念/钩子\n"
            "- 不复述上一章结尾\n"
            "- 对话+行为占正文60%以上，描写不超过40%\n"
            "- 每个场景必须有对话（独处场景用自言自语/回忆/打电话）\n"
            "- 严格遵循 Director 的情绪弧线和节奏策略",
        ]

        # Varying context — changes per chapter
        parts.append(f"\n=== TARGET ===\n目标字数: {packet.chapter_plan.target_chars}")

        if packet.director_guidance.guidance_id:
            parts.append(f"\n=== DIRECTOR GUIDANCE ===\n"
                        f"方向: {packet.director_guidance.chapter_direction}\n"
                        f"情绪弧线: {packet.director_guidance.emotional_arc}\n"
                        f"节奏策略: {packet.director_guidance.pacing_strategy}\n"
                        f"对话基调: {packet.director_guidance.dialogue_tone}")

        if packet.writing_intent:
            parts.append(f"\n=== WRITING INTENT ===\n{packet.writing_intent}")

        parts.append(f"\n=== CHAPTER PLAN ===\n{packet.chapter_plan.to_dict()}")

        if packet.previous_chapter_summary:
            parts.append(f"\n=== PREVIOUS CHAPTER ===\n{packet.previous_chapter_summary}")

        if packet.character_states:
            parts.append(f"\n=== CHARACTER STATES ===\n{packet.character_states}")

        if packet.relevant_ledger_items:
            items_text = "\n".join(f"- [{i.section}] {i.entity}: {i.content}" for i in packet.relevant_ledger_items)
            parts.append(f"\n=== CONTINUITY CONTEXT ===\n{items_text}")

        return WRITER_SYSTEM_PROMPT, "\n".join(parts)

    def _build_beat_prompt(self, packet: NovelWritePacket) -> tuple[str, str]:
        """Build prompt for a single beat. Returns (system_prompt, user_prompt)."""
        beat = packet.current_scene_beat

        # Stable prefix
        parts = [
            "=== OUTPUT RULES ===\n"
            "- 只输出本 beat 的正文\n"
            "- 无标签、无 JSON、无元信息\n"
            "- 对话+行为占正文60%以上，描写不超过40%\n"
            "- 必须有对话。即使 beat 描述没提对话，也要加入：自言自语、回忆别人说过的话、对物件说话、打电话\n"
            "- 对话要有互动感和功能：不是轮流发言，要推进剧情/展示人设/制造冲突\n"
            "- 描写点到即止：一个物件一句话，不要铺开写三句",
            f"\n=== TARGET ===\n字数: {beat.budget_chars} | 密度: {beat.density}",
        ]

        # Varying context
        parts.append(f"\n=== CURRENT BEAT ===\n"
                    f"描述: {beat.description}\n"
                    f"功能: {beat.function_tag}\n"
                    f"注意：以上描述只是骨架。你必须用对话填充血肉。没有对话的beat是失败的。")

        if packet.accumulated_text:
            # Show last 500 chars for style continuity
            tail = packet.accumulated_text[-500:]
            parts.append(f"\n=== ACCUMULATED TEXT (tail) ===\n{tail}")

        parts.append(f"\n=== CHAPTER PLAN (summary) ===\n"
                    f"标题: {packet.chapter_plan.title}\n"
                    f"情绪: {packet.chapter_plan.target_emotion}\n"
                    f"位置: {packet.chapter_plan.chapter_position}")

        if packet.director_guidance.guidance_id:
            parts.append(f"\n=== DIRECTOR GUIDANCE ===\n"
                        f"方向: {packet.director_guidance.chapter_direction}\n"
                        f"情绪弧线: {packet.director_guidance.emotional_arc}")

        parts.append(f"\n=== OUTPUT RULES ===\n"
                    f"- 只输出本 beat 的正文\n"
                    f"- 目标 {beat.budget_chars} 字\n"
                    f"- 密度: {beat.density}\n"
                    f"- 无标签、无 JSON、无元信息")

        return WRITER_SYSTEM_PROMPT, "\n".join(parts)

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """Call LLM with thinking=medium. Raises on failure (no placeholder)."""
        from .novel_llm_factory import NovelLLMFactory
        factory = NovelLLMFactory.get_instance()
        adapter = factory.get_adapter("writer")
        thinking = factory.get_thinking_config("writer")
        model = factory.get_model("writer")
        max_tokens = factory.get_max_tokens("writer")

        try:
            text, receipt = adapter.generate_text(
                prompt,
                max_tokens=max_tokens,
                provider_role="novel_writer",
                model=model,
                extra_body=thinking,
                system_prompt=system_prompt or None,
            )
            if text and text.strip():
                return text
        except Exception:
            # Fall through to the failure raise below.
            pass
        # Previously returned a placeholder string, which got persisted as the
        # chapter text and silently counted as a "completed" chapter. Now raise
        # so the caller (NovelEngine retry loop / batch_write except) can handle it.
        raise RuntimeError("Novel writer LLM returned empty output")
