"""Application-level cascade deletion for card sessions and cards."""

from __future__ import annotations

from .session_runtime_registry import SessionRuntimeStoreRegistry


class SessionDeletionService:
    def __init__(self, registry: SessionRuntimeStoreRegistry) -> None:
        self._registry = registry

    def delete_session(self, session_id: str) -> None:
        registry = self._registry
        registry.turn_record_store.delete_by_session(session_id)
        registry.opening_record_store.delete_by_session(session_id)
        registry.worldbook_binding_store.delete_by_session(session_id)
        registry.bootstrap_receipt_store.delete_by_session(session_id)
        registry.card_session_binding_store.delete(session_id)

    def delete_card(self, logical_card_id: str) -> None:
        registry = self._registry
        for binding in registry.card_session_binding_store.list_by_card(logical_card_id):
            self.delete_session(binding.session_id)
        registry.card_definition_store.delete(logical_card_id)
