from __future__ import annotations

import asyncio
from types import SimpleNamespace

from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.storage.sqlite.database import Database
from awp_rp_runtime_v2.tests.factories import (
    make_binding,
    make_opening_record,
    make_turn_record,
)
from awp_rp_runtime_v2.tests.test_management_api_new_endpoints import (
    _Request,
    _data,
    _load_api,
)


def _registry(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


def _seed_history(reg):
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    reg.opening_record_store.save(
        make_opening_record(session_id="s1", logical_card_id="c1", content="Opening line")
    )
    for index in range(3):
        reg.turn_record_store.save(
            make_turn_record(
                session_id="s1",
                card_id="c1",
                turn_id=f"t{index}",
                turn_index=index,
                player_input=f"player {index}",
                writer_output=f"turn {index}",
            )
        )


def test_reopen_session_shows_full_history_from_stores(tmp_path):
    reg = _registry(tmp_path)
    _seed_history(reg)

    turns = reg.turn_record_store.list_by_session("s1")
    opening = reg.opening_record_store.get_by_session("s1")

    assert opening is not None
    assert opening.safe_display_content == "Opening line"
    assert len(turns) == 3
    assert [turn.turn_index for turn in turns] == [0, 1, 2]
    assert [turn.writer_output for turn in turns] == ["turn 0", "turn 1", "turn 2"]


def test_reopen_session_api_returns_opening_and_all_turns(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    _seed_history(reg)
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    get_session = routes.handlers[("GET", "/awp/api/v1/sessions/{session_id}")]
    list_turns = routes.handlers[("GET", "/awp/api/v1/sessions/{session_id}/turns")]
    get_opening = routes.handlers[("GET", "/awp/api/v1/sessions/{session_id}/opening")]

    session_response = asyncio.run(get_session(_Request(match_info={"session_id": "s1"})))
    turns_response = asyncio.run(list_turns(_Request(match_info={"session_id": "s1"})))
    opening_response = asyncio.run(get_opening(_Request(match_info={"session_id": "s1"})))

    assert session_response.status == 200
    assert _data(session_response)["opening_content"] == "Opening line"
    turns = _data(turns_response)
    assert [turn["turn_index"] for turn in turns] == [0, 1, 2]
    assert [turn["writer_output"] for turn in turns] == ["turn 0", "turn 1", "turn 2"]
    assert _data(opening_response)["content"] == "Opening line"
