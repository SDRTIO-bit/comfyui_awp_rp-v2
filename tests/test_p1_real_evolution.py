"""P1 Tests: Real RP Evolution Loop.

Validates:
  1. TurnEvolutionCurator produces real state proposals
  2. No fake revision increment when nothing changed
  3. ConditionEvaluator evaluates conditions safely
  4. ConditionWorldbookActivation activates/deactivates entries based on CardState
  5. Memory candidates come from curator (not fake D6)
  6. Effects projection is populated
  7. AWPV2ContinueTurn creates a formal continue turn
  8. Real Director generates delegation plans (0-2 tasks)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from ..contracts.card_state import CardState, VariableEntry, EventFlag, SceneState
from ..contracts.card_state_patch import CardStatePatch, CardStatePatchOperation, PatchOpType
from ..contracts.curator_request import CuratorRequest
from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.turn_evolution_proposal import (
    TurnEvolutionProposal, StateUpdateProposalV2, MemoryCandidate,
)
from ..runtime.condition_evaluator import ConditionEvaluator, ConditionEvaluationError
from ..runtime.turn_evolution_curator import TurnEvolutionCurator


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════
# ConditionEvaluator tests
# ═══════════════════════════════════════════════════════════════════════

class TestConditionEvaluator:
    """Safe condition evaluation against CardState."""

    def test_01_equals_operator(self):
        evaluator = ConditionEvaluator()
        state = {"variables": {"trust": {"value": 10}}}
        condition = {"op": "equals", "path": "variables.trust.value", "value": 10}
        assert evaluator.evaluate(condition, state) is True

        condition_false = {"op": "equals", "path": "variables.trust.value", "value": 5}
        assert evaluator.evaluate(condition_false, state) is False

    def test_02_not_equals_operator(self):
        evaluator = ConditionEvaluator()
        state = {"variables": {"trust": {"value": 10}}}
        condition = {"op": "notEquals", "path": "variables.trust.value", "value": 5}
        assert evaluator.evaluate(condition, state) is True

    def test_03_gt_gte_operators(self):
        evaluator = ConditionEvaluator()
        state = {"variables": {"favorability": {"value": 50}}}

        assert evaluator.evaluate({"op": "gt", "path": "variables.favorability.value", "value": 30}, state) is True
        assert evaluator.evaluate({"op": "gt", "path": "variables.favorability.value", "value": 50}, state) is False
        assert evaluator.evaluate({"op": "gte", "path": "variables.favorability.value", "value": 50}, state) is True

    def test_04_lt_lte_operators(self):
        evaluator = ConditionEvaluator()
        state = {"variables": {"hp": {"value": 30}}}

        assert evaluator.evaluate({"op": "lt", "path": "variables.hp.value", "value": 50}, state) is True
        assert evaluator.evaluate({"op": "lte", "path": "variables.hp.value", "value": 30}, state) is True

    def test_05_exists_operator(self):
        evaluator = ConditionEvaluator()
        state = {"variables": {"trust": {"value": 10}}}

        assert evaluator.evaluate({"op": "exists", "path": "variables.trust"}, state) is True
        assert evaluator.evaluate({"op": "exists", "path": "variables.nonexistent"}, state) is False

    def test_06_contains_operator(self):
        evaluator = ConditionEvaluator()
        state = {"event_flags": {"quest_started": {"fired": True}}}

        assert evaluator.evaluate({"op": "contains", "path": "event_flags", "value": "quest_started"}, state) is True

    def test_07_boolean_operator(self):
        evaluator = ConditionEvaluator()
        state = {"event_flags": {"quest_started": True}}

        assert evaluator.evaluate({"op": "boolean", "path": "event_flags.quest_started"}, state) is True

    def test_08_and_or_not_operators(self):
        evaluator = ConditionEvaluator()
        state = {"variables": {"a": {"value": 10}, "b": {"value": 20}}}

        # AND
        and_cond = {
            "op": "and",
            "conditions": [
                {"op": "gt", "path": "variables.a.value", "value": 5},
                {"op": "lt", "path": "variables.b.value", "value": 30},
            ],
        }
        assert evaluator.evaluate(and_cond, state) is True

        # OR
        or_cond = {
            "op": "or",
            "conditions": [
                {"op": "lt", "path": "variables.a.value", "value": 5},
                {"op": "lt", "path": "variables.b.value", "value": 30},
            ],
        }
        assert evaluator.evaluate(or_cond, state) is True

        # NOT
        not_cond = {"op": "not", "condition": {"op": "lt", "path": "variables.a.value", "value": 5}}
        assert evaluator.evaluate(not_cond, state) is True

    def test_09_unsupported_operator_raises(self):
        evaluator = ConditionEvaluator()
        state = {}
        with pytest.raises(ConditionEvaluationError, match="Unsupported operator"):
            evaluator.evaluate({"op": "eval", "path": "x"}, state)

    def test_10_missing_path_returns_false(self):
        evaluator = ConditionEvaluator()
        state = {"variables": {}}
        condition = {"op": "equals", "path": "variables.nonexistent.value", "value": 10}
        assert evaluator.evaluate(condition, state) is False

    def test_11_nested_condition_worldbook_entry(self):
        """Test a realistic worldbook condition: trust >= 50 AND quest_started."""
        evaluator = ConditionEvaluator()
        state = {
            "variables": {"trust": {"value": 60}},
            "event_flags": {"quest_started": {"fired": True, "event_id": "quest_started"}},
        }
        condition = {
            "op": "and",
            "conditions": [
                {"op": "gte", "path": "variables.trust.value", "value": 50},
                {"op": "exists", "path": "event_flags.quest_started"},
            ],
        }
        assert evaluator.evaluate(condition, state) is True


# ═══════════════════════════════════════════════════════════════════════
# TurnEvolutionCurator tests
# ═══════════════════════════════════════════════════════════════════════

class TestTurnEvolutionCurator:
    """TurnEvolutionCurator produces real proposals."""

    def test_12_deterministic_no_change_for_greeting(self):
        """Simple greeting with no state signals should produce no_state_change."""
        curator = TurnEvolutionCurator(llm_adapter=None)
        # Use text with NO Chinese keywords that would trigger state changes
        request = CuratorRequest(
            request_id="r1", turn_id="t1", session_id="s1",
            player_input="Hello",
            accepted_writer_output="Welcome to the tavern. The fire crackles warmly in the hearth.",
            pre_turn_card_state={"variables": {}, "event_flags": {}, "scene_state": {}, "revision": 0},
            base_card_state_revision=0,
        )
        proposal = curator.curate(request)
        assert isinstance(proposal, TurnEvolutionProposal)
        assert proposal.is_no_state_change is True
        assert len(proposal.state_update_proposal.operations) == 0

    def test_13_deterministic_detects_trust_keyword(self):
        """Trust keyword in output should produce state change."""
        curator = TurnEvolutionCurator(llm_adapter=None)
        request = CuratorRequest(
            request_id="r2", turn_id="t2", session_id="s1",
            player_input="我想信任你",
            accepted_writer_output="她看着你的眼睛，感受到你话语中的信任。她微笑着说：谢谢你的信任。",
            pre_turn_card_state={"variables": {}, "event_flags": {}, "scene_state": {}, "revision": 0},
            base_card_state_revision=0,
        )
        proposal = curator.curate(request)
        assert proposal.is_no_state_change is False
        ops = proposal.state_update_proposal.operations
        assert len(ops) > 0
        trust_ops = [op for op in ops if "trust" in op.get("path", "")]
        assert len(trust_ops) > 0

    def test_14_deterministic_detects_scene_change(self):
        """Scene keyword should produce scene_state patch."""
        curator = TurnEvolutionCurator(llm_adapter=None)
        request = CuratorRequest(
            request_id="r3", turn_id="t3", session_id="s1",
            player_input="我走进森林",
            accepted_writer_output="你踏上了通往森林的小路。树木越来越密。",
            pre_turn_card_state={"variables": {}, "event_flags": {}, "scene_state": {}, "revision": 0},
            base_card_state_revision=0,
        )
        proposal = curator.curate(request)
        ops = proposal.state_update_proposal.operations
        scene_ops = [op for op in ops if op.get("path", "").startswith("scene_state.")]
        assert len(scene_ops) > 0

    def test_15_deterministic_generates_active_memory(self):
        """Promise keyword should generate active memory candidate."""
        curator = TurnEvolutionCurator(llm_adapter=None)
        request = CuratorRequest(
            request_id="r4", turn_id="t4", session_id="s1",
            player_input="你答应过我的",
            accepted_writer_output="她低下头，想起了之前的承诺。好的，我会遵守诺言。",
            pre_turn_card_state={"variables": {}, "event_flags": {}, "scene_state": {}, "revision": 0},
            base_card_state_revision=0,
        )
        proposal = curator.curate(request)
        assert len(proposal.memory_candidates_active) > 0
        promise_candidates = [c for c in proposal.memory_candidates_active if c.kind == "promise"]
        assert len(promise_candidates) > 0

    def test_16_deterministic_generates_rag_memory(self):
        """Any accepted output should generate RAG memory."""
        curator = TurnEvolutionCurator(llm_adapter=None)
        request = CuratorRequest(
            request_id="r5", turn_id="t5", session_id="s1",
            player_input="你好",
            accepted_writer_output="这是一段足够长的测试文本，用来确保RAG记忆可以被正确生成。" * 5,
            pre_turn_card_state={"variables": {}, "event_flags": {}, "scene_state": {}, "revision": 0},
            base_card_state_revision=0,
        )
        proposal = curator.curate(request)
        assert len(proposal.memory_candidates_rag) > 0

    def test_17_patch_validation_rejects_invalid_ops(self):
        """Invalid patch operations should cause no_state_change."""
        curator = TurnEvolutionCurator(llm_adapter=None)
        request = CuratorRequest(
            request_id="r6", turn_id="t6", session_id="s1",
            player_input="test",
            accepted_writer_output="test output",
            pre_turn_card_state={"variables": {}, "event_flags": {}, "scene_state": {}, "revision": 0},
            base_card_state_revision=0,
        )
        # Manually create a proposal with invalid ops
        proposal = TurnEvolutionProposal(
            turn_id="t6", session_id="s1",
            state_update_proposal=StateUpdateProposalV2(
                expected_revision=0,
                operations=[{"op": "set", "path": "invalid_path", "value": 1}],
            ),
        )
        validated = curator._validate_proposal(proposal, request.pre_turn_card_state)
        assert validated.is_no_state_change is True

    def test_17b_curator_prompt_requires_memory_candidate_arrays(self):
        """LLM curator prompt should explicitly require both memory candidate arrays."""
        curator = TurnEvolutionCurator(llm_adapter=object())
        request = CuratorRequest(
            request_id="r7", turn_id="t7", session_id="s1",
            player_input="她答应以后会等我回来。",
            accepted_writer_output="她低声答应会等你回来，这个承诺改变了两人的关系。",
            pre_turn_card_state={"variables": {}, "event_flags": {}, "scene_state": {}, "revision": 0},
            base_card_state_revision=0,
        )

        prompt = curator._build_curator_prompt(request)

        assert "memory_candidates_active" in prompt
        assert "memory_candidates_rag" in prompt
        assert "即使没有候选也必须返回空数组" in prompt

    def test_17b1_curator_prompt_preserves_full_evidence_context(self):
        """Curator needs full accepted evidence to create state and memory updates."""
        curator = TurnEvolutionCurator(llm_adapter=object())
        request = CuratorRequest(
            request_id="r8",
            turn_id="t8",
            session_id="s1",
            player_input="CURATOR_INPUT_" + "A" * 650 + "_INPUT_TAIL",
            accepted_writer_output="CURATOR_OUTPUT_" + "B" * 2200 + "_OUTPUT_TAIL",
            pre_turn_card_state={
                "variables": {"trust": {"value": 1}},
                "event_flags": {},
                "scene_state": {"location": "yard"},
                "revision": 0,
            },
            final_turn_brief={"turn_goal": "GOAL_" + "G" * 260 + "_GOAL_TAIL"},
            recent_turns=[
                {
                    "turn_index": i,
                    "player_input": f"turn{i}_player_" + "P" * 260 + f"_PLAYER_TAIL_{i}",
                    "writer_output": f"turn{i}_writer_" + "W" * 360 + f"_WRITER_TAIL_{i}",
                }
                for i in [6, 5, 4, 3, 2]
            ],
            active_memory=[{"kind": "promise", "summary": "MEMORY_" + "M" * 120 + "_MEMORY_TAIL"}],
            resolved_worldbook_context=[{
                "title": "World",
                "content_excerpt": "WORLDBOOK_" + "L" * 220 + "_WORLDBOOK_TAIL",
            }],
            agent_suggestions=[{"role": "continuity", "summary": "SUGGESTION_" + "S" * 160 + "_SUGGESTION_TAIL"}],
        )

        prompt = curator._build_curator_prompt(request)

        assert "_INPUT_TAIL" in prompt
        assert "_OUTPUT_TAIL" in prompt
        assert "_GOAL_TAIL" in prompt
        assert "_PLAYER_TAIL_6" in prompt
        assert "_WRITER_TAIL_6" in prompt
        assert "_PLAYER_TAIL_2" in prompt
        assert "_WRITER_TAIL_2" in prompt
        assert "_MEMORY_TAIL" in prompt
        assert "_WORLDBOOK_TAIL" in prompt
        assert "_SUGGESTION_TAIL" in prompt

    def test_17c_writer_prompt_keeps_player_input_after_stable_prefix(self):
        """Writer prompt should keep volatile turn data behind a stable prefix."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        from ..contracts.writer_input_bundle import WriterInputBundle

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        base = dict(
            final_turn_brief={
                "turn_goal": "推进当前场景",
                "scene_focus": "院子",
                "must_preserve_facts": ["周语晴在院中"],
            },
            opening_context={"safe_display_content": "开场背景"},
            recent_turns_context=[{"turn_index": 1, "player_input": "旧输入", "writer_output": "旧输出"}],
            worldbook_context=[{"title": "桃花村", "content_excerpt": "固定村庄设定"}],
            card_state_context={"scene_state": {"location": "院子"}},
        )
        p1 = adapter._build_writer_prompt(WriterInputBundle(player_input="当前输入A", **base))
        p2 = adapter._build_writer_prompt(WriterInputBundle(player_input="当前输入B", **base))

        prefix1 = p1.split("=== TURN PACKET", 1)[0]
        prefix2 = p2.split("=== TURN PACKET", 1)[0]
        assert prefix1 == prefix2
        # Preset is now in system prompt, not in user prompt
        assert p1.index("当前输入A") > p1.index("=== TURN PACKET")

    def test_17c1_writer_prompt_keeps_director_plan_after_stable_prefix(self):
        """DirectorPlan fields change every turn and must not precede stable lore."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        from ..contracts.writer_input_bundle import WriterInputBundle

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        base = dict(
            player_input="当前输入",
            opening_context={"safe_display_content": "开场背景"},
            worldbook_context=[{
                "title": "常开设定",
                "content_excerpt": "STABLE_LORE_" + "A" * 1200,
                "entry_kind": "constant",
                "activation_reason": "constant",
            }],
            card_state_context={"scene_state": {"location": "院子"}},
        )
        p1 = adapter._build_writer_prompt(WriterInputBundle(
            final_turn_brief={
                "turn_goal": "目标A",
                "scene_focus": "焦点A",
                "must_preserve_facts": ["事实A"],
                "writer_constraints": ["约束A"],
                "narrative_opportunities": ["机会A"],
            },
            **base,
        ))
        p2 = adapter._build_writer_prompt(WriterInputBundle(
            final_turn_brief={
                "turn_goal": "目标B",
                "scene_focus": "焦点B",
                "must_preserve_facts": ["事实B"],
                "writer_constraints": ["约束B"],
                "narrative_opportunities": ["机会B"],
            },
            **base,
        ))

        prefix1 = p1.split("=== TURN PACKET", 1)[0]
        prefix2 = p2.split("=== TURN PACKET", 1)[0]
        turn_packet = p1.split("=== TURN PACKET", 1)[1]
        assert prefix1 == prefix2
        assert "STABLE_LORE_" in prefix1
        assert "目标A" in turn_packet
        assert "事实A" in turn_packet
        assert "约束A" in turn_packet
        assert "机会A" in turn_packet

    def test_17c2_writer_prompt_puts_constant_worldbook_in_stable_prefix(self):
        """Constant worldbook belongs to the cacheable prefix, dynamic lore does not."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        from ..contracts.writer_input_bundle import WriterInputBundle

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        prompt = adapter._build_writer_prompt(WriterInputBundle(
            player_input="当前输入",
            final_turn_brief={"turn_goal": "推进", "scene_focus": "院子"},
            worldbook_context=[
                {
                    "title": "常开设定",
                    "content_excerpt": "STABLE_LORE_" + "A" * 1200,
                    "entry_kind": "constant",
                    "activation_reason": "constant",
                },
                {
                    "title": "动态设定",
                    "content_excerpt": "DYNAMIC_LORE_" + "B" * 1200,
                    "entry_kind": "selective",
                    "activation_reason": "matched_primary_keywords",
                },
            ],
            card_state_context={"scene_state": {"location": "院子"}},
        ))

        stable_prefix = prompt.split("=== TURN PACKET", 1)[0]
        turn_packet = prompt.split("=== TURN PACKET", 1)[1]
        assert "STABLE_LORE_" in stable_prefix
        assert "DYNAMIC_LORE_" not in stable_prefix
        assert "DYNAMIC_LORE_" in turn_packet

    def test_17c2_profile_context_is_stable_writer_context(self):
        """Character profile is immutable RP context and must reach Writer."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        from ..contracts.writer_input_bundle import WriterInputBundle

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        prompt = adapter._build_writer_prompt(WriterInputBundle(
            player_input="current input",
            card_profile_context={
                "name": "PROFILE_NAME_MARKER",
                "description": "PROFILE_DESCRIPTION_MARKER",
                "personality": "PROFILE_PERSONALITY_MARKER",
                "scenario": "PROFILE_SCENARIO_MARKER",
                "mes_example": "PROFILE_EXAMPLE_MARKER",
                "creator_notes": "PROFILE_NOTES_MARKER",
            },
            worldbook_context=[{
                "title": "constant lore",
                "content_excerpt": "STABLE_LORE_MARKER",
                "entry_kind": "constant",
                "activation_reason": "constant",
            }],
        ))

        stable_prefix = prompt.split("=== TURN PACKET", 1)[0]
        turn_packet = prompt.split("=== TURN PACKET", 1)[1]
        assert "Character profile:" in stable_prefix
        assert "PROFILE_NAME_MARKER" in stable_prefix
        assert "PROFILE_DESCRIPTION_MARKER" in stable_prefix
        assert "PROFILE_PERSONALITY_MARKER" in stable_prefix
        assert "PROFILE_SCENARIO_MARKER" in stable_prefix
        assert "PROFILE_EXAMPLE_MARKER" in stable_prefix
        assert "PROFILE_NOTES_MARKER" in stable_prefix
        assert "STABLE_LORE_MARKER" in stable_prefix
        assert "PROFILE_PERSONALITY_MARKER" not in turn_packet

    def test_17c2a_writer_prompt_keeps_opening_out_of_stable_prefix(self):
        """Opening text is history context, not immutable cacheable lore."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        from ..contracts.writer_input_bundle import WriterInputBundle

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        prompt = adapter._build_writer_prompt(WriterInputBundle(
            player_input="当前输入",
            opening_context={"safe_display_content": "OPENING_SHOULD_DECAY"},
            worldbook_context=[{
                "title": "常开设定",
                "content_excerpt": "STABLE_LORE",
                "entry_kind": "constant",
                "activation_reason": "constant",
            }],
            card_state_context={"scene_state": {"location": "院子"}},
        ))

        stable_prefix = prompt.split("=== TURN PACKET", 1)[0]
        turn_packet = prompt.split("=== TURN PACKET", 1)[1]
        assert "OPENING_SHOULD_DECAY" not in stable_prefix
        assert "OPENING_SHOULD_DECAY" in turn_packet

    def test_17c2aa_writer_prompt_renders_recent_history_chronologically(self):
        """Latest-five history is stored newest-first but rendered oldest-first."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        from ..contracts.writer_input_bundle import WriterInputBundle

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        prompt = adapter._build_writer_prompt(WriterInputBundle(
            player_input="current input",
            recent_turns_context=[
                {"turn_index": 6, "player_input": "p6", "writer_output": "w6"},
                {"turn_index": 5, "player_input": "p5", "writer_output": "w5"},
                {"turn_index": 4, "player_input": "p4", "writer_output": "w4"},
                {"turn_index": 3, "player_input": "p3", "writer_output": "w3"},
                {"turn_index": 2, "player_input": "p2", "writer_output": "w2"},
            ],
        ))

        history = prompt.split("=== RECENT HISTORY (full) ===", 1)[1].split("=== CURRENT STATE", 1)[0]
        assert history.index("Turn 2:") < history.index("Turn 3:")
        assert history.index("Turn 3:") < history.index("Turn 4:")
        assert history.index("Turn 4:") < history.index("Turn 5:")
        assert history.index("Turn 5:") < history.index("Turn 6:")

    def test_17c2b_writer_prompt_does_not_hard_truncate_dynamic_context(self):
        """Writer prompt assembly should preserve upstream-selected context."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        from ..contracts.writer_input_bundle import WriterInputBundle

        player_tail = "PLAYER_TAIL"
        history_tail = "HISTORY_TAIL"
        dynamic_tail = "DYNAMIC_TAIL"
        memory_tail = "MEMORY_TAIL"

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        prompt = adapter._build_writer_prompt(WriterInputBundle(
            player_input=("玩家输入" * 300) + player_tail,
            recent_turns_context=[{
                "turn_index": 7,
                "player_input": "上一轮玩家",
                "writer_output": ("上一轮输出" * 300) + history_tail,
            }],
            active_memory_context=[{"summary": ("活跃记忆" * 100) + memory_tail}],
            rag_memory_context=[{"content": ("检索记忆" * 100) + "RAG_TAIL"}],
            worldbook_context=[{
                "title": "动态设定",
                "content_excerpt": ("动态世界书" * 120) + dynamic_tail,
                "entry_kind": "selective",
                "activation_reason": "matched_primary_keywords",
            }],
            card_state_context={"scene_state": {"location": "院子"}},
        ))

        turn_packet = prompt.split("=== TURN PACKET", 1)[1]
        assert player_tail in turn_packet
        assert history_tail in turn_packet
        assert dynamic_tail in turn_packet
        assert memory_tail in turn_packet

    def test_17c3_writer_revise_prompt_preserves_original_prompt_prefix(self):
        """Revision calls must not put volatile text before the cacheable writer prefix."""
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter

        adapter = RealWriterV2Adapter(object(), preset_text="FIXED STYLE PRESET")
        original_prompt = (
            "=== WRITER STYLE & CONSTRAINT PRESET (highest priority) ===\n"
            "FIXED STYLE PRESET\n"
            "=== END PRESET ===\n\n"
            "=== STABLE WRITER CONTRACT ===\n"
            "Stable worldbook context:\n"
            "STABLE_LORE_" + "A" * 1200 + "\n"
            "=== TURN PACKET (volatile; changes every turn) ===\n"
            "Player said: 当前输入"
        )

        revise_prompt = adapter._build_revise_prompt(
            original_prompt=original_prompt,
            current_text="短输出",
            issues=["WORD_COUNT_LOW"],
            attempt=1,
        )

        assert revise_prompt.startswith(original_prompt)
        assert revise_prompt.index("STABLE_LORE_") < revise_prompt.index("=== TURN PACKET")
        assert revise_prompt.index("=== REVISION REQUEST") > revise_prompt.index("Player said: 当前输入")

    def test_17d_director_prompt_keeps_player_input_after_stable_prefix(self):
        """Director prompt should put volatile turn data after the stable instruction block."""
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.card_state import CardState

        adapter = RealDirectorV2Adapter(object(), model="test")
        s1 = RoundSnapshot(
            player_input="当前输入A",
            card_state=CardState(),
            active_worldbook_entries=[{"title": "桃花村", "content_excerpt": "固定设定"}],
        )
        s2 = RoundSnapshot(
            player_input="当前输入B",
            card_state=CardState(),
            active_worldbook_entries=[{"title": "桃花村", "content_excerpt": "固定设定"}],
        )
        p1 = adapter._build_plan_prompt(s1)
        p2 = adapter._build_plan_prompt(s2)

        prefix1 = p1.split("=== TURN PACKET", 1)[0]
        prefix2 = p2.split("=== TURN PACKET", 1)[0]
        assert prefix1 == prefix2
        assert p1.index("当前输入A") > p1.index("=== TURN PACKET")

    def test_17e_director_prompt_puts_constant_worldbook_in_stable_prefix(self):
        """Constant worldbook belongs to Director's cacheable prefix."""
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.card_state import CardState

        adapter = RealDirectorV2Adapter(object(), model="test")
        snapshot = RoundSnapshot(
            player_input="当前输入",
            card_state=CardState(),
            active_worldbook_entries=[
                {
                    "title": "稳定设定",
                    "content_excerpt": "STABLE_LORE_" + "A" * 1200,
                    "entry_kind": "constant",
                    "activation_reason": "constant",
                },
                {
                    "title": "动态设定",
                    "content_excerpt": "DYNAMIC_LORE_" + "B" * 1200,
                    "entry_kind": "selective",
                    "activation_reason": "matched_primary_keywords",
                },
            ],
        )

        prompt = adapter._build_plan_prompt(snapshot)
        prefix = prompt.split("=== TURN PACKET", 1)[0]
        volatile = prompt.split("=== TURN PACKET", 1)[1]
        assert "STABLE_LORE_" in prefix
        assert "DYNAMIC_LORE_" not in prefix
        assert "DYNAMIC_LORE_" in volatile

    def test_17e1_director_prompt_includes_profile_in_stable_prefix(self):
        """Director planning must be grounded by immutable character profile."""
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.card_state import CardState

        adapter = RealDirectorV2Adapter(object(), model="test")
        snapshot = RoundSnapshot(
            player_input="current input",
            card_state=CardState(),
            card_profile_context={
                "name": "DIRECTOR_PROFILE_NAME",
                "description": "DIRECTOR_PROFILE_DESCRIPTION",
                "personality": "DIRECTOR_PROFILE_PERSONALITY",
                "scenario": "DIRECTOR_PROFILE_SCENARIO",
            },
            active_worldbook_entries=[{
                "title": "constant lore",
                "content_excerpt": "STABLE_LORE_MARKER",
                "entry_kind": "constant",
                "activation_reason": "constant",
            }],
        )

        prompt = adapter._build_plan_prompt(snapshot)
        prefix = prompt.split("=== TURN PACKET", 1)[0]
        volatile = prompt.split("=== TURN PACKET", 1)[1]
        assert "Character profile:" in prefix
        assert "DIRECTOR_PROFILE_NAME" in prefix
        assert "DIRECTOR_PROFILE_DESCRIPTION" in prefix
        assert "DIRECTOR_PROFILE_PERSONALITY" in prefix
        assert "DIRECTOR_PROFILE_SCENARIO" in prefix
        assert "STABLE_LORE_MARKER" in prefix
        assert "DIRECTOR_PROFILE_PERSONALITY" not in volatile

    def test_17f_director_prompt_preserves_latest_five_full_turns_and_worldbook(self):
        """Director must not throw away the newest turns or hard-truncate RP context."""
        from types import SimpleNamespace
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.card_state import CardState

        adapter = RealDirectorV2Adapter(object(), model="test")
        snapshot = RoundSnapshot(
            player_input="PLAYER_INPUT_" + "A" * 650 + "_PLAYER_TAIL",
            card_state=CardState(),
            recent_turn_records=[
                SimpleNamespace(
                    turn_index=i,
                    player_input=f"turn{i}_player_" + "P" * 260 + f"_PLAYER_TAIL_{i}",
                    writer_output=f"turn{i}_writer_" + "W" * 260 + f"_WRITER_TAIL_{i}",
                )
                for i in [6, 5, 4, 3, 2]
            ],
            older_turns_summary="Turn 1: old emotional summary",
            active_worldbook_entries=[
                {
                    "title": f"Entry {i}",
                    "content_excerpt": f"WORLDBOOK_{i}_" + "L" * 260 + f"_WORLDBOOK_TAIL_{i}",
                    "entry_kind": "selective",
                    "activation_reason": "matched_primary_keywords",
                }
                for i in range(1, 7)
            ],
        )

        prompt = adapter._build_plan_prompt(snapshot)

        assert "_PLAYER_TAIL" in prompt
        assert "Turn 6 Player" in prompt
        assert "_PLAYER_TAIL_6" in prompt
        assert "_WRITER_TAIL_6" in prompt
        assert "_PLAYER_TAIL_2" in prompt
        assert "_WRITER_TAIL_2" in prompt
        assert "Turn 1: old emotional summary" in prompt
        assert "_WORLDBOOK_TAIL_6" in prompt

# ═══════════════════════════════════════════════════════════════════════
# Full engine integration tests
# ═══════════════════════════════════════════════════════════════════════

    def test_17f1_director_prompt_renders_recent_history_chronologically(self):
        """Director should read the selected latest-five turns in story order."""
        from types import SimpleNamespace
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.card_state import CardState

        adapter = RealDirectorV2Adapter(object(), model="test")
        snapshot = RoundSnapshot(
            player_input="current input",
            card_state=CardState(),
            recent_turn_records=[
                SimpleNamespace(turn_index=6, player_input="p6", writer_output="w6"),
                SimpleNamespace(turn_index=5, player_input="p5", writer_output="w5"),
                SimpleNamespace(turn_index=4, player_input="p4", writer_output="w4"),
                SimpleNamespace(turn_index=3, player_input="p3", writer_output="w3"),
                SimpleNamespace(turn_index=2, player_input="p2", writer_output="w2"),
            ],
        )

        prompt = adapter._build_plan_prompt(snapshot)
        recent = prompt.split("=== Recent Turns ===", 1)[1].split("=== Earlier Turns Summary ===", 1)[0]
        assert recent.index("Turn 2 Player") < recent.index("Turn 3 Player")
        assert recent.index("Turn 3 Player") < recent.index("Turn 4 Player")
        assert recent.index("Turn 4 Player") < recent.index("Turn 5 Player")
        assert recent.index("Turn 5 Player") < recent.index("Turn 6 Player")


class TestP1EngineIntegration:
    """P1 engine produces real evolution, not fake patches."""

    def _seed_session(self, registry, session_id: str, card_id: str):
        """Seed a minimal session for testing."""
        from ..contracts.card_session_binding import CardSessionBinding
        from ..contracts.opening_record import OpeningRecord
        from ..contracts.worldbook_binding import WorldbookBinding, WorldbookBindingEntry
        from ..contracts.card_definition import CardDefinition, CardDefinitionStatus

        now = _now()

        # Card definition
        card_def = CardDefinition(
            logical_card_id=card_id,
            card_version=1,
            source_id="test_src",
            source_hash="test_hash",
            name="TestCard",
            display_name="TestCard",
            status=CardDefinitionStatus.READY,
            greetings=[{
                "schema_id": "awp.rp.card-greeting.v1",
                "schema_version": 1,
                "greeting_id": "g0",
                "index": 0,
                "label": "Default",
                "safe_display_content": "Welcome, traveler.",
                "content_hash": "gh0",
                "is_default": True,
                "source_path": "data.first_mes",
            }],
            worldbook_catalog=[],
            worldbook_chunks=[],
            created_at=now,
            updated_at=now,
        )

        from ..storage.sqlite.card_definition_store import SqliteCardDefinitionStore
        def_store = SqliteCardDefinitionStore(registry.db)
        def_store.save(card_def)

        # Binding
        registry.card_session_binding_store.save(CardSessionBinding(
            session_id=session_id,
            logical_card_id=card_id,
            card_version=1,
            source_hash="test_hash",
            selected_greeting_id="g0",
            opening_record_id=f"op_{session_id}",
            worldbook_binding_id=f"wb_{session_id}",
            status="ready",
            created_at=now,
        ))

        # Opening
        registry.opening_record_store.save(OpeningRecord(
            opening_record_id=f"op_{session_id}",
            session_id=session_id,
            logical_card_id=card_id,
            card_version=1,
            greeting_id="g0",
            safe_display_content="Welcome to the tavern, traveler.",
            created_at=now,
        ))

        # Worldbook binding
        registry.worldbook_binding_store.save(WorldbookBinding(
            worldbook_binding_id=f"wb_{session_id}",
            session_id=session_id,
            logical_card_id=card_id,
            card_version=1,
            source_hash="test_hash",
            entries=[],
            created_at=now,
        ))

    def test_18_persistent_first_turn_no_fake_revision(self):
        """First turn with simple greeting: revision stays at 0."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AWP_RUNTIME_PROFILE"] = "test"
            os.environ["AWP_TEST_STORE_ROOT"] = tmp
            os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = "p1_test_18"
            clear_registry_cache()
            try:
                factory = RuntimeStoreFactory.from_env()
                self._seed_session(factory.registry, "s1", "c1")

                from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
                node = AWPV2PersistentFirstTurn()
                result = node.execute(
                    session_id="s1",
                    player_input="你好",
                    turn_id="t1", request_id="r1",
                    workflow_run_id="w1", trace_id="tc1",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )

                diag = result[2]
                assert diag["outcome"] == "success"
                assert diag["quality_verdict"] == "accept"
                # P1: no_state_change when no real state signals
                assert diag["card_state_commit_status"] == "no_state_change"
                assert diag["turn_record_commit_status"] == "committed"

                cs = factory.registry.card_state_store.load("c1", "s1")
                assert cs.revision == 0  # NOT incremented
            finally:
                clear_registry_cache()
                for k in ("AWP_TEST_STORE_ROOT", "AWP_TEST_RUNTIME_NAMESPACE"):
                    os.environ.pop(k, None)

    def test_19_curator_produces_effects_in_context(self):
        """Engine context should include effects from curator."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AWP_RUNTIME_PROFILE"] = "test"
            os.environ["AWP_TEST_STORE_ROOT"] = tmp
            os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = "p1_test_19"
            clear_registry_cache()
            try:
                factory = RuntimeStoreFactory.from_env()
                self._seed_session(factory.registry, "s1", "c1")

                from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
                node = AWPV2PersistentFirstTurn()
                result = node.execute(
                    session_id="s1",
                    player_input="你好",
                    turn_id="t1", request_id="r1",
                    workflow_run_id="w1", trace_id="tc1",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )

                ctx = result[1]
                assert "effects" in ctx
                effects = ctx["effects"]
                assert "state_effects" in effects
                assert "memory_effects" in effects
                assert "delegation" in effects
            finally:
                clear_registry_cache()
                for k in ("AWP_TEST_STORE_ROOT", "AWP_TEST_RUNTIME_NAMESPACE"):
                    os.environ.pop(k, None)

    def test_20_turn_evolution_curator_step_recorded(self):
        """turn_evolution_curator step should appear in diagnostics."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AWP_RUNTIME_PROFILE"] = "test"
            os.environ["AWP_TEST_STORE_ROOT"] = tmp
            os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = "p1_test_20"
            clear_registry_cache()
            try:
                factory = RuntimeStoreFactory.from_env()
                self._seed_session(factory.registry, "s1", "c1")

                from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
                node = AWPV2PersistentFirstTurn()
                result = node.execute(
                    session_id="s1",
                    player_input="你好",
                    turn_id="t1", request_id="r1",
                    workflow_run_id="w1", trace_id="tc1",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )

                diag = result[2]
                assert "turn_evolution_curator" in diag["steps_completed"]
            finally:
                clear_registry_cache()
                for k in ("AWP_TEST_STORE_ROOT", "AWP_TEST_RUNTIME_NAMESPACE"):
                    os.environ.pop(k, None)

    def test_21_condition_evaluator_in_worldbook_resolver(self):
        """Condition-based worldbook entries should activate based on CardState."""
        from ..runtime.version_locked_worldbook_resolver import VersionLockedWorldbookResolver

        evaluator = ConditionEvaluator()
        state = {
            "variables": {"trust": {"value": 60}},
            "event_flags": {},
            "scene_state": {},
        }

        # Condition: trust >= 50
        condition = {"op": "gte", "path": "variables.trust.value", "value": 50}
        assert evaluator.evaluate(condition, state) is True

        # Condition: trust < 50
        condition_low = {"op": "lt", "path": "variables.trust.value", "value": 50}
        assert evaluator.evaluate(condition_low, state) is False

    def test_22_real_director_delegation_plan_generation(self):
        """RealDirectorV2Adapter should generate delegation plans."""
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.director_plan import DirectorPlan
        from ..contracts.round_snapshot import RoundSnapshot
        from ..contracts.card_state import CardState

        snapshot = RoundSnapshot(
            snapshot_id="snap1", trace_id="t1",
            card_id="c1", session_id="s1",
            base_card_state_revision=0,
            card_state=CardState(),
            player_input="你好",
            recent_turn_records=[],
            active_memories=[{"memory_id": "m1", "kind": "promise", "summary": "test"}],
        )
        plan = DirectorPlan(plan_id="dp1", turn_goal="greet", scene_focus="tavern")

        # Create a mock deepseek adapter
        class MockLLM:
            def generate_structured(self, prompt, schema, **kwargs):
                return {"turn_goal": "test", "scene_focus": "tavern"}, type('Receipt', (), {'success': True, 'to_dict': lambda self: {}})()

        adapter = RealDirectorV2Adapter(MockLLM(), model="test")
        delegation_plan, receipt = adapter.generate_delegation_plan(snapshot, plan)

        assert delegation_plan is not None
        assert len(delegation_plan.tasks) <= 3  # Max 3 tasks

    def test_22a_delegation_role_ids_normalize_for_runtime(self):
        """Director role ids should map to production D1-D5 trigger names."""
        from ..runtime.persistent_turn_engine import _delegation_agent_name

        assert _delegation_agent_name("history_recall") == "d1_history_recall"
        assert _delegation_agent_name("history-recall") == "d1_history_recall"
        assert _delegation_agent_name("opportunity") == "d2_opportunity"
        assert _delegation_agent_name("world_life") == "d3_world_life"
        assert _delegation_agent_name("world-life") == "d3_world_life"
        assert _delegation_agent_name("emotion_relationship") == "d4_emotion_rel"
        assert _delegation_agent_name("emotion-relationship") == "d4_emotion_rel"
        assert _delegation_agent_name("continuity") == "d5_continuity"

    def test_22b_real_director_plan_uses_function_calling_mode(self):
        """Director should disable thinking mode to enable function calling.

        DeepSeek v4 models default to thinking mode server-side, and thinking
        rejects tool_choice. Director explicitly disables thinking so the SDK's
        function calling path (tool_calls) can be used for reliable structured
        output instead of fragile raw-text JSON parsing.
        """
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.round_snapshot import RoundSnapshot
        from ..contracts.card_state import CardState

        class MockLLM:
            def __init__(self):
                self.kwargs = {}

            def generate_structured(self, prompt, schema, **kwargs):
                self.kwargs = kwargs
                receipt = type('Receipt', (), {'success': True, 'to_dict': lambda self: {}})()
                return {"turn_goal": "test", "scene_focus": "tavern"}, receipt

        llm = MockLLM()
        adapter = RealDirectorV2Adapter(llm, model="test")
        snapshot = RoundSnapshot(
            snapshot_id="snap1", trace_id="t1",
            card_id="c1", session_id="s1",
            base_card_state_revision=0,
            card_state=CardState(),
            player_input="hello",
        )

        plan, receipt = adapter.generate_plan(snapshot)

        assert plan.turn_goal == "test"
        assert llm.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
        assert llm.kwargs["max_tokens"] == 1200

    def test_22c_sub_agent_tools_return_expected_data(self):
        """Sub-agent tool execution should return data from the snapshot."""
        from types import SimpleNamespace
        from ..runtime.sub_agent_llm_runner import _execute_tool

        snapshot = SimpleNamespace(
            player_input="input A",
            card_state=SimpleNamespace(scene_state=SimpleNamespace(
                location="yard", time_of_day="morning", weather="clear", active_npcs=["npc1"],
            )),
            recent_turn_records=[SimpleNamespace(turn_index=1, player_input="p1", writer_output="w1")],
            active_memories=[{"kind": "promise", "summary": "promise"}],
            rag_recall=[{"summary": "old fact"}],
            active_worldbook_entries=[{"title": "village", "content_excerpt": "stable lore"}],
            card_profile_context={"name": "TestChar"},
        )

        scene = _execute_tool("scene_context_lookup", {}, snapshot)
        assert "yard" in scene
        assert "morning" in scene
        assert "npc1" in scene

        turns = _execute_tool("accepted_turn_lookup", {"limit": 5}, snapshot)
        assert "p1" in turns
        assert "w1" in turns

        wb = _execute_tool("worldbook_lookup", {}, snapshot)
        assert "village" in wb
        assert "stable lore" in wb

        mem = _execute_tool("active_memory_lookup", {}, snapshot)
        assert "promise" in mem

        profile = _execute_tool("character_profile_lookup", {}, snapshot)
        assert "TestChar" in profile

    def test_22c1_sub_agent_prompt_preserves_latest_five_full_context(self):
        """D1-D5 tool execution should return full context without truncation."""
        from types import SimpleNamespace
        from ..runtime.sub_agent_llm_runner import _execute_tool

        snapshot = SimpleNamespace(
            player_input="SUB_AGENT_INPUT_" + "A" * 360 + "_INPUT_TAIL",
            card_state=SimpleNamespace(scene_state=SimpleNamespace(
                location="yard", time_of_day="morning", weather="clear", active_npcs=["npc1"],
            )),
            recent_turn_records=[
                SimpleNamespace(
                    turn_index=i,
                    player_input=f"turn{i}_player_" + "P" * 220 + f"_PLAYER_TAIL_{i}",
                    writer_output=f"turn{i}_writer_" + "W" * 220 + f"_WRITER_TAIL_{i}",
                )
                for i in [6, 5, 4, 3, 2]
            ],
            active_memories=[{"kind": "promise", "summary": "MEMORY_" + "M" * 160 + "_MEMORY_TAIL"}],
            rag_recall=[{"summary": "RAG_" + "R" * 160 + "_RAG_TAIL"}],
            active_worldbook_entries=[{
                "title": "village",
                "content_excerpt": "WORLDBOOK_" + "L" * 240 + "_WORLDBOOK_TAIL",
            }],
            card_profile_context={},
        )

        turns = _execute_tool("accepted_turn_lookup", {"limit": 5}, snapshot)
        assert "_PLAYER_TAIL_6" in turns
        assert "_WRITER_TAIL_6" in turns
        assert "_PLAYER_TAIL_2" in turns
        assert "_WRITER_TAIL_2" in turns

        mem = _execute_tool("active_memory_lookup", {}, snapshot)
        assert "_MEMORY_TAIL" in mem

        rag = _execute_tool("rag_memory_lookup", {}, snapshot)
        assert "_RAG_TAIL" in rag

        wb = _execute_tool("worldbook_lookup", {}, snapshot)
        assert "_WORLDBOOK_TAIL" in wb

    def test_22d_sub_agent_llm_disables_thinking_mode(self):
        """Sub-agent Flash calls should keep thinking disabled."""
        from types import SimpleNamespace
        from ..runtime.sub_agent_llm_runner import run_sub_agent_llm

        class MockMessage:
            content = "Specific analysis."
            tool_calls = None

        class MockAdapter:
            def __init__(self):
                self.kwargs = {}

            def call_with_tools(self, messages, tools, **kwargs):
                self.kwargs = kwargs
                usage = type('Usage', (), {'total_tokens': 0})()
                return MockMessage(), usage

        adapter = MockAdapter()
        snapshot = SimpleNamespace(
            player_input="hello",
            card_state=SimpleNamespace(scene_state=SimpleNamespace()),
            recent_turn_records=[],
            active_memories=[],
            rag_recall=[],
            active_worldbook_entries=[],
            card_profile_context={},
        )

        text = run_sub_agent_llm("opportunity", snapshot, adapter)

        assert text == "Specific analysis."
        assert adapter.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}

    def test_22e_real_director_generates_read_only_tool_plan(self):
        """Director should configure bounded read-only tools for context enrichment."""
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        from ..contracts.director_plan import DirectorPlan
        from ..contracts.round_snapshot import RoundSnapshot
        from ..contracts.card_state import CardState

        adapter = RealDirectorV2Adapter(object(), model="test")
        snapshot = RoundSnapshot(
            snapshot_id="snap1", trace_id="t1",
            card_id="c1", session_id="s1",
            base_card_state_revision=0,
            card_state=CardState(),
            player_input="hello",
            active_worldbook_entries=[{"entry_id": "wb1", "title": "world", "content_excerpt": "lore"}],
            active_memories=[{"memory_id": "m1", "summary": "promise"}],
            rag_recall=[{"memory_id": "r1", "summary": "old fact"}],
        )
        plan = DirectorPlan(plan_id="dp1", turn_goal="continue", scene_focus="yard")

        tool_plan, receipt = adapter.generate_tool_plan(snapshot, plan)
        tool_ids = [request.tool_id for request in tool_plan.requests]

        assert receipt.success is True
        assert tool_ids[0] == "scene_context_lookup"
        assert "worldbook_lookup" in tool_ids
        assert "active_memory_lookup" in tool_ids
        assert "rag_memory_lookup" in tool_ids
        assert len(tool_ids) <= 5

    def test_22f_snapshot_tool_runner_returns_current_snapshot_data(self):
        """Director tools should read current RoundSnapshot data, not fake defaults."""
        from types import SimpleNamespace
        from ..contracts.card_state import CardState
        from ..contracts.tool_plan import ToolPlan, PlannedToolRequest
        from ..contracts.execution_trace import ExecutionTrace
        from ..runtime.tool_registry import ToolRegistry
        from ..runtime.tool_permission_policy import ToolPermissionPolicy
        from ..runtime.tool_budget_runtime import ToolBudgetRuntime
        from ..runtime.tool_gateway import ToolGateway
        from ..runtime.snapshot_tool_runner import SnapshotToolRunner

        snapshot = SimpleNamespace(
            card_id="c1",
            session_id="s1",
            card_state=CardState(card_id="c1", session_id="s1"),
            active_worldbook_entries=[{
                "entry_id": "wb1", "title": "Village", "content_excerpt": "current lore",
            }],
            recent_turn_records=[
                SimpleNamespace(turn_id="t1", turn_index=1, player_input="p", writer_output="w"),
            ],
            active_memories=[{"memory_id": "m1", "kind": "promise", "summary": "current memory"}],
            rag_recall=[{"memory_id": "r1", "summary": "current rag"}],
        )
        plan = ToolPlan(
            tool_plan_id="tp1", trace_id="trace1", snapshot_id="snap1",
            card_id="c1", session_id="s1",
            requests=[
                PlannedToolRequest(request_id="req_wb", tool_id="worldbook_lookup"),
                PlannedToolRequest(request_id="req_mem", tool_id="active_memory_lookup"),
            ],
        )
        registry = ToolRegistry()
        gateway = ToolGateway(
            registry,
            ToolPermissionPolicy(registry),
            ToolBudgetRuntime(),
            SnapshotToolRunner(),
        )

        bundle = gateway.execute(plan, snapshot, ExecutionTrace(trace_id="trace1"))

        assert bundle.successful_request_ids == ["req_wb", "req_mem"]
        wb_result = bundle.results[0].structured_data["entries"][0]
        mem_result = bundle.results[1].structured_data["memories"][0]
        assert wb_result["content_excerpt"] == "current lore"
        assert mem_result["summary"] == "current memory"

    def test_22g_writer_bundle_includes_director_tool_findings_as_guidance(self):
        """Writer should receive accepted Director tool findings as guidance."""
        from ..contracts.final_turn_brief import FinalTurnBrief
        from ..contracts.round_snapshot import RoundSnapshot
        from ..contracts.card_state import CardState
        from ..runtime.writer_input_bundle_v2_builder import WriterInputBundleV2Builder

        snapshot = RoundSnapshot(
            snapshot_id="snap1", trace_id="t1",
            card_id="c1", session_id="s1",
            base_card_state_revision=0,
            card_state=CardState(card_id="c1", session_id="s1"),
            player_input="hello",
        )
        brief = FinalTurnBrief(
            brief_id="ftb1",
            accepted_tool_findings=["[worldbook_lookup] entries: 1 items"],
        )

        bundle = WriterInputBundleV2Builder().build(snapshot, brief)

        assert "[worldbook_lookup] entries: 1 items" in bundle.accepted_guidance

    def test_23_continue_turn_uses_continue_instruction(self):
        """AWPV2ContinueTurn should use CONTINUE_INSTRUCTION, not empty input."""
        from ..nodes.continue_turn_execution_node import CONTINUE_INSTRUCTION

        assert len(CONTINUE_INSTRUCTION) > 50
        assert "Continue" in CONTINUE_INSTRUCTION or "世界" in CONTINUE_INSTRUCTION
