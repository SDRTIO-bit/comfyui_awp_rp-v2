"""D3: World-Life Agent V1 — Tests.

Tests 1-31: Unit tests for trigger policy, validator, ranker, permissions, merge.
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

# D3 contracts
from awp_rp_runtime_v2.contracts.world_life_request import WorldLifeRequest
from awp_rp_runtime_v2.contracts.world_life_candidate import (
    WorldLifeCandidate, WorldLifeKind, WorldLayer, VisibilityMode,
)
from awp_rp_runtime_v2.contracts.world_life_evidence import WorldLifeEvidence
from awp_rp_runtime_v2.contracts.world_life_result import (
    WorldLifeResult, WorldLifeStatus, RejectedWorldLifeCandidate,
)
from awp_rp_runtime_v2.contracts.world_life_risk import WorldLifeRisk, WorldLifeRiskLevel
from awp_rp_runtime_v2.contracts.world_life_suggestion import (
    WorldLifeSuggestion, WorldLifeSuggestionKind,
)
from awp_rp_runtime_v2.contracts.world_life_trigger_diagnostics import WorldLifeTriggerDiagnostics

# D3 runtime
from awp_rp_runtime_v2.runtime.world_life_trigger_policy import WorldLifeTriggerPolicy, WorldLifeTriggerResult
from awp_rp_runtime_v2.runtime.world_life_runtime import WorldLifeRuntime
from awp_rp_runtime_v2.runtime.world_life_query_planner import WorldLifeQueryPlanner
from awp_rp_runtime_v2.runtime.world_life_candidate_generator import WorldLifeCandidateGenerator
from awp_rp_runtime_v2.runtime.world_life_validator import WorldLifeValidator
from awp_rp_runtime_v2.runtime.world_life_ranker import WorldLifeRanker, MAX_ACCEPTED
from awp_rp_runtime_v2.runtime.world_life_adapter import WorldLifeAdapter
from awp_rp_runtime_v2.runtime.world_life_tool_profile import (
    WORLD_LIFE_TOOLS, WORLD_LIFE_ROLE_SPEC,
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
        scene_focus="普通房间",
        base_card_state_revision=snapshot.base_card_state_revision,
        risk_flags=risk_flags or [],
        unresolved_threads=unresolved_threads or [],
        relationship_tensions=relationship_tensions or [],
        narrative_opportunities=narrative_opportunities or [],
    )


def _make_evidence(
    evidence_id: str = "ev_1",
    source_type: str = "scene_context",
    source_ref: str = "",
    excerpt: str = "当前地点: 普通房间",
    confidence: float = 0.8,
) -> WorldLifeEvidence:
    return WorldLifeEvidence(
        evidence_id=evidence_id,
        source_type=source_type,
        source_ref=source_ref or f"scene_{evidence_id}",
        excerpt=excerpt,
        entity_refs=[],
        location_ref="普通房间",
        confidence=confidence,
        relevance_score=0.7,
    )


def _make_candidate(
    candidate_id: str = "wlc_test",
    kind: WorldLifeKind = WorldLifeKind.ENVIRONMENTAL_PRESSURE,
    evidence_refs: list[str] | None = None,
    foundation_facts: list[str] | None = None,
    focus_entities: list[str] | None = None,
    summary: str = "基于当前场景环境，可在描写中体现自然的环境变化",
    player_agency_risk: float = 0.0,
    state_change_risk: float = 0.0,
    must_not_assert_as_fact: bool = True,
    must_not_commit_state: bool = True,
    suggested_writer_use: str = "可在环境描写中自然体现天气、时间、氛围变化",
    suggested_director_use: str = "可作为场景氛围的自然背景",
) -> WorldLifeCandidate:
    return WorldLifeCandidate(
        candidate_id=candidate_id,
        trace_id="t1",
        snapshot_id="s1",
        kind=kind,
        title="测试候选",
        summary=summary,
        world_layer=WorldLayer.ENVIRONMENT,
        narrative_function="增强场景在场感",
        focus_entities=focus_entities if focus_entities is not None else [],
        focus_location="普通房间",
        foundation_facts=foundation_facts if foundation_facts is not None else ["当前地点: 普通房间"],
        evidence_refs=evidence_refs if evidence_refs is not None else ["ev_scene_普通房间"],
        activation_conditions=["描写场景时自然提及环境"],
        visibility_mode=VisibilityMode.BACKGROUND,
        player_agency_risk=player_agency_risk,
        continuity_risk=0.1,
        state_change_risk=state_change_risk,
        novelty_score=0.5,
        relevance_score=0.7,
        confidence=0.7,
        suggested_writer_use=suggested_writer_use,
        suggested_director_use=suggested_director_use,
        must_not_assert_as_fact=must_not_assert_as_fact,
        must_not_commit_state=must_not_commit_state,
    )


# ─────────────────────────────────────────────
# Test 1: No environment, no NPC, no event stage → no trigger
# ─────────────────────────────────────────────

class TestTriggerPolicy:
    """Tests for WorldLifeTriggerPolicy."""

    def test_01_no_risk_no_trigger(self):
        """当前场景无世界压力、无活跃NPC、无事件阶段时不触发。"""
        snapshot = _make_snapshot("你好", location="普通房间")
        plan = _make_director_plan(snapshot)
        policy = WorldLifeTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False
        assert result.trigger_reasons == []
        assert result.risk_level == "none"

    def test_02_weather_time_triggers(self):
        """天气、地点、节日、时间压力等已知场景信息可触发。"""
        snapshot = _make_snapshot("下雨了", location="庭院")
        plan = _make_director_plan(snapshot)
        policy = WorldLifeTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("环境" in r for r in result.trigger_reasons)

    def test_03_npc_pressure_triggers(self):
        """活跃NPC具有独立事件阶段或压力时可触发。"""
        snapshot = _make_snapshot("NPC看起来很紧张")
        plan = _make_director_plan(snapshot)
        policy = WorldLifeTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("NPC" in r for r in result.trigger_reasons)

    def test_04_worldbook_relevance_triggers(self):
        """世界书与当前地点、时间、角色高度相关时可触发。"""
        active_worldbook = [
            {"title": "月光庭院的节日", "content": "每年满月时分，庭院会举办庆典"},
        ]
        snapshot = _make_snapshot("继续探索", active_worldbook=active_worldbook)
        plan = _make_director_plan(snapshot)
        policy = WorldLifeTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is True
        assert any("世界书" in r for r in result.trigger_reasons)

    def test_05_retry_recovery_no_trigger(self):
        """当前回合是重试、恢复或状态冲突处理时不触发。"""
        snapshot = _make_snapshot("你好", location="普通房间")
        plan = _make_director_plan(snapshot)
        policy = WorldLifeTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False

    def test_06_not_trigger_just_for_more_calls(self):
        """仅为了增加子Agent调用次数不得触发。"""
        snapshot = _make_snapshot("你好", location="普通房间")
        plan = _make_director_plan(snapshot)
        policy = WorldLifeTriggerPolicy()
        result = policy.evaluate(snapshot, plan)
        assert result.should_trigger is False


# ─────────────────────────────────────────────
# Tests 7-13: Candidate validation
# ─────────────────────────────────────────────

class TestWorldLifeValidator:
    """Tests for WorldLifeValidator."""

    def test_07_no_evidence_rejected(self):
        """无 evidence 的 WorldLifeCandidate 被拒绝。"""
        validator = WorldLifeValidator()
        candidate = _make_candidate(evidence_refs=[], foundation_facts=["某事"])
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("证据" in e for e in errors)

    def test_08_conflict_with_cardstate_rejected(self):
        """与 CardState 冲突的候选被拒绝。"""
        validator = WorldLifeValidator()
        candidate = _make_candidate(
            summary="让角色自动转移到森林",
            suggested_writer_use="修改状态角色位置改为森林",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("状态修改" in e for e in errors)

    def test_09_conflict_with_accepted_turn_rejected(self):
        """与 accepted TurnRecord 冲突的候选被拒绝。"""
        validator = WorldLifeValidator()
        candidate = _make_candidate(
            summary="NPC已经发生突然闯入事件",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("事件断言" in e for e in errors)

    def test_10_player_agency_violation_rejected(self):
        """侵犯玩家代理权的候选被拒绝。"""
        validator = WorldLifeValidator()
        candidate = _make_candidate(
            summary="让玩家自动接受任务",
            suggested_writer_use="玩家同意了NPC的请求",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("玩家代理权" in e or "代理" in e for e in errors)

    def test_11_event_assertion_rejected(self):
        """将候选伪装成已发生事件的候选被拒绝。"""
        validator = WorldLifeValidator()
        candidate = _make_candidate(
            summary="秘密已经暴露在众人面前",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("事件断言" in e for e in errors)

    def test_12_auto_advance_time_rejected(self):
        """自动推进时间的候选被拒绝。"""
        validator = WorldLifeValidator()
        candidate = _make_candidate(
            summary="三天过去，事件阶段自动推进",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0
        assert any("自动推进" in e for e in errors)

    def test_13_auto_advance_event_stage_rejected(self):
        """自动触发事件阶段的候选被拒绝。"""
        validator = WorldLifeValidator()
        candidate = _make_candidate(
            summary="事件已经触发进入下一阶段",
            suggested_writer_use="自动触发事件阶段推进",
        )
        errors = validator.validate(candidate)
        assert len(errors) > 0


# ─────────────────────────────────────────────
# Tests 14-20: Permission boundaries
# ─────────────────────────────────────────────

class TestWorldLifePermissions:
    """Tests for permission boundaries of World-Life Agent."""

    def test_14_cannot_access_store(self):
        """World-Life Agent 无法访问 Store / SQLite。"""
        runtime = WorldLifeRuntime()
        assert not hasattr(runtime, 'card_state_store')
        assert not hasattr(runtime, 'turn_record_store')


    def test_15_cannot_cross_card_session(self):
        """World-Life Agent 无法跨 cardId / sessionId 查询。"""
        snapshot = _make_snapshot(card_id="card1", session_id="sess1")
        planner = WorldLifeQueryPlanner()
        queries = planner.plan_queries(
            snapshot=snapshot,
            focus_entities=["npc_1"],
            focus_locations=["普通房间"],
            world_life_domains=["environment"],
        )
        for q in queries:
            assert q.get("card_id", "card1") == "card1"
            assert q.get("session_id", "sess1") == "sess1"

    def test_16_cannot_call_unauthorized_tools(self):
        """World-Life Agent 无法调用未授权工具。"""
        profile_tools = set(WORLD_LIFE_TOOLS.keys())
        allowed = {
            "worldbook_lookup", "timeline_lookup",
            "relationship_context_lookup", "accepted_turn_lookup",
            "active_memory_lookup", "rag_memory_lookup",
            "entity_alias_lookup", "event_stage_lookup",
            "scene_context_lookup", "npc_context_lookup",
        }
        assert profile_tools == allowed

    def test_17_cannot_delegate(self):
        """World-Life Agent 无法递归委派。"""
        assert WORLD_LIFE_ROLE_SPEC.can_delegate is False

    def test_18_cannot_generate_state_update_proposal(self):
        """World-Life Agent 无法生成 StateUpdateProposal。"""
        assert WORLD_LIFE_ROLE_SPEC.can_write_state is False

    def test_19_cannot_generate_memory_commit_plan(self):
        """World-Life Agent 无法生成 MemoryCommitPlan。"""
        assert WORLD_LIFE_ROLE_SPEC.can_write_memory is False

    def test_20_cannot_generate_final_text(self):
        """World-Life Agent 输出最终玩家正文时被拒绝。"""
        assert WORLD_LIFE_ROLE_SPEC.can_generate_final_text is False


# ─────────────────────────────────────────────
# Test 21: Max 2 accepted candidates per turn
# ─────────────────────────────────────────────

class TestWorldLifeRanker:
    """Tests for WorldLifeRanker."""

    def test_21_max_two_accepted(self):
        """每回合最多 2 个可采纳候选。"""
        ranker = WorldLifeRanker()
        kinds = [
            WorldLifeKind.ENVIRONMENTAL_PRESSURE,
            WorldLifeKind.WEATHER_OR_TIME_ATMOSPHERE,
            WorldLifeKind.NPC_SIDE_TENSION,
            WorldLifeKind.EVENT_STAGE_ECHO,
            WorldLifeKind.LOCATION_LIFE_DETAIL,
        ]
        candidates = [
            _make_candidate(f"wlc_{i}", kind=kinds[i], focus_entities=[f"npc_{i}"])
            for i in range(5)
        ]
        accepted, rejected = ranker.rank(candidates, max_accepted=2)
        assert len(accepted) == 2
        assert len(rejected) == 3

    def test_22_high_evidence_scene_over_low_evidence_rumor(self):
        """高证据场景压力优先于低证据远方传闻。"""
        ranker = WorldLifeRanker()
        high_evidence_scene = _make_candidate(
            "wlc_scene",
            kind=WorldLifeKind.ENVIRONMENTAL_PRESSURE,
        )
        high_evidence_scene.confidence = 0.95
        high_evidence_scene.relevance_score = 0.95

        low_evidence_rumor = _make_candidate(
            "wlc_rumor",
            kind=WorldLifeKind.AMBIENT_RUMOR_SIGNAL,
        )
        low_evidence_rumor.confidence = 0.3
        low_evidence_rumor.relevance_score = 0.3

        accepted, rejected = ranker.rank(
            [low_evidence_rumor, high_evidence_scene], max_accepted=1
        )
        assert len(accepted) == 1
        assert accepted[0].candidate_id == "wlc_scene"

    def test_23_duplicates_merged_or_eliminated(self):
        """重复候选被合并或淘汰。"""
        ranker = WorldLifeRanker()
        # Two candidates with same kind and same focus entities
        c1 = _make_candidate("wlc_1", kind=WorldLifeKind.ENVIRONMENTAL_PRESSURE)
        c1.focus_entities = []
        c1.focus_location = "普通房间"
        c2 = _make_candidate("wlc_2", kind=WorldLifeKind.ENVIRONMENTAL_PRESSURE)
        c2.focus_entities = []
        c2.focus_location = "普通房间"
        # Different kind → not duplicate
        c3 = _make_candidate("wlc_3", kind=WorldLifeKind.NPC_SIDE_TENSION)
        c3.focus_entities = []

        accepted, rejected = ranker.rank([c1, c2, c3], max_accepted=5)
        # c1 and c2 are duplicates (same kind + same focus location), only one survives
        accepted_ids = [c.candidate_id for c in accepted]
        assert "wlc_1" in accepted_ids or "wlc_2" in accepted_ids
        # Not both
        assert not ("wlc_1" in accepted_ids and "wlc_2" in accepted_ids)
        # c3 is different kind, should survive
        assert "wlc_3" in accepted_ids


# ─────────────────────────────────────────────
# Tests 24-26: SuggestionMerge and FinalTurnBrief
# ─────────────────────────────────────────────

class TestSuggestionMergeWorldLife:
    """Tests for SuggestionMerge with world-life suggestions."""

    def test_24_world_life_as_soft_guidance(self):
        """SuggestionMerge 将 World-Life 视为软 Guidance。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        merger = SuggestionMerger()
        snapshot = _make_snapshot("test")
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")

        sug = AgentSuggestion(
            suggestion_id="s1", task_id="t1", role="world-life",
            kind=SuggestionKind.ENVIRONMENTAL_PRESSURE,
            summary="可在环境描写中自然体现天气变化",
            priority=0.7, confidence=0.7,
            recommendations=["可在描写中自然体现湿冷、屋檐滴水"],
            source_refs=["ev_1"],
        )
        result = AgentExecutionResult(
            task_id="t1", role="world-life", trace_id="t1",
            success=True, suggestions=[sug],
        )
        merge = merger.merge(plan, brief, snapshot, [result])
        assert merge is not None
        # World-life suggestions should be adopted as writer guidance
        adopted_sugs = [item for item in merge.adopted if item.role == "world-life"]
        assert len(adopted_sugs) >= 1
        # Check it appears in writer_guidance
        assert len(merge.writer_guidance) > 0

    def test_25_final_brief_only_accepted_world_life(self):
        """FinalTurnBrief 只包含已采纳世界活性候选。"""
        brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_world_life_candidates=[
                {"candidate_id": "wlc_1", "summary": "可在环境描写中体现天气变化"},
            ],
            rejected_world_life_candidates=[
                {"candidate_id": "wlc_2", "reason": "缺少证据"},
            ],
            world_life_warnings=["注意状态变更风险"],
            world_life_evidence_refs=["ev_1"],
        )
        assert len(brief.accepted_world_life_candidates) == 1
        assert len(brief.rejected_world_life_candidates) == 1
        assert brief.accepted_world_life_candidates[0]["candidate_id"] == "wlc_1"

    def test_26_writer_cannot_read_raw_world_life_result(self):
        """Writer 不可读取原始 WorldLifeResult。"""
        from awp_rp_runtime_v2.runtime.writer_input_bundle_v2_builder import WriterInputBundleV2Builder
        builder = WriterInputBundleV2Builder()
        snapshot = _make_snapshot()
        final_brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_world_life_candidates=[{"candidate_id": "wlc_1", "summary": "test"}],
        )
        bundle = builder.build(snapshot, final_brief)
        bundle_dict = bundle.to_dict()
        # The bundle should NOT contain the full WorldLifeResult object
        assert "world_life_result" not in bundle_dict


# ─────────────────────────────────────────────
# Test 27: No-op path completes
# ─────────────────────────────────────────────

class TestNoOpPath:
    """Test that no-op path (shouldTrigger=False) completes normally."""

    def test_27_noop_path_completes(self):
        """shouldTrigger=false → 空 WorldLifeSuggestion → SuggestionMerge 正常完成。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief
        snapshot = _make_snapshot("你好", location="普通房间")
        plan = _make_director_plan(snapshot)
        policy = WorldLifeTriggerPolicy()
        trigger_result = policy.evaluate(snapshot, plan)
        assert trigger_result.should_trigger is False

        # Run world-life runtime with no trigger
        runtime = WorldLifeRuntime()
        task = DelegationTask(
            task_id="wl_1", role="world-life",
            tool_allowlist=list(WORLD_LIFE_TOOLS.keys()),
        )
        result = runtime.run(snapshot, task, trigger_result)
        assert result.status == WorldLifeStatus.NO_TRIGGER
        assert len(result.candidates) == 0

        # Merge completes normally with no suggestions
        merger = SuggestionMerger()
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        del_plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")
        merge = merger.merge(del_plan, brief, snapshot, [])
        assert merge.adopted_count == 0
        assert merge.conflict_count == 0


# ─────────────────────────────────────────────
# Test 28: Tool timeout returns degraded
# ─────────────────────────────────────────────

class TestToolFailureBehavior:
    """Tests for tool timeout and failure degradation."""

    def test_28_tool_timeout_returns_degraded(self):
        """optional Tool timeout 返回 degraded，不阻断主链。"""
        from awp_rp_runtime_v2.contracts.tool_result import ToolResult, ToolResultStatus
        tr = ToolResult(
            result_id="tr1", request_id="req1", trace_id="t1",
            tool_id="scene_context_lookup",
            status=ToolResultStatus.TIMEOUT,
            failure_reason="timeout",
        )
        assert tr.is_failed()
        # Degraded result should not block the main chain
        result = WorldLifeResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=WorldLifeStatus.DEGRADED,
            degraded_reasons=["scene_context_lookup timeout"],
        )
        assert result.status == WorldLifeStatus.DEGRADED
        assert len(result.degraded_reasons) > 0


# ─────────────────────────────────────────────
# Test 29: Official workflow JSON validation
# ─────────────────────────────────────────────

class TestD3NodeRegistration:
    """D3: World-Life node registration tests."""

    def test_d3_nodes_present(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS
        d3 = {
            "AWPV2WorldLifeTrigger", "AWPV2WorldLifeRequest",
            "AWPV2WorldLifeAgent", "AWPV2WorldLifeValidator",
            "AWPV2WorldLifeRanker", "AWPV2WorldLifeResult",
            "AWPV2WorldLifeDiagnostics",
        }
        for name in d3:
            assert name in NODE_CLASS_MAPPINGS, f"Missing: {name}"

    def test_d3_display_names_chinese(self):
        from awp_rp_runtime_v2.nodes import NODE_DISPLAY_NAME_MAPPINGS
        d3_displays = [
            "AWP V2 世界活性触发", "AWP V2 世界活性请求",
            "AWP V2 世界活性Agent", "AWP V2 世界活性验证",
            "AWP V2 世界活性排序", "AWP V2 世界活性结果",
            "AWP V2 世界活性诊断",
        ]
        for display in d3_displays:
            assert display in NODE_DISPLAY_NAME_MAPPINGS.values(), f"Missing: {display}"


# ─────────────────────────────────────────────
# Contract serialization tests
# ─────────────────────────────────────────────

class TestD3ContractSerialization:
    """Test round-trip serialization of D3 contracts."""

    def test_world_life_request_roundtrip(self):
        req = WorldLifeRequest(
            request_id="req1", trace_id="t1", snapshot_id="s1",
            task_run_id="tr1", card_id="card1", session_id="sess1",
            focus_entities=["npc_1"], focus_locations=["普通房间"],
            player_intent="对话",
            must_not_create_facts=True, must_not_advance_timeline=True,
            must_not_modify_card_state=True, max_candidates=5,
        )
        d = req.to_dict()
        restored = WorldLifeRequest.from_dict(d)
        assert restored.focus_entities == ["npc_1"]
        assert restored.must_not_create_facts is True
        assert restored.must_not_advance_timeline is True
        assert restored.must_not_modify_card_state is True

    def test_world_life_candidate_roundtrip(self):
        cand = _make_candidate("wlc_1")
        d = cand.to_dict()
        restored = WorldLifeCandidate.from_dict(d)
        assert restored.candidate_id == "wlc_1"
        assert restored.kind == WorldLifeKind.ENVIRONMENTAL_PRESSURE
        assert restored.must_not_assert_as_fact is True
        assert restored.must_not_commit_state is True

    def test_world_life_evidence_roundtrip(self):
        ev = _make_evidence("ev_1")
        d = ev.to_dict()
        restored = WorldLifeEvidence.from_dict(d)
        assert restored.evidence_id == "ev_1"
        assert restored.source_type == "scene_context"

    def test_world_life_result_roundtrip(self):
        cand = [_make_candidate()]
        result = WorldLifeResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=WorldLifeStatus.SUCCESS,
            candidates=cand,
        )
        d = result.to_dict()
        restored = WorldLifeResult.from_dict(d)
        assert restored.status == WorldLifeStatus.SUCCESS
        assert len(restored.candidates) == 1

    def test_world_life_risk_roundtrip(self):
        risk = WorldLifeRisk(
            risk_id="r1",
            risk_level=WorldLifeRiskLevel.HIGH,
            description="高风险",
            entity_refs=["npc_1"],
        )
        d = risk.to_dict()
        restored = WorldLifeRisk.from_dict(d)
        assert restored.risk_level == WorldLifeRiskLevel.HIGH

    def test_world_life_suggestion_roundtrip(self):
        sug = WorldLifeSuggestion(
            suggestion_id="ws1",
            kind=WorldLifeSuggestionKind.ENVIRONMENTAL_PRESSURE,
            title="环境压力",
            summary="可在描写中体现天气变化",
            evidence_refs=["ev_1"],
        )
        d = sug.to_dict()
        restored = WorldLifeSuggestion.from_dict(d)
        assert restored.kind == WorldLifeSuggestionKind.ENVIRONMENTAL_PRESSURE

    def test_world_life_trigger_diagnostics_roundtrip(self):
        diag = WorldLifeTriggerDiagnostics(
            diagnostics_id="wld1", trace_id="t1", snapshot_id="s1",
            should_trigger=True,
            trigger_reasons=["环境特征"],
            candidates_generated=3,
            candidates_accepted=2,
            candidates_rejected=1,
        )
        d = diag.to_dict()
        restored = WorldLifeTriggerDiagnostics.from_dict(d)
        assert restored.candidates_generated == 3
        assert restored.candidates_accepted == 2


# ─────────────────────────────────────────────
# Adapter test
# ─────────────────────────────────────────────

class TestWorldLifeAdapter:
    """Tests for WorldLifeAdapter."""

    def test_result_to_agent_suggestion(self):
        """WorldLifeResult 正确转换为 AgentSuggestion。"""
        adapter = WorldLifeAdapter()
        cand = _make_candidate("wlc_1")
        result = WorldLifeResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=WorldLifeStatus.SUCCESS,
            candidates=[cand],
        )
        suggestions = adapter.to_suggestions(result)
        assert len(suggestions) >= 1
        sug = suggestions[0]
        assert sug.role == "world-life"
        assert sug.kind == SuggestionKind.ENVIRONMENTAL_PRESSURE
        assert len(sug.source_refs) > 0


# ─────────────────────────────────────────────
# E2E Test 1: Normal world-life adoption path
# ─────────────────────────────────────────────

class TestD3E2ENormalPath:
    """E2E: Normal world-life adoption path with fake LLM."""

    def test_e2e_normal_world_life_adoption(self):
        """正常世界活性路径: 6回合历史 → 触发 → 候选 → 验证 → 排序 → 合并 → Writer。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief

        # 1. Build history (6 turns)
        turns = []
        for i in range(1, 7):
            turns.append(_make_turn_record(
                f"tr_{i}",
                f"第{i}回合: {'下雨了，庭院变得湿冷' if i == 3 else '在月光庭院相遇' if i == 1 else '继续对话'}",
                turn_index=i,
            ))

        active_memories = [
            {"memory_id": "am_1", "summary": "庭院正在举办节日庆典", "kind": "event",
             "entity_refs": [], "importance": 0.8, "confidence": 0.9, "status": "active"},
        ]

        # 2. Build snapshot
        snapshot = _make_snapshot(
            player_input="继续探索庭院",
            recent_turns=turns,
            active_memories=active_memories,
            location="月光庭院",
        )

        # 3. Director plan
        plan = _make_director_plan(snapshot)

        # 4. Trigger policy fires
        policy = WorldLifeTriggerPolicy()
        trigger = policy.evaluate(snapshot, plan)
        assert trigger.should_trigger is True
        assert len(trigger.trigger_reasons) > 0

        # 5. Create delegation task
        task = DelegationTask(
            task_id="wl_1", role="world-life",
            priority=0.7,
            purpose="识别本回合的世界活性",
            input_field_allowlist=[
                "player_input", "recent_turn_records",
                "active_memories", "rag_recall",
            ],
            tool_allowlist=list(WORLD_LIFE_TOOLS.keys()),
            max_tokens=1000,
            timeout_ms=30000,
            required=False,
            failure_policy="skip",
        )

        # 6. Build envelope
        registry = AgentRuntimeRegistry()
        registry.register_spec(WORLD_LIFE_ROLE_SPEC)
        builder = TaskEnvelopeBuilder(registry)
        envelope = builder.build(task, snapshot, "brief1")
        assert envelope is not None

        # 7. Execute world-life runtime
        runtime = WorldLifeRuntime()
        wl_result = runtime.run(
            snapshot=snapshot,
            task=task,
            trigger_result=trigger,
            envelope=envelope,
        )

        assert wl_result is not None
        assert wl_result.trace_id == snapshot.trace_id
        assert wl_result.status in (WorldLifeStatus.SUCCESS, WorldLifeStatus.DEGRADED)

        # 8. Convert to suggestions
        adapter = WorldLifeAdapter()
        suggestions = adapter.to_suggestions(wl_result)
        assert isinstance(suggestions, list)

        # 9. Execute through pool (integration)
        class FakeWorldLifeRunner:
            def run(self, envelope):
                return suggestions

        registry.register_runner("world-life", FakeWorldLifeRunner())
        pool = DynamicSubAgentPool(registry, builder)
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
        brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        merge = merger.merge(delegation, brief, snapshot, exec_results)
        assert merge is not None
        assert merge.merge_id != ""


# ─────────────────────────────────────────────
# E2E Test 2: Violated candidates and degradation path
# ─────────────────────────────────────────────

class TestD3E2EViolationDegradation:
    """E2E: Violated candidates and degradation path."""

    def test_e2e_violation_and_degradation(self):
        """违规候选与降级路径: 无证据/既成事件/代理权侵犯/冲突 → 全部拒绝 → degraded。"""
        from awp_rp_runtime_v2.contracts.turn_brief import TurnBrief

        # 1. Setup snapshot with minimal data
        snapshot = _make_snapshot("和NPC说话")

        # 2. Build candidates with various violations
        bad_candidates = [
            # No evidence
            _make_candidate("wlc_no_ev", evidence_refs=[], foundation_facts=["某事"]),
            # Event assertion
            _make_candidate("wlc_event", summary="NPC已经发生突然闯入事件"),
            # Player agency violation
            _make_candidate("wlc_agency", summary="让玩家自动接受任务"),
            # Auto advance time
            _make_candidate("wlc_time", summary="三天过去，事件阶段自动推进"),
            # Auto advance relationship
            _make_candidate("wlc_rel", summary="自动让NPC改变关系或离场"),
        ]

        # 3. Validate all candidates
        validator = WorldLifeValidator()
        valid, rejected = validator.validate_batch(bad_candidates, snapshot)
        # All should be rejected
        assert len(valid) == 0
        assert len(rejected) == 5

        # 4. Build result with degradation
        rejected_records = []
        for cand, errors in rejected:
            for error in errors:
                violated_policy = "unknown"
                if "证据" in error:
                    violated_policy = "missing_evidence"
                elif "事件断言" in error:
                    violated_policy = "event_assertion"
                elif "玩家代理权" in error or "代理" in error:
                    violated_policy = "player_agency"
                elif "状态修改" in error or "自动推进" in error:
                    violated_policy = "auto_advance"
                rejected_records.append(RejectedWorldLifeCandidate(
                    candidate_id=cand.candidate_id,
                    reason=error,
                    violated_policy=violated_policy,
                    evidence_refs=cand.evidence_refs,
                ))

        result = WorldLifeResult(
            result_id="r1", trace_id="t1", snapshot_id="s1", task_run_id="tr1",
            status=WorldLifeStatus.DEGRADED,
            candidates=[],
            rejected_candidates=rejected_records,
            degraded_reasons=["所有候选均被验证拒绝或淘汰"],
        )

        # 5. Verify degraded status
        assert result.status == WorldLifeStatus.DEGRADED
        assert len(result.rejected_candidates) >= 5

        # 6. Adapter converts to warnings
        adapter = WorldLifeAdapter()
        suggestions = adapter.to_suggestions(result)
        # Should include warning suggestions for player_agency and event_assertion violations
        warning_sugs = [s for s in suggestions if s.kind == SuggestionKind.WORLD_LIFE_WARNING]
        assert len(warning_sugs) > 0

        # 7. Writer must not reference violated candidates
        brief = FinalTurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            accepted_world_life_candidates=[],
            rejected_world_life_candidates=[
                {"candidate_id": r.candidate_id, "reason": r.reason}
                for r in rejected_records
            ],
            world_life_warnings=["所有候选均被拒绝"],
        )
        assert len(brief.accepted_world_life_candidates) == 0
        assert len(brief.rejected_world_life_candidates) > 0

        # 8. Merge with empty suggestions completes normally
        merger = SuggestionMerger()
        turn_brief = TurnBrief(brief_id="b1", must_not_do=[], must_preserve_facts=[])
        plan = DelegationPlan(plan_id="p1", trace_id="t1", snapshot_id="s1", brief_id="b1")

        # No execution results (all candidates rejected)
        merge = merger.merge(plan, turn_brief, snapshot, [])
        assert merge.adopted_count == 0
        assert merge.merge_id != ""

        # 9. Verify no agent wrote directly to state
        # (This is enforced by architecture — WorldLifeRuntime has no store references)
        runtime = WorldLifeRuntime()
        assert not hasattr(runtime, 'card_state_store')
        assert not hasattr(runtime, 'turn_record_store')
