"""WriterInputBundleV2Builder — builds WriterInputBundle with FinalTurnBrief.

Creates the WriterInputBundle that is Writer's ONLY formal input.
Writer cannot access stores, tool gateway, or raw tool results.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.final_turn_brief import FinalTurnBrief
from ..contracts.suggestion_merge_result import SuggestionMergeResult
from ..contracts.writer_input_bundle import WriterInputBundle


class WriterInputBundleV2Builder:
    """Builds WriterInputBundle with FinalTurnBrief for Writer V2."""

    def build(
        self,
        snapshot: RoundSnapshot,
        final_brief: FinalTurnBrief,
        merge_result: SuggestionMergeResult | None = None,
        card_profile_context: dict | None = None,
        opening_context: dict | None = None,
        worldbook_context: list[dict] | None = None,
        score: str = "",
        older_turns_summary: str = "",
    ) -> WriterInputBundle:
        """Build a WriterInputBundle.

        Writer can ONLY read from this bundle.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Build accepted guidance from merge result
        accepted_guidance = []
        if merge_result:
            for item in merge_result.adopted:
                if item.suggestion and item.suggestion.summary:
                    accepted_guidance.append(item.suggestion.summary)
            accepted_guidance.extend(merge_result.writer_guidance)
        accepted_guidance.extend(final_brief.accepted_tool_findings[:8])

        # Build writer constraints from FinalTurnBrief
        writer_constraints = list(final_brief.writer_constraints)
        writer_constraints.extend([
            "Must not use tools or make tool calls",
            "Must not delegate to sub-agents",
            "Must not write to CardState, TurnRecord, or Memory",
            "Must not output JSON, debug info, or analysis",
            "Must not expose sub-agent suggestions to player",
        ])

        recent_turns_context = [
            {
                "turn_id": turn.turn_id,
                "turn_index": turn.turn_index,
                "player_input": turn.player_input,
                "writer_output": turn.writer_output,
            }
            for turn in snapshot.recent_turn_records[:5]
        ]

        card_state_context = {
            "revision": snapshot.card_state.revision,
            "scene_state": {
                "location": snapshot.card_state.scene_state.location,
                "time_of_day": snapshot.card_state.scene_state.time_of_day,
                "weather": snapshot.card_state.scene_state.weather,
                "active_npcs": list(snapshot.card_state.scene_state.active_npcs),
                "description": snapshot.card_state.scene_state.description,
                "metadata": dict(snapshot.card_state.scene_state.metadata),
            },
            "variables": {
                name: {
                    "name": entry.name,
                    "value": entry.value,
                    "var_type": entry.var_type,
                    "description": entry.description,
                    "last_updated_turn": entry.last_updated_turn,
                }
                for name, entry in snapshot.card_state.variables.items()
            },
            "event_flags": {
                name: {
                    "event_id": entry.event_id,
                    "fired": entry.fired,
                    "fired_at_turn": entry.fired_at_turn,
                    "metadata": dict(entry.metadata),
                }
                for name, entry in snapshot.card_state.event_flags.items()
            },
            "active_stage_ids": list(snapshot.card_state.active_stage_ids),
        }
        variable_snapshot = self._build_variable_snapshot(snapshot)
        if not older_turns_summary:
            older_turns_summary = getattr(snapshot, "older_turns_summary", "")
        if card_profile_context is None:
            card_profile_context = getattr(snapshot, "card_profile_context", {})

        return WriterInputBundle(
            bundle_id=f"wib_{uuid.uuid4().hex[:12]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            final_turn_brief_id=final_brief.brief_id,
            suggestion_merge_id=merge_result.merge_id if merge_result else "",
            card_id=snapshot.card_id,
            session_id=snapshot.session_id,
            base_card_state_revision=snapshot.base_card_state_revision,
            recent_accepted_turns_ref=snapshot.snapshot_id,
            active_memory_refs=[m.get("memory_id", "") for m in snapshot.active_memories[:15]],
            rag_recall_refs=[r.get("memory_id", "") for r in snapshot.rag_recall[:10]],
            final_turn_brief=final_brief.to_dict(),
            accepted_guidance=accepted_guidance,
            writer_constraints=writer_constraints,
            player_input=snapshot.player_input,
            card_profile_context=dict(card_profile_context or {}),
            opening_context=dict(opening_context or {}),
            worldbook_context=list(
                worldbook_context if worldbook_context is not None
                else snapshot.active_worldbook_entries
            ),
            recent_turns_context=recent_turns_context,
            card_state_context=card_state_context,
            active_memory_context=list(snapshot.active_memories),
            rag_memory_context=list(snapshot.rag_recall),
            score=score,
            variable_snapshot=variable_snapshot,
            older_turns_summary=older_turns_summary,
            style_contract={
                "style": "narrative",
                "language": "zh",
                "perspective": "third_person",
            },
            format_contract={
                "min_length": 1000,
                "max_length": 5000,
            },
            budget_contract={
                "max_tokens": 4000,
            },
            state_proposal_hints=merge_result.state_proposal_hints if merge_result else [],
            memory_proposal_hints=merge_result.memory_proposal_hints if merge_result else [],
            created_at=now,
        )

    def _build_variable_snapshot(self, snapshot: RoundSnapshot) -> dict:
        """Build volatile state context for Writer prompt assembly."""
        return {
            "location": snapshot.card_state.scene_state.location,
            "time_of_day": snapshot.card_state.scene_state.time_of_day,
            "weather": snapshot.card_state.scene_state.weather,
            "active_npcs": list(snapshot.card_state.scene_state.active_npcs),
            "variables": {
                name: {
                    "value": entry.value,
                    "last_updated_turn": entry.last_updated_turn,
                }
                for name, entry in snapshot.card_state.variables.items()
            },
            "event_flags": {
                name: {
                    "fired": entry.fired,
                    "fired_at_turn": entry.fired_at_turn,
                }
                for name, entry in snapshot.card_state.event_flags.items()
            },
        }
