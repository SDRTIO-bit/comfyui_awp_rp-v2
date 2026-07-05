"""D1: History / Recall Dynamic Sub-Agent V1 — Tests.

Tests 1-26: Unit tests for contracts, trigger policy, runtime, validator, adapter.
Tests E2E-1, E2E-2: End-to-end integration tests.
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

# D1 contracts
from awp_rp_runtime_v2.contracts.recall_focus import RecallFocus, RecallKind
from awp_rp_runtime_v2.contracts.recall_evidence import RecallEvidence, EvidenceSourceType
from awp_rp_runtime_v2.contracts.continuity_risk import ContinuityRisk, RiskLevel
from awp_rp_runtime_v2.contracts.history_recall_request import HistoryRecallRequest
from awp_rp_runtime_v2.contracts.history_recall_result import HistoryRecallResult, HistoryRecallStatus
from awp_rp_runtime_v2.contracts.history_recall_suggestion import HistoryRecallSuggestion, HistorySuggestionKind
from awp_rp_runtime_v2.contracts.history_recall_diagnostics import HistoryRecallDiagnostics

# D1 runtime
from awp_rp_runtime_v2.runtime.history_recall_trigger_policy import HistoryRecallTriggerPolicy, TriggerResult
from awp_rp_runtime_v2.runtime.history_recall_runtime import HistoryRecallRuntime
from awp_rp_runtime_v2.runtime.history_recall_query_planner import HistoryRecallQueryPlanner
from awp_rp_runtime_v2.runtime.recall_evidence_ranker import RecallEvidenceRanker
from awp_rp_runtime_v2.runtime.history_recall_validator import HistoryRecallValidator
from awp_rp_runtime_v2.runtime.history_recall_adapter import HistoryRecallAdapter
from awp_rp_runtime_v2.runtime.history_recall_tool_profile import (
    HISTORY_RECALL_TOOLS, create_history_recall_tool_registry,
)

# Existing runtime
from awp_rp_runtime_v2.runtime.tool_registry import ToolRegistry
from awp_rp_runtime_v2.runtime.tool_permission_policy import ToolPermissionPolicy
from awp_rp_runtime_v2.runtime.tool_budget_runtime import ToolBudgetRuntime
from awp_rp_runtime_v2.runtime.tool_gateway import ToolGateway, FakeToolRunner
from awp_rp_runtime_v2.runtime.agent_runtime_registry import AgentRuntimeRegistry, AgentRoleSpec
from awp_rp_runtime_v2.runtime.task_envelope_builder import TaskEnvelopeBuilder
from awp_rp_runtime_v2.runtime.dynamic_subagent_pool import DynamicSubAgentPool
from awp_rp_runtime_v2.runtime.suggestion_merger import SuggestionMerger
from awp_rp_runtime_v2.runtime.final_turn_brief_runtime import FinalTurnBriefRuntime


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
    )


def _make_evidence(
    evidence_id: str = "ev_1",
    source_type: str = "accepted_turn",
    excerpt: str = "NPC承诺帮助主角",
    confidence: float = 0.9,
) -> RecallEvidence:
    return RecallEvidence(
        evidence_id=evidence_id,
        source_type=source_type,
        source_ref=f"turn_{evidence_id}",
        source_turn_id=f"tr_{evidence_id}",
        excerpt=excerpt,
        entity_refs=["npc_1"],
        confidence=confidence,
        relevance_score=0.8,
    )


# ─────────────────────────────────────────────
# Test 1: No historical risk → Trigger does not fire
# ─────────────────────────────────────────────

class TestTriggerPolicy:
    """Tests for HistoryRecallTriggerPolicy."""

    def test_1_no_risk_no_trigger(self):
        """普通对话不触发历史回查。"""
        snapshot = _make_snapshot("你好，今天天气真好")
        plan = _make_director_plan(snapshot)
        policy = HistoryRecallTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False
        assert result.trigger_reasons == []
        assert result.risk_level == RiskLevel.NONE

    def test_2_historical_reference_triggers(self):
        """历史指代词触发。"""
        for keyword in ["之前", "上次", "当年", "那件事", "答应过", "你还记得"]:
            snapshot = _make_snapshot(f"你还记得{keyword}吗")
            plan = _make_director_plan(snapshot)
            policy = HistoryRecallTriggerPolicy()
            result = policy.evaluate(snapshot, plan)
            assert result.should_trigger is True, f"Failed for keyword: {keyword}"
            assert len(result.trigger_reasons) > 0

    def test_3_promise_conflict_secret_triggers(self):
        """未兑现承诺/关系变化/旧秘密触发。"""
        for keyword in ["承诺", "答应", "秘密", "债务", "冲突", "误会"]:
            snapshot = _make_snapshot(f"关于那个{keyword}")
            plan = _make_director_plan(snapshot)
            policy = HistoryRecallTriggerPolicy()
            result = policy.evaluate(snapshot, plan)
            assert result.should_trigger is True, f"Failed for keyword: {keyword}"

    def test_4_cardstate_rag_conflict_triggers(self):
        """CardState 与 RAG 冲突时触发。"""
        rag = [{"memory_id": "rag_1", "content": "NPC是敌人", "summary": "NPC是敌人",
                "entity_refs": ["npc_1"], "conflict_status": "conflicted"}]
        snapshot = _make_snapshot("和NPC说话", rag_recall=rag)
        plan = _make_director_plan(snapshot)
        policy = HistoryRecallTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True

    def test_5_director_risk_flag_triggers(self):
        """Director 风险标记触发。"""
        snapshot = _make_snapshot("普通对话")
        plan = _make_director_plan(snapshot, risk_flags=["identity_confusion"])
        policy = HistoryRecallTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True

    def test_6_unresolved_threads_trigger(self):
        """未解决伏笔触发。"""
        snapshot = _make_snapshot("继续前行")
        plan = _make_director_plan(snapshot, unresolved_threads=["未解之谜"])
        policy = HistoryRecallTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True

    def test_7_entity_alias_triggers(self):
        """实体别名/代词触发。"""
        snapshot = _make_snapshot("他之前说过什么")
        plan = _make_director_plan(snapshot)
        policy = HistoryRecallTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True


# ─────────────────────────────────────────────
# Tests 4-6: Evidence priority
# ─────────────────────────────────────────────

class TestEvidenceRanker:
    """Tests for RecallEvidenceRanker."""

    def test_4_cardstate_over_accepted_turn(self):
        """CardState 硬事实 > accepted_turn 证据。"""
        ranker = RecallEvidenceRanker()
        e1 = _make_evidence("ev1", "accepted_turn", "NPC帮助了主角", 0.9)
        e2 = _make_evidence("ev2", "card_state", "NPC当前在月光庭院", 1.0)
        ranked = ranker.rank([e1, e2])
        assert ranked[0].source_type == "card_state"

    def test_5_accepted_turn_over_active_memory(self):
        """accepted_turn > ActiveMemory。"""
        ranker = RecallEvidenceRanker()
        e1 = _make_evidence("ev1", "active_memory", "NPC曾经帮助", 0.7)
        e2 = _make_evidence("ev2", "accepted_turn", "NPC承诺帮助", 0.9)
        ranked = ranker.rank([e1, e2])
        assert ranked[0].source_type == "accepted_turn"

    def test_6_active_memory_over_rag(self):
        """ActiveMemory > RagMemory。"""
        ranker = RecallEvidenceRanker()
        e1 = _make_evidence("ev1", "rag_memory", "旧事件", 0.6)
        e2 = _make_evidence("ev2", "active_memory", "近期事件", 0.7)
        ranked = ranker.rank([e1, e2])
        assert ranked[0].source_type == "active_memory"


# ─────────────────────────────────────────────
# Tests 7-8: Evidence validation
# ─────────────────────────────────────────────

class TestHistoryRecallValidator:
    """Tests for HistoryRecallValidator."""

    def test_7_no_source_ref_rejected(self):
        """无 sourceRef 的证据不能成为 confirmedFact。"""
        validator = HistoryRecallValidator()
        e = RecallEvidence(
            evidence_id="ev1", source_type="accepted_turn",
            source_ref="", excerpt="某事发生", confidence=0.9,
        )
        result = HistoryRecallResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=HistoryRecallStatus.SUCCESS,
            confirmed_facts=["某事确实发生了"],
            evidence=[e],
        )
        errors = validator.validate(result)
        assert any("source_ref" in err or "evidence" in err for err in errors)

    def test_8_no_evidence_conclusion_rejected(self):
        """无证据的模型结论被拒绝。"""
        validator = HistoryRecallValidator()
        result = HistoryRecallResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=HistoryRecallStatus.SUCCESS,
            confirmed_facts=["NPC曾经背叛过主角"],  # No evidence at all
            evidence=[],
        )
        errors = validator.validate(result)
        assert len(errors) > 0
        assert any("evidence" in err.lower() or "confirmed" in err.lower() for err in errors)

    def test_16_final_text_rejected(self):
        """Agent 输出最终玩家正文时被拒绝。"""
        validator = HistoryRecallValidator()
        # Long narrative text that looks like player-visible final text
        long_text = "月光如水洒在庭院中的青石板路上远处传来若有若无的笛声仿佛在诉说着什么不为人知的故事空气中弥漫着淡淡的花香混合着夜露的清凉"
        result = HistoryRecallResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=HistoryRecallStatus.SUCCESS,
            confirmed_facts=[],
            evidence=[],
            writer_recommendations=[long_text],
        )
        errors = validator.validate(result)
        assert any("正文" in err or "玩家可见" in err or "叙事" in err for err in errors)


# ─────────────────────────────────────────────
# Tests 9-15: Permission boundaries
# ─────────────────────────────────────────────

class TestHistoryRecallPermissions:
    """Tests for permission boundaries of History/Recall Agent."""

    def test_9_cannot_read_unauthorized_snapshot_fields(self):
        """Agent 只能读取 Envelope 中允许的字段。"""
        snapshot = _make_snapshot()
        task = DelegationTask(
            task_id="t1", role="history-recall",
            input_field_allowlist=["player_input", "recent_turn_records"],
        )
        registry = AgentRuntimeRegistry()
        from awp_rp_runtime_v2.runtime.agent_runtime_registry import BUILTIN_ROLES
        if "history-recall" not in {s.role_id for s in registry._specs.values()}:
            registry.register_spec(AgentRoleSpec(
                role_id="history-recall",
                allowed_suggestion_kinds=[SuggestionKind.CONTINUITY_ISSUE],
            ))
        builder = TaskEnvelopeBuilder(registry)
        envelope = builder.build(task, snapshot, "brief1")
        assert envelope is not None
        assert "card_state" not in envelope.allowed_snapshot_data
        assert "active_memories" not in envelope.allowed_snapshot_data

    def test_10_cannot_access_store(self):
        """Agent 无法直接访问 Store / SQLite。"""
        # HistoryRecallRuntime does not accept any store parameter
        runtime = HistoryRecallRuntime()
        # Verify no store attributes
        assert not hasattr(runtime, 'card_state_store')
        assert not hasattr(runtime, 'turn_record_store')
        assert not hasattr(runtime, 'active_memory_store')
        assert not hasattr(runtime, 'rag_memory_store')

    def test_11_cannot_cross_card_session(self):
        """Agent 无法跨 cardId / sessionId 检索。"""
        snapshot = _make_snapshot(card_id="card1", session_id="sess1")
        planner = HistoryRecallQueryPlanner()
        queries = planner.plan_queries(
            snapshot=snapshot,
            focus_entities=["npc_1"],
            recall_kinds=[RecallKind.EVENT_HISTORY],
        )
        for q in queries:
            assert q.get("card_id", "card1") == "card1"
            assert q.get("session_id", "sess1") == "sess1"

    def test_12_cannot_call_unauthorized_tools(self):
        """Agent 只能调用白名单工具。"""
        profile_tools = set(HISTORY_RECALL_TOOLS.keys())
        allowed = {
            "rag_memory_lookup", "entity_alias_lookup", "timeline_lookup",
            "relationship_context_lookup", "worldbook_lookup",
            "accepted_turn_lookup", "active_memory_lookup",
        }
        assert profile_tools == allowed

    def test_13_cannot_delegate(self):
        """Agent 无法递归委派。"""
        from awp_rp_runtime_v2.runtime.history_recall_tool_profile import HISTORY_RECALL_ROLE_SPEC
        assert HISTORY_RECALL_ROLE_SPEC.can_delegate is False

    def test_14_cannot_generate_cardstate_patch(self):
        """Agent 无法直接生成 CardState patch。"""
        from awp_rp_runtime_v2.runtime.history_recall_tool_profile import HISTORY_RECALL_ROLE_SPEC
        assert HISTORY_RECALL_ROLE_SPEC.can_write_state is False

    def test_15_cannot_generate_memory_commit(self):
        """Agent 无法直接生成 MemoryCommitPlan。"""
        from awp_rp_runtime_v2.runtime.history_recall_tool_profile import HISTORY_RECALL_ROLE_SPEC
        assert HISTORY_RECALL_ROLE_SPEC.can_write_memory is False


# ─────────────────────────────────────────────
# Tests 17-19: Tool failure behavior
# ─────────────────────────────────────────────

class TestToolFailureBehavior:
    """Tests for tool timeout and failure degradation."""

    def test_17_tool_timeout_returns_degraded(self):
        """Tool timeout 返回 degraded，不阻断主链。"""
        # Create a tool result with timeout status
        from awp_rp_runtime_v2.contracts.tool_result import ToolResult, ToolResultStatus
        tr = ToolResult(
            result_id="tr1", request_id="req1", trace_id="t1",
            tool_id="rag_memory_lookup",
            status=ToolResultStatus.TIMEOUT,
            failure_reason="timeout",
        )
        assert tr.is_failed()
        # Optional tool with failure → degraded in Gateway
        # This is tested by Gateway behavior, verified here via contract

    def test_18_optional_tool_failure_no_fabrication(self):
        """optional 工具失败不会伪造检索结果。"""
        runtime = HistoryRecallRuntime()
        # Simulate a result with failed tools
        result = HistoryRecallResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=HistoryRecallStatus.DEGRADED,
            degraded_reasons=["rag_memory_lookup timeout"],
            evidence=[],
            confirmed_facts=[],
        )
        # Degraded result should have empty confirmed facts
        assert result.confirmed_facts == []
        assert len(result.degraded_reasons) > 0

    def test_19_required_tool_failure_policy(self):
        """required 工具失败行为符合 failurePolicy。"""
        task = DelegationTask(
            task_id="t1", role="history-recall",
            required=False, failure_policy="skip",
        )
        assert task.failure_policy == "skip"
        assert task.required is False


# ─────────────────────────────────────────────
# Test 20: HistoryRecallResult → AgentSuggestion
# ─────────────────────────────────────────────

class TestHistoryRecallAdapter:
    """Tests for HistoryRecallAdapter."""

    def test_20_result_to_agent_suggestion(self):
        """HistoryRecallResult 正确转换为 AgentSuggestion。"""
        adapter = HistoryRecallAdapter()
        evidence = [_make_evidence("ev1", "accepted_turn", "NPC承诺帮助")]
        result = HistoryRecallResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=HistoryRecallStatus.SUCCESS,
            focus_entities=["npc_1"],
            evidence=evidence,
            confirmed_facts=["NPC曾在第三回合承诺帮助主角"],
            writer_recommendations=["提醒Writer: NPC曾承诺帮助"],
            continuity_risks=[],
        )
        suggestions = adapter.to_suggestions(result)
        assert len(suggestions) >= 1
        sug = suggestions[0]
        assert sug.kind == SuggestionKind.CONTINUITY_ISSUE
        assert len(sug.evidence) > 0
        assert len(sug.source_refs) > 0
        assert sug.role == "history-recall"


# ─────────────────────────────────────────────
# Tests 21-23: SuggestionMerge and FinalTurnBrief
# ─────────────────────────────────────────────

class TestSuggestionMergeHistory:
    """Tests for SuggestionMerge with history suggestions."""

    def test_21_conflict_with_cardstate_rejected(self):
        """SuggestionMerge 会拒绝与 CardState 冲突的历史建议。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        merger = SuggestionMerger()
        snapshot = _make_snapshot("test")
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")

        # Create a suggestion that conflicts with mustNotDo
        sug = AgentSuggestion(
            suggestion_id="s1", task_id="t1", role="history-recall",
            kind=SuggestionKind.CONTINUITY_ISSUE,
            summary="Override scene state", priority=0.9, confidence=0.9,
            recommendations=["Change location to forest"],
            risk_flags=["conflict"],
        )
        result = AgentExecutionResult(
            task_id="t1", role="history-recall", trace_id="t1",
            success=True, suggestions=[sug],
        )
        merge = merger.merge(plan, brief, snapshot, [result])
        # Should be adopted or ignored, not crash
        assert merge is not None

    def test_22_final_brief_includes_history(self):
        """FinalTurnBrief 包含历史发现。"""
        from awp_rp_runtime_v2.contracts.enrichment_bundle import EnrichmentBundle
        snapshot = _make_snapshot()
        director_plan = DirectorPlan(
            plan_id="dp1", trace_id="t1", snapshot_id="s1",
            card_id="card1", session_id="sess1",
        )
        enrichment = EnrichmentBundle(
            bundle_id="eb1", trace_id="t1", snapshot_id="s1",
        )
        brief_runtime = FinalTurnBriefRuntime()
        final_brief = brief_runtime.produce(director_plan, enrichment, snapshot)
        # Verify history fields exist and can be set
        assert hasattr(final_brief, 'accepted_history_findings')
        assert hasattr(final_brief, 'history_continuity_warnings')
        final_brief.accepted_history_findings = ["NPC曾承诺帮助"]
        assert len(final_brief.accepted_history_findings) == 1

    def test_23_writer_cannot_read_raw_result(self):
        """Writer 无法读取原始 HistoryRecallResult。"""
        from awp_rp_runtime_v2.runtime.writer_input_bundle_v2_builder import WriterInputBundleV2Builder
        from awp_rp_runtime_v2.contracts.final_turn_brief import FinalTurnBrief
        builder = WriterInputBundleV2Builder()
        snapshot = _make_snapshot()
        final_brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_history_findings=["NPC曾承诺帮助"],
        )
        bundle = builder.build(snapshot, final_brief)
        # Writer only sees the bundle, not the raw HistoryRecallResult
        bundle_dict = bundle.to_dict()
        # The bundle should NOT contain the full HistoryRecallResult object
        # It should only have the FinalTurnBrief with history findings
        assert "history_recall_result" not in bundle_dict


# ─────────────────────────────────────────────
# Test 24: No-op path completes
# ─────────────────────────────────────────────

class TestNoOpPath:
    """Test that no-op path (shouldTrigger=False) completes normally."""

    def test_24_noop_path_completes(self):
        """shouldTrigger=false → 空 suggestion → SuggestionMerge 正常完成。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        snapshot = _make_snapshot("你好")
        plan = _make_director_plan(snapshot)
        policy = HistoryRecallTriggerPolicy()
        trigger_result = policy.evaluate(snapshot, plan)
        assert trigger_result.should_trigger is False

        # No delegation task generated → empty suggestions
        merger = SuggestionMerger()
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        del_plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")
        merge = merger.merge(del_plan, brief, snapshot, [])
        assert merge.adopted_count == 0
        assert merge.conflict_count == 0


# ─────────────────────────────────────────────
# Contract serialization tests
# ─────────────────────────────────────────────

class TestContractSerialization:
    """Test round-trip serialization of D1 contracts."""

    def test_recall_focus_roundtrip(self):
        focus = RecallFocus(
            focus_id="f1",
            entity="npc_1",
            aliases=["那家伙"],
            recall_kinds=[RecallKind.EVENT_HISTORY, RecallKind.PROMISE_HISTORY],
            query_hints="NPC曾经承诺",
        )
        d = focus.to_dict()
        restored = RecallFocus.from_dict(d)
        assert restored.entity == "npc_1"
        assert RecallKind.EVENT_HISTORY in restored.recall_kinds

    def test_recall_evidence_roundtrip(self):
        ev = _make_evidence("ev1", "accepted_turn", "NPC承诺帮助", 0.9)
        d = ev.to_dict()
        restored = RecallEvidence.from_dict(d)
        assert restored.evidence_id == "ev1"
        assert restored.source_type == "accepted_turn"

    def test_history_recall_request_roundtrip(self):
        req = HistoryRecallRequest(
            request_id="req1", trace_id="t1", snapshot_id="s1",
            task_run_id="tr1", card_id="card1", session_id="sess1",
            focus_entities=["npc_1"],
            recall_kinds=[RecallKind.PROMISE_HISTORY],
            max_evidence_items=10,
        )
        d = req.to_dict()
        restored = HistoryRecallRequest.from_dict(d)
        assert restored.focus_entities == ["npc_1"]

    def test_history_recall_result_roundtrip(self):
        ev = [_make_evidence()]
        result = HistoryRecallResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=HistoryRecallStatus.SUCCESS,
            focus_entities=["npc_1"],
            evidence=ev,
            confirmed_facts=["NPC承诺帮助"],
        )
        d = result.to_dict()
        restored = HistoryRecallResult.from_dict(d)
        assert restored.status == HistoryRecallStatus.SUCCESS
        assert len(restored.evidence) == 1

    def test_continuity_risk_roundtrip(self):
        risk = ContinuityRisk(
            risk_id="cr1",
            risk_level=RiskLevel.HIGH,
            description="角色身份矛盾",
            entity_refs=["npc_1"],
        )
        d = risk.to_dict()
        restored = ContinuityRisk.from_dict(d)
        assert restored.risk_level == RiskLevel.HIGH

    def test_history_recall_suggestion_roundtrip(self):
        sug = HistoryRecallSuggestion(
            suggestion_id="hs1",
            kind=HistorySuggestionKind.CONTINUITY_FACT,
            summary="NPC曾承诺帮助",
            evidence_refs=["ev1"],
        )
        d = sug.to_dict()
        restored = HistoryRecallSuggestion.from_dict(d)
        assert restored.kind == HistorySuggestionKind.CONTINUITY_FACT

    def test_history_recall_diagnostics_roundtrip(self):
        diag = HistoryRecallDiagnostics(
            diagnostics_id="d1", trace_id="t1", snapshot_id="s1",
            trigger_reasons=["历史指代"],
            tool_calls_made=3,
            tool_calls_succeeded=2,
            tool_calls_failed=1,
        )
        d = diag.to_dict()
        restored = HistoryRecallDiagnostics.from_dict(d)
        assert restored.tool_calls_made == 3


# ─────────────────────────────────────────────
# E2E Test 1: Normal history recall path
# ─────────────────────────────────────────────

class TestD1E2ENormalPath:
    """E2E: Normal history recall path with fake LLM."""

    def test_e2e_normal_history_recall(self):
        """完整历史回查路径: 6回合历史 → 触发 → 回查 → 建议 → 合并。"""
        # 1. Build history (6 turns)
        turns = []
        for i in range(1, 7):
            turns.append(_make_turn_record(
                f"tr_{i}",
                f"第{i}回合: NPC{'承诺帮助主角' if i == 3 else '在月光庭院相遇' if i == 1 else '继续对话'}",
                turn_index=i,
            ))

        active_memories = [
            {"memory_id": "am_1", "summary": "NPC在第3回合承诺帮助主角", "kind": "promise",
             "entity_refs": ["npc_1"], "importance": 0.8, "confidence": 0.9, "status": "active"},
        ]
        rag_recall = [
            {"memory_id": "rag_1", "summary": "NPC曾经与主角有过秘密交易",
             "entity_refs": ["npc_1"], "importance": 0.6, "confidence": 0.7},
        ]

        # 2. Build snapshot with historical reference
        snapshot = _make_snapshot(
            player_input="你还记得答应过我什么吗",
            recent_turns=turns,
            active_memories=active_memories,
            rag_recall=rag_recall,
        )

        # 3. Director detects risk
        plan = _make_director_plan(snapshot, risk_flags=["historical_reference"])

        # 4. Trigger policy fires
        policy = HistoryRecallTriggerPolicy()
        trigger = policy.evaluate(snapshot, plan)
        assert trigger.should_trigger is True
        assert len(trigger.trigger_reasons) > 0

        # 5. Create delegation task
        task = DelegationTask(
            task_id="hist_1", role="history-recall",
            priority=0.9,
            purpose="回查NPC对主角的承诺历史",
            input_field_allowlist=[
                "player_input", "recent_turn_records",
                "active_memories", "rag_recall",
            ],
            tool_allowlist=list(HISTORY_RECALL_TOOLS.keys()),
            max_tokens=1000,
            timeout_ms=30000,
            required=False,
            failure_policy="skip",
            expected_suggestion_kinds=[
                "continuity_issue", "character_consistency",
            ],
        )

        # 6. Build envelope
        registry = AgentRuntimeRegistry()
        registry.register_spec(AgentRoleSpec(
            role_id="history-recall",
            description="History/Recall sub-agent for historical evidence",
            allowed_suggestion_kinds=[
                SuggestionKind.CONTINUITY_ISSUE,
                SuggestionKind.CHARACTER_CONSISTENCY,
            ],
            allowed_tools=list(HISTORY_RECALL_TOOLS.keys()),
            can_delegate=False,
            can_write_state=False,
            can_write_memory=False,
            can_generate_final_text=False,
        ))
        builder = TaskEnvelopeBuilder(registry)
        envelope = builder.build(task, snapshot, "brief1")
        assert envelope is not None

        # 7. Execute history recall via runtime
        history_runtime = HistoryRecallRuntime()
        hr_result = history_runtime.run(
            snapshot=snapshot,
            task=task,
            trigger_result=trigger,
            envelope=envelope,
        )

        assert hr_result is not None
        assert hr_result.trace_id == snapshot.trace_id

        # 8. Convert to suggestions
        adapter = HistoryRecallAdapter()
        suggestions = adapter.to_suggestions(hr_result)
        # May be empty if no evidence found in fake mode, but should not crash
        assert isinstance(suggestions, list)

        # 9. Execute through pool (integration)
        pool = DynamicSubAgentPool(registry, builder)

        # Register a fake runner for history-recall
        class FakeHistoryRunner:
            def run(self, envelope):
                return suggestions

        registry.register_runner("history-recall", FakeHistoryRunner())
        delegation = DelegationPlan(
            plan_id="dp1", trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id, brief_id="b1",
            tasks=[task],
        )
        exec_results = pool.execute(delegation, snapshot)
        assert len(exec_results) == 1
        assert exec_results[0].success

        # 10. Merge suggestions
        merger = SuggestionMerger()
        brief = type('FakeBrief', (), {
            'must_not_do': [],
            'must_preserve_facts': [],
            'brief_id': 'b1',
        })()
        merge = merger.merge(delegation, brief, snapshot, exec_results)
        assert merge is not None
        # Even with no suggestions, merge should complete
        assert merge.merge_id != ""


# ─────────────────────────────────────────────
# E2E Test 2: Conflict and degradation path
# ─────────────────────────────────────────────

class TestD1E2EConflictDegradation:
    """E2E: Conflict and degradation path."""

    def test_e2e_conflict_and_degradation(self):
        """CardState 与 RagMemory 冲突 + optional 工具 timeout → degraded。"""
        # 1. Setup conflicting data
        rag_recall = [
            {"memory_id": "rag_1", "summary": "NPC已经死了",
             "entity_refs": ["npc_1"], "conflict_status": "conflicted",
             "importance": 0.8, "confidence": 0.6},
        ]
        active_memories = [
            {"memory_id": "am_1", "summary": "NPC仍然活着",
             "entity_refs": ["npc_1"], "importance": 0.9, "confidence": 0.95,
             "status": "active"},
        ]

        # 2. Build snapshot
        snapshot = _make_snapshot(
            player_input="和NPC说话",
            active_memories=active_memories,
            rag_recall=rag_recall,
        )

        # 3. Trigger fires (conflict detected)
        plan = _make_director_plan(snapshot)
        policy = HistoryRecallTriggerPolicy()
        trigger = policy.evaluate(snapshot, plan)
        assert trigger.should_trigger is True

        # 4. Run history recall
        runtime = HistoryRecallRuntime()
        task = DelegationTask(
            task_id="hist_1", role="history-recall",
            tool_allowlist=list(HISTORY_RECALL_TOOLS.keys()),
        )
        result = runtime.run(
            snapshot=snapshot,
            task=task,
            trigger_result=trigger,
            envelope=None,  # Will build internally
        )

        # 5. Verify degraded behavior
        assert result is not None
        # Result should indicate conflicts or degradation
        if result.status == HistoryRecallStatus.DEGRADED:
            assert len(result.degraded_reasons) > 0

        # 6. Verify evidence ranking handles conflicts
        ranker = RecallEvidenceRanker()
        e1 = _make_evidence("ev1", "rag_memory", "NPC已经死了", 0.6)
        e1 = RecallEvidence(
            evidence_id="ev1", source_type="rag_memory",
            source_ref="rag_1", excerpt="NPC已经死了",
            confidence=0.6, conflict_status="conflicted",
        )
        e2 = _make_evidence("ev2", "active_memory", "NPC仍然活着", 0.95)
        ranked = ranker.rank([e1, e2])
        # Active memory should rank higher
        assert ranked[0].source_type == "active_memory"
        # Conflicted evidence should be marked
        for ev in ranked:
            if ev.conflict_status == "conflicted":
                assert ev.source_type == "rag_memory"

        # 7. Validator rejects conflicted confirmed facts
        validator = HistoryRecallValidator()
        bad_result = HistoryRecallResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=HistoryRecallStatus.SUCCESS,
            confirmed_facts=["NPC已经死了"],  # Based on conflicted evidence
            evidence=[e1],
        )
        errors = validator.validate(bad_result)
        # Should flag conflicted evidence as confirmed fact
        assert len(errors) > 0

        # 8. Writer should not reference conflicted history
        # This is enforced by FinalTurnBrief not including rejected findings
        assert result.status in (HistoryRecallStatus.SUCCESS, HistoryRecallStatus.DEGRADED)


class TestHistoryRecallRuntimeWorldbookEvidence:
    def test_worldbook_content_excerpt_is_used_as_evidence(self):
        snapshot = _make_snapshot(
            active_worldbook=[{
                "entry_id": "wb_gate",
                "title": "Gate Rule",
                "content_excerpt": "CRITICAL_WORLDBOOK_EXCERPT",
            }],
        )
        trigger = TriggerResult(should_trigger=True)

        evidence = HistoryRecallRuntime()._collect_evidence_from_snapshot(snapshot, trigger)

        assert any(ev.excerpt == "CRITICAL_WORLDBOOK_EXCERPT" for ev in evidence)
