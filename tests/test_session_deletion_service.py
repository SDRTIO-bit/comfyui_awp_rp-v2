from awp_rp_runtime_v2.runtime.session_deletion_service import SessionDeletionService
from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.storage.sqlite.database import Database
from awp_rp_runtime_v2.tests.factories import (
    make_binding,
    make_bootstrap_receipt,
    make_card_definition,
    make_opening_record,
    make_turn_record,
    make_worldbook_binding,
)


def _registry(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


def _seed_session(reg, session_id: str, logical_card_id: str = "c1") -> None:
    reg.card_session_binding_store.save(
        make_binding(session_id=session_id, logical_card_id=logical_card_id)
    )
    reg.turn_record_store.save(
        make_turn_record(session_id=session_id, card_id=logical_card_id, turn_id=f"t-{session_id}")
    )
    reg.opening_record_store.save(
        make_opening_record(session_id=session_id, logical_card_id=logical_card_id)
    )
    reg.worldbook_binding_store.save(
        make_worldbook_binding(session_id=session_id, logical_card_id=logical_card_id)
    )
    reg.bootstrap_receipt_store.save(
        make_bootstrap_receipt(session_id=session_id, logical_card_id=logical_card_id)
    )


def test_delete_session_cascades_all(tmp_path):
    reg = _registry(tmp_path)
    _seed_session(reg, "s1", "c1")

    svc = SessionDeletionService(reg)
    svc.delete_session("s1")

    assert reg.card_session_binding_store.load("s1") is None
    assert reg.turn_record_store.list_by_session("s1") == []
    assert reg.opening_record_store.get_by_session("s1") is None
    assert reg.worldbook_binding_store.get_by_session("s1") is None
    assert reg.bootstrap_receipt_store.load("receipt-s1") is None


def test_delete_card_cascades_sessions(tmp_path):
    reg = _registry(tmp_path)
    reg.card_definition_store.save(make_card_definition(logical_card_id="c1"))
    _seed_session(reg, "s1", "c1")
    _seed_session(reg, "s2", "c1")
    _seed_session(reg, "s3", "c2")

    svc = SessionDeletionService(reg)
    svc.delete_card("c1")

    assert reg.card_definition_store.get_latest("c1") is None
    assert reg.card_session_binding_store.list_by_card("c1") == []
    assert reg.turn_record_store.list_by_session("s1") == []
    assert reg.turn_record_store.list_by_session("s2") == []
    assert reg.card_session_binding_store.load("s3") is not None
