"""Real Director Adapter -- uses DeepSeek for Director planning.

Implements DirectorV2Adapter protocol with real provider calls.
On failure, produces structured ProviderFailure.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from .deepseek_adapter import DeepSeekAdapter
from ...contracts.director_plan import DirectorPlan
from ...contracts.tool_plan import ToolPlan, PlannedToolRequest
from ...contracts.delegation_plan import DelegationPlan, DelegationTask
from ...contracts.round_snapshot import RoundSnapshot
from ...contracts.provider_request import ProviderAttemptReceipt


class RealDirectorV2Adapter:
    """Real Director adapter using DeepSeek.

    Generates DirectorPlan, ToolPlan, and DelegationPlan from RoundSnapshot.
    """

    def __init__(self, deepseek: DeepSeekAdapter, model: str = ""):
        self._llm = deepseek
        self._model = model
        # Director is a structured-planning role (filling schema fields, not
        # creative prose), so it uses function calling instead of thinking.
        #
        # DeepSeek v4 models default to thinking mode server-side, and thinking
        # mode rejects tool_choice ("Thinking mode does not support this
        # tool_choice" → 400 → SDK retries → EMPTY_RESPONSE). So we must
        # explicitly DISABLE thinking to unlock function calling. With thinking
        # disabled, the SDK's tool_calls path returns valid structured JSON,
        # avoiding the old raw-text json.loads failures (markdown fences /
        # truncation / empty content).
        self._extra_body = {"thinking": {"type": "disabled"}}

    def generate_plan(
        self,
        snapshot: RoundSnapshot,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
    ) -> tuple[DirectorPlan, ProviderAttemptReceipt]:
        """Generate DirectorPlan from snapshot."""
        prompt = self._build_plan_prompt(snapshot)
        schema = {
            "type": "object",
            "required": ["turn_goal", "scene_focus"],
            "properties": {
                "turn_goal": {"type": "string"},
                "scene_focus": {"type": "string"},
                "must_preserve_facts": {"type": "array", "items": {"type": "string"}},
                "must_not_do": {"type": "array", "items": {"type": "string"}},
                "narrative_opportunities": {"type": "array", "items": {"type": "string"}},
                "writer_constraints": {"type": "array", "items": {"type": "string"}},
                "active_character_refs": {"type": "array", "items": {"type": "string"}},
                "relationship_tensions": {"type": "array", "items": {"type": "string"}},
                "unresolved_threads": {"type": "array", "items": {"type": "string"}},
                "pacing_guidance": {"type": "string"},
                "risk_flags": {"type": "array", "items": {"type": "string"}},
            },
        }

        parsed, receipt = self._llm.generate_structured(
            prompt, schema,
            max_tokens=1200,
            provider_role="director",
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            turn_id=turn_id,
            model=self._model,
            attempt_id=attempt_id,
            extra_body=self._extra_body,
        )

        if not receipt.success:
            return DirectorPlan(), receipt

        plan = DirectorPlan(
            turn_goal=parsed.get("turn_goal", ""),
            scene_focus=parsed.get("scene_focus", ""),
            must_preserve_facts=parsed.get("must_preserve_facts", []),
            must_not_do=parsed.get("must_not_do", []),
            narrative_opportunities=parsed.get("narrative_opportunities", []),
            writer_constraints=parsed.get("writer_constraints", []),
            active_character_refs=parsed.get("active_character_refs", []),
            relationship_tensions=parsed.get("relationship_tensions", []),
            unresolved_threads=parsed.get("unresolved_threads", []),
            pacing_guidance=parsed.get("pacing_guidance", ""),
            risk_flags=parsed.get("risk_flags", []),
        )
        return plan, receipt

    def generate_tool_plan(
        self,
        snapshot: RoundSnapshot,
        plan: DirectorPlan,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
    ) -> tuple[ToolPlan, ProviderAttemptReceipt]:
        """Generate a bounded read-only ToolPlan for Director enrichment."""
        requests: list[PlannedToolRequest] = []

        def add(tool_id: str, purpose: str, query: str = "", required: bool = False) -> None:
            if len(requests) >= 5:
                return
            requests.append(PlannedToolRequest(
                request_id=f"dir_{tool_id}_{len(requests) + 1}",
                tool_id=tool_id,
                purpose=purpose,
                priority=0.8 if required else 0.5,
                input={"query": query[:160]} if query else {},
                timeout_ms=15000,
                token_budget=600,
                required=required,
                failure_policy="degrade",
                evidence_requirement=purpose,
            ))

        query = " ".join([
            str(snapshot.player_input or "")[:160],
            str(plan.turn_goal or "")[:120],
            str(plan.scene_focus or "")[:120],
        ]).strip()

        add("scene_context_lookup", "Read current scene state before planning writer constraints.", query, required=True)
        if snapshot.active_worldbook_entries:
            add("worldbook_lookup", "Read active worldbook facts that must constrain this turn.", query)
        if snapshot.recent_turn_records:
            add("accepted_turn_lookup", "Read recent accepted turns for continuity and callbacks.", query)
        if snapshot.active_memories:
            add("active_memory_lookup", "Read active memories for promises, relationships, and facts.", query)
        if snapshot.rag_recall:
            add("rag_memory_lookup", "Read recalled long-term memories relevant to this turn.", query)

        receipt = ProviderAttemptReceipt(
            provider_role="director",
            success=True,
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            turn_id=turn_id,
            attempt_id=attempt_id,
        )
        return ToolPlan(
            tool_plan_id=f"tp_{uuid.uuid4().hex[:12]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            director_plan_id=plan.plan_id,
            card_id=snapshot.card_id,
            session_id=snapshot.session_id,
            requests=requests,
            max_request_count=5,
            max_parallelism=1,
            total_token_budget=3000,
            total_time_budget_ms=30000,
            fallback_policy="degrade_optional",
        ), receipt

    def generate_delegation_plan(
        self,
        snapshot: RoundSnapshot,
        plan: DirectorPlan,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
    ) -> tuple[DelegationPlan, ProviderAttemptReceipt]:
        """Generate DelegationPlan — Director controls pre-writer sub-agents.

        Uses DirectorPlan + snapshot signals to decide which D1-D5 agents to
        invoke. Max 3 per turn to control cost; the engine executes them
        concurrently.
        """
        receipt = ProviderAttemptReceipt(
            provider_role="director",
            success=True,
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            turn_id=turn_id,
            attempt_id=attempt_id,
        )

        # Determine which sub-agents are contextually relevant
        tasks: list[DelegationTask] = []
        recent_turn_count = len(snapshot.recent_turn_records)
        active_mem_count = len(snapshot.active_memories)
        has_worldbook = bool(snapshot.active_worldbook_entries)
        scene = getattr(snapshot.card_state, "scene_state", None)
        active_npc_count = len(getattr(scene, "active_npcs", []) or []) if scene else 0

        tool_allowlist = [
            "accepted_turn_lookup", "active_memory_lookup", "rag_memory_lookup",
            "memory_rag_lookup", "worldbook_lookup", "scene_context_lookup",
            "relationship_context_lookup", "timeline_lookup", "entity_alias_lookup",
        ]

        # D1: History Recall — uses RAG + recent turns, not worldbook
        if recent_turn_count >= 2:
            tasks.append(DelegationTask(
                task_id=f"d1_{uuid.uuid4().hex[:8]}",
                role="history_recall",
                priority=0.7,
                purpose=(
                    f"Check recent history for this turn. "
                    f"Director's goal: {plan.turn_goal}. "
                    f"Risks to verify: {'; '.join(plan.risk_flags[:3]) if plan.risk_flags else 'none'}. "
                    f"Look for contradictions with established facts, unresolved threads, and callbacks."
                ),
                max_tokens=500,
                timeout_ms=20000,
                failure_policy="skip",
                tool_allowlist=tool_allowlist,
                input_field_allowlist=[
                    "player_input", "recent_turn_records", "active_memories",
                    "rag_recall", "card_state",
                ],
                expected_suggestion_kinds=["identity_clarification", "historical_conflict"],
            ))

        # D2: Opportunity — useful when the Director found possible beats.
        if plan.narrative_opportunities or plan.unresolved_threads or plan.relationship_tensions:
            tasks.append(DelegationTask(
                task_id=f"d2_{uuid.uuid4().hex[:8]}",
                role="opportunity",
                priority=0.6,
                purpose=(
                    f"Find dramatic opportunities for this turn. "
                    f"Director's goal: {plan.turn_goal}. "
                    f"Scene focus: {plan.scene_focus}. "
                    f"Known opportunities: {'; '.join(plan.narrative_opportunities[:3])}. "
                    f"Ground your analysis in established facts from recent turns and worldbook."
                ),
                max_tokens=500,
                timeout_ms=20000,
                failure_policy="skip",
                tool_allowlist=tool_allowlist,
                input_field_allowlist=[
                    "player_input", "recent_turn_records", "active_memories",
                    "rag_recall", "active_worldbook_entries", "card_state",
                ],
                expected_suggestion_kinds=["narrative_opportunity"],
            ))

        # D3: World Life — useful when worldbook or NPC context is active.
        if has_worldbook or active_npc_count > 0:
            tasks.append(DelegationTask(
                task_id=f"d3_{uuid.uuid4().hex[:8]}",
                role="world_life",
                priority=0.5,
                purpose=(
                    f"Add world texture and sensory details for this turn. "
                    f"Scene focus: {plan.scene_focus}. "
                    f"Look for environmental details, NPC background actions, and sensory elements "
                    f"that match the current location and time."
                ),
                max_tokens=500,
                timeout_ms=20000,
                failure_policy="skip",
                tool_allowlist=tool_allowlist,
                input_field_allowlist=[
                    "player_input", "recent_turn_records", "active_memories",
                    "rag_recall", "active_worldbook_entries", "card_state",
                ],
                expected_suggestion_kinds=["world_detail"],
            ))

        # D4: Emotion/Relationship — uses memories + recent turns, not worldbook
        if active_mem_count > 0 or recent_turn_count >= 1 or plan.relationship_tensions:
            tasks.append(DelegationTask(
                task_id=f"d4_{uuid.uuid4().hex[:8]}",
                role="emotion_relationship",
                priority=0.6,
                purpose=(
                    f"Analyze emotional state and relationship dynamics. "
                    f"Director's goal: {plan.turn_goal}. "
                    f"Relationship tensions: {'; '.join(plan.relationship_tensions[:3]) if plan.relationship_tensions else 'none'}. "
                    f"Look for what characters are feeling but not saying."
                ),
                max_tokens=500,
                timeout_ms=20000,
                failure_policy="skip",
                tool_allowlist=tool_allowlist,
                input_field_allowlist=[
                    "player_input", "recent_turn_records", "active_memories",
                    "rag_recall", "card_state",
                ],
                expected_suggestion_kinds=["relationship_shift"],
            ))

        # D5: Continuity — useful when facts need verification
        if recent_turn_count >= 3:
            tasks.append(DelegationTask(
                task_id=f"d5_{uuid.uuid4().hex[:8]}",
                role="continuity",
                priority=0.8,
                purpose=(
                    f"Verify factual continuity for this turn. "
                    f"Risks: {'; '.join(plan.risk_flags[:3]) if plan.risk_flags else 'none'}. "
                    f"Must preserve: {'; '.join(plan.must_preserve_facts[:3]) if plan.must_preserve_facts else 'none'}. "
                    f"Check names, relationships, locations, and timeline."
                ),
                max_tokens=500,
                timeout_ms=20000,
                failure_policy="skip",
                tool_allowlist=tool_allowlist,
                input_field_allowlist=[
                    "player_input", "recent_turn_records", "active_memories",
                    "rag_recall", "active_worldbook_entries", "card_state",
                ],
                expected_suggestion_kinds=["continuity_fact_constraint"],
            ))

        # Cap at 3 tasks per turn to control cost
        # Prioritize by priority score (higher = more important)
        tasks.sort(key=lambda t: -t.priority)
        tasks = tasks[:3]

        return DelegationPlan(
            plan_id=f"del_{uuid.uuid4().hex[:12]}",
            trace_id=trace_id,
            snapshot_id=snapshot.snapshot_id,
            brief_id=plan.plan_id,
            card_id=snapshot.card_id,
            session_id=snapshot.session_id,
            tasks=tasks,
            max_task_count=3,
            total_token_budget=3000,
            total_time_budget_ms=60000,
        ), receipt

    def _build_plan_prompt(self, snapshot: RoundSnapshot) -> str:
        """Build user prompt for Director plan generation.

        Separates stable worldbook context from volatile turn data for
        provider prefix caching. Role/workflow/format instructions are in
        the system prompt (SYSTEM_PROMPT_DIRECTOR), not repeated here.
        """
        player_input = snapshot.player_input
        scene_location = ""
        if hasattr(snapshot.card_state, 'scene_state'):
            scene_location = getattr(snapshot.card_state.scene_state, 'location', '')

        recent_turn_count = len(snapshot.recent_turn_records)

        # ── Worldbook: split stable (constant) vs dynamic ───────────────
        stable_worldbook_lines = []
        dynamic_worldbook_lines = []
        for entry in (snapshot.active_worldbook_entries or []):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", "") or entry.get("entry_id", "Untitled"))
            content = str(entry.get("content_excerpt", "") or entry.get("content", "") or "")
            activation_reason = str(entry.get("activation_reason", "") or "")
            matched = entry.get("matched_keywords", [])
            matched_text = ", ".join(str(item) for item in matched) if isinstance(matched, list) else ""
            line = f"- {title}: {content}"
            if activation_reason:
                line += f" (reason: {activation_reason})"
            if matched_text:
                line += f" (matched: {matched_text})"
            is_constant = (
                bool(entry.get("constant", False))
                or str(entry.get("entry_kind", "") or "") == "constant"
                or activation_reason == "constant"
            )
            if is_constant:
                stable_worldbook_lines.append(line)
            else:
                dynamic_worldbook_lines.append(line)
        stable_worldbook_block = "\n".join(stable_worldbook_lines) if stable_worldbook_lines else "(none)"
        dynamic_worldbook_block = "\n".join(dynamic_worldbook_lines) if dynamic_worldbook_lines else "(none)"
        profile_block = self._format_card_profile(
            getattr(snapshot, "card_profile_context", {}) or {}
        )

        # ── Recent turns (last 2-3, truncated) ──────────────────────────
        turn_lines = []
        recent_limit = int(getattr(snapshot, "max_turn_history", 5) or 5)
        for turn in self._chronological_turns((snapshot.recent_turn_records or [])[:recent_limit]):
            idx = getattr(turn, 'turn_index', '?')
            p = str(getattr(turn, 'player_input', '') or '')
            w = str(getattr(turn, 'writer_output', '') or '')
            turn_lines.append(f"Turn {idx} Player: {p}")
            turn_lines.append(f"Turn {idx} Writer: {w}")
        recent_turns_block = "\n".join(turn_lines) if turn_lines else "(none)"
        older_turns_summary = str(getattr(snapshot, "older_turns_summary", "") or "").strip()

        # ── Active memories (top 5, truncated) ──────────────────────────
        mem_lines = []
        for entry in (snapshot.active_memories or []):
            if isinstance(entry, dict):
                summary = str(entry.get("summary", "") or entry.get("content", "") or "")
                if summary:
                    mem_lines.append(f"- {summary}")
        mem_block = "\n".join(mem_lines) if mem_lines else "(none)"

        return f"""You are a narrative director for a roleplay session.
Keep the fixed instructions above separate from the volatile turn context below so provider prefix caching can be reused.

=== STABLE DIRECTOR CONTRACT ===

This block contains stable worldbuilding context. It changes infrequently.
The instructions above (role, workflow, output format) remain in effect.
Character profile:
{profile_block or "(none)"}

Stable worldbook context:
{stable_worldbook_block}

=== TURN PACKET (volatile; changes every turn) ===

Current scene: {scene_location}
Player input: {player_input}
Recent turns count: {recent_turn_count}
Active worldbook entries count: {len(snapshot.active_worldbook_entries)}
Active memories count: {len(snapshot.active_memories)}

=== Dynamic Worldbook Context ===

{dynamic_worldbook_block}

=== Recent Turns ===

{recent_turns_block}

=== Earlier Turns Summary ===

{older_turns_summary or "(none)"}

=== Active Memories ===

{mem_block}"""

    def _format_card_profile(self, profile: dict[str, Any]) -> str:
        if not isinstance(profile, dict) or not profile:
            return ""
        fields = (
            ("name", "Name"),
            ("description", "Description"),
            ("personality", "Personality"),
            ("scenario", "Scenario"),
            ("mes_example", "Example messages"),
            ("creator_notes", "Creator notes"),
        )
        lines = []
        for key, label in fields:
            value = str(profile.get(key, "") or "").strip()
            if value:
                lines.append(f"{label}:\n{value}")
        return "\n\n".join(lines)

    def _chronological_turns(self, turns: list[Any]) -> list[Any]:
        def key(turn: Any) -> tuple[int, str]:
            raw_index = getattr(turn, "turn_index", 0)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                index = 0
            return (index, str(getattr(turn, "turn_id", "") or ""))

        return sorted(turns, key=key)
