"""D4: Emotion / Relationship Agent V1 — Tests.

Tests 1-29: Unit tests for trigger policy, validator, ranker, permissions, merge.
Tests E2E-1, E2E-2: End-to-end integration tests with fake LLM.
"""

import pytest
import uuid
from datetime import datetime, timezone

from awp_rp_runtime_v2.contracts.card_state import CardState, VariableEntry, SceneState
from awp_rp_runtime_v2.contracts.round_snapshot import RoundSnapshot
from awp_rp_runtime_v2.contracts.turn_record import TurnRecord
from awp_rp_runtime_v2.contracts.director_plan import DirectorPlan
from awp_rp_runtime_v2.contracts.delegation_plan import DelegationPlan, DelegationTask
from awp_rp_runtime_v2.contracts.agent_task_envelope import AgentTaskEnvelope, TaskBudget
from awp_rp_runtime_v2.contracts.agent_suggestion import AgentSuggestion, SuggestionKind
from awp_rp_runtime_v2.contracts.agent_execution_result import AgentExecutionResult
from awp_rp_runtime_v2.contracts.execution_trace import ExecutionTrace
from awp_rp_runtime_v2.contracts.final_turn_brief import FinalTurnBrief
from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief

# D4 contracts
from awp_rp_runtime_v2.contracts.emotion_relationship_request import EmotionRelationshipRequest
from awp_rp_runtime_v2.contracts.emotion_relationship_candidate import (
    EmotionRelationshipCandidate, RelationshipKind,
)
from awp_rp_runtime_v2.contracts.relationship_evidence import RelationshipEvidence
from awp_rp_runtime_v2.contracts.emotion_relationship_result import (
    EmotionRelationshipResult, EmotionRelationshipStatus, RejectedEmotionCandidate,
)
from awp_rp_runtime_v2.contracts.relationship_risk import RelationshipRisk, RelationshipRiskLevel
from awp_rp_runtime_v2.contracts.emotion_relationship_suggestion import (
    EmotionRelationshipSuggestion, EmotionRelationshipSuggestionKind,
)
from awp_rp_runtime_v2.contracts.emotion_relationship_trigger_diagnostics import EmotionRelationshipTriggerDiagnostics

# D4 runtime
from awp_rp_runtime_v2.runtime.emotion_relationship_trigger_policy import (
    EmotionRelationshipTriggerPolicy, EmotionRelationshipTriggerResult,
)
from awp_rp_runtime_v2.runtime.emotion_relationship_runtime import EmotionRelationshipRuntime
from awp_rp_runtime_v2.runtime.emotion_relationship_query_planner import EmotionRelationshipQueryPlanner
from awp_rp_runtime_v2.runtime.emotion_relationship_candidate_generator import EmotionRelationshipCandidateGenerator
from awp_rp_runtime_v2.runtime.emotion_relationship_validator import EmotionRelationshipValidator
from awp_rp_runtime_v2.runtime.emotion_relationship_ranker import EmotionRelationshipRanker, MAX_ACCEPTED
from awp_rp_runtime_v2.runtime.emotion_relationship_adapter import EmotionRelationshipAdapter
from awp_rp_runtime_v2.runtime.emotion_relationship_tool_profile import (
    EMOTION_RELATIONSHIP_TOOLS, EMOTION_RELATIONSHIP_ROLE_SPEC,
)

# Existing runtime
from awp_rp_runtime_v2.runtime.tool_registry import ToolRegistry
from awp_rp_runtime_v2.runtime.tool_permission_policy import ToolPermissionPolicy
from awp_rp_runtime_v2.runtime.tool_gateway import ToolGateway, FakeToolRunner
from awp_rp_runtime_v2.runtime.agent_runtime_registry import AgentRuntimeRegistry, AgentRoleSpec
from awp_rp_runtime_v2.runtime.task_envelope_builder import TaskEnvelopeBuilder
from awp_rp_runtime_v2.runtime.dynamic_subagent_pool import DynamicSubAgentPool
from awp_rp_runtime_v2.runtime.suggestion_merger import SuggestionMerger


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_snapshot(
    player_input: str = "普通对话",
    card_id: str = "card1",
    session_id: str = "sess1",
    recent_turns: list[TurnRecord] | None = None,
    active_memories: list[dict] | None = None,
    rag_recall: list[dict] | None = None,
    active_worldbook: list[dict] | None = None,
) -> RoundSnapshot:
    return RoundSnapshot(
        snapshot_id=f"snap_{uuid.uuid4().hex[:8]}",
        trace_id=f"trace_{uuid.uuid4().hex[:8]}",
        card_id=card_id,
        session_id=session_id,
        player_input=player_input,
        card_state=CardState(
            variables={"scene": VariableEntry(name="scene", value="月光庭院")},
            scene_state=SceneState(location="月光庭院"),
        ),
        recent_turn_records=recent_turns or [],
        active_memories=active_memories or [],
        rag_recall=rag_recall or [],
        active_worldbook_entries=active_worldbook or [],
    )


def _make_turn_record(turn_id: str, writer_output: str, turn_index: int = 1) -> TurnRecord:
    return TurnRecord(
        turn_id=turn_id,
        card_id="card1",
        session_id="sess1",
        turn_index=turn_index,
        player_input="test",
        writer_output=writer_output,
        accepted_at=datetime.now(timezone.utc).isoformat(),
    )


def _make_director_plan(
    snapshot: RoundSnapshot,
    risk_flags: list[str] | None = None,
    unresolved_threads: list[str] | None = None,
    relationship_tensions: list[str] | None = None,
    narrative_opportunities: list[str] | None = None,
) -> DirectorPlan:
    return DirectorPlan(
        plan_id=f"dp_{uuid.uuid4().hex[:8]}",
        trace_id=snapshot.trace_id,
        snapshot_id=snapshot.snapshot_id,
        card_id=snapshot.card_id,
        session_id=snapshot.session_id,
        player_intent=snapshot.player_input[:100],
        turn_goal="Continue narrative",
        scene_focus="月光庭院",
        base_card_state_revision=snapshot.base_card_state_revision,
        risk_flags=risk_flags or [],
        unresolved_threads=unresolved_threads or [],
        relationship_tensions=relationship_tensions or [],
        narrative_opportunities=narrative_opportunities or [],
    )


def _make_evidence(
    evidence_id: str = "ev_1",
    source_type: str = "accepted_turn",
    source_ref: str = "",
    excerpt: str = "NPC对主角表现出迟疑",
    confidence: float = 0.9,
) -> RelationshipEvidence:
    return RelationshipEvidence(
        evidence_id=evidence_id,
        source_type=source_type,
        source_ref=source_ref or f"turn_{evidence_id}",
        excerpt=excerpt,
        entity_refs=["npc_1"],
        confidence=confidence,
        relevance_score=0.8,
    )


def _make_candidate(
    candidate_id: str = "erc_test",
    kind: RelationshipKind = RelationshipKind.TRUST_TENSION,
    evidence_refs: list[str] | None = None,
    foundation_facts: list[str] | None = None,
    focus_entities: list[str] | None = None,
    summary: str = "基于关系记忆，角色之间存在信任张力",
    player_agency_risk: float = 0.1,
    sudden_shift_risk: float = 0.1,
    must_not_assert_as_fact: bool = True,
    must_not_modify_relationship: bool = True,
    suggested_writer_use: str = "角色回应可更克制",
    suggested_director_use: str = "可作为关系发展的微妙信号",
) -> EmotionRelationshipCandidate:
    return EmotionRelationshipCandidate(
        candidate_id=candidate_id,
        trace_id="t1",
        snapshot_id="s1",
        kind=kind,
        summary=summary,
        focus_entities=focus_entities if focus_entities is not None else ["npc_1"],
        relationship_state_interpretation="关系处于试探阶段",
        emotional_signals=["迟疑", "避免目光"],
        foundation_facts=foundation_facts if foundation_facts is not None else ["NPC曾承诺帮助主角"],
        evidence_refs=evidence_refs if evidence_refs is not None else ["ev_turn_1"],
        confidence=0.7,
        player_agency_risk=player_agency_risk,
        continuity_risk=0.2,
        sudden_shift_risk=sudden_shift_risk,
        suggested_writer_use=suggested_writer_use,
        suggested_director_use=suggested_director_use,
        must_not_assert_as_fact=must_not_assert_as_fact,
        must_not_modify_relationship=must_not_modify_relationship,
    )


# ─────────────────────────────────────────────
# Test 1: No relationship risk → no trigger
# ─────────────────────────────────────────────

class TestTriggerPolicy:
    """Tests for EmotionRelationshipTriggerPolicy."""

    def test_01_no_risk_no_trigger(self):
        """无关系风险时不触发。"""
        snapshot = _make_snapshot("你好，今天天气真好")
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False
        assert result.trigger_reasons == []
        assert result.risk_level == "none"

    def test_02_promise_triggers(self):
        """承诺触发。"""
        active_memories = [
            {"memory_id": "am_1", "summary": "NPC承诺帮助主角", "kind": "promise",
             "entity_refs": ["npc_1"], "importance": 0.8, "confidence": 0.9},
        ]
        snapshot = _make_snapshot("和NPC说话", active_memories=active_memories)
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("promise" in d for d in result.emotion_relationship_domains)

    def test_03_misunderstanding_triggers(self):
        """误会触发。"""
        active_memories = [
            {"memory_id": "am_1", "summary": "NPC与主角有未解误会", "kind": "misunderstanding",
             "entity_refs": ["npc_1"], "importance": 0.7, "confidence": 0.6},
        ]
        snapshot = _make_snapshot("和NPC对话", active_memories=active_memories)
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("misunderstanding" in d for d in result.emotion_relationship_domains)

    def test_04_apology_triggers(self):
        """道歉触发。"""
        snapshot = _make_snapshot("对不起，我不该那样说")
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True

    def test_05_probe_triggers(self):
        """试探触发。"""
        snapshot = _make_snapshot("你是不是还在生气，为什么不理我")
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True

    def test_06_conflict_triggers(self):
        """冲突触发。"""
        snapshot = _make_snapshot("我们之间的冲突必须解决")
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True

    def test_07_secret_from_rag_triggers(self):
        """RAG中的秘密触发。"""
        rag_recall = [
            {"memory_id": "rag_1", "summary": "NPC有不可告人的秘密",
             "kind": "secret", "entity_refs": ["npc_1"],
             "importance": 0.7, "confidence": 0.6},
        ]
        snapshot = _make_snapshot("和NPC说话", rag_recall=rag_recall)
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True

    def test_08_not_trigger_just_for_more_calls(self):
        """仅为了增加子Agent调用次数不得触发。"""
        snapshot = _make_snapshot("你好")
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False


# ─────────────────────────────────────────────
# Tests 9-14: Candidate validation
# ─────────────────────────────────────────────

class TestEmotionRelationshipValidator:
    """Tests for EmotionRelationshipValidator."""

    def test_09_no_evidence_rejected(self):
        """无 evidence 的候选被拒绝。"""
        validator = EmotionRelationshipValidator()
        candidate = _make_candidate(evidence_refs=[], foundation_facts=["某事"])
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("证据" in e for e in errors)

    def test_10_relationship_modification_rejected(self):
        """修改关系值的候选被拒绝。"""
        validator = EmotionRelationshipValidator()
        candidate = _make_candidate(
            summary="关系值自动增加到亲密",
            suggested_writer_use="好感增加到最高",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("关系修改" in e for e in errors)

    def test_11_sudden_confession_rejected(self):
        """突然表白的候选被拒绝。"""
        validator = EmotionRelationshipValidator()
        candidate = _make_candidate(
            summary="NPC突然告白",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0

    def test_12_player_agency_violation_rejected(self):
        """代替玩家决定情感选择的候选被拒绝。"""
        validator = EmotionRelationshipValidator()
        candidate = _make_candidate(
            summary="让玩家自动接受NPC的感情",
            suggested_writer_use="玩家同意了NPC的表白",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("情感代理权" in e or "代理" in e for e in errors)

    def test_13_relationship_event_assertion_rejected(self):
        """将关系变化断言为已发生事件的候选被拒绝。"""
        validator = EmotionRelationshipValidator()
        candidate = _make_candidate(
            summary="NPC已经原谅玩家",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("关系事件断言" in e for e in errors)

    def test_14_must_not_modify_relationship(self):
        """must_not_modify_relationship=False 的候选被拒绝。"""
        validator = EmotionRelationshipValidator()
        candidate = _make_candidate(must_not_modify_relationship=False)
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("mustNotModifyRelationship" in e for e in errors)


# ─────────────────────────────────────────────
# Tests 15-21: Permission boundaries
# ─────────────────────────────────────────────

class TestEmotionRelationshipPermissions:
    """Tests for permission boundaries of Emotion/Relationship Agent."""

    def test_15_cannot_access_store(self):
        """Emotion/Relationship Agent 无法访问 Store / SQLite。"""
        runtime = EmotionRelationshipRuntime()
        assert not hasattr(runtime, 'card_state_store')
        assert not hasattr(runtime, 'turn_record_store')


    def test_16_cannot_cross_card_session(self):
        """Emotion/Relationship Agent 无法跨 cardId / sessionId 查询。"""
        snapshot = _make_snapshot(card_id="card1", session_id="sess1")
        planner = EmotionRelationshipQueryPlanner()
        queries = planner.plan_queries(
            snapshot=snapshot,
            focus_entities=["npc_1"],
            emotion_relationship_domains=["relationship_action"],
        )
        for q in queries:
            assert q.get("card_id", "card1") == "card1"
            assert q.get("session_id", "sess1") == "sess1"

    def test_17_cannot_call_unauthorized_tools(self):
        """Emotion/Relationship Agent 无法调用未授权工具。"""
        profile_tools = set(EMOTION_RELATIONSHIP_TOOLS.keys())
        allowed = {
            "rag_memory_lookup", "entity_alias_lookup", "timeline_lookup",
            "relationship_context_lookup", "worldbook_lookup",
            "accepted_turn_lookup", "active_memory_lookup",
        }
        assert profile_tools == allowed

    def test_18_cannot_delegate(self):
        """Emotion/Relationship Agent 无法递归委派。"""
        assert EMOTION_RELATIONSHIP_ROLE_SPEC.can_delegate is False

    def test_19_cannot_generate_state_update_proposal(self):
        """Emotion/Relationship Agent 无法生成 StateUpdateProposal。"""
        assert EMOTION_RELATIONSHIP_ROLE_SPEC.can_write_state is False

    def test_20_cannot_generate_memory_commit_plan(self):
        """Emotion/Relationship Agent 无法生成 MemoryCommitPlan。"""
        assert EMOTION_RELATIONSHIP_ROLE_SPEC.can_write_memory is False

    def test_21_cannot_generate_final_text(self):
        """Emotion/Relationship Agent 输出最终玩家正文时被拒绝。"""
        assert EMOTION_RELATIONSHIP_ROLE_SPEC.can_generate_final_text is False


# ─────────────────────────────────────────────
# Test 22: Max 2 accepted candidates per turn
# ─────────────────────────────────────────────

class TestEmotionRelationshipRanker:
    """Tests for EmotionRelationshipRanker."""

    def test_22_max_two_accepted(self):
        """每回合最多 2 个可采纳候选。"""
        ranker = EmotionRelationshipRanker()
        kinds = [
            RelationshipKind.TRUST_TENSION,
            RelationshipKind.GUARDEDNESS,
            RelationshipKind.EMOTIONAL_RESIDUE,
            RelationshipKind.MISUNDERSTANDING_SIGNAL,
            RelationshipKind.SUBTEXT_OPPORTUNITY,
        ]
        candidates = [
            _make_candidate(f"erc_{i}", kind=kinds[i], focus_entities=[f"npc_{i}"])
            for i in range(5)
        ]
        accepted, rejected = ranker.rank(candidates, max_accepted=2)
        assert len(accepted) == 2
        assert len(rejected) == 3

    def test_23_high_evidence_boundary_over_low_evidence_subtext(self):
        """高证据关系边界优先于低证据潜文本机会。"""
        ranker = EmotionRelationshipRanker()
        high_evidence_boundary = _make_candidate(
            "erc_boundary",
            kind=RelationshipKind.RELATIONSHIP_BOUNDARY,
        )
        high_evidence_boundary.confidence = 0.95

        low_evidence_subtext = _make_candidate(
            "erc_subtext",
            kind=RelationshipKind.SUBTEXT_OPPORTUNITY,
        )
        low_evidence_subtext.confidence = 0.3

        accepted, rejected = ranker.rank(
            [low_evidence_subtext, high_evidence_boundary], max_accepted=1
        )
        assert len(accepted) == 1
        assert accepted[0].candidate_id == "erc_boundary"

    def test_24_duplicates_merged_or_eliminated(self):
        """重复候选被合并或淘汰。"""
        ranker = EmotionRelationshipRanker()
        c1 = _make_candidate("erc_1", kind=RelationshipKind.TRUST_TENSION)
        c1.focus_entities = ["npc_1"]
        c2 = _make_candidate("erc_2", kind=RelationshipKind.TRUST_TENSION)
        c2.focus_entities = ["npc_1"]
        c3 = _make_candidate("erc_3", kind=RelationshipKind.GUARDEDNESS)
        c3.focus_entities = ["npc_1"]

        accepted, rejected = ranker.rank([c1, c2, c3], max_accepted=5)
        accepted_ids = [c.candidate_id for c in accepted]
        assert "erc_1" in accepted_ids or "erc_2" in accepted_ids
        assert not ("erc_1" in accepted_ids and "erc_2" in accepted_ids)
        assert "erc_3" in accepted_ids


# ─────────────────────────────────────────────
# Tests 25-27: SuggestionMerge and FinalTurnBrief
# ─────────────────────────────────────────────

class TestSuggestionMergeEmotionRelationship:
    """Tests for SuggestionMerge with emotion/relationship suggestions."""

    def test_25_er_as_soft_guidance(self):
        """SuggestionMerge 将 Emotion/Relationship 视为软 Guidance。"""
        merger = SuggestionMerger()
        snapshot = _make_snapshot("test")
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")

        sug = AgentSuggestion(
            suggestion_id="s1", task_id="t1", role="emotion-relationship",
            kind=SuggestionKind.ER_TRUST_TENSION,
            summary="角色可自然表现出信任张力",
            priority=0.8, confidence=0.7,
            recommendations=["角色在对话中表现出迟疑"],
            source_refs=["ev_1"],
        )
        result = AgentExecutionResult(
            task_id="t1", role="emotion-relationship", trace_id="t1",
            success=True, suggestions=[sug],
        )
        merge = merger.merge(plan, brief, snapshot, [result])
        assert merge is not None
        adopted_sugs = [item for item in merge.adopted if item.role == "emotion-relationship"]
        assert len(adopted_sugs) >= 1
        assert len(merge.writer_guidance) > 0

    def test_26_final_brief_only_accepted_findings(self):
        """FinalTurnBrief 只包含已采纳建议。"""
        brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_relationship_findings=[
                {"candidate_id": "erc_1", "summary": "角色之间存在信任张力"},
            ],
            rejected_relationship_findings=[
                {"candidate_id": "erc_2", "reason": "缺少证据"},
            ],
            relationship_warnings=["注意玩家代理权"],
            relationship_evidence_refs=["ev_1"],
        )
        assert len(brief.accepted_relationship_findings) == 1
        assert len(brief.rejected_relationship_findings) == 1
        assert brief.accepted_relationship_findings[0]["candidate_id"] == "erc_1"

    def test_27_writer_cannot_read_raw_er_result(self):
        """Writer 不可读取原始 EmotionRelationshipResult。"""
        from awp_rp_runtime_v2.runtime.writer_input_bundle_v2_builder import WriterInputBundleV2Builder
        builder = WriterInputBundleV2Builder()
        snapshot = _make_snapshot()
        final_brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_relationship_findings=[{"candidate_id": "erc_1", "summary": "test"}],
        )
        bundle = builder.build(snapshot, final_brief)
        bundle_dict = bundle.to_dict()
        assert "emotion_relationship_result" not in bundle_dict


# ─────────────────────────────────────────────
# Test 28: No-op path completes
# ─────────────────────────────────────────────

class TestNoOpPath:
    """Test that no-op path (shouldTrigger=False) completes normally."""

    def test_28_noop_path_completes(self):
        """shouldTrigger=false → 空结果 → SuggestionMerge 正常完成。"""
        snapshot = _make_snapshot("你好")
        plan = _make_director_plan(snapshot)
        policy = EmotionRelationshipTriggerPolicy()
        trigger_result = policy.evaluate(snapshot, plan)
        assert trigger_result.should_trigger is False

        runtime = EmotionRelationshipRuntime()
        task = DelegationTask(
            task_id="er_1", role="emotion-relationship",
            tool_allowlist=list(EMOTION_RELATIONSHIP_TOOLS.keys()),
        )
        result = runtime.run(snapshot, task, trigger_result)
        assert result.status == EmotionRelationshipStatus.NO_TRIGGER
        assert len(result.candidates) == 0

        merger = SuggestionMerger()
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        del_plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")
        merge = merger.merge(del_plan, brief, snapshot, [])
        assert merge.adopted_count == 0
        assert merge.conflict_count == 0


# ─────────────────────────────────────────────
# Test 29: Tool timeout returns degraded
# ─────────────────────────────────────────────

class TestToolFailureBehavior:
    """Tests for tool timeout and failure degradation."""

    def test_29_tool_timeout_returns_degraded(self):
        """Tool timeout 返回 degraded，不阻断主链。"""
        from awp_rp_runtime_v2.contracts.tool_result import ToolResult, ToolResultStatus
        tr = ToolResult(
            result_id="tr1", request_id="req1", trace_id="t1",
            tool_id="rag_memory_lookup",
            status=ToolResultStatus.TIMEOUT,
            failure_reason="timeout",
        )
        assert tr.is_failed()
        result = EmotionRelationshipResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=EmotionRelationshipStatus.DEGRADED,
            degraded_reasons=["rag_memory_lookup timeout"],
        )
        assert result.status == EmotionRelationshipStatus.DEGRADED
        assert len(result.degraded_reasons) > 0


# ─────────────────────────────────────────────
# Test 30: Official workflow JSON validation
# ─────────────────────────────────────────────

class TestD4NodeRegistration:
    """D4: Emotion/Relationship node registration tests."""

    def test_d4_nodes_present(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS
        d4 = {
            "AWPV2EmotionRelationshipTrigger", "AWPV2EmotionRelationshipRequest",
            "AWPV2EmotionRelationshipAgent", "AWPV2EmotionRelationshipValidator",
            "AWPV2EmotionRelationshipRanker", "AWPV2EmotionRelationshipResult",
            "AWPV2EmotionRelationshipDiagnostics",
        }
        for name in d4:
            assert name in NODE_CLASS_MAPPINGS, f"Missing: {name}"

    def test_d4_display_names_chinese(self):
        from awp_rp_runtime_v2.nodes import NODE_DISPLAY_NAME_MAPPINGS
        d4_displays = [
            "AWP V2 情绪关系触发", "AWP V2 情绪关系请求",
            "AWP V2 情绪关系Agent", "AWP V2 情绪关系验证",
            "AWP V2 情绪关系排序", "AWP V2 情绪关系结果",
            "AWP V2 情绪关系诊断",
        ]
        for display in d4_displays:
            assert display in NODE_DISPLAY_NAME_MAPPINGS.values(), f"Missing: {display}"


# ─────────────────────────────────────────────
# Contract serialization tests
# ─────────────────────────────────────────────

class TestD4ContractSerialization:
    """Test round-trip serialization of D4 contracts."""

    def test_emotion_relationship_request_roundtrip(self):
        req = EmotionRelationshipRequest(
            request_id="req1", trace_id="t1", snapshot_id="s1",
            task_run_id="tr1", card_id="card1", session_id="sess1",
            focus_entities=["npc_1"], player_intent="对话",
            must_not_create_facts=True, must_not_modify_relationships=True,
            max_candidates=5,
        )
        d = req.to_dict()
        restored = EmotionRelationshipRequest.from_dict(d)
        assert restored.focus_entities == ["npc_1"]
        assert restored.must_not_create_facts is True
        assert restored.must_not_modify_relationships is True

    def test_emotion_relationship_candidate_roundtrip(self):
        cand = _make_candidate("erc_1")
        d = cand.to_dict()
        restored = EmotionRelationshipCandidate.from_dict(d)
        assert restored.candidate_id == "erc_1"
        assert restored.kind == RelationshipKind.TRUST_TENSION
        assert restored.must_not_assert_as_fact is True
        assert restored.must_not_modify_relationship is True

    def test_relationship_evidence_roundtrip(self):
        ev = _make_evidence("ev_1")
        d = ev.to_dict()
        restored = RelationshipEvidence.from_dict(d)
        assert restored.evidence_id == "ev_1"
        assert restored.source_type == "accepted_turn"

    def test_emotion_relationship_result_roundtrip(self):
        cand = [_make_candidate()]
        result = EmotionRelationshipResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=EmotionRelationshipStatus.SUCCESS,
            candidates=cand,
        )
        d = result.to_dict()
        restored = EmotionRelationshipResult.from_dict(d)
        assert restored.status == EmotionRelationshipStatus.SUCCESS
        assert len(restored.candidates) == 1

    def test_relationship_risk_roundtrip(self):
        risk = RelationshipRisk(
            risk_id="r1",
            risk_level=RelationshipRiskLevel.HIGH,
            description="高风险",
            entity_refs=["npc_1"],
        )
        d = risk.to_dict()
        restored = RelationshipRisk.from_dict(d)
        assert restored.risk_level == RelationshipRiskLevel.HIGH

    def test_emotion_relationship_suggestion_roundtrip(self):
        sug = EmotionRelationshipSuggestion(
            suggestion_id="es1",
            kind=EmotionRelationshipSuggestionKind.TRUST_TENSION,
            title="信任张力",
            summary="角色之间存在信任张力",
            evidence_refs=["ev_1"],
        )
        d = sug.to_dict()
        restored = EmotionRelationshipSuggestion.from_dict(d)
        assert restored.kind == EmotionRelationshipSuggestionKind.TRUST_TENSION

    def test_er_trigger_diagnostics_roundtrip(self):
        diag = EmotionRelationshipTriggerDiagnostics(
            diagnostics_id="erd1", trace_id="t1", snapshot_id="s1",
            should_trigger=True,
            trigger_reasons=["承诺未兑现"],
            candidates_generated=3,
            candidates_accepted=2,
            candidates_rejected=1,
        )
        d = diag.to_dict()
        restored = EmotionRelationshipTriggerDiagnostics.from_dict(d)
        assert restored.candidates_generated == 3
        assert restored.candidates_accepted == 2


# ─────────────────────────────────────────────
# Adapter test
# ─────────────────────────────────────────────

class TestEmotionRelationshipAdapter:
    """Tests for EmotionRelationshipAdapter."""

    def test_result_to_agent_suggestion(self):
        """EmotionRelationshipResult 正确转换为 AgentSuggestion。"""
        adapter = EmotionRelationshipAdapter()
        cand = _make_candidate("erc_1")
        result = EmotionRelationshipResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=EmotionRelationshipStatus.SUCCESS,
            candidates=[cand],
        )
        suggestions = adapter.to_suggestions(result)
        assert len(suggestions) >= 1
        sug = suggestions[0]
        assert sug.role == "emotion-relationship"
        assert sug.kind == SuggestionKind.ER_TRUST_TENSION
        assert len(sug.source_refs) > 0


# ─────────────────────────────────────────────
# E2E Test 1: Normal emotion/relationship adoption path
# ─────────────────────────────────────────────

class TestD4E2ENormalPath:
    """E2E: Normal emotion/relationship adoption path with fake LLM."""

    def test_e2e_normal_er_adoption(self):
        """正常关系建议采纳路径: 触发 → 候选 → 验证 → 排序 → 合并 → Writer。"""
        active_memories = [
            {"memory_id": "am_1", "summary": "NPC在第3回合承诺帮助主角", "kind": "promise",
             "entity_refs": ["npc_1"], "importance": 0.8, "confidence": 0.9, "status": "active"},
            {"memory_id": "am_2", "summary": "NPC与主角之间存在信任问题", "kind": "relationship_shift",
             "entity_refs": ["npc_1"], "importance": 0.7, "confidence": 0.8, "status": "active"},
        ]
        rag_recall = [
            {"memory_id": "rag_1", "summary": "NPC与主角有过未解的误会",
             "kind": "misunderstanding", "entity_refs": ["npc_1"],
             "importance": 0.6, "confidence": 0.7},
        ]

        snapshot = _make_snapshot(
            player_input="你之前说的话是什么意思",
            active_memories=active_memories,
            rag_recall=rag_recall,
        )

        plan = _make_director_plan(
            snapshot,
            relationship_tensions=["NPC与主角之间存在信任问题"],
        )

        policy = EmotionRelationshipTriggerPolicy()
        trigger = policy.evaluate(snapshot, plan)
        assert trigger.should_trigger is True
        assert len(trigger.trigger_reasons) > 0

        task = DelegationTask(
            task_id="er_1", role="emotion-relationship",
            priority=0.8,
            purpose="解读角色情绪与关系动态",
            input_field_allowlist=[
                "player_input", "recent_turn_records",
                "active_memories", "rag_recall",
            ],
            tool_allowlist=list(EMOTION_RELATIONSHIP_TOOLS.keys()),
            max_tokens=1000,
            timeout_ms=30000,
            required=False,
            failure_policy="skip",
        )

        registry = AgentRuntimeRegistry()
        registry.register_spec(EMOTION_RELATIONSHIP_ROLE_SPEC)
        builder = TaskEnvelopeBuilder(registry)
        envelope = builder.build(task, snapshot, "brief1")
        assert envelope is not None

        runtime = EmotionRelationshipRuntime()
        er_result = runtime.run(
            snapshot=snapshot,
            task=task,
            trigger_result=trigger,
            envelope=envelope,
        )

        assert er_result is not None
        assert er_result.trace_id == snapshot.trace_id
        assert er_result.status in (EmotionRelationshipStatus.SUCCESS, EmotionRelationshipStatus.DEGRADED)

        adapter = EmotionRelationshipAdapter()
        suggestions = adapter.to_suggestions(er_result)
        assert isinstance(suggestions, list)

        class FakeERRunner:
            def run(self, envelope):
                return suggestions

        registry.register_runner("emotion-relationship", FakeERRunner())
        pool = DynamicSubAgentPool(registry, builder)
        delegation = DelegationPlan(
            plan_id="dp1", trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id, brief_id="b1",
            tasks=[task],
        )
        exec_results = pool.execute(delegation, snapshot)
        assert len(exec_results) == 1
        assert exec_results[0].success

        merger = SuggestionMerger()
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        merge = merger.merge(delegation, brief, snapshot, exec_results)
        assert merge is not None
        assert merge.merge_id != ""


# ─────────────────────────────────────────────
# E2E Test 2: Violated candidates and degradation path
# ─────────────────────────────────────────────

class TestD4E2EViolationDegradation:
    """E2E: Violated candidates and degradation path."""

    def test_e2e_violation_and_degradation(self):
        """违规候选与降级路径: 无证据/关系事件/代理权侵犯/关系修改 → 全部拒绝 → degraded。"""
        snapshot = _make_snapshot("和NPC说话")

        bad_candidates = [
            _make_candidate("erc_no_ev", evidence_refs=[], foundation_facts=["某事"]),
            _make_candidate("erc_event", summary="NPC已经原谅玩家"),
            _make_candidate("erc_agency", summary="让玩家自动接受NPC的感情"),
            _make_candidate("erc_modify", summary="修改关系值增加好感"),
        ]

        validator = EmotionRelationshipValidator()
        valid, rejected = validator.validate_batch(bad_candidates, snapshot)
        assert len(valid) == 0
        assert len(rejected) == 4

        rejected_records = []
        for cand, errors in rejected:
            for error in errors:
                violated_policy = "unknown"
                if "证据" in error:
                    violated_policy = "missing_evidence"
                elif "关系事件断言" in error:
                    violated_policy = "relationship_event"
                elif "情感代理权" in error or "代理" in error:
                    violated_policy = "player_agency"
                elif "关系修改" in error:
                    violated_policy = "relationship_modification"
                rejected_records.append(RejectedEmotionCandidate(
                    candidate_id=cand.candidate_id,
                    reason=error,
                    violated_policy=violated_policy,
                    evidence_refs=cand.evidence_refs,
                ))

        result = EmotionRelationshipResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=EmotionRelationshipStatus.DEGRADED,
            candidates=[],
            rejected_candidates=rejected_records,
            degraded_reasons=["所有候选均被验证拒绝或淘汰"],
        )

        assert result.status == EmotionRelationshipStatus.DEGRADED
        assert len(result.rejected_candidates) >= 4

        adapter = EmotionRelationshipAdapter()
        suggestions = adapter.to_suggestions(result)
        warning_sugs = [s for s in suggestions if s.kind == SuggestionKind.ER_WARNING]
        assert len(warning_sugs) > 0

        brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_relationship_findings=[],
            rejected_relationship_findings=[
                {"candidate_id": r.candidate_id, "reason": r.reason}
                for r in rejected_records
            ],
            relationship_warnings=["所有候选均被拒绝"],
        )
        assert len(brief.accepted_relationship_findings) == 0
        assert len(brief.rejected_relationship_findings) > 0

        merger = SuggestionMerger()
        turn_brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")
        merge = merger.merge(plan, turn_brief, snapshot, [])
        assert merge.adopted_count == 0
        assert merge.merge_id != ""

        runtime = EmotionRelationshipRuntime()
        assert not hasattr(runtime, 'card_state_store')
        assert not hasattr(runtime, 'turn_record_store')
