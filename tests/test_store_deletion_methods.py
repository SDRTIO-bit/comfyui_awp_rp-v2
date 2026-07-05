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


def test_card_definition_delete_and_list_by_card(tmp_path):
    reg = _registry(tmp_path)
    cd = make_card_definition(logical_card_id="card-1")
    reg.card_definition_store.save(cd)

    assert reg.card_definition_store.get_latest("card-1") is not None
    assert [c.logical_card_id for c in reg.card_definition_store.list_by_card("card-1")] == ["card-1"]

    reg.card_definition_store.delete("card-1")

    assert reg.card_definition_store.get_latest("card-1") is None
    assert reg.card_definition_store.list_by_card("card-1") == []


def test_binding_delete_and_list_by_card(tmp_path):
    reg = _registry(tmp_path)
    b = make_binding(session_id="s1", logical_card_id="card-1")
    reg.card_session_binding_store.save(b)

    assert len(reg.card_session_binding_store.list_by_card("card-1")) == 1

    reg.card_session_binding_store.delete("s1")

    assert reg.card_session_binding_store.load("s1") is None
    assert len(reg.card_session_binding_store.list_by_card("card-1")) == 0


def test_turn_record_delete_by_session(tmp_path):
    reg = _registry(tmp_path)
    t = make_turn_record(session_id="s1")
    reg.turn_record_store.save(t)

    assert len(reg.turn_record_store.list_by_session("s1")) == 1

    reg.turn_record_store.delete_by_session("s1")

    assert len(reg.turn_record_store.list_by_session("s1")) == 0


def test_bootstrap_stores_delete_by_session(tmp_path):
    reg = _registry(tmp_path)
    reg.opening_record_store.save(make_opening_record(session_id="s1"))
    reg.worldbook_binding_store.save(make_worldbook_binding(session_id="s1"))
    reg.bootstrap_receipt_store.save(make_bootstrap_receipt(session_id="s1"))

    reg.opening_record_store.delete_by_session("s1")
    reg.worldbook_binding_store.delete_by_session("s1")
    reg.bootstrap_receipt_store.delete_by_session("s1")

    assert reg.opening_record_store.get_by_session("s1") is None
    assert reg.worldbook_binding_store.get_by_session("s1") is None
    assert reg.bootstrap_receipt_store.load("receipt-s1") is None
