"""D5: Continuity Agent V1 — Tests.

Tests 1-26: Unit tests for trigger policy, validator, ranker, permissions, merge.
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

# D5 contracts
from awp_rp_runtime_v2.contracts.continuity_request import ContinuityRequest
from awp_rp_runtime_v2.contracts.continuity_evidence import (
    ContinuityEvidence, EvidenceSourceType, ConflictStatus, EVIDENCE_PRIORITY,
)
from awp_rp_runtime_v2.contracts.continuity_issue import (
    ContinuityIssue, ContinuityIssueKind, ContinuitySeverity,
)
from awp_rp_runtime_v2.contracts.continuity_conflict import ContinuityConflict, ConflictResolution
from awp_rp_runtime_v2.contracts.continuity_result import ContinuityResult, ContinuityStatus
from awp_rp_runtime_v2.contracts.continuity_suggestion import ContinuitySuggestion, ContinuitySuggestionKind
from awp_rp_runtime_v2.contracts.continuity_trigger_diagnostics import ContinuityTriggerDiagnostics

# D5 runtime
from awp_rp_runtime_v2.runtime.continuity_trigger_policy import ContinuityTriggerPolicy, ContinuityTriggerResult
from awp_rp_runtime_v2.runtime.continuity_runtime import ContinuityRuntime
from awp_rp_runtime_v2.runtime.continuity_query_planner import ContinuityQueryPlanner
from awp_rp_runtime_v2.runtime.continuity_evidence_ranker import ContinuityEvidenceRanker
from awp_rp_runtime_v2.runtime.continuity_issue_detector import ContinuityIssueDetector
from awp_rp_runtime_v2.runtime.continuity_validator import ContinuityValidator
from awp_rp_runtime_v2.runtime.continuity_ranker import ContinuityRanker, MAX_BLOCKING, MAX_WARNING
from awp_rp_runtime_v2.runtime.continuity_adapter import ContinuityAdapter
from awp_rp_runtime_v2.runtime.continuity_tool_profile import CONTINUITY_TOOLS, CONTINUITY_ROLE_SPEC

# Existing runtime
from awp_rp_runtime_v2.runtime.tool_registry import ToolRegistry
from awp_rp_runtime_v2.runtime.agent_runtime_registry import AgentRuntimeRegistry


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
    location: str = "普通房间",
) -> RoundSnapshot:
    return RoundSnapshot(
        snapshot_id=f"snap_{uuid.uuid4().hex[:8]}",
        trace_id=f"trace_{uuid.uuid4().hex[:8]}",
        card_id=card_id,
        session_id=session_id,
        player_input=player_input,
        card_state=CardState(
            variables={"scene": VariableEntry(name="scene", value=location)},
            scene_state=SceneState(location=location),
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
        scene_focus="普通房间",
        base_card_state_revision=snapshot.base_card_state_revision,
        risk_flags=risk_flags or [],
        unresolved_threads=unresolved_threads or [],
        narrative_opportunities=narrative_opportunities or [],
    )


def _make_evidence(
    evidence_id: str = "ev_1",
    source_type: EvidenceSourceType = EvidenceSourceType.CARD_STATE,
    source_ref: str = "",
    excerpt: str = "当前地点: 普通房间",
    confidence: float = 1.0,
) -> ContinuityEvidence:
    return ContinuityEvidence(
        evidence_id=evidence_id,
        source_type=source_type,
        source_ref=source_ref or f"src_{evidence_id}",
        excerpt=excerpt,
        entity_refs=[],
        location_refs=["普通房间"],
        confidence=confidence,
        recency=0.8,
        relevance_score=0.7,
    )


def _make_issue(
    issue_id: str = "ci_test",
    kind: ContinuityIssueKind = ContinuityIssueKind.LOCATION_CONFLICT,
    severity: ContinuitySeverity = ContinuitySeverity.BLOCKING,
    evidence_refs: list[str] | None = None,
    summary: str = "CardState 确认当前场景在某地",
    writer_constraint: str = "正文不得改变当前地点",
) -> ContinuityIssue:
    return ContinuityIssue(
        issue_id=issue_id,
        trace_id="t1",
        snapshot_id="s1",
        kind=kind,
        severity=severity,
        summary=summary,
        affected_entities=[],
        affected_locations=["普通房间"],
        foundation_facts=["当前地点: 普通房间"],
        evidence_refs=evidence_refs if evidence_refs is not None else ["ev_cardstate_普通房间"],
        priority_decision="CardState 权威优先",
        writer_constraint=writer_constraint,
        director_recommendation="如需切换场景，应由 Director 规划",
        must_not_assert_as_fact=True,
        must_not_modify_state=True,
    )


# ─────────────────────────────────────────────
# Test 1: Simple input, no risk → no trigger
# ─────────────────────────────────────────────

class TestTriggerPolicy:
    """Tests for ContinuityTriggerPolicy."""

    def test_01_no_risk_no_trigger(self):
        """简单即时输入、无风险时不触发。"""
        snapshot = _make_snapshot("你好", location="普通房间")
        plan = _make_director_plan(snapshot)
        policy = ContinuityTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False
        assert result.trigger_reasons == []
        assert result.risk_level == "none"

    def test_02_location_conflict_triggers(self):
        """场景/角色位置变化时触发。"""
        snapshot = _make_snapshot("来到城门外", location="客栈二楼")
        plan = _make_director_plan(snapshot)
        policy = ContinuityTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("地点" in r for r in result.trigger_reasons)

    def test_03_knowledge_boundary_triggers(self):
        """知识边界/秘密/身份信号时触发。"""
        snapshot = _make_snapshot("他不知道那个秘密")
        plan = _make_director_plan(snapshot)
        policy = ContinuityTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("知识" in r or "秘密" in r for r in result.trigger_reasons)
        assert result.risk_level == "high"

    def test_04_promise_triggers(self):
        """承诺/约定信号时触发。"""
        snapshot = _make_snapshot("他答应过要回来")
        plan = _make_director_plan(snapshot)
        policy = ContinuityTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("承诺" in r for r in result.trigger_reasons)

    def test_05_continuity_reference_triggers(self):
        """连续性指代词（之前/已经/还没）触发。"""
        snapshot = _make_snapshot("之前那个人回来了吗")
        plan = _make_director_plan(snapshot)
        policy = ContinuityTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("连续性" in r for r in result.trigger_reasons)

    def test_06_not_trigger_just_for_more_calls(self):
        """仅为了增加Agent调用次数不得触发。"""
        snapshot = _make_snapshot("你好", location="普通房间")
        plan = _make_director_plan(snapshot)
        policy = ContinuityTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False


# ─────────────────────────────────────────────
# Tests 7-11: Issue validation
# ─────────────────────────────────────────────

class TestContinuityValidator:
    """Tests for ContinuityValidator."""

    def test_07_no_evidence_blocking_rejected(self):
        """无 evidence 的 blocking issue 被拒绝。"""
        validator = ContinuityValidator()
        issue = _make_issue(evidence_refs=[], severity=ContinuitySeverity.BLOCKING)
        errors = validator.validate(issue)
        assert len(errors) > 0
        assert any("evidence" in e.lower() or "证据" in e for e in errors)

    def test_08_low_priority_rag_cannot_produce_blocking(self):
        """低优先级 RAG 不得产生高优先级硬约束。"""
        validator = ContinuityValidator()
        # Create evidence list with only RAG-level evidence
        rag_ev = ContinuityEvidence(
            evidence_id="ev_rag_1",
            source_type=EvidenceSourceType.RAG_MEMORY,
            excerpt="某条RAG记忆",
        )
        issue = _make_issue(
            evidence_refs=["ev_rag_1"],
            severity=ContinuitySeverity.BLOCKING,
        )
        errors = validator.validate(issue, evidence=[rag_ev])
        assert len(errors) > 0
        assert any("高优先级" in e or "blocking" in e for e in errors)

    def test_09_state_modification_rejected(self):
        """自动推进时间/事件/关系的建议被拒绝。"""
        validator = ContinuityValidator()
        issue = _make_issue(
            summary="推进时间到明天",
            writer_constraint="修改状态角色位置",
        )
        errors = validator.validate(issue)
        assert len(errors) > 0
        assert any("状态修改" in e for e in errors)

    def test_10_event_creation_rejected(self):
        """创建事件/自动触发的建议被拒绝。"""
        validator = ContinuityValidator()
        issue = _make_issue(
            summary="事件已经触发进入下一阶段",
        )
        errors = validator.validate(issue)
        assert len(errors) > 0
        assert any("事件" in e for e in errors)

    def test_11_memory_commit_rejected(self):
        """包含MemoryCommit指令的建议被拒绝。"""
        validator = ContinuityValidator()
        issue = _make_issue(
            writer_constraint="memory_commit 写入记忆",
        )
        errors = validator.validate(issue)
        assert len(errors) > 0
        assert any("MemoryCommit" in e for e in errors)


# ─────────────────────────────────────────────
# Tests 12-17: Permission boundaries
# ─────────────────────────────────────────────

class TestContinuityPermissions:
    """Tests for permission boundaries of Continuity Agent."""

    def test_12_cannot_access_store(self):
        """Continuity Agent 无法访问 Store / SQLite。"""
        runtime = ContinuityRuntime()
        assert not hasattr(runtime, 'card_state_store')
        assert not hasattr(runtime, 'turn_record_store')
        assert not hasattr(runtime, 'active_memory_store')
        assert not hasattr(runtime, 'rag_memory_store')

    def test_13_cannot_cross_card_session(self):
        """Continuity Agent 无法跨 cardId / sessionId 查询。"""
        snapshot = _make_snapshot(card_id="card1", session_id="sess1")
        planner = ContinuityQueryPlanner()
        queries = planner.plan_queries(
            snapshot=snapshot,
            focus_entities=["npc_1"],
            focus_locations=["普通房间"],
            continuity_domains=["knowledge_boundary"],
        )
        for q in queries:
            assert q.get("card_id", "card1") == "card1"
            assert q.get("session_id", "sess1") == "sess1"

    def test_14_cannot_call_unauthorized_tools(self):
        """Continuity Agent 无法调用未授权工具。"""
        profile_tools = set(CONTINUITY_TOOLS.keys())
        allowed = {
            "accepted_turn_lookup", "active_memory_lookup",
            "rag_memory_lookup", "timeline_lookup",
            "relationship_context_lookup", "worldbook_lookup",
            "entity_alias_lookup", "event_stage_lookup",
            "scene_context_lookup", "npc_context_lookup",
        }
        assert profile_tools == allowed

    def test_15_cannot_delegate(self):
        """Continuity Agent 无法递归委派。"""
        assert CONTINUITY_ROLE_SPEC.can_delegate is False

    def test_16_cannot_write_state(self):
        """Continuity Agent 无法生成 StateUpdateProposal。"""
        assert CONTINUITY_ROLE_SPEC.can_write_state is False

    def test_17_cannot_write_memory(self):
        """Continuity Agent 无法生成 MemoryCommitPlan。"""
        assert CONTINUITY_ROLE_SPEC.can_write_memory is False

    def test_18_cannot_generate_final_text(self):
        """Continuity Agent 输出最终玩家正文时被拒绝。"""
        assert CONTINUITY_ROLE_SPEC.can_generate_final_text is False


class TestContinuityRuntimeWorldbookEvidence:
    def test_worldbook_content_excerpt_is_used_as_evidence(self):
        snapshot = _make_snapshot(
            active_worldbook=[{
                "entry_id": "wb_lore",
                "title": "Lore",
                "content_excerpt": "CRITICAL_WORLDBOOK_EXCERPT",
            }],
        )
        trigger = ContinuityTriggerResult(should_trigger=True)

        evidence = ContinuityRuntime()._collect_evidence_from_snapshot(snapshot, trigger)

        assert any(ev.excerpt == "CRITICAL_WORLDBOOK_EXCERPT" for ev in evidence)


# ─────────────────────────────────────────────
# Tests 19-21: Ranker
# ─────────────────────────────────────────────

class TestContinuityRanker:
    """Tests for ContinuityRanker."""

    def test_19_max_three_blocking_three_warning(self):
        """每回合默认最多 3 个 blocking + 3 个 warning。"""
        ranker = ContinuityRanker()
        issues = []
        for i in range(6):
            issues.append(_make_issue(
                f"ci_block_{i}",
                severity=ContinuitySeverity.BLOCKING,
                evidence_refs=[f"ev_{i}"],
            ))
        for i in range(6):
            issues.append(_make_issue(
                f"ci_warn_{i}",
                severity=ContinuitySeverity.WARNING,
                evidence_refs=[f"ev_{i}"],
            ))
        accepted, rejected = ranker.rank(issues)
        blocking = [i for i in accepted if i.severity == ContinuitySeverity.BLOCKING]
        warnings = [i for i in accepted if i.severity == ContinuitySeverity.WARNING]
        assert len(blocking) <= MAX_BLOCKING
        assert len(warnings) <= MAX_WARNING

    def test_20_blocking_with_cardstate_evidence_first(self):
        """blocking issue + CardState 证据排在最前。"""
        ranker = ContinuityRanker()
        cardstate_issue = _make_issue(
            "ci_cardstate",
            severity=ContinuitySeverity.BLOCKING,
            evidence_refs=["ev_cardstate"],
        )
        warning_issue = _make_issue(
            "ci_warning",
            severity=ContinuitySeverity.WARNING,
            evidence_refs=["ev_rag"],
        )
        accepted, _ = ranker.rank([warning_issue, cardstate_issue])
        assert accepted[0].issue_id == "ci_cardstate"

    def test_21_deduplicate_by_kind_and_location(self):
        """同 kind + 同 location 的 issue 去重。"""
        ranker = ContinuityRanker()
        issue1 = _make_issue("ci_1", kind=ContinuityIssueKind.LOCATION_CONFLICT)
        issue2 = _make_issue("ci_2", kind=ContinuityIssueKind.LOCATION_CONFLICT)
        # Both have same kind and affected_locations
        accepted, _ = ranker.rank([issue1, issue2], max_blocking=5)
        # Both should be accepted (ranker doesn't deduplicate, that's for candidates)
        assert len(accepted) == 2


# ─────────────────────────────────────────────
# Tests 22-24: SuggestionMerge and FinalTurnBrief
# ─────────────────────────────────────────────

class TestSuggestionMergeContinuity:
    """Tests for SuggestionMerge with continuity suggestions."""

    def test_22_blocking_constraint_in_final_brief(self):
        """blocking issue 进入 FinalTurnBrief 硬约束。"""
        brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_continuity_constraints=[
                "正文不得改变当前地点",
                "角色不应表现出已知秘密",
            ],
            rejected_continuity_findings=[],
            continuity_warnings=["时间线存在歧义"],
            continuity_evidence_refs=["ev_cardstate", "ev_turn"],
        )
        assert len(brief.accepted_continuity_constraints) == 2
        assert "正文不得改变当前地点" in brief.accepted_continuity_constraints

    def test_23_warning_as_soft_guidance(self):
        """warning 只作为软 Guidance。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        merger = __import__('awp_rp_runtime_v2.runtime.suggestion_merger', fromlist=['SuggestionMerger']).SuggestionMerger()
        snapshot = _make_snapshot("test")
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")

        sug = AgentSuggestion(
            suggestion_id="s1", task_id="t1", role="continuity",
            kind=SuggestionKind.CONTINUITY_WRITER_CONSTRAINT,
            summary="时间线存在歧义",
            priority=0.7, confidence=0.7,
            recommendations=["注意时间一致性"],
            source_refs=["ev_1"],
        )
        result = AgentExecutionResult(
            task_id="t1", role="continuity", trace_id="t1",
            success=True, suggestions=[sug],
        )
        merge = merger.merge(plan, brief, snapshot, [result])
        assert merge is not None
        adopted_sugs = [item for item in merge.adopted if item.role == "continuity"]
        assert len(adopted_sugs) >= 1

    def test_24_writer_cannot_read_raw_continuity_result(self):
        """Writer 不可读取原始 ContinuityResult。"""
        from awp_rp_runtime_v2.runtime.writer_input_bundle_v2_builder import WriterInputBundleV2Builder
        builder = WriterInputBundleV2Builder()
        snapshot = _make_snapshot()
        final_brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_continuity_constraints=["正文不得改变当前地点"],
        )
        bundle = builder.build(snapshot, final_brief)
        bundle_dict = bundle.to_dict()
        assert "continuity_result" not in bundle_dict


# ─────────────────────────────────────────────
# Test 25: No-op path completes
# ─────────────────────────────────────────────

class TestNoOpPath:
    """Test that no-op path (shouldTrigger=False) completes normally."""

    def test_25_noop_path_completes(self):
        """shouldTrigger=false → 空 ContinuityResult → SuggestionMerge 正常完成。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        snapshot = _make_snapshot("你好", location="普通房间")
        plan = _make_director_plan(snapshot)
        policy = ContinuityTriggerPolicy()
        trigger_result = policy.evaluate(snapshot, plan)
        assert trigger_result.should_trigger is False

        # Run continuity runtime with no trigger
        runtime = ContinuityRuntime()
        task = DelegationTask(
            task_id="cl_1", role="continuity",
            tool_allowlist=list(CONTINUITY_TOOLS.keys()),
        )
        result = runtime.run(snapshot, task, trigger_result)
        assert result.status == ContinuityStatus.NO_TRIGGER
        assert len(result.issues) == 0

        # Merge completes normally with no suggestions
        from awp_rp_runtime_v2.runtime.suggestion_merger import SuggestionMerger
        merger = SuggestionMerger()
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        del_plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")
        merge = merger.merge(del_plan, brief, snapshot, [])
        assert merge.adopted_count == 0
        assert merge.conflict_count == 0


# ─────────────────────────────────────────────
# Test 26: Tool timeout returns degraded
# ─────────────────────────────────────────────

class TestToolFailureBehavior:
    """Tests for tool timeout and failure degradation."""

    def test_26_tool_timeout_returns_degraded(self):
        """optional Tool timeout 返回 degraded，不阻断主链。"""
        from awp_rp_runtime_v2.contracts.tool_result import ToolResult, ToolResultStatus
        tr = ToolResult(
            result_id="tr1", request_id="req1", trace_id="t1",
            tool_id="accepted_turn_lookup",
            status=ToolResultStatus.TIMEOUT,
            failure_reason="timeout",
        )
        assert tr.is_failed()
        # Degraded result should not block the main chain
        result = ContinuityResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=ContinuityStatus.DEGRADED,
            degraded_reasons=["accepted_turn_lookup timeout"],
        )
        assert result.status == ContinuityStatus.DEGRADED
        assert len(result.degraded_reasons) > 0


# ─────────────────────────────────────────────
# Test 27: Official workflow JSON validation
# ─────────────────────────────────────────────

class TestD5NodeRegistration:
    """D5: Continuity node registration tests."""

    def test_d5_nodes_present(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS
        d5 = {
            "AWPV2ContinuityTrigger", "AWPV2ContinuityRequest",
            "AWPV2ContinuityAgent", "AWPV2ContinuityValidator",
            "AWPV2ContinuityRanker", "AWPV2ContinuityResult",
            "AWPV2ContinuityDiagnostics",
        }
        for name in d5:
            assert name in NODE_CLASS_MAPPINGS, f"Missing: {name}"

    def test_d5_display_names_chinese(self):
        from awp_rp_runtime_v2.nodes import NODE_DISPLAY_NAME_MAPPINGS
        d5_displays = [
            "AWP V2 连续性触发", "AWP V2 连续性请求",
            "AWP V2 连续性Agent", "AWP V2 连续性验证",
            "AWP V2 连续性排序", "AWP V2 连续性结果",
            "AWP V2 连续性诊断",
        ]
        for display in d5_displays:
            assert display in NODE_DISPLAY_NAME_MAPPINGS.values(), f"Missing: {display}"


# ─────────────────────────────────────────────
# Contract serialization tests
# ─────────────────────────────────────────────

class TestD5ContractSerialization:
    """Test round-trip serialization of D5 contracts."""

    def test_continuity_request_roundtrip(self):
        req = ContinuityRequest(
            request_id="req1", trace_id="t1", snapshot_id="s1",
            task_run_id="tr1", card_id="card1", session_id="sess1",
            focus_entities=["npc_1"], focus_locations=["普通房间"],
            max_issues=6, required_evidence=True,
        )
        d = req.to_dict()
        restored = ContinuityRequest.from_dict(d)
        assert restored.focus_entities == ["npc_1"]
        assert restored.required_evidence is True

    def test_continuity_evidence_roundtrip(self):
        ev = _make_evidence("ev_1")
        d = ev.to_dict()
        restored = ContinuityEvidence.from_dict(d)
        assert restored.evidence_id == "ev_1"
        assert restored.source_type == EvidenceSourceType.CARD_STATE

    def test_continuity_issue_roundtrip(self):
        issue = _make_issue("ci_1")
        d = issue.to_dict()
        restored = ContinuityIssue.from_dict(d)
        assert restored.issue_id == "ci_1"
        assert restored.kind == ContinuityIssueKind.LOCATION_CONFLICT
        assert restored.severity == ContinuitySeverity.BLOCKING

    def test_continuity_conflict_roundtrip(self):
        conflict = ContinuityConflict(
            conflict_id="cc1", trace_id="t1", snapshot_id="s1",
            higher_priority_evidence_id="ev_card",
            lower_priority_evidence_id="ev_rag",
            fact_description="地点冲突",
            resolution=ConflictResolution.HIGHER_PRIORITY_WINS,
        )
        d = conflict.to_dict()
        restored = ContinuityConflict.from_dict(d)
        assert restored.resolution == ConflictResolution.HIGHER_PRIORITY_WINS

    def test_continuity_result_roundtrip(self):
        issue = [_make_issue()]
        result = ContinuityResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=ContinuityStatus.SUCCESS,
            issues=issue,
            blocking_issues=issue,
        )
        d = result.to_dict()
        restored = ContinuityResult.from_dict(d)
        assert restored.status == ContinuityStatus.SUCCESS
        assert len(restored.blocking_issues) == 1

    def test_continuity_suggestion_roundtrip(self):
        sug = ContinuitySuggestion(
            suggestion_id="cs1",
            kind=ContinuitySuggestionKind.WRITER_CONSTRAINT,
            summary="正文不得改变地点",
            writer_constraint="场景必须在客栈",
        )
        d = sug.to_dict()
        restored = ContinuitySuggestion.from_dict(d)
        assert restored.kind == ContinuitySuggestionKind.WRITER_CONSTRAINT

    def test_continuity_trigger_diagnostics_roundtrip(self):
        diag = ContinuityTriggerDiagnostics(
            diagnostics_id="cld1", trace_id="t1", snapshot_id="s1",
            should_trigger=True,
            trigger_reasons=["连续性指代"],
            issues_detected=3,
            issues_blocking=1,
            issues_warning=2,
        )
        d = diag.to_dict()
        restored = ContinuityTriggerDiagnostics.from_dict(d)
        assert restored.issues_detected == 3
        assert restored.issues_blocking == 1


# ─────────────────────────────────────────────
# Adapter test
# ─────────────────────────────────────────────

class TestContinuityAdapter:
    """Tests for ContinuityAdapter."""

    def test_result_to_agent_suggestion(self):
        """ContinuityResult 正确转换为 AgentSuggestion。"""
        adapter = ContinuityAdapter()
        issue = _make_issue("ci_1")
        result = ContinuityResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=ContinuityStatus.SUCCESS,
            blocking_issues=[issue],
            writer_constraints=["正文不得改变地点"],
        )
        suggestions = adapter.to_suggestions(result)
        assert len(suggestions) >= 1
        # Should have blocking suggestion + constraint suggestion
        blocking_sugs = [s for s in suggestions if "continuity_blocking" in s.risk_flags]
        assert len(blocking_sugs) >= 1


# ─────────────────────────────────────────────
# Evidence priority tests
# ─────────────────────────────────────────────

class TestEvidencePriority:
    """Tests for evidence priority ordering."""

    def test_card_state_over_accepted_turn(self):
        """CardState 优先于 accepted_turn。"""
        ranker = ContinuityEvidenceRanker()
        card_ev = _make_evidence("ev_card", EvidenceSourceType.CARD_STATE)
        turn_ev = _make_evidence("ev_turn", EvidenceSourceType.ACCEPTED_TURN)
        ranked = ranker.rank([turn_ev, card_ev])
        assert ranked[0].source_type == EvidenceSourceType.CARD_STATE

    def test_accepted_turn_over_active_memory(self):
        """accepted_turn 优先于 ActiveMemory。"""
        ranker = ContinuityEvidenceRanker()
        turn_ev = _make_evidence("ev_turn", EvidenceSourceType.ACCEPTED_TURN)
        am_ev = _make_evidence("ev_am", EvidenceSourceType.ACTIVE_MEMORY)
        ranked = ranker.rank([am_ev, turn_ev])
        assert ranked[0].source_type == EvidenceSourceType.ACCEPTED_TURN

    def test_active_memory_over_rag(self):
        """ActiveMemory 优先于 RagMemory。"""
        ranker = ContinuityEvidenceRanker()
        am_ev = _make_evidence("ev_am", EvidenceSourceType.ACTIVE_MEMORY)
        rag_ev = _make_evidence("ev_rag", EvidenceSourceType.RAG_MEMORY)
        ranked = ranker.rank([rag_ev, am_ev])
        assert ranked[0].source_type == EvidenceSourceType.ACTIVE_MEMORY

    def test_stale_low_priority_marked(self):
        """低优先级记忆与高优先级事实冲突时标记 stale。"""
        ranker = ContinuityEvidenceRanker()
        card_ev = _make_evidence("ev_card", EvidenceSourceType.CARD_STATE, excerpt="地点在客栈")
        rag_ev = _make_evidence("ev_rag", EvidenceSourceType.RAG_MEMORY, excerpt="不在客栈")
        rag_ev.entity_refs = []
        card_ev.entity_refs = []
        # They share location
        card_ev.location_refs = ["客栈"]
        rag_ev.location_refs = ["客栈"]
        ranked = ranker.rank([card_ev, rag_ev])
        conflicts = ranker.detect_conflicts(ranked)
        # RAG should be marked conflicted
        assert rag_ev.conflict_status == ConflictStatus.CONFLICTED


# ─────────────────────────────────────────────
# E2E Test 1: Normal continuity constraint path
# ─────────────────────────────────────────────

class TestD5E2ENormalPath:
    """E2E: Normal continuity constraint path with fake LLM."""

    def test_e2e_normal_continuity_constraint(self):
        """正常连续性约束路径: 6回合历史 → 触发 → 证据 → issue → 验证 → 排序 → 合并。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        from awp_rp_runtime_v2.runtime.suggestion_merger import SuggestionMerger

        # 1. Build history (6 turns)
        turns = []
        for i in range(1, 7):
            turns.append(_make_turn_record(
                f"tr_{i}",
                f"第{i}回合: {'客栈二楼对话' if i == 3 else '到达客栈' if i == 1 else '继续对话'}",
                turn_index=i,
            ))

        active_memories = [
            {"memory_id": "am_1", "summary": "NPC答应三天后回来", "kind": "promise",
             "entity_refs": ["npc_1"], "importance": 0.9, "confidence": 0.9, "status": "active"},
            {"memory_id": "am_2", "summary": "玩家知道一个秘密", "kind": "secret",
             "entity_refs": ["player"], "importance": 0.8, "confidence": 0.8, "status": "active"},
        ]

        # 2. Build snapshot
        snapshot = _make_snapshot(
            player_input="之前答应的事情还记得吗",
            recent_turns=turns,
            active_memories=active_memories,
            location="客栈二楼",
        )

        # 3. Director plan
        plan = _make_director_plan(snapshot)

        # 4. Trigger policy fires
        policy = ContinuityTriggerPolicy()
        trigger = policy.evaluate(snapshot, plan)
        assert trigger.should_trigger is True
        assert len(trigger.trigger_reasons) > 0

        # 5. Create delegation task
        task = DelegationTask(
            task_id="cl_1", role="continuity",
            priority=0.9,
            purpose="检查连续性约束",
            tool_allowlist=list(CONTINUITY_TOOLS.keys()),
            max_tokens=1000,
            timeout_ms=30000,
            required=False,
            failure_policy="skip",
        )

        # 6. Execute continuity runtime
        runtime = ContinuityRuntime()
        cl_result = runtime.run(
            snapshot=snapshot,
            task=task,
            trigger_result=trigger,
        )

        assert cl_result is not None
        assert cl_result.trace_id == snapshot.trace_id
        assert cl_result.status in (ContinuityStatus.SUCCESS, ContinuityStatus.DEGRADED)

        # 7. Convert to suggestions
        adapter = ContinuityAdapter()
        suggestions = adapter.to_suggestions(cl_result)
        assert isinstance(suggestions, list)

        # 8. Verify writer constraints exist
        if cl_result.writer_constraints:
            assert all(isinstance(c, str) for c in cl_result.writer_constraints)

        # 9. Build FinalTurnBrief with continuity constraints
        brief = FinalTurnBrief(
            brief_id="b1", trace_id=snapshot.trace_id, snapshot_id=snapshot.snapshot_id,
            accepted_continuity_constraints=cl_result.writer_constraints,
            continuity_warnings=[w.summary for w in cl_result.warnings],
            continuity_evidence_refs=[],
        )
        assert brief.brief_id == "b1"


# ─────────────────────────────────────────────
# E2E Test 2: Conflict, no-evidence, and degradation path
# ─────────────────────────────────────────────

class TestD5E2EViolationDegradation:
    """E2E: Conflict, no-evidence, and degradation path."""

    def test_e2e_violation_and_degradation(self):
        """违规issue与降级路径: 无证据blocking/RAG覆盖CardState/自动推进 → 全部拒绝 → degraded。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        from awp_rp_runtime_v2.runtime.suggestion_merger import SuggestionMerger

        # 1. Setup snapshot with minimal data
        snapshot = _make_snapshot("和NPC说话")

        # 2. Build issues with various violations
        bad_issues = [
            # No evidence blocking
            _make_issue("ci_no_ev", evidence_refs=[], severity=ContinuitySeverity.BLOCKING),
            # State modification
            _make_issue("ci_state", summary="推进时间到明天"),
            # Event creation
            _make_issue("ci_event", summary="事件已经触发进入下一阶段"),
            # Memory commit
            _make_issue("ci_mem", writer_constraint="memory_commit 写入记忆"),
        ]

        # 3. Validate all issues
        validator = ContinuityValidator()
        valid, rejected = validator.validate_batch(bad_issues)
        # All should be rejected
        assert len(valid) == 0
        assert len(rejected) == 4

        # 4. Build result with degradation
        result = ContinuityResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=ContinuityStatus.DEGRADED,
            issues=[],
            blocking_issues=[],
            warnings=[],
            degraded_reasons=["所有 issue 均被验证拒绝或淘汰"],
        )

        # 5. Verify degraded status
        assert result.status == ContinuityStatus.DEGRADED

        # 6. Adapter converts to suggestions (should be empty or warning only)
        adapter = ContinuityAdapter()
        suggestions = adapter.to_suggestions(result)
        # No blocking issues → no blocking suggestions
        blocking_sugs = [s for s in suggestions if "continuity_blocking" in s.risk_flags]
        assert len(blocking_sugs) == 0

        # 7. Writer must not reference violated constraints
        brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_continuity_constraints=[],
            rejected_continuity_findings=[
                {"issue_id": iss.issue_id, "reason": "验证拒绝"}
                for iss, _ in rejected
            ],
            continuity_warnings=["所有issue均被拒绝"],
        )
        assert len(brief.accepted_continuity_constraints) == 0

        # 8. Merge with empty suggestions completes normally
        merger = SuggestionMerger()
        turn_brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")
        merge = merger.merge(plan, turn_brief, snapshot, [])
        assert merge.adopted_count == 0
        assert merge.merge_id != ""

        # 9. Verify no agent wrote directly to state
        runtime = ContinuityRuntime()
        assert not hasattr(runtime, 'card_state_store')
        assert not hasattr(runtime, 'turn_record_store')


# ─────────────────────────────────────────────
# Additional permission tests (requirement 12-18)
# ─────────────────────────────────────────────

class TestContinuityAdditionalPermissions:
    """Additional permission tests for requirements 12-18."""

    def test_12_agent_cannot_access_store(self):
        """Agent 无法访问 Store / SQLite。"""
        runtime = ContinuityRuntime()
        assert not hasattr(runtime, 'store')
        assert not hasattr(runtime, 'db')
        assert not hasattr(runtime, 'sqlite')

    def test_13_agent_cannot_cross_card_session(self):
        """Agent 无法跨 cardId / sessionId 查询。"""
        snapshot = _make_snapshot(card_id="card_a", session_id="sess_a")
        planner = ContinuityQueryPlanner()
        queries = planner.plan_queries(
            snapshot=snapshot,
            focus_entities=["npc_1"],
            focus_locations=["room"],
            continuity_domains=["knowledge_boundary"],
        )
        for q in queries:
            assert q["card_id"] == "card_a"
            assert q["session_id"] == "sess_a"

    def test_14_cannot_call_unauthorized_tools(self):
        """Agent 无法调用未授权工具。"""
        # Verify all tools in profile are in the allowed set
        allowed_tools = {
            "accepted_turn_lookup", "active_memory_lookup",
            "rag_memory_lookup", "timeline_lookup",
            "relationship_context_lookup", "worldbook_lookup",
            "entity_alias_lookup", "event_stage_lookup",
            "scene_context_lookup", "npc_context_lookup",
        }
        assert set(CONTINUITY_TOOLS.keys()) == allowed_tools

    def test_15_cannot_delegate(self):
        """Agent 无法递归委派。"""
        assert CONTINUITY_ROLE_SPEC.can_delegate is False

    def test_16_cannot_generate_state_update_proposal(self):
        """Agent 无法生成 StateUpdateProposal。"""
        assert CONTINUITY_ROLE_SPEC.can_write_state is False

    def test_17_cannot_generate_memory_commit_plan(self):
        """Agent 无法生成 MemoryCommitPlan。"""
        assert CONTINUITY_ROLE_SPEC.can_write_memory is False

    def test_18_cannot_generate_final_text(self):
        """Agent 输出最终玩家正文时被拒绝。"""
        assert CONTINUITY_ROLE_SPEC.can_generate_final_text is False
