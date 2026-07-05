from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.storage.sqlite.database import Database


def test_registry_exposes_card_definition_store(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    registry = SessionRuntimeStoreRegistry(db)

    assert registry.card_definition_store is not None
    assert isinstance(registry.card_definition_store.list_all(), list)
