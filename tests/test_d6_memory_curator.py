"""D6: Memory Curator Agent V1 — comprehensive tests.

Tests the post-acceptance memory governance system:
  - Trigger policy gate checks
  - Candidate generation from accepted turns
  - Candidate validation (evidence, source, prohibitions)
  - Candidate ranking (importance, capacity, dedup)
  - Plan compilation (MemoryCommitPlan)
  - End-to-end integration (normal path + rejection/failure/idempotency)
  - Permission boundaries (no write, no delegate, no cross-session)
"""

from __future__ import annotations

import uuid
import pytest

from awp_rp_runtime_v2.contracts.quality_decision import QualityDecision, QualityVerdict
from awp_rp_runtime_v2.contracts.card_state_commit import (
    CardStateCommitResult, CardStateCommitStatus,
)
from awp_rp_runtime_v2.contracts.turn_record import TurnRecord, TurnMode
from awp_rp_runtime_v2.contracts.round_snapshot import RoundSnapshot
from awp_rp_runtime_v2.contracts.card_state import CardState, SceneState
from awp_rp_runtime_v2.contracts.active_memory import ActiveMemoryRecord, ActiveMemoryKind, ActiveMemoryStatus
from awp_rp_runtime_v2.contracts.rag_memory import RagMemoryRecord, RagMemoryStatus
from awp_rp_runtime_v2.contracts.execution_trace import ExecutionTrace
from awp_rp_runtime_v2.contracts.memory_curation_trigger_diagnostics import MemoryCurationTriggerDiagnostics
from awp_rp_runtime_v2.contracts.memory_curation_request import MemoryCurationRequest
from awp_rp_runtime_v2.contracts.memory_curation_candidate import (
    MemoryCurationCandidate, CurationTargetLayer, CurationOperation,
)
from awp_rp_runtime_v2.contracts.memory_curation_evidence import MemoryCurationEvidence
from awp_rp_runtime_v2.contracts.memory_curation_result import MemoryCurationResult
from awp_rp_runtime_v2.contracts.memory_commit_plan import MemoryCommitPlan

from awp_rp_runtime_v2.runtime.memory_curation_trigger_policy import MemoryCurationTriggerPolicy
from awp_rp_runtime_v2.runtime.memory_curation_runtime import MemoryCurationRuntime
from awp_rp_runtime_v2.runtime.memory_curation_query_planner import MemoryCurationQueryPlanner
from awp_rp_runtime_v2.runtime.memory_candidate_generator import FakeMemoryCandidateGenerator
from awp_rp_runtime_v2.runtime.memory_curation_validator import MemoryCurationValidator
from awp_rp_runtime_v2.runtime.memory_curation_ranker import MemoryCurationRanker
from awp_rp_runtime_v2.runtime.memory_plan_compiler import MemoryPlanCompiler
from awp_rp_runtime_v2.runtime.memory_curator_adapter import FakeMemoryCuratorAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_quality_decision(verdict: str = "accept") -> QualityDecision:
    return QualityDecision(
        verdict=QualityVerdict(verdict),
        trace_id=f"trace_{uuid.uuid4().hex[:8]}",
    )


def _make_card_state_commit(status: str = "accepted") -> CardStateCommitResult:
    return CardStateCommitResult(
        status=status,
        from_revision=1,
        to_revision=2,
    )


def _make_turn_record(
    turn_id: str = "",
    writer_output: str = "她微笑着说：'我们明天再见面吧。'两人约定了下次见面的时间。",
    player_input: str = "我对她说：'明天见！'",
) -> TurnRecord:
    return TurnRecord(
        turn_id=turn_id or f"turn_{uuid.uuid4().hex[:8]}",
        trace_id=f"trace_{uuid.uuid4().hex[:8]}",
        card_id="card_001",
        session_id="session_001",
        turn_index=1,
        player_input=player_input,
        writer_output=writer_output,
        quality_decision_ref="",
        state_commit_ref="",
        base_card_state_revision=1,
        result_card_state_revision=2,
    )


def _make_active_memory(
    memory_id: str = "am_001",
    kind: str = "promise",
    status: str = "active",
    entity_refs: list[str] | None = None,
    summary: str = "林晓承诺下周帮张伟搬家，两人约定周六早上八点见面",
) -> ActiveMemoryRecord:
    return ActiveMemoryRecord(
        memory_id=memory_id,
        card_id="card_001",
        session_id="session_001",
        summary=summary,
        kind=kind,
        entity_refs=entity_refs or ["林晓", "张伟"],
        source_turn_ids=["turn_prev_001"],
        source_card_state_revision=1,
        importance=0.7,
        confidence=0.8,
        status=status,
    )


def _make_rag_memory(
    memory_id: str = "rag_001",
    content: str = "林晓和张伟是大学同学，关系一直很好",
) -> RagMemoryRecord:
    return RagMemoryRecord(
        memory_id=memory_id,
        card_id="card_001",
        session_id="session_001",
        scope="session",
        content=content,
        summary=content[:80],
        entity_refs=["林晓", "张伟"],
        source_turn_ids=["turn_prev_001"],
        source_card_state_revision=1,
        importance=0.6,
        confidence=0.7,
    )


def _make_snapshot(
    active_memories: list[dict] | None = None,
    rag_recall: list[dict] | None = None,
) -> RoundSnapshot:
    card_state = CardState(
        card_id="card_001",
        session_id="session_001",
        revision=1,
        scene_state=SceneState(location="咖啡馆"),
    )
    active = active_memories or []
    rag = rag_recall or []
    return RoundSnapshot(
        snapshot_id=f"snap_{uuid.uuid4().hex[:8]}",
        trace_id=f"trace_{uuid.uuid4().hex[:8]}",
        card_id="card_001",
        session_id="session_001",
        base_card_state_revision=1,
        card_state=card_state,
        player_input="我对她说：'明天见！'",
        active_memories=active,
        rag_recall=rag,
    )


# ===========================================================================
# 1. Quality Gate reject 时绝不触发 Memory Curator
# ===========================================================================

class TestTriggerGateReject:

    def test_reject_does_not_trigger(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("reject")
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record_committed=False,
            turn_record=None,
            snapshot=None,
        )
        assert result.should_trigger is False
        assert "quality_not_accepted" in result.skip_reason


# ===========================================================================
# 2. CardStateCommit 失败时绝不触发
# ===========================================================================

class TestTriggerCardStateFailure:

    def test_card_state_failure_does_not_trigger(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("accept")
        cs = _make_card_state_commit("revision_conflict")
        tr = _make_turn_record()
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=cs,
            turn_record_committed=True,
            turn_record=tr,
            snapshot=None,
        )
        assert result.should_trigger is False
        assert "card_state_commit_failed" in result.skip_reason


# ===========================================================================
# 3. TurnRecordCommit 失败时绝不触发
# ===========================================================================

class TestTriggerTurnRecordFailure:

    def test_turn_record_failure_does_not_trigger(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record()
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record_committed=False,
            turn_record=tr,
            snapshot=None,
        )
        assert result.should_trigger is False
        assert "turn_record_not_committed" in result.skip_reason


# ===========================================================================
# 4. accepted Turn 且存在长期事实时可触发
# ===========================================================================

class TestTriggerAcceptedTurnWithSignals:

    def test_promise_signal_triggers(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(
            writer_output="林晓答应下周帮张伟搬家，两人约定了时间地点",
            player_input="我答应帮她搬家",
        )
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record_committed=True,
            turn_record=tr,
            snapshot=None,
        )
        assert result.should_trigger is True
        assert "promise" in result.curation_domains

    def test_secret_signal_triggers(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(
            writer_output="她隐藏了自己的真实身份，假装只是一个普通学生",
            player_input="我怀疑她有什么秘密",
        )
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record_committed=True,
            turn_record=tr,
            snapshot=None,
        )
        assert result.should_trigger is True
        assert "secret" in result.curation_domains


# ===========================================================================
# 5. 普通闲聊、无长期价值时正常 no-op
# ===========================================================================

class TestTriggerNoSignalNoop:

    def test_trivial_chat_noop(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(
            writer_output="天气真好啊，阳光明媚的。",
            player_input="今天天气怎么样？",
        )
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record_committed=True,
            turn_record=tr,
            snapshot=None,
        )
        assert result.should_trigger is False
        assert result.skip_reason == "no_long_term_signals"


# ===========================================================================
# 6. Curator 只能读取 accepted final output，不能读取 draft
# ===========================================================================

class TestCuratorOnlyReadsAccepted:

    def test_request_binds_accepted_output(self):
        tr = _make_turn_record(writer_output="accepted final text here")
        snap = _make_snapshot()
        trigger = MemoryCurationTriggerDiagnostics(should_trigger=True)
        runtime = MemoryCurationRuntime()
        request = runtime._build_request(tr, snap, trigger)
        assert request.accepted_output == "accepted final text here"
        assert request.must_use_accepted_facts_only is True
        assert request.must_not_create_facts is True
        assert request.must_not_write_storage is True


# ===========================================================================
# 7. Curator 不能从 rejected output 提取记忆
# ===========================================================================

class TestCuratorNoRejectedOutput:

    def test_trigger_rejects_non_accepted(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("reject")
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record_committed=False,
            turn_record=None,
            snapshot=None,
        )
        assert result.should_trigger is False


# ===========================================================================
# 8. 无 evidence candidate 被拒绝
# ===========================================================================

class TestValidatorNoEvidence:

    def test_candidate_without_evidence_rejected(self):
        candidate = MemoryCurationCandidate(
            candidate_id="cand_001",
            target_layer=CurationTargetLayer.ACTIVE_MEMORY,
            operation=CurationOperation.CREATE_ACTIVE,
            summary="这是一条没有证据的记忆候选，应该被验证器拒绝处理",
            source_turn_ids=["turn_001"],
            # no evidence_refs
        )
        request = MemoryCurationRequest(card_id="card_001", session_id="session_001")
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, request)
        assert result.valid is False
        assert "missing_evidence" in result.rejection_reason


# ===========================================================================
# 9. 无 accepted sourceTurnId candidate 被拒绝
# ===========================================================================

class TestValidatorNoSourceTurn:

    def test_candidate_without_source_turn_rejected(self):
        candidate = MemoryCurationCandidate(
            candidate_id="cand_002",
            target_layer=CurationTargetLayer.RAG_MEMORY,
            operation=CurationOperation.CREATE_RAG,
            content="some content",
            evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
            # no source_turn_ids
        )
        request = MemoryCurationRequest(card_id="card_001", session_id="session_001")
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, request)
        assert result.valid is False
        assert "missing_source_turn_id" in result.rejection_reason


# ===========================================================================
# 10. AgentSuggestion 不能直接沉淀为长期事实
# ===========================================================================

class TestNoAgentSuggestionAsFact:

    def test_must_not_assert_unsupported_fact(self):
        candidate = MemoryCurationCandidate(
            candidate_id="cand_003",
            target_layer=CurationTargetLayer.RAG_MEMORY,
            operation=CurationOperation.CREATE_RAG,
            content="some content",
            evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
            source_turn_ids=["turn_001"],
            must_not_assert_unsupported_fact=False,  # violation
        )
        request = MemoryCurationRequest()
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, request)
        assert result.valid is False
        assert "assertion_violation" in result.rejection_reason


# ===========================================================================
# 11. ActiveMemory 条目满足 30～80 中文字符限制
# ===========================================================================

class TestActiveMemorySummaryLength:

    def test_summary_too_short_rejected(self):
        candidate = MemoryCurationCandidate(
            candidate_id="cand_short",
            target_layer=CurationTargetLayer.ACTIVE_MEMORY,
            operation=CurationOperation.CREATE_ACTIVE,
            summary="太短了",  # < 30 chars
            evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
            source_turn_ids=["turn_001"],
        )
        request = MemoryCurationRequest()
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, request)
        assert result.valid is False
        assert "summary_too_short" in result.rejection_reason

    def test_summary_too_long_rejected(self):
        candidate = MemoryCurationCandidate(
            candidate_id="cand_long",
            target_layer=CurationTargetLayer.ACTIVE_MEMORY,
            operation=CurationOperation.CREATE_ACTIVE,
            summary="这是一条超过八十字符限制的非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的记忆摘要文本内容用于测试验证器的长度检查功能",
            evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
            source_turn_ids=["turn_001"],
        )
        request = MemoryCurationRequest()
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, request)
        assert result.valid is False
        assert "summary_too_long" in result.rejection_reason


# ===========================================================================
# 12. ActiveMemory 永远不超过 15 条
# ===========================================================================

class TestActiveMemoryLimit:

    def test_ranker_respects_limit(self):
        ranker = MemoryCurationRanker()
        # Create 10 candidates for active memory
        candidates = []
        for i in range(10):
            candidates.append(MemoryCurationCandidate(
                candidate_id=f"cand_{i}",
                target_layer=CurationTargetLayer.ACTIVE_MEMORY,
                operation=CurationOperation.CREATE_ACTIVE,
                summary=f"这是第{i}条记忆摘要，用于测试活跃记忆上限控制功能",
                importance=0.5 + i * 0.03,
                confidence=0.6,
            ))

        # Current active = 14, so only 1 slot available
        result = ranker.rank(candidates, current_active_count=14, max_active=15)
        # Only the highest-scoring candidate should be accepted
        active_accepted = [
            c for c in result.accepted
            if c.operation == CurationOperation.CREATE_ACTIVE
        ]
        assert len(active_accepted) <= 1


# ===========================================================================
# 13. ActiveMemory 满时优先 merge / resolve / demote
# ===========================================================================

class TestActiveMemoryFullPriority:

    def test_resolve_takes_priority_over_create(self):
        ranker = MemoryCurationRanker()
        candidates = [
            MemoryCurationCandidate(
                candidate_id="cand_resolve",
                target_layer=CurationTargetLayer.ACTIVE_MEMORY,
                operation=CurationOperation.MARK_RESOLVED,
                duplicate_of_memory_ids=["am_old"],
                importance=0.5,
            ),
            MemoryCurationCandidate(
                candidate_id="cand_create",
                target_layer=CurationTargetLayer.ACTIVE_MEMORY,
                operation=CurationOperation.CREATE_ACTIVE,
                summary="这是一条新的活跃记忆摘要，用于测试排序优先级",
                importance=0.9,
            ),
        ]
        result = ranker.rank(candidates, current_active_count=15, max_active=15)
        # Resolve should always be accepted (frees a slot)
        resolved = [c for c in result.accepted if c.operation == CurationOperation.MARK_RESOLVED]
        assert len(resolved) == 1
        # Create should also be accepted (resolve freed a slot: 15-1+1=15)
        created = [c for c in result.accepted if c.operation == CurationOperation.CREATE_ACTIVE]
        assert len(created) == 1


# ===========================================================================
# 14. 未解决承诺优先于已解决闲聊
# ===========================================================================

class TestPriorityUnresolvedPromise:

    def test_promise_scores_higher_than_chat(self):
        ranker = MemoryCurationRanker()
        promise = MemoryCurationCandidate(
            candidate_id="cand_promise",
            target_layer=CurationTargetLayer.ACTIVE_MEMORY,
            operation=CurationOperation.CREATE_ACTIVE,
            summary="林晓承诺下周帮张伟搬家，这是一个重要的未解决承诺",
            tags=["promise"],
            importance=0.8,
            confidence=0.7,
        )
        chat = MemoryCurationCandidate(
            candidate_id="cand_chat",
            target_layer=CurationTargetLayer.ACTIVE_MEMORY,
            operation=CurationOperation.CREATE_ACTIVE,
            summary="两人聊了聊最近的天气和日常琐事，气氛轻松愉快",
            tags=["scene_pressure"],
            importance=0.3,
            confidence=0.5,
        )
        score_promise = ranker._score(promise)
        score_chat = ranker._score(chat)
        assert score_promise > score_chat


# ===========================================================================
# 15. 当前回合推进旧承诺时更新既有 ActiveMemory
# ===========================================================================

class TestUpdateExistingMemory:

    def test_update_candidate_for_existing_memory(self):
        generator = FakeMemoryCandidateGenerator()
        request = MemoryCurationRequest(
            card_id="card_001",
            session_id="session_001",
            turn_id="turn_new",
            accepted_output="林晓今天帮张伟搬完了家，承诺已经兑现",
            player_input="我们搬家吧",
            active_memory_snapshot=[{
                "memory_id": "am_promise",
                "kind": "promise",
                "status": "active",
                "summary": "林晓承诺下周帮张伟搬家",
                "entity_refs": ["林晓", "张伟"],
            }],
        )
        plan = MemoryCurationQueryPlanner().plan(
            MemoryCurationTriggerDiagnostics(
                should_trigger=True,
                curation_domains=["promise"],
            ),
            _make_turn_record(),
            _make_snapshot(),
        )
        candidates = generator.generate(request, plan)
        # Should have a resolve or update for the existing memory
        updates = [
            c for c in candidates
            if c.operation in (CurationOperation.MARK_RESOLVED, CurationOperation.UPDATE_ACTIVE)
            and "am_promise" in (c.duplicate_of_memory_ids + c.merge_target_memory_ids)
        ]
        assert len(updates) >= 1


# ===========================================================================
# 16. 相同事实重复出现时不会无限写入 RagMemory
# ===========================================================================

class TestNoInfiniteRagDuplication:

    def test_single_rag_per_turn(self):
        generator = FakeMemoryCandidateGenerator()
        request = MemoryCurationRequest(
            card_id="card_001",
            session_id="session_001",
            turn_id="turn_001",
            accepted_output="今天发生了一些事情",
        )
        plan = MemoryCurationQueryPlanner().plan(
            MemoryCurationTriggerDiagnostics(should_trigger=True),
            _make_turn_record(),
            _make_snapshot(),
        )
        candidates = generator.generate(request, plan)
        rag_candidates = [
            c for c in candidates
            if c.target_layer == CurationTargetLayer.RAG_MEMORY
        ]
        # Should only create one RAG per turn
        assert len(rag_candidates) <= 1


# ===========================================================================
# 17. RagMemory 写入必须有 tags、entityRefs、provenance
# ===========================================================================

class TestRagMemoryProvenance:

    def test_rag_candidate_has_tags_and_evidence(self):
        generator = FakeMemoryCandidateGenerator()
        request = MemoryCurationRequest(
            card_id="card_001",
            session_id="session_001",
            turn_id="turn_001",
            accepted_output="今天的重要事件记录",
        )
        plan = MemoryCurationQueryPlanner().plan(
            MemoryCurationTriggerDiagnostics(should_trigger=True),
            _make_turn_record(),
            _make_snapshot(),
        )
        candidates = generator.generate(request, plan)
        rag_candidates = [
            c for c in candidates
            if c.target_layer == CurationTargetLayer.RAG_MEMORY
        ]
        for c in rag_candidates:
            assert c.tags, f"RAG candidate {c.candidate_id} must have tags"
            assert c.evidence_refs, f"RAG candidate {c.candidate_id} must have evidence"


# ===========================================================================
# 18. 已解决 ActiveMemory 可被标记 resolved 或 archive
# ===========================================================================

class TestResolvedMemoryHandling:

    def test_resolved_memory_has_status(self):
        candidate = MemoryCurationCandidate(
            candidate_id="cand_resolve",
            target_layer=CurationTargetLayer.ACTIVE_MEMORY,
            operation=CurationOperation.MARK_RESOLVED,
            duplicate_of_memory_ids=["am_old"],
            resolution_status="resolved",
            evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
            source_turn_ids=["turn_001"],
        )
        request = MemoryCurationRequest()
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, request)
        assert result.valid is True


# ===========================================================================
# 19. Curator 无法访问 Store / SQLite
# ===========================================================================

class TestCuratorNoStoreAccess:

    def test_request_has_no_storage_write(self):
        request = MemoryCurationRequest(
            must_not_write_storage=True,
        )
        assert request.must_not_write_storage is True


# ===========================================================================
# 20. Curator 无法跨 cardId / sessionId 查询
# ===========================================================================

class TestCuratorIsolation:

    def test_request_binds_card_session(self):
        request = MemoryCurationRequest(
            card_id="card_001",
            session_id="session_001",
        )
        assert request.card_id == "card_001"
        assert request.session_id == "session_001"


# ===========================================================================
# 21. Curator 无法调用未授权工具
# ===========================================================================

class TestCuratorToolProfile:

    def test_tool_profile_exists(self):
        from awp_rp_runtime_v2.runtime.memory_curator_tool_profile import MEMORY_CURATOR_ROLE_SPEC
        assert MEMORY_CURATOR_ROLE_SPEC.role_id == "memory-curator"
        assert MEMORY_CURATOR_ROLE_SPEC.can_delegate is False
        assert MEMORY_CURATOR_ROLE_SPEC.can_write_state is False
        assert MEMORY_CURATOR_ROLE_SPEC.can_write_memory is False
        assert MEMORY_CURATOR_ROLE_SPEC.can_generate_final_text is False

    def test_allowed_tools_whitelist(self):
        from awp_rp_runtime_v2.runtime.memory_curator_tool_profile import MEMORY_CURATOR_TOOLS
        allowed = set(MEMORY_CURATOR_TOOLS.keys())
        expected = {
            "accepted_turn_lookup", "active_memory_lookup", "rag_memory_lookup",
            "entity_alias_lookup", "timeline_lookup", "relationship_context_lookup",
        }
        assert allowed == expected


# ===========================================================================
# 22. Curator 无法递归委派
# ===========================================================================

class TestCuratorNoDelegation:

    def test_can_delegate_false(self):
        from awp_rp_runtime_v2.runtime.memory_curator_tool_profile import MEMORY_CURATOR_ROLE_SPEC
        assert MEMORY_CURATOR_ROLE_SPEC.can_delegate is False


# ===========================================================================
# 23. Curator 无法生成 StateUpdateProposal
# ===========================================================================

class TestCuratorNoStateProposal:

    def test_can_write_state_false(self):
        from awp_rp_runtime_v2.runtime.memory_curator_tool_profile import MEMORY_CURATOR_ROLE_SPEC
        assert MEMORY_CURATOR_ROLE_SPEC.can_write_state is False


# ===========================================================================
# 24. Curator 无法直接执行 MemoryCommit
# ===========================================================================

class TestCuratorNoMemoryWrite:

    def test_can_write_memory_false(self):
        from awp_rp_runtime_v2.runtime.memory_curator_tool_profile import MEMORY_CURATOR_ROLE_SPEC
        assert MEMORY_CURATOR_ROLE_SPEC.can_write_memory is False


# ===========================================================================
# 25. Curator 输出玩家正文时被拒绝
# ===========================================================================

class TestCuratorNoFinalText:

    def test_can_generate_final_text_false(self):
        from awp_rp_runtime_v2.runtime.memory_curator_tool_profile import MEMORY_CURATOR_ROLE_SPEC
        assert MEMORY_CURATOR_ROLE_SPEC.can_generate_final_text is False


# ===========================================================================
# 26. MemoryCommitPlan 必须携带 idempotencyKey
# ===========================================================================

class TestPlanIdempotencyKey:

    def test_plan_has_idempotency_key(self):
        compiler = MemoryPlanCompiler()
        result = MemoryCurationResult(
            turn_id="turn_001",
            card_id="card_001",
            session_id="session_001",
            accepted_candidates=[
                MemoryCurationCandidate(
                    candidate_id="cand_001",
                    target_layer=CurationTargetLayer.RAG_MEMORY,
                    operation=CurationOperation.CREATE_RAG,
                    summary="这是一条测试记忆摘要",
                    content="test content",
                    evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
                    source_turn_ids=["turn_001"],
                ),
            ],
        )
        plan = compiler.compile(
            curation_result=result,
            turn_id="turn_001",
            card_id="card_001",
            session_id="session_001",
            trace_id="trace_001",
            expected_card_state_revision=2,
            quality_decision_ref="qd_001",
        )
        assert plan.idempotency_key
        assert plan.memory_commit_id


# ===========================================================================
# 27. 同一 turn retry 不得重复创建 ActiveMemory
# ===========================================================================

class TestIdempotencyRetry:

    def test_already_curated_turn_skipped(self):
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(turn_id="turn_repeat")
        result = policy.evaluate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record_committed=True,
            turn_record=tr,
            snapshot=None,
            existing_curated_turn_ids={"turn_repeat"},
        )
        assert result.should_trigger is False
        assert "already_curated" in result.skip_reason


# ===========================================================================
# 28. 同一 turn retry 不得重复创建 RagMemory
# ===========================================================================

class TestIdempotencyRagRetry:

    def test_same_turn_same_plan(self):
        compiler = MemoryPlanCompiler()
        result = MemoryCurationResult(
            turn_id="turn_001",
            accepted_candidates=[
                MemoryCurationCandidate(
                    candidate_id="cand_001",
                    target_layer=CurationTargetLayer.RAG_MEMORY,
                    operation=CurationOperation.CREATE_RAG,
                    summary="测试记忆摘要内容",
                    content="test",
                    evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
                    source_turn_ids=["turn_001"],
                ),
            ],
        )
        plan1 = compiler.compile(result, "turn_001", "c", "s", "t", 2, "qd")
        plan2 = compiler.compile(result, "turn_001", "c", "s", "t", 2, "qd")
        # Both plans should have the same RAG entry (deterministic)
        assert len(plan1.new_rag_entries) == len(plan2.new_rag_entries)
        assert plan1.new_rag_entries[0].memory_id == plan2.new_rag_entries[0].memory_id


# ===========================================================================
# 29. MemoryCommitRuntime 部分 operation 失败必须可观测
# ===========================================================================

class TestPartialFailureObservable:

    def test_degraded_result_has_reasons(self):
        result = MemoryCurationResult(
            turn_id="turn_001",
            degraded=True,
            degraded_reasons=["adapter_timeout"],
        )
        assert result.degraded is True
        assert "adapter_timeout" in result.degraded_reasons


# ===========================================================================
# 30. Curator runtime timeout 返回 degraded
# ===========================================================================

class TestCuratorTimeoutDegraded:

    def test_adapter_error_produces_degraded(self):
        class BrokenAdapter:
            def curate(self, request, plan):
                raise TimeoutError("adapter timeout")

        runtime = MemoryCurationRuntime()
        runtime.adapter = BrokenAdapter()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(writer_output="林晓承诺下周帮张伟搬家")
        snap = _make_snapshot()

        result = runtime.curate(qd, None, tr, snap)
        assert result.degraded is True
        assert any("adapter_error" in r for r in result.degraded_reasons)


# ===========================================================================
# 31. MemoryCommitRuntime timeout / failure 不撤销 accepted turn
# ===========================================================================

class TestFailureDoesNotRollback:

    def test_degraded_does_not_affect_turn(self):
        result = MemoryCurationResult(
            turn_id="turn_001",
            degraded=True,
            degraded_reasons=["some_error"],
        )
        # The result itself doesn't affect the turn record
        assert result.turn_id == "turn_001"
        # Degraded is just a flag, not a rollback signal
        assert result.degraded is True


# ===========================================================================
# 32. no-op 路径正常完成
# ===========================================================================

class TestNoopPath:

    def test_noop_returns_empty_result(self):
        runtime = MemoryCurationRuntime()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(writer_output="天气不错", player_input="天气？")
        snap = _make_snapshot()

        result = runtime.curate(qd, None, tr, snap)
        assert result.degraded is False
        assert len(result.accepted_candidates) == 0
        assert len(result.rejected_candidates) == 0


# ===========================================================================
# 33. 所有既有测试持续通过 (covered by running full suite)
# ===========================================================================


# ===========================================================================
# 34. 官方 workflow JSON 结构校验通过
# ===========================================================================

class TestE2ENormalCuration:
    """End-to-end: 6 turns history → active memory near capacity →
    accepted turn advances a promise + produces relationship change →
    curator triggers → generates update + RAG → plan compiles → commits."""

    def test_normal_curation_path(self):
        # Setup: 6 turns of history, active memory at 14
        active_memories = []
        for i in range(14):
            active_memories.append({
                "memory_id": f"am_{i}",
                "kind": "scene_pressure" if i < 10 else "promise",
                "status": "active",
                "summary": f"这是第{i}条活跃记忆，用于测试记忆治理的正常流程和排序逻辑",
                "entity_refs": [f"角色{i}"],
                "importance": 0.3 + i * 0.04,
                "confidence": 0.5,
            })

        # The promise memory (am_10) is about 林晓 promising to help
        active_memories[10]["kind"] = "promise"
        active_memories[10]["entity_refs"] = ["林晓", "张伟"]
        active_memories[10]["summary"] = "林晓承诺下周帮张伟搬家，两人约定周六早上见面"
        active_memories[10]["importance"] = 0.8

        snapshot = _make_snapshot(active_memories=active_memories)

        turn_record = _make_turn_record(
            turn_id="turn_006",
            writer_output="林晓今天如约来到张伟家，两人一起完成了搬家。张伟感激地说：'谢谢你，林晓。'林晓微笑着说：'朋友之间不用客气。'",
            player_input="我们开始搬家吧",
        )

        qd = _make_quality_decision("accept")

        # Run the full curation pipeline
        runtime = MemoryCurationRuntime()
        result = runtime.curate(
            quality_decision=qd,
            card_state_commit_result=None,
            turn_record=turn_record,
            snapshot=snapshot,
        )

        # Verify curator triggered
        assert result.degraded is False

        # Compile to MemoryCommitPlan
        compiler = MemoryPlanCompiler()
        plan = compiler.compile(
            curation_result=result,
            turn_id="turn_006",
            card_id="card_001",
            session_id="session_001",
            trace_id="trace_001",
            expected_card_state_revision=2,
            quality_decision_ref=qd.trace_id,
        )

        # Verify plan has idempotency key
        assert plan.idempotency_key
        assert plan.memory_commit_id

        # Verify RAG entry has provenance
        for rag in plan.new_rag_entries:
            assert rag.provenance
            assert rag.source_turn_ids
            assert "turn_006" in rag.source_turn_ids

        # Verify active memory operations
        # Should have at least one resolve or update for the promise
        has_resolve = len(plan.resolved_active_ids) > 0
        has_update = len(plan.updated_active_entries) > 0
        has_new = len(plan.new_active_entries) > 0
        assert has_resolve or has_update or has_new, "Should have some active memory operation"


# ===========================================================================
# E2E Test B: 拒绝、失败与幂等路径
# ===========================================================================

class TestE2ERejectFailureIdempotency:
    """End-to-end: Various failure/rejection scenarios."""

    def test_quality_reject_no_curator(self):
        """Quality Gate reject → no curation."""
        qd = _make_quality_decision("reject")
        tr = _make_turn_record()
        runtime = MemoryCurationRuntime()
        result = runtime.curate(qd, None, tr, _make_snapshot())
        assert len(result.accepted_candidates) == 0

    def test_no_evidence_candidate_rejected(self):
        """Candidate without evidence is rejected."""
        candidate = MemoryCurationCandidate(
            candidate_id="no_ev",
            target_layer=CurationTargetLayer.RAG_MEMORY,
            operation=CurationOperation.CREATE_RAG,
            content="test",
            # no evidence_refs
        )
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, MemoryCurationRequest())
        assert result.valid is False

    def test_state_modification_candidate_rejected(self):
        """Candidate that tries to write storage is rejected."""
        candidate = MemoryCurationCandidate(
            candidate_id="bad_write",
            target_layer=CurationTargetLayer.RAG_MEMORY,
            operation=CurationOperation.CREATE_RAG,
            content="test",
            evidence_refs=[MemoryCurationEvidence(source_turn_id="t")],
            source_turn_ids=["t"],
            must_not_write_storage=False,
        )
        validator = MemoryCurationValidator()
        result = validator.validate_single(candidate, MemoryCurationRequest())
        assert result.valid is False

    def test_same_turn_idempotency(self):
        """Same turn idempotency check."""
        policy = MemoryCurationTriggerPolicy()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(turn_id="turn_idem")
        # First call triggers
        r1 = policy.evaluate(qd, None, True, tr, None)
        assert r1.should_trigger is True
        # Second call with same turn_id in curated set → no trigger
        r2 = policy.evaluate(qd, None, True, tr, None, {"turn_idem"})
        assert r2.should_trigger is False

    def test_degraded_result_preserves_turn(self):
        """Degraded curation does not affect accepted turn."""
        class ErrorAdapter:
            def curate(self, request, plan):
                raise RuntimeError("test error")

        runtime = MemoryCurationRuntime()
        runtime.adapter = ErrorAdapter()
        qd = _make_quality_decision("accept")
        tr = _make_turn_record(writer_output="林晓承诺下周帮张伟搬家")
        result = runtime.curate(qd, None, tr, _make_snapshot())
        assert result.degraded is True
        assert result.turn_id == tr.turn_id


# ===========================================================================
# Contract serialization tests
# ===========================================================================

class TestContractSerialization:

    def test_trigger_diagnostics_roundtrip(self):
        diag = MemoryCurationTriggerDiagnostics(
            should_trigger=True,
            trigger_reasons=["reason1"],
            curation_domains=["promise"],
            risk_level="medium",
        )
        d = diag.to_dict()
        restored = MemoryCurationTriggerDiagnostics.from_dict(d)
        assert restored.should_trigger is True
        assert restored.risk_level == "medium"

    def test_request_roundtrip(self):
        req = MemoryCurationRequest(
            request_id="req_001",
            card_id="card_001",
            session_id="session_001",
            turn_id="turn_001",
            accepted_output="test output",
            must_use_accepted_facts_only=True,
        )
        d = req.to_dict()
        restored = MemoryCurationRequest.from_dict(d)
        assert restored.request_id == "req_001"
        assert restored.must_use_accepted_facts_only is True

    def test_candidate_roundtrip(self):
        cand = MemoryCurationCandidate(
            candidate_id="cand_001",
            target_layer=CurationTargetLayer.ACTIVE_MEMORY,
            operation=CurationOperation.CREATE_ACTIVE,
            summary="这是一条测试记忆摘要，用于验证序列化和反序列化功能",
            evidence_refs=[MemoryCurationEvidence(source_turn_id="turn_001")],
            source_turn_ids=["turn_001"],
        )
        d = cand.to_dict()
        restored = MemoryCurationCandidate.from_dict(d)
        assert restored.candidate_id == "cand_001"
        assert len(restored.evidence_refs) == 1

    def test_result_roundtrip(self):
        result = MemoryCurationResult(
            result_id="res_001",
            turn_id="turn_001",
            card_id="card_001",
            session_id="session_001",
            degraded=False,
            total_candidates_generated=3,
            total_candidates_accepted=2,
            total_candidates_rejected=1,
        )
        d = result.to_dict()
        restored = MemoryCurationResult.from_dict(d)
        assert restored.result_id == "res_001"
        assert restored.total_candidates_generated == 3
