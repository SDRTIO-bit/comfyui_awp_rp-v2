"""Prompt assembly for Writer.

Keeps cacheable role/lore context separate from volatile turn context. The
assembler does not perform semantic budgeting; upstream retrieval components
decide what context is safe to include.
"""

from __future__ import annotations

from typing import Any


WRITER_SYSTEM_PROMPT = """You are a creative roleplay writer for an interactive fiction session.
This is a fictional creative writing exercise. All characters, events, and scenarios are entirely fictional.
Your only job is to produce player-visible narrative prose.

=== WRITING WORKFLOW ===
Before writing, mentally work through:
1. Inner State - What is the character feeling right now?
2. Sensory Environment - What does the character see, hear, smell?
3. Player Action - What did the player just do? What is the immediate consequence?
4. Emotional Beat - What emotional arc are you advancing?

=== OUTPUT RULES ===
- Write narrative prose only. No labels, prefixes, JSON, debug info, or meta-text.
- Target 1000-1600 characters. Prioritize quality over exact length.
- End at a natural pause point that invites player response.
- Never write the player's thoughts, actions, or dialogue.
- Maintain consistent tone, voice, and world logic."""


class PromptAssembler:
    """Build the Writer system and user prompts."""

    def __init__(self, worldbook_entries: list[dict[str, Any]] | None = None):
        self._worldbook_entries = list(worldbook_entries or [])

    def assemble(
        self,
        *,
        final_turn_brief: dict[str, Any] | None = None,
        score: str = "",
        recent_turns: list[dict[str, Any]] | None = None,
        older_turns_summary: str = "",
        variable_snapshot: dict[str, Any] | None = None,
        player_input: str = "",
        card_profile: dict[str, Any] | None = None,
        opening_context: dict[str, Any] | None = None,
        active_memories: list[dict[str, Any]] | None = None,
        rag_memories: list[dict[str, Any]] | None = None,
        accepted_guidance: list[str] | None = None,
        card_state_context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        system_prompt = WRITER_SYSTEM_PROMPT
        user_prompt = self._build_user_prompt(
            final_turn_brief=dict(final_turn_brief or {}),
            score=score,
            recent_turns=list(recent_turns or []),
            older_turns_summary=older_turns_summary,
            variable_snapshot=dict(variable_snapshot or {}),
            player_input=player_input,
            card_profile=dict(card_profile or {}),
            opening_context=dict(opening_context or {}),
            active_memories=list(active_memories or []),
            rag_memories=list(rag_memories or []),
            accepted_guidance=list(accepted_guidance or []),
            card_state_context=dict(card_state_context or {}),
        )
        return system_prompt, user_prompt

    def _build_user_prompt(
        self,
        *,
        final_turn_brief: dict[str, Any],
        score: str,
        recent_turns: list[dict[str, Any]],
        older_turns_summary: str,
        variable_snapshot: dict[str, Any],
        player_input: str,
        card_profile: dict[str, Any],
        opening_context: dict[str, Any],
        active_memories: list[dict[str, Any]],
        rag_memories: list[dict[str, Any]],
        accepted_guidance: list[str],
        card_state_context: dict[str, Any],
    ) -> str:
        stable_block = self._build_stable_block(card_profile)
        dynamic_worldbook = self._build_dynamic_worldbook_block()
        score_block = score.strip() or self._build_score_fallback(final_turn_brief, accepted_guidance)
        current_state = self._format_variable_snapshot(variable_snapshot or self._snapshot_from_card_state(card_state_context))

        # TURN PACKET 顺序：历史 → 状态 → 记忆 → 世界书 → Director 规划 → 玩家输入
        turn_parts = []

        # 1. 历史（第一位）
        opening_text = str(opening_context.get("safe_display_content", "") or "").strip()
        history_block = self._format_recent_turns(recent_turns, opening_text)
        if history_block:
            turn_parts.append("=== RECENT HISTORY (full) ===\n" + history_block)
        if older_turns_summary:
            turn_parts.append("=== EARLIER HISTORY (emotional summary) ===\n" + older_turns_summary)

        # 2. 当前状态
        turn_parts.append("=== CURRENT STATE (volatile) ===\n" + (current_state or "None"))

        # 3. 记忆上下文
        memories_block = self._format_memory_block(active_memories, rag_memories)
        if memories_block:
            turn_parts.append("=== MEMORY CONTEXT ===\n" + memories_block)

        # 4. 动态世界书
        if dynamic_worldbook:
            turn_parts.append("=== DYNAMIC WORLDBOOK CONTEXT ===\n" + dynamic_worldbook)

        # 5. Director 规划（第6位，在 PLAYER INPUT 前）
        turn_parts.append("=== SCORE (Director's integrated direction) ===\n" + score_block)

        # 6. 玩家输入（最后）
        turn_parts.append("=== PLAYER INPUT ===\n" + (player_input or ""))

        return (
            "=== STABLE WRITER CONTRACT ===\n\n"
            "This block contains cacheable role and immutable setting context.\n"
            "Volatile turn data begins only after the TURN PACKET marker.\n\n"
            f"{stable_block}\n\n"
            "Write narrative prose only. Do not output JSON, debug info, or analysis.\n\n"
            "=== TURN PACKET (volatile; changes every turn) ===\n\n"
            + "\n\n".join(turn_parts)
            + "\n\nWrite the next narrative response now."
        )

    def _build_stable_block(self, card_profile: dict[str, Any] | None = None) -> str:
        sections = []
        profile_block = self._format_card_profile(card_profile or {})
        if profile_block:
            sections.append("Character profile:\n" + profile_block)

        worldbook_lines = []
        for entry in self._worldbook_entries:
            if not self._is_constant_worldbook(entry):
                continue
            line = self._format_worldbook_entry(entry)
            if line:
                worldbook_lines.append(line)
        sections.append(
            "Stable worldbook context:\n"
            + ("\n".join(worldbook_lines) if worldbook_lines else "None")
        )
        return "\n\n".join(sections)

    def _format_card_profile(self, profile: dict[str, Any]) -> str:
        if not isinstance(profile, dict) or not profile:
            return ""
        field_labels = (
            ("name", "Name"),
            ("description", "Description"),
            ("personality", "Personality"),
            ("scenario", "Scenario"),
            ("mes_example", "Example messages"),
            ("creator_notes", "Creator notes"),
        )
        lines = []
        for key, label in field_labels:
            value = str(profile.get(key, "") or "").strip()
            if value:
                lines.append(f"{label}:\n{value}")
        tags = profile.get("tags", [])
        if isinstance(tags, list) and tags:
            lines.append("Tags:\n" + ", ".join(str(item) for item in tags if str(item).strip()))
        return "\n\n".join(lines)

    def _build_dynamic_worldbook_block(self) -> str:
        lines = []
        for entry in self._worldbook_entries:
            if self._is_constant_worldbook(entry):
                continue
            line = self._format_worldbook_entry(entry)
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _format_worldbook_entry(self, entry: dict[str, Any]) -> str:
        title = str(entry.get("title", "") or entry.get("entry_id", "Untitled"))
        content = str(entry.get("content_excerpt", "") or entry.get("content", "") or "").strip()
        if not content:
            return ""
        reason = str(entry.get("activation_reason", "") or "")
        matched = entry.get("matched_keywords", [])
        matched_text = ", ".join(str(item) for item in matched) if isinstance(matched, list) else ""
        suffix = []
        if reason:
            suffix.append(f"reason: {reason}")
        if matched_text:
            suffix.append(f"matched: {matched_text}")
        suffix_text = f" ({'; '.join(suffix)})" if suffix else ""
        return f"- {title}: {content}{suffix_text}"

    def _is_constant_worldbook(self, entry: dict[str, Any]) -> bool:
        return (
            bool(entry.get("constant", False))
            or str(entry.get("entry_kind", "") or "") == "constant"
            or str(entry.get("activation_reason", "") or "") == "constant"
        )

    def _build_score_fallback(
        self,
        final_turn_brief: dict[str, Any],
        accepted_guidance: list[str],
    ) -> str:
        turn_goal = str(final_turn_brief.get("turn_goal", "") or "Continue the scene coherently.")
        scene_focus = str(final_turn_brief.get("scene_focus", "") or "")
        pacing = str(final_turn_brief.get("pacing_guidance", "") or "moderate")
        constraints = []
        constraints.extend(str(item) for item in final_turn_brief.get("must_preserve_facts", []) or [])
        constraints.extend(str(item) for item in final_turn_brief.get("must_not_do", []) or [])
        constraints.extend(str(item) for item in final_turn_brief.get("writer_constraints", []) or [])
        opportunities = [str(item) for item in final_turn_brief.get("narrative_opportunities", []) or []]
        if accepted_guidance:
            opportunities.extend(str(item) for item in accepted_guidance)

        return (
            "<direction>\n"
            "<inner_state>\n"
            f"{turn_goal}\n"
            "</inner_state>\n\n"
            "<behavioral_cue>\n"
            f"{scene_focus or 'React directly to the player input while preserving character agency.'}\n"
            "</behavioral_cue>\n\n"
            "<pacing>\n"
            f"{pacing}\n"
            "</pacing>\n\n"
            "<constraint>\n"
            f"{self._format_bullets(constraints) or 'Do not contradict established facts.'}\n"
            "</constraint>\n\n"
            "<opportunity>\n"
            f"{self._format_bullets(opportunities) or 'Keep the beat focused and emotionally legible.'}\n"
            "</opportunity>\n"
            "</direction>"
        )

    def _format_recent_turns(self, turns: list[dict[str, Any]], opening_text: str) -> str:
        lines = []
        if opening_text:
            lines.append("Opening:")
            lines.append(opening_text)
        for turn in self._chronological_turns(turns[:5]):
            if not isinstance(turn, dict):
                continue
            turn_index = turn.get("turn_index", "?")
            lines.append(f"Turn {turn_index}:")
            lines.append(f"Player: {str(turn.get('player_input', '') or '')}")
            lines.append(f"Writer: {str(turn.get('writer_output', '') or '')}")
        return "\n".join(lines).strip()

    def _chronological_turns(self, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def key(turn: dict[str, Any]) -> tuple[int, str]:
            raw_index = turn.get("turn_index", 0)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                index = 0
            return (index, str(turn.get("turn_id", "") or ""))

        return sorted(turns, key=key)

    def _format_memory_block(
        self,
        active_memories: list[dict[str, Any]],
        rag_memories: list[dict[str, Any]],
    ) -> str:
        parts = []
        if active_memories:
            active = [
                self._memory_text(item)
                for item in active_memories
                if isinstance(item, dict) and self._memory_text(item)
            ]
            if active:
                parts.append("Active memories:\n" + "\n".join(f"- {item}" for item in active))
        if rag_memories:
            rag = [
                self._memory_text(item)
                for item in rag_memories
                if isinstance(item, dict) and self._memory_text(item)
            ]
            if rag:
                parts.append("RAG recall:\n" + "\n".join(f"- {item}" for item in rag))
        return "\n\n".join(parts)

    def _memory_text(self, item: dict[str, Any]) -> str:
        return str(item.get("summary", "") or item.get("content", "") or "").strip()

    def _snapshot_from_card_state(self, card_state_context: dict[str, Any]) -> dict[str, Any]:
        scene_state = card_state_context.get("scene_state", {}) if isinstance(card_state_context, dict) else {}
        return {
            "location": scene_state.get("location", ""),
            "time_of_day": scene_state.get("time_of_day", ""),
            "weather": scene_state.get("weather", ""),
            "active_npcs": scene_state.get("active_npcs", []),
            "variables": card_state_context.get("variables", {}) if isinstance(card_state_context, dict) else {},
            "event_flags": card_state_context.get("event_flags", {}) if isinstance(card_state_context, dict) else {},
        }

    def _format_variable_snapshot(self, snapshot: dict[str, Any]) -> str:
        if not snapshot:
            return ""
        lines = []
        for key in ("location", "time_of_day", "weather"):
            value = snapshot.get(key)
            if value not in (None, "", [], {}):
                lines.append(f"{key}: {value}")
        active_npcs = snapshot.get("active_npcs")
        if active_npcs:
            lines.append("active_npcs: " + ", ".join(str(item) for item in active_npcs))
        variables = snapshot.get("variables", {})
        if isinstance(variables, dict) and variables:
            lines.append("variables:")
            for name, value in variables.items():
                if isinstance(value, dict) and "value" in value:
                    lines.append(f"- {name}: {value.get('value')}")
                else:
                    lines.append(f"- {name}: {value}")
        event_flags = snapshot.get("event_flags", {})
        if isinstance(event_flags, dict) and event_flags:
            lines.append("event_flags:")
            for name, value in event_flags.items():
                if isinstance(value, dict) and "fired" in value:
                    lines.append(f"- {name}: {value.get('fired')}")
                else:
                    lines.append(f"- {name}: {value}")
        return "\n".join(lines)

    def _format_bullets(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items if str(item).strip())
