"""WriterInputBundle — the only formal input for Writer.

schemaId: awp.rp.writer-input-bundle.v1

Writer can ONLY read from this bundle. Not from raw suggestions, not from stores.
Updated in C1 to include FinalTurnBrief and structured content.
Backward compatible with P2 fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_ID = "awp.rp.writer-input-bundle.v1"
SCHEMA_VERSION = 1


@dataclass
class WriterInputBundle:
    """The only formal input for Writer.

    Writer can ONLY read from this bundle.
    Writer cannot access stores, tool gateway, or raw tool results.
    """
    schema_id: str = SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    # Identity
    bundle_id: str = ""
    trace_id: str = ""
    snapshot_id: str = ""
    brief_id: str = ""  # P2 backward compat
    final_turn_brief_id: str = ""  # C1
    merge_id: str = ""  # P2 backward compat
    suggestion_merge_id: str = ""  # C1
    card_id: str = ""
    session_id: str = ""
    base_card_state_revision: int = 0

    # P2 references (backward compat)
    round_snapshot_ref: str = ""
    turn_brief_ref: str = ""
    suggestion_merge_ref: str = ""

    # C1 references
    recent_accepted_turns_ref: str = ""
    active_memory_refs: list[str] = field(default_factory=list)
    rag_recall_refs: list[str] = field(default_factory=list)

    # The FinalTurnBrief (C1: Director's enriched plan)
    final_turn_brief: dict[str, Any] = field(default_factory=dict)

    # Guidance
    accepted_guidance: list[str] = field(default_factory=list)
    writer_constraints: list[str] = field(default_factory=list)

    # P0 canonical persistent formal context
    player_input: str = ""
    card_profile_context: dict[str, Any] = field(default_factory=dict)
    opening_context: dict[str, Any] = field(default_factory=dict)
    worldbook_context: list[dict[str, Any]] = field(default_factory=list)
    recent_turns_context: list[dict[str, Any]] = field(default_factory=list)
    card_state_context: dict[str, Any] = field(default_factory=dict)
    active_memory_context: list[dict[str, Any]] = field(default_factory=list)
    rag_memory_context: list[dict[str, Any]] = field(default_factory=list)

    # Prompt assembly v2
    score: str = ""
    variable_snapshot: dict[str, Any] = field(default_factory=dict)
    older_turns_summary: str = ""

    # Style and format contracts (C1)
    style_contract: dict[str, Any] = field(default_factory=dict)
    format_contract: dict[str, Any] = field(default_factory=dict)
    budget_contract: dict[str, Any] = field(default_factory=dict)

    # Hints (from suggestion merge)
    state_proposal_hints: list[dict[str, Any]] = field(default_factory=list)
    memory_proposal_hints: list[dict[str, Any]] = field(default_factory=list)

    # Timestamp
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id, "schema_version": self.schema_version,
            "bundle_id": self.bundle_id, "trace_id": self.trace_id,
            "snapshot_id": self.snapshot_id,
            "brief_id": self.brief_id,
            "final_turn_brief_id": self.final_turn_brief_id,
            "merge_id": self.merge_id,
            "suggestion_merge_id": self.suggestion_merge_id,
            "card_id": self.card_id, "session_id": self.session_id,
            "base_card_state_revision": self.base_card_state_revision,
            "round_snapshot_ref": self.round_snapshot_ref,
            "turn_brief_ref": self.turn_brief_ref,
            "suggestion_merge_ref": self.suggestion_merge_ref,
            "recent_accepted_turns_ref": self.recent_accepted_turns_ref,
            "active_memory_refs": self.active_memory_refs,
            "rag_recall_refs": self.rag_recall_refs,
            "final_turn_brief": self.final_turn_brief,
            "accepted_guidance": self.accepted_guidance,
            "writer_constraints": self.writer_constraints,
            "player_input": self.player_input,
            "card_profile_context": self.card_profile_context,
            "opening_context": self.opening_context,
            "worldbook_context": self.worldbook_context,
            "recent_turns_context": self.recent_turns_context,
            "card_state_context": self.card_state_context,
            "active_memory_context": self.active_memory_context,
            "rag_memory_context": self.rag_memory_context,
            "score": self.score,
            "variable_snapshot": self.variable_snapshot,
            "older_turns_summary": self.older_turns_summary,
            "style_contract": self.style_contract,
            "format_contract": self.format_contract,
            "budget_contract": self.budget_contract,
            "state_proposal_hints": self.state_proposal_hints,
            "memory_proposal_hints": self.memory_proposal_hints,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WriterInputBundle:
        return cls(
            schema_id=data.get("schema_id", SCHEMA_ID),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            bundle_id=data.get("bundle_id", ""),
            trace_id=data.get("trace_id", ""),
            snapshot_id=data.get("snapshot_id", ""),
            brief_id=data.get("brief_id", ""),
            final_turn_brief_id=data.get("final_turn_brief_id", ""),
            merge_id=data.get("merge_id", ""),
            suggestion_merge_id=data.get("suggestion_merge_id", ""),
            card_id=data.get("card_id", ""),
            session_id=data.get("session_id", ""),
            base_card_state_revision=data.get("base_card_state_revision", 0),
            round_snapshot_ref=data.get("round_snapshot_ref", ""),
            turn_brief_ref=data.get("turn_brief_ref", ""),
            suggestion_merge_ref=data.get("suggestion_merge_ref", ""),
            recent_accepted_turns_ref=data.get("recent_accepted_turns_ref", ""),
            active_memory_refs=data.get("active_memory_refs", []),
            rag_recall_refs=data.get("rag_recall_refs", []),
            final_turn_brief=data.get("final_turn_brief", {}),
            accepted_guidance=data.get("accepted_guidance", []),
            writer_constraints=data.get("writer_constraints", []),
            player_input=data.get("player_input", ""),
            card_profile_context=data.get("card_profile_context", {}),
            opening_context=data.get("opening_context", {}),
            worldbook_context=data.get("worldbook_context", []),
            recent_turns_context=data.get("recent_turns_context", []),
            card_state_context=data.get("card_state_context", {}),
            active_memory_context=data.get("active_memory_context", []),
            rag_memory_context=data.get("rag_memory_context", []),
            score=data.get("score", ""),
            variable_snapshot=data.get("variable_snapshot", {}),
            older_turns_summary=data.get("older_turns_summary", ""),
            style_contract=data.get("style_contract", {}),
            format_contract=data.get("format_contract", {}),
            budget_contract=data.get("budget_contract", {}),
            state_proposal_hints=data.get("state_proposal_hints", []),
            memory_proposal_hints=data.get("memory_proposal_hints", []),
            created_at=data.get("created_at", ""),
        )
