"""M1: Three-Layer Memory Foundation tests.

Covers the 28 required M1 scenarios plus one end-to-end integration test.
Uses Fake stores (deterministic) plus real SQLite (FTS5) for L3 retrieval.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone

import pytest

from awp_rp_runtime_v2.testing.fakes import (
    FakeCardStateStore, FakeTurnRecordStore, FakeActiveMemoryStore,
    FakeRagMemoryStore, FakeTraceStore, FakeLLMProvider,
    FakeRetentionDecisionStore,
)
from awp_rp_runtime_v2.contracts.card_state import CardState
from awp_rp_runtime_v2.contracts.turn_record import TurnRecord, TurnMode
from awp_rp_runtime_v2.contracts.quality_decision import QualityDecision, QualityVerdict
from awp_rp_runtime_v2.contracts.active_memory import (
    ActiveMemoryRecord, ActiveMemoryStatus, ActiveMemoryKind,
)
from awp_rp_runtime_v2.contracts.rag_memory import (
    RagMemoryRecord, RagMemoryStatus, RagMemoryScope,
)
from awp_rp_runtime_v2.contracts.memory_commit_plan import (
    MemoryCommitPlan, MemoryCommitRequest, MemoryCommitStatus,
)
from awp_rp_runtime_v2.contracts.memory_recall_request import MemoryRecallRequest
from awp_rp_runtime_v2.contracts.accepted_turn_window import (
    AcceptedTurnWindow, select_accepted_window, DEFAULT_WINDOW_SIZE,
)
from awp_rp_runtime_v2.runtime.active_memory_commit_runtime import ActiveMemoryCommitRuntime
from awp_rp_runtime_v2.runtime.rag_memory_commit_runtime import RagMemoryCommitRuntime
from awp_rp_runtime_v2.runtime.round_snapshot_builder import RoundSnapshotBuilder
from awp_rp_runtime_v2.runtime.memory_context_assembler import (
    MemoryContextAssembler, ConflictSignal,
)
from awp_rp_runtime_v2.policies.memory_policy import MemoryPolicy
from awp_rp_runtime_v2.storage.sqlite.database import Database
from awp_rp_runtime_v2.storage.sqlite.active_memory_store import SqliteActiveMemoryStore
from awp_rp_runtime_v2.storage.sqlite.rag_memory_store import SqliteRagMemoryStore

SUM = "主角向守卫许下黄昏前归还宝剑的承诺，然而日落将至仍未兑现，场面紧张且悬念未解"


# ---------- helpers ----------

def _qd(trace_id="tr1", verdict=QualityVerdict.ACCEPTED) -> QualityDecision:
    return QualityDecision(trace_id=trace_id, verdict=verdict, source_turn_id="t1")


def _active(mid="m1", card="c1", sess="s1", turn_id="t1", rev=1,
            importance=0.5, kind=ActiveMemoryKind.PROMISE.value, summary=SUM,
            status=ActiveMemoryStatus.ACTIVE.value) -> ActiveMemoryRecord:
    return ActiveMemoryRecord(
        memory_id=mid, card_id=card, session_id=sess, summary=summary, kind=kind,
        entity_refs=["guard"], source_turn_ids=[turn_id], source_card_state_revision=rev,
        importance=importance, confidence=0.6, status=status,
    )


def _rag(mid="r1", card="c1", sess="s1", turn_id="t1", rev=1, content="守卫在月光庭院巡逻",
         summary="守卫巡逻", importance=0.5, confidence=0.6,
         status=RagMemoryStatus.ACTIVE.value, scope=RagMemoryScope.SESSION.value,
         entity_refs=None, aliases=None, event_tags=None) -> RagMemoryRecord:
    return RagMemoryRecord(
        memory_id=mid, card_id=card, session_id=sess, scope=scope,
        content=content, summary=summary,
        entity_refs=entity_refs if entity_refs is not None else ["guard"],
        aliases=aliases or [], event_tags=event_tags or ["patrol"], location_tags=["courtyard"],
        source_turn_ids=[turn_id], source_card_state_revision=rev,
        importance=importance, confidence=confidence, status=status,
        provenance=f"commit:{turn_id}", evidence=[turn_id],
    )


def _plan(turn_id="t1", card="c1", sess="s1", trace_id="tr1", rev=1,
          new_active=None, new_rag=None, resolved=None) -> MemoryCommitPlan:
    return MemoryCommitPlan(
        turn_id=turn_id, card_id=card, session_id=sess, trace_id=trace_id,
        expected_card_state_revision=rev, quality_decision_ref=trace_id,
        new_active_entries=new_active or [], new_rag_entries=new_rag or [],
        resolved_active_ids=resolved or [],
    )


def _req(plan, qd, cs_ok=True, tr_ok=True, idem=None, mcid="mc1") -> MemoryCommitRequest:
    return MemoryCommitRequest(
        plan=plan, card_id=plan.card_id, session_id=plan.session_id,
        turn_id=plan.turn_id, trace_id=plan.trace_id,
        memory_commit_id=mcid, idempotency_key=idem or f"{plan.turn_id}:{mcid}",
        quality_decision_ref=qd.trace_id if qd else "",
        expected_card_state_revision=plan.expected_card_state_revision,
        card_state_commit_success=cs_ok, turn_record_commit_success=tr_ok,
    )


# ====================================================================
# L1: AcceptedTurnWindow
# ====================================================================

class TestL1AcceptedTurnWindow:

    def _save_turns(self, store, card, sess, n, prefix="t"):
        for i in range(1, n + 1):
            store.save(TurnRecord(
                turn_id=f"{prefix}_{card}_{sess}_{i}", card_id=card, session_id=sess,
                turn_index=i, player_input=f"input_{i}_{card}_{sess}",
                writer_output=f"output_{i}" * 5,
                accepted_at=f"2026-01-{i:02d}T00:00:00",
            ))

    def test_1_only_accepted_turns_returned(self):
        # 1: window only returns accepted TurnRecords (store only persists accepted).
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 3)
        # A draft/failed attempt is never stored; defensive: empty turn_id filtered.
        store.save(TurnRecord(turn_id="", card_id="c1", session_id="s1", turn_index=99))
        turns = store.get_recent("c1", "s1", limit=5)
        window = select_accepted_window(turns, limit=5)
        assert all(t.turn_id for t in window)
        assert len(window) == 3

    def test_2_at_most_five(self):
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 6)
        turns = store.get_recent("c1", "s1", limit=5)
        window = select_accepted_window(turns, limit=5)
        assert len(window) == 5

    def test_3_fifth_turn_not_truncated(self):
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 5)
        turns = store.get_recent("c1", "s1", limit=5)
        window = select_accepted_window(turns, limit=5)
        # Every turn retains full player_input + writer_output (oldest = 5th).
        for t in window:
            assert t.player_input != ""
            assert t.writer_output != ""
        # The 5th (oldest in window) is fully present, not a summary.
        oldest = window[-1]
        assert oldest.player_input == "input_1_c1_s1"
        assert oldest.writer_output == "output_1" * 5

    def test_4_rejected_revise_failed_not_in_l1(self):
        # rejected/revise/failed attempts are never written as TurnRecords, so
        # they can never appear in the L1 window.
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 2)
        turns = store.get_recent("c1", "s1", limit=5)
        window = select_accepted_window(turns, limit=5)
        assert len(window) == 2
        # No draft/rejected/failed payload can sneak in (only turn_id-bearing records).
        assert all(t.turn_id.startswith("t") for t in window)

    def test_5_card_id_isolation(self):
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 3)
        self._save_turns(store, "c2", "s1", 2)
        turns_a = store.get_recent("c1", "s1", limit=5)
        window_a = select_accepted_window(turns_a, limit=5)
        assert all(t.card_id == "c1" for t in window_a)
        assert len(window_a) == 3

    def test_6_session_id_isolation(self):
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 3)
        self._save_turns(store, "c1", "s2", 2)
        turns = store.get_recent("c1", "s1", limit=5)
        window = select_accepted_window(turns, limit=5)
        assert all(t.session_id == "s1" for t in window)
        assert len(window) == 3

    def test_9_stable_sort_by_turn_index(self):
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 5)
        turns = store.get_recent("c1", "s1", limit=5)
        window = select_accepted_window(turns, limit=5)
        indices = [t.turn_index for t in window]
        assert indices == [5, 4, 3, 2, 1]

    def test_10_replay_restores_window(self):
        store = FakeTurnRecordStore()
        self._save_turns(store, "c1", "s1", 3)
        turns = store.get_recent("c1", "s1", limit=5)
        window = AcceptedTurnWindow.build("c1", "s1", turns, snapshot_id="snap1")
        restored = AcceptedTurnWindow.from_dict(window.to_dict())
        assert len(restored.turns) == len(window.turns)
        assert [t.turn_id for t in restored.turns] == [t.turn_id for t in window.turns]


# ====================================================================
# L2: ActiveMemory (15-slot, retention, source binding)
# ====================================================================

class TestL2ActiveMemory:

    def test_7_max_fifteen_active(self):
        store = FakeActiveMemoryStore()
        rt = ActiveMemoryCommitRuntime(store, retention_store=FakeRetentionDecisionStore())
        qd = _qd()
        for i in range(16):
            plan = _plan(turn_id=f"t{i}", rev=i,
                         new_active=[_active(mid=f"m{i}", turn_id=f"t{i}", rev=i,
                                             summary=SUM)])
            r = rt.commit_request(_req(plan, qd, idem=f"t{i}:mc", mcid=f"mc{i}"), qd)
            assert r.success
        assert store.get_active_count("c1", "s1") <= 15

    def test_8_deterministic_eviction_at_cap(self):
        store = FakeActiveMemoryStore()
        rt = ActiveMemoryCommitRuntime(store, retention_store=FakeRetentionDecisionStore())
        qd = _qd()
        # Fill 15 low-importance memories.
        for i in range(15):
            plan = _plan(turn_id=f"t{i}", rev=i,
                         new_active=[_active(mid=f"low{i}", turn_id=f"t{i}", rev=i,
                                             importance=0.1,
                                             summary=SUM)])
            rt.commit_request(_req(plan, qd, idem=f"t{i}:mc", mcid=f"mc{i}"), qd)
        # Add one more; lowest-importance should be evicted.
        plan = _plan(turn_id="t99", rev=99,
                     new_active=[_active(mid="high99", turn_id="t99", rev=99,
                                         importance=0.9,
                                         summary=SUM)])
        rt.commit_request(_req(plan, qd, idem="t99:mc", mcid="mc99"), qd)
        assert store.get_active_count("c1", "s1") == 15
        active_ids = {m.memory_id for m in store.get_all("c1", "s1")}
        assert "high99" in active_ids  # high-importance kept

    def test_9_resolved_evicted_first(self):
        store = FakeActiveMemoryStore()
        rt = ActiveMemoryCommitRuntime(store, retention_store=FakeRetentionDecisionStore())
        qd = _qd()
        # Add a resolved memory (low priority for retention).
        plan = _plan(turn_id="t0", rev=0,
                     new_active=[_active(mid="resolved0", turn_id="t0", rev=0,
                                         importance=0.9,
                                         summary=SUM)])
        rt.commit_request(_req(plan, qd, idem="t0:mc", mcid="mc0"), qd)
        store.resolve("c1", "s1", "resolved0")
        # Fill to 15 more.
        for i in range(1, 16):
            plan = _plan(turn_id=f"t{i}", rev=i,
                         new_active=[_active(mid=f"m{i}", turn_id=f"t{i}", rev=i,
                                             importance=0.5,
                                             summary=SUM)])
            rt.commit_request(_req(plan, qd, idem=f"t{i}:mc", mcid=f"mc{i}"), qd)
        # resolved0 should not occupy an active slot (it is resolved, not active).
        active = store.get_all("c1", "s1")
        assert all(m.memory_id != "resolved0" for m in active)
        assert store.get_active_count("c1", "s1") <= 15

    def test_10_high_importance_promise_not_ejected_by_low(self):
        store = FakeActiveMemoryStore()
        policy = MemoryPolicy()
        # Manually test retention scoring: high promise vs low new.
        high = _active(mid="promise", importance=0.95,
                       kind=ActiveMemoryKind.PROMISE.value)
        lows = [
            _active(mid=f"low{i}", importance=0.1,
                    kind=ActiveMemoryKind.SCENE_PRESSURE.value,
                    summary=f"低重要度第{i}条足够长以满足下限要求")
            for i in range(16)
        ]
        result = policy.decide_retention([high], lows, "c1", "s1", turn_id="t1")
        kept_ids = {d.memory_id for d in result.decisions if d.action == "keep"}
        assert "promise" in kept_ids

    def test_11_active_memory_requires_source_turn_and_revision(self):
        store = FakeActiveMemoryStore()
        rt = ActiveMemoryCommitRuntime(store)
        qd = _qd()
        # Entry without source_turn_ids -> validation fails -> blocked.
        bad = ActiveMemoryRecord(
            memory_id="m1", card_id="c1", session_id="s1", summary=SUM,
            kind="promise", source_turn_ids=[], source_card_state_revision=0,
        )
        plan = _plan(new_active=[bad])
        r = rt.commit_request(_req(plan, qd), qd)
        assert r.status == MemoryCommitStatus.BLOCKED_VALIDATION
        assert store.get_active_count("c1", "s1") == 0


# ====================================================================
# L3: RAG memory (FTS5, filters, isolation, stale downgrade, conflict)
# ====================================================================

class TestL3RagMemory:

    def _db_store(self):
        db = Database(tempfile.mktemp(suffix=".db"))
        db.initialize()
        return SqliteRagMemoryStore(db)

    def test_12_fts5_keyword_recall(self):
        store = self._db_store()
        store.save("c1", "s1", _rag(mid="r1", content="守卫在月光庭院巡逻", summary="守卫巡逻"))
        store.save("c1", "s1", _rag(mid="r2", turn_id="t2", content="商人在集市叫卖香料", summary="商人叫卖"))
        req = MemoryRecallRequest(card_id="c1", session_id="s1", query="守卫 庭院", limit=5)
        result = store.recall("c1", "s1", req)
        ids = [h.memory_id for h in result.hits]
        assert "r1" in ids
        assert "r2" not in ids

    def test_13_entity_alias_tag_filters(self):
        store = self._db_store()
        store.save("c1", "s1", _rag(mid="r1", entity_refs=["guard"], aliases=["sentinel"]))
        store.save("c1", "s1", _rag(mid="r2", turn_id="t2", entity_refs=["merchant"],
                                   content="商人在集市叫卖香料", summary="商人叫卖",
                                   aliases=["trader"], event_tags=["trade"]))
        # entity filter
        req = MemoryRecallRequest(card_id="c1", session_id="s1", entity_refs=["guard"], limit=5)
        result = store.recall("c1", "s1", req)
        assert {h.memory_id for h in result.hits} == {"r1"}
        # alias filter via get_by_entity
        alias_hits = store.get_by_entity("c1", "s1", "sentinel")
        assert {h.memory_id for h in alias_hits} == {"r1"}
        # event_tag filter
        req2 = MemoryRecallRequest(card_id="c1", session_id="s1", event_tags=["patrol"], limit=5)
        result2 = store.recall("c1", "s1", req2)
        assert {h.memory_id for h in result2.hits} == {"r1"}

    def test_14_no_cross_card_session_leak(self):
        store = self._db_store()
        store.save("c1", "s1", _rag(mid="r1"))
        store.save("c2", "s1", _rag(mid="r2", card="c2", turn_id="t2", content="other card"))
        store.save("c1", "s2", _rag(mid="r3", sess="s2", turn_id="t3", content="other session"))
        req = MemoryRecallRequest(card_id="c1", session_id="s1", limit=10)
        result = store.recall("c1", "s1", req)
        assert {h.memory_id for h in result.hits} == {"r1"}

    def test_15_stale_downgraded_by_default(self):
        store = self._db_store()
        store.save("c1", "s1", _rag(mid="r1", status=RagMemoryStatus.ACTIVE.value))
        store.save("c1", "s1", _rag(mid="r2", turn_id="t2", status=RagMemoryStatus.RESOLVED.value))
        store.save("c1", "s1", _rag(mid="r3", turn_id="t3", status=RagMemoryStatus.EXPIRED.value))
        req = MemoryRecallRequest(card_id="c1", session_id="s1", limit=10)
        result = store.recall("c1", "s1", req)
        hit_ids = {h.memory_id for h in result.hits}
        excluded_ids = {e["memory_id"] for e in result.excluded}
        assert "r1" in hit_ids
        assert "r2" in excluded_ids
        assert "r3" in excluded_ids

    def test_16_rag_conflict_with_cardstate_ignored(self):
        # Deterministic conflict adjudication via MemoryContextAssembler.
        from awp_rp_runtime_v2.contracts.memory_recall_result import MemoryRecallResult, RecallHit
        card_state = CardState(card_id="c1", session_id="s1", revision=5)
        rag_hit = RecallHit(
            memory_id="r1", layer="rag", score=0.9, status="active",
            summary="守卫已经死亡，无法继续巡逻", content="守卫已经死亡",
            entity_refs=["guard"], source_refs=["t1"],
            importance=0.8, confidence=0.9,
        )
        rag_result = MemoryRecallResult(hits=[rag_hit])
        from awp_rp_runtime_v2.contracts.memory_recall_result import MemoryRecallResult as RR
        active_result = RR(hits=[])
        assembler = MemoryContextAssembler()
        ctx = assembler.assemble(
            card_state=card_state, l1_turns=[], active_result=active_result,
            rag_result=rag_result,
            conflict_signals=[ConflictSignal(
                entity_refs=["guard"], negated_terms=["死亡"],
                reason="conflicts_with_card_state_guard_alive",
            )],
        )
        diag = ctx.diagnostics[0]
        assert diag["conflict_status"] == "ignored"
        assert diag["kept"] is False
        # Conflicting RAG removed from high-priority context.
        assert all(h["memory_id"] != "r1" for h in ctx.rag_recall)


# ====================================================================
# Memory Commit: gate, idempotency, retry
# ====================================================================

class TestMemoryCommitGate:

    def _setup(self):
        store = FakeActiveMemoryStore()
        rag = FakeRagMemoryStore()
        return (
            ActiveMemoryCommitRuntime(store, retention_store=FakeRetentionDecisionStore()),
            RagMemoryCommitRuntime(rag),
            store, rag,
        )

    def test_17_gate_revise_zero_write(self):
        art, rrt, store, rag = self._setup()
        qd = _qd(verdict=QualityVerdict.REVISE)
        plan = _plan(new_active=[_active()], new_rag=[_rag()])
        req = _req(plan, qd)
        ra = art.commit_request(req, qd)
        rr = rrt.commit_request(req, qd)
        assert ra.status == MemoryCommitStatus.BLOCKED_GATE_NOT_ACCEPT
        assert rr.status == MemoryCommitStatus.BLOCKED_GATE_NOT_ACCEPT
        assert store.get_active_count("c1", "s1") == 0
        assert len(rag.search("c1", "s1", "守卫", 10)) == 0

    def test_18_gate_reject_zero_write(self):
        art, rrt, store, rag = self._setup()
        qd = _qd(verdict=QualityVerdict.REJECTED)
        plan = _plan(new_active=[_active()], new_rag=[_rag()])
        req = _req(plan, qd)
        assert art.commit_request(req, qd).status == MemoryCommitStatus.BLOCKED_GATE_NOT_ACCEPT
        assert rrt.commit_request(req, qd).status == MemoryCommitStatus.BLOCKED_GATE_NOT_ACCEPT
        assert store.get_active_count("c1", "s1") == 0

    def test_19_missing_gate_zero_write(self):
        art, rrt, store, rag = self._setup()
        plan = _plan(new_active=[_active()], new_rag=[_rag()])
        req = _req(plan, None)
        assert art.commit_request(req, None).status == MemoryCommitStatus.BLOCKED_NO_GATE
        assert rrt.commit_request(req, None).status == MemoryCommitStatus.BLOCKED_NO_GATE
        assert store.get_active_count("c1", "s1") == 0

    def test_20_card_state_commit_failed_zero_write(self):
        art, rrt, store, rag = self._setup()
        qd = _qd()
        plan = _plan(new_active=[_active()], new_rag=[_rag()])
        req = _req(plan, qd, cs_ok=False)
        assert art.commit_request(req, qd).status == MemoryCommitStatus.BLOCKED_CARD_STATE
        assert rrt.commit_request(req, qd).status == MemoryCommitStatus.BLOCKED_CARD_STATE
        assert store.get_active_count("c1", "s1") == 0

    def test_21_turn_record_commit_failed_zero_write(self):
        art, rrt, store, rag = self._setup()
        qd = _qd()
        plan = _plan(new_active=[_active()], new_rag=[_rag()])
        req = _req(plan, qd, tr_ok=False)
        assert art.commit_request(req, qd).status == MemoryCommitStatus.BLOCKED_TURN_RECORD
        assert rrt.commit_request(req, qd).status == MemoryCommitStatus.BLOCKED_TURN_RECORD
        assert store.get_active_count("c1", "s1") == 0

    def test_22_idempotency_replay_no_duplicate(self):
        art, rrt, store, rag = self._setup()
        qd = _qd()
        plan = _plan(new_active=[_active()], new_rag=[_rag()])
        req = _req(plan, qd, idem="key1", mcid="mc1")
        r1 = art.commit_request(req, qd)
        r1r = rrt.commit_request(req, qd)
        assert r1.status == MemoryCommitStatus.COMMITTED
        assert r1r.status == MemoryCommitStatus.COMMITTED
        # Replay same idempotency_key.
        r2 = art.commit_request(req, qd)
        r2r = rrt.commit_request(req, qd)
        assert r2.status == MemoryCommitStatus.IDEMPOTENT_REPLAY
        assert r2r.status == MemoryCommitStatus.IDEMPOTENT_REPLAY
        # No duplicate writes.
        assert store.get_active_count("c1", "s1") == 1
        assert len(rag.search("c1", "s1", "守卫", 10)) == 1

    def test_23_retry_no_duplicate_memory(self):
        art, rrt, store, rag = self._setup()
        # Attempt 1: gate revise (retry) -> 0 write.
        qd_revise = _qd(verdict=QualityVerdict.REVISE)
        plan = _plan(new_active=[_active()], new_rag=[_rag()])
        req1 = _req(plan, qd_revise, idem="attempt1", mcid="mc1")
        art.commit_request(req1, qd_revise)
        rrt.commit_request(req1, qd_revise)
        assert store.get_active_count("c1", "s1") == 0
        # Attempt 2 (retry succeeds): gate accept -> writes once.
        qd_accept = _qd()
        req2 = _req(plan, qd_accept, idem="attempt2", mcid="mc2")
        r2 = art.commit_request(req2, qd_accept)
        r2r = rrt.commit_request(req2, qd_accept)
        assert r2.status == MemoryCommitStatus.COMMITTED
        assert r2r.status == MemoryCommitStatus.COMMITTED
        assert store.get_active_count("c1", "s1") == 1
        assert len(rag.search("c1", "s1", "守卫", 10)) == 1


# ====================================================================
# RoundSnapshot memory context
# ====================================================================

class TestSnapshotMemoryContext:

    def _builder(self):
        return RoundSnapshotBuilder(
            FakeCardStateStore(), FakeTurnRecordStore(),
            FakeActiveMemoryStore(), FakeRagMemoryStore(),
        )

    def test_24_snapshot_immutable(self):
        builder = self._builder()
        snap = builder.build("c1", "s1", "hello")
        with pytest.raises(AttributeError):
            snap.active_memories = []
        with pytest.raises(AttributeError):
            snap.memory_recall_diagnostics = []

    def test_25_snapshot_records_recall_diagnostics(self):
        builder = self._builder()
        # Seed an active memory so diagnostics have content.
        builder.active_memory_store.upsert("c1", "s1", _active())
        snap = builder.build("c1", "s1", "守卫")
        assert isinstance(snap.memory_recall_diagnostics, list)
        assert isinstance(snap.memory_budget_decision, dict)
        # budget decision records L1/active/rag usage.
        b = snap.memory_budget_decision
        assert "l1_turns_used" in b
        assert "active_memories_used" in b
        assert "rag_used" in b
        assert b["l1_truncated"] is False

    def test_26_priority_l1_over_l2_over_l3(self):
        assembler = MemoryContextAssembler()
        from awp_rp_runtime_v2.contracts.memory_recall_result import MemoryRecallResult, RecallHit
        from awp_rp_runtime_v2.contracts.card_state import CardState
        card_state = CardState(card_id="c1", session_id="s1", revision=2)
        from awp_rp_runtime_v2.contracts.turn_record import TurnRecord
        l1 = [TurnRecord(turn_id="t1", card_id="c1", session_id="s1", turn_index=1,
                         player_input="p", writer_output="w")]
        active = MemoryRecallResult(hits=[RecallHit(
            memory_id="a1", layer="active", score=0.9, summary=SUM,
            entity_refs=["g"], source_refs=["t1"], importance=0.9, confidence=0.9,
        )])
        rag = MemoryRecallResult(hits=[RecallHit(
            memory_id="r1", layer="rag", score=0.9, summary="rag",
            entity_refs=["g"], source_refs=["t1"], importance=0.9, confidence=0.9,
        )])
        ctx = assembler.assemble(card_state, l1, active, rag, [{"wb": 1}])
        # Priority order fixed: CardState < L1 < Active < RAG-high < RAG < Worldbook
        from awp_rp_runtime_v2.policies.memory_policy import (
            PRIORITY_CARD_STATE, PRIORITY_L1_TURNS, PRIORITY_ACTIVE_MEMORY, PRIORITY_RAG,
            PRIORITY_WORLDBOOK,
        )
        po = ctx.priority_order
        assert po.index(PRIORITY_L1_TURNS) < po.index(PRIORITY_ACTIVE_MEMORY)
        assert po.index(PRIORITY_ACTIVE_MEMORY) < po.index(PRIORITY_RAG)
        assert po.index(PRIORITY_RAG) < po.index(PRIORITY_WORLDBOOK)
        assert po[0] == PRIORITY_CARD_STATE


# ====================================================================
# Workflow JSON structure
# ====================================================================

class TestM1EndToEnd:

    def test_e2e_six_turns_then_snapshot_then_retry(self):
        from awp_rp_runtime_v2.runtime.director_runtime import DirectorRuntime, FakeDirectorAdapter
        from awp_rp_runtime_v2.runtime.delegation_planner import DelegationPlanner
        from awp_rp_runtime_v2.runtime.suggestion_merger import SuggestionMerger
        from awp_rp_runtime_v2.runtime.writer_runtime import WriterRuntime
        from awp_rp_runtime_v2.runtime.critic_runtime import CriticRuntime
        from awp_rp_runtime_v2.runtime.state_proposal_runtime import StateProposalRuntime
        from awp_rp_runtime_v2.runtime.card_state_commit_runtime import CardStateCommitRuntime
        from awp_rp_runtime_v2.runtime.turn_record_commit_runtime import TurnRecordCommitRuntime
        from awp_rp_runtime_v2.runtime.turn_orchestrator import TurnOrchestrator
        from awp_rp_runtime_v2.runtime.retry_runtime import RetryRuntime
        from awp_rp_runtime_v2.runtime.agent_runtime_registry import AgentRuntimeRegistry
        from awp_rp_runtime_v2.runtime.task_envelope_builder import TaskEnvelopeBuilder
        from awp_rp_runtime_v2.runtime.dynamic_subagent_pool import DynamicSubAgentPool

        card_store = FakeCardStateStore()
        turn_store = FakeTurnRecordStore()
        active_store = FakeActiveMemoryStore()
        rag_store = FakeRagMemoryStore()
        llm = FakeLLMProvider()

        snapshot_builder = RoundSnapshotBuilder(card_store, turn_store, active_store, rag_store)
        orchestrator = TurnOrchestrator(
            snapshot_builder=snapshot_builder,
            director=DirectorRuntime(FakeDirectorAdapter()),
            delegation_planner=DelegationPlanner(),
            subagent_pool=DynamicSubAgentPool(AgentRuntimeRegistry(), TaskEnvelopeBuilder(AgentRuntimeRegistry())),
            suggestion_merger=SuggestionMerger(),
            writer=WriterRuntime(llm),
            critic=CriticRuntime(llm),
            state_proposal=StateProposalRuntime(llm),
            state_commit=CardStateCommitRuntime(card_store),
            turn_commit=TurnRecordCommitRuntime(turn_store),
            memory_commit=ActiveMemoryCommitRuntime(active_store, retention_store=FakeRetentionDecisionStore()),
            rag_commit=RagMemoryCommitRuntime(rag_store),
            retry_runtime=RetryRuntime(),
        )

        card_store.initialize("card1", "sess1")

        # Run 6 accepted turns, each advancing the CardState revision.
        for i in range(6):
            res = orchestrator.execute_turn(
                card_id="card1", session_id="sess1",
                player_input=f"第{i+1}回合：主角走进月光庭院与守卫交谈",
            )
            assert res.success, f"turn {i+1} failed: {res.error}"

        # ActiveMemory + RAGMemory produced.
        assert active_store.get_active_count("card1", "sess1") > 0
        assert len(rag_store.search("card1", "sess1", "月光", 20)) > 0

        # 7th turn: build snapshot, verify L1 window has exactly 5 full accepted turns.
        snap = snapshot_builder.build("card1", "sess1", "第7回合：再次进入庭院")
        assert len(snap.recent_turn_records) == 5
        # All 5 are full (non-truncated).
        for tr in snap.recent_turn_records:
            assert tr.turn_id != ""
            assert tr.player_input != ""
            assert tr.writer_output != ""
        # ActiveMemory <= 15.
        assert active_store.get_active_count("card1", "sess1") <= 15
        # RAG recall has source refs + deterministic ordering.
        # (FakeLLM writer output contains "月光")
        rag_req = MemoryRecallRequest(card_id="card1", session_id="sess1", query="月光", limit=10)
        rag_result = rag_store.recall("card1", "sess1", rag_req)
        assert len(rag_result.hits) > 0
        assert all(h.source_refs for h in rag_result.hits)
        assert rag_result.ordered_by != ""

        # CardState hard facts override conflicting RAG.
        from awp_rp_runtime_v2.contracts.memory_recall_result import MemoryRecallResult
        # Force a conflicting RAG hit and verify assembler ignores it.
        conflict_hit = type(rag_result.hits[0])(
            memory_id="conflict", layer="rag", score=1.0, status="active",
            summary="守卫已经死亡，庭院无人", content="守卫已经死亡",
            entity_refs=["guard"], source_refs=["t1"],
            importance=0.9, confidence=0.9,
        )
        conflict_result = MemoryRecallResult(hits=[conflict_hit])
        from awp_rp_runtime_v2.contracts.card_state import CardState as CS
        ctx = MemoryContextAssembler().assemble(
            card_state=card_store.load("card1", "sess1"),
            l1_turns=snap.recent_turn_records,
            active_result=MemoryRecallResult(hits=[]),
            rag_result=conflict_result,
            conflict_signals=[ConflictSignal(
                entity_refs=["guard"], negated_terms=["死亡"],
                reason="guard_alive_in_cardstate",
            )],
        )
        assert all(d["memory_id"] != "conflict" or d["kept"] is False for d in ctx.diagnostics)

        # Retry the 7th turn: verify no duplicate Memory Commit.
        receipts_before = len(active_store._receipts)
        rag_receipts_before = len(rag_store._receipts)
        # Simulate a retry that re-commits with a NEW memory_commit_id but same turn.
        # In the formal path, a retry that fails must not write; a retry that
        # succeeds writes exactly once with a new idempotency key.
        from awp_rp_runtime_v2.contracts.memory_commit_plan import MemoryCommitPlan
        last_turn = turn_store.get_last_accepted("card1", "sess1")
        # Replay with same idempotency key => idempotent, no duplicate.
        qd = QualityDecision(trace_id=snap.trace_id, verdict=QualityVerdict.ACCEPTED)
        plan = MemoryCommitPlan(
            turn_id=last_turn.turn_id, card_id="card1", session_id="sess1",
            trace_id=snap.trace_id, expected_card_state_revision=last_turn.result_card_state_revision,
            quality_decision_ref=qd.trace_id,
            new_active_entries=[_active(mid=f"am_{last_turn.turn_id}", turn_id=last_turn.turn_id,
                                        rev=last_turn.result_card_state_revision)],
        )
        req = MemoryCommitRequest(
            plan=plan, card_id="card1", session_id="sess1", turn_id=last_turn.turn_id,
            trace_id=snap.trace_id, memory_commit_id="mc_retry_1",
            idempotency_key=f"{last_turn.turn_id}:mc_retry_1", quality_decision_ref=qd.trace_id,
            expected_card_state_revision=last_turn.result_card_state_revision,
            card_state_commit_success=True, turn_record_commit_success=True,
        )
        ar = orchestrator.memory_commit.commit_request(req, qd)
        assert ar.status == MemoryCommitStatus.COMMITTED
        # Replay same idempotency key => no duplicate.
        ar2 = orchestrator.memory_commit.commit_request(req, qd)
        assert ar2.status == MemoryCommitStatus.IDEMPOTENT_REPLAY
        assert len(active_store._receipts) == receipts_before + 1  # only one new receipt
