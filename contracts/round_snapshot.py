"""RoundSnapshot — frozen facts for the current round.

schemaId: awp.rp.round-snapshot.v1

Immutable once built. All agents read from this snapshot.
Must contain snapshotId for traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .card_state import CardState
from .turn_record import TurnRecord

SCHEMA_ID = "awp.rp.round-snapshot.v1"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RoundSnapshot:
    """Frozen facts for the current round.

    Built by RoundSnapshotBuilder, read by all agents.
    Immutable once created.
    """
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    # Identity
    snapshot_id: str = ""
    trace_id: str = ""
    card_id: str = ""
    session_id: str = ""

    # CardState
    base_card_state_revision: int = 0
    card_state: CardState = field(default_factory=CardState)

    # Player input
    player_input: str = ""

    # Immutable character profile for roleplay grounding
    card_profile_context: dict[str, Any] = field(default_factory=dict)

    # Recent turn records (last N, most recent first)
    recent_turn_records: list[TurnRecord] = field(default_factory=list)
    older_turns_summary: str = ""

    # Conditional worldbook entries activated for this round
    active_worldbook_entries: list[dict[str, Any]] = field(default_factory=list)

    # Active memories (up to 15)
    active_memories: list[dict[str, Any]] = field(default_factory=list)

    # RAG recall results
    rag_recall: list[dict[str, Any]] = field(default_factory=list)

    # M1: memory recall diagnostics + budget decision
    memory_recall_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    memory_budget_decision: dict[str, Any] = field(default_factory=dict)

    # Configuration
    max_turn_history: int = 5
    max_active_memories: int = 15

    # Timestamps
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "trace_id": self.trace_id,
            "card_id": self.card_id,
            "session_id": self.session_id,
            "base_card_state_revision": self.base_card_state_revision,
            "card_state": self.card_state.to_dict(),
            "player_input": self.player_input,
            "card_profile_context": self.card_profile_context,
            "recent_turn_records": [tr.to_dict() for tr in self.recent_turn_records],
            "older_turns_summary": self.older_turns_summary,
            "active_worldbook_entries": self.active_worldbook_entries,
            "active_memories": self.active_memories,
            "rag_recall": self.rag_recall,
            "memory_recall_diagnostics": self.memory_recall_diagnostics,
            "memory_budget_decision": self.memory_budget_decision,
            "max_turn_history": self.max_turn_history,
            "max_active_memories": self.max_active_memories,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoundSnapshot:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            snapshot_id=data.get("snapshot_id", ""),
            trace_id=data.get("trace_id", ""),
            card_id=data.get("card_id", ""),
            session_id=data.get("session_id", ""),
            base_card_state_revision=data.get("base_card_state_revision", 0),
            card_state=CardState.from_dict(data.get("card_state", {})),
            player_input=data.get("player_input", ""),
            card_profile_context=data.get("card_profile_context", {}),
            recent_turn_records=[
                TurnRecord.from_dict(tr) for tr in data.get("recent_turn_records", [])
            ],
            older_turns_summary=data.get("older_turns_summary", ""),
            active_worldbook_entries=data.get("active_worldbook_entries", []),
            active_memories=data.get("active_memories", []),
            rag_recall=data.get("rag_recall", []),
            memory_recall_diagnostics=data.get("memory_recall_diagnostics", []),
            memory_budget_decision=data.get("memory_budget_decision", {}),
            max_turn_history=data.get("max_turn_history", 5),
            max_active_memories=data.get("max_active_memories", 15),
            created_at=data.get("created_at", ""),
        )
