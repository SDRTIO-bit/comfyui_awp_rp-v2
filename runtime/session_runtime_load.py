"""SessionRuntimeLoad - restores L0/L1/L2/L3 from persistent stores."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..contracts.card_session_binding import CardSessionBinding
from ..contracts.card_state import CardState
from ..contracts.opening_record import OpeningRecord
from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.worldbook_binding import WorldbookBinding
from ..storage.sqlite.card_definition_store import SqliteCardDefinitionStore
from .round_snapshot_builder import RoundSnapshotBuilder
from .session_runtime_registry import SessionRuntimeStoreRegistry
from .version_locked_worldbook_resolver import VersionLockedWorldbookResolver


@dataclass
class SessionRuntimeBundle:
    """All data loaded from persistent stores for a single turn execution."""

    card_session_binding: CardSessionBinding | None = None
    card_state: CardState | None = None
    opening_record: OpeningRecord | None = None
    worldbook_binding: WorldbookBinding | None = None
    round_snapshot: RoundSnapshot | None = None
    worldbook_retrieval: dict[str, Any] = field(default_factory=dict)
    l1_turn_count: int = 0
    l2_active_memory_count: int = 0
    l3_rag_recall_count: int = 0
    load_errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return (
            self.card_session_binding is not None
            and self.card_state is not None
            and self.opening_record is not None
            and self.worldbook_binding is not None
            and len(self.load_errors) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_session_binding": self.card_session_binding.to_dict() if self.card_session_binding else None,
            "card_state": self.card_state.to_dict() if self.card_state else None,
            "opening_record": self.opening_record.to_dict() if self.opening_record else None,
            "worldbook_binding": self.worldbook_binding.to_dict() if self.worldbook_binding else None,
            "round_snapshot_id": self.round_snapshot.snapshot_id if self.round_snapshot else "",
            "worldbook_retrieval": dict(self.worldbook_retrieval),
            "l1_turn_count": self.l1_turn_count,
            "l2_active_memory_count": self.l2_active_memory_count,
            "l3_rag_recall_count": self.l3_rag_recall_count,
            "load_errors": list(self.load_errors),
        }


class SessionRuntimeLoad:
    """Loads session state from persistent stores and builds RoundSnapshot."""

    def __init__(
        self,
        registry: SessionRuntimeStoreRegistry,
        max_turn_history: int = 5,
        max_active_memories: int = 15,
    ):
        self._registry = registry
        self._max_turn_history = max_turn_history
        self._max_active_memories = max_active_memories
        self._card_definitions = SqliteCardDefinitionStore(registry.db)

    def load(
        self,
        session_id: str,
        player_input: str,
        expected_logical_card_id: str = "",
        expected_card_version: int = 0,
        expected_source_hash: str = "",
        worldbook_entries: list[dict[str, Any]] | None = None,
    ) -> SessionRuntimeBundle:
        bundle = SessionRuntimeBundle()

        binding = self._registry.card_session_binding_store.load(session_id)
        if not binding:
            bundle.load_errors.append(f"No CardSessionBinding for session {session_id}")
            return bundle
        bundle.card_session_binding = binding

        if expected_logical_card_id and binding.logical_card_id != expected_logical_card_id:
            bundle.load_errors.append(
                f"logicalCardId mismatch: binding={binding.logical_card_id}, expected={expected_logical_card_id}"
            )
        if expected_card_version and binding.card_version != expected_card_version:
            bundle.load_errors.append(
                f"cardVersion mismatch: binding={binding.card_version}, expected={expected_card_version}"
            )
        if expected_source_hash and binding.source_hash != expected_source_hash:
            bundle.load_errors.append(
                f"sourceHash mismatch: binding={binding.source_hash}, expected={expected_source_hash}"
            )
        if getattr(binding, "status", "") != "ready":
            bundle.load_errors.append(
                f"Session status is '{binding.status}', expected 'ready'"
            )
        if bundle.load_errors:
            return bundle

        card_state = self._registry.card_state_store.load(binding.logical_card_id, session_id)
        if not card_state:
            card_state = self._registry.card_state_store.initialize(binding.logical_card_id, session_id)
        bundle.card_state = card_state

        opening = self._registry.opening_record_store.get_by_session(session_id)
        if not opening:
            bundle.load_errors.append(f"No OpeningRecord for session {session_id}")
            return bundle
        bundle.opening_record = opening

        worldbook_binding = self._registry.worldbook_binding_store.get_by_session(session_id)
        if not worldbook_binding:
            bundle.load_errors.append(f"No WorldbookBinding for session {session_id}")
            return bundle
        bundle.worldbook_binding = worldbook_binding

        recent_turns = self._registry.turn_record_store.get_recent(
            binding.logical_card_id,
            session_id,
            limit=self._max_turn_history,
        )

        if worldbook_entries is None:
            try:
                # P1: pass CardState context for condition-based worldbook activation
                card_state_ctx = card_state.to_dict() if card_state else {}
                retrieval = VersionLockedWorldbookResolver(self._card_definitions).resolve(
                    binding=binding,
                    worldbook_binding=worldbook_binding,
                    opening_record=opening,
                    player_input=player_input,
                    recent_turns=recent_turns,
                    card_state_context=card_state_ctx,
                )
            except ValueError as e:
                bundle.load_errors.append(str(e))
                return bundle
            bundle.worldbook_retrieval = retrieval
            worldbook_entries = list(retrieval.get("activated_content", []))
        else:
            bundle.worldbook_retrieval = {
                "activated_content": list(worldbook_entries),
            }

        snapshot_builder = RoundSnapshotBuilder(
            card_state_store=self._registry.card_state_store,
            turn_record_store=self._registry.turn_record_store,
            active_memory_store=self._registry.active_memory_store,
            rag_memory_store=self._registry.rag_memory_store,
            max_turn_history=self._max_turn_history,
            max_active_memories=self._max_active_memories,
        )
        snapshot = snapshot_builder.build(
            card_id=binding.logical_card_id,
            session_id=session_id,
            player_input=player_input,
            worldbook_entries=worldbook_entries,
            card_profile_context=self._load_card_profile_context(binding),
        )
        bundle.round_snapshot = snapshot
        bundle.l1_turn_count = len(snapshot.recent_turn_records)
        bundle.l2_active_memory_count = len(snapshot.active_memories)
        bundle.l3_rag_recall_count = len(snapshot.rag_recall)
        return bundle

    def _load_card_profile_context(self, binding: CardSessionBinding) -> dict[str, Any]:
        try:
            definition = self._card_definitions.load(
                binding.logical_card_id,
                binding.card_version,
            )
            if definition is None:
                definition = self._card_definitions.get_latest(binding.logical_card_id)
        except Exception:
            return {}
        if definition is None:
            return {}
        profile = dict(getattr(definition, "profile", {}) or {})
        if not profile.get("name"):
            profile["name"] = (
                getattr(definition, "display_name", "")
                or getattr(definition, "name", "")
                or binding.logical_card_id
            )
        profile["logical_card_id"] = binding.logical_card_id
        profile["card_version"] = getattr(definition, "card_version", binding.card_version)
        return profile
