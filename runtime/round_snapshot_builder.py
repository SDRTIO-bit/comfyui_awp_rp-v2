"""RoundSnapshotBuilder — builds the frozen RoundSnapshot for a round.

Wires the formal three-layer memory into the snapshot:
  L1: last <=5 full accepted TurnRecords (AcceptedTurnWindow, never truncated)
  L2: ActiveMemory recall (deterministic)
  L3: RAG recall (FTS5 + filters)
All assembled by MemoryContextAssembler with the fixed priority order and
deterministic conflict adjudication. The snapshot records recall diagnostics
and the budget decision.

Constructor and build() signatures are preserved for backward compatibility.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.card_state import CardState
from ..contracts.turn_record import TurnRecord
from ..contracts.accepted_turn_window import AcceptedTurnWindow, DEFAULT_WINDOW_SIZE
from ..contracts.memory_recall_request import MemoryRecallRequest
from ..storage.interfaces import (
    CardStateStore, TurnRecordStore, ActiveMemoryStore, RagMemoryStore,
)
from .active_memory_recall_runtime import ActiveMemoryRecallRuntime
from .rag_recall_runtime import RagMemoryRecallRuntime
from .memory_context_assembler import MemoryContextAssembler
from .emotional_summarizer import EmotionalSummarizer


class RoundSnapshotBuilder:

    def __init__(
        self,
        card_state_store: CardStateStore,
        turn_record_store: TurnRecordStore,
        active_memory_store: ActiveMemoryStore,
        rag_memory_store: RagMemoryStore,
        max_turn_history: int = 5,
        max_active_memories: int = 15,
        assembler: MemoryContextAssembler | None = None,
    ):
        self.card_state_store = card_state_store
        self.turn_record_store = turn_record_store
        self.active_memory_store = active_memory_store
        self.rag_memory_store = rag_memory_store
        self.max_turn_history = max_turn_history
        self.max_active_memories = max_active_memories
        self.assembler = assembler or MemoryContextAssembler(
            max_l1_turns=max_turn_history, max_active=max_active_memories
        )
        self.active_recall = ActiveMemoryRecallRuntime(active_memory_store)
        self.rag_recall = RagMemoryRecallRuntime(rag_memory_store)

    def build(
        self,
        card_id: str,
        session_id: str,
        player_input: str,
        worldbook_entries: list[dict[str, Any]] | None = None,
        card_profile_context: dict[str, Any] | None = None,
    ) -> RoundSnapshot:
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        card_state = self.card_state_store.load(card_id, session_id)
        if not card_state:
            card_state = self.card_state_store.initialize(card_id, session_id)

        # L1: accepted turn window (most recent first, up to max_turn_history).
        recent_raw = self.turn_record_store.get_recent(
            card_id, session_id, limit=self.max_turn_history
        )
        window = AcceptedTurnWindow.build(
            card_id=card_id, session_id=session_id, turns=recent_raw,
            snapshot_id=snapshot_id, window_size=self.max_turn_history,
        )
        # AcceptedTurnWindow returns most-recent first; keep that order.
        l1_turns = list(window.turns)
        older_turns_summary = self._build_older_turns_summary(
            card_id=card_id,
            session_id=session_id,
            recent_turns=l1_turns,
        )

        # L2: active memory recall
        active_request = MemoryRecallRequest(
            card_id=card_id, session_id=session_id, snapshot_id=snapshot_id,
            trace_id=trace_id,
            query=player_input,
            limit=self.max_active_memories,
        )
        active_result = self.active_recall.recall(active_request)

        # L3: RAG recall
        rag_request = MemoryRecallRequest(
            card_id=card_id, session_id=session_id, snapshot_id=snapshot_id,
            trace_id=trace_id,
            query=player_input,
            limit=10,
        )
        rag_result = self.rag_recall.recall(rag_request)

        # Assemble with fixed priority + deterministic conflict adjudication
        assembled = self.assembler.assemble(
            card_state=card_state,
            l1_turns=l1_turns,
            active_result=active_result,
            rag_result=rag_result,
            worldbook_entries=worldbook_entries,
        )

        return RoundSnapshot(
            snapshot_id=snapshot_id,
            trace_id=trace_id,
            card_id=card_id,
            session_id=session_id,
            base_card_state_revision=card_state.revision,
            card_state=card_state,
            player_input=player_input,
            card_profile_context=dict(card_profile_context or {}),
            recent_turn_records=l1_turns,
            older_turns_summary=older_turns_summary,
            active_worldbook_entries=assembled.worldbook_entries,
            active_memories=assembled.active_memories,
            rag_recall=assembled.rag_recall,
            memory_recall_diagnostics=assembled.diagnostics,
            memory_budget_decision=assembled.budget.to_dict(),
            max_turn_history=self.max_turn_history,
            max_active_memories=self.max_active_memories,
            created_at=now,
        )

    def _build_older_turns_summary(
        self,
        *,
        card_id: str,
        session_id: str,
        recent_turns: list[TurnRecord],
    ) -> str:
        recent_ids = {turn.turn_id for turn in recent_turns}
        all_turns = [
            turn for turn in self.turn_record_store.list_by_session(session_id)
            if turn.card_id == card_id
        ]
        older_turns = [turn for turn in all_turns if turn.turn_id not in recent_ids]
        return EmotionalSummarizer().summarize(older_turns)
