from __future__ import annotations

import hashlib

from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.tests.test_long_session_v1 import (
    _close_db,
    _make_db,
    _make_snapshot,
    _seed_session,
)


def test_engine_stream_callbacks_emit_nine_steps_and_writer_text(tmp_path):
    db = _make_db(str(tmp_path))
    registry = SessionRuntimeStoreRegistry(db)
    _seed_session(registry)
    snapshot = _make_snapshot(registry, "c1", "s1")
    card_state = registry.card_state_store.load("c1", "s1")
    binding = registry.card_session_binding_store.load("s1")

    from awp_rp_runtime_v2.runtime.persistent_turn_engine import PersistentTurnEngine

    steps: list[tuple[str, dict]] = []
    writer_text: list[str] = []
    engine = PersistentTurnEngine(registry, profile="test")

    result = engine.execute(
        session_id="s1",
        player_input="hello",
        binding=binding,
        snapshot=snapshot,
        card_state=card_state,
        turn_id="t-stream",
        attempt_id="a-stream",
        request_id="r-stream",
        workflow_run_id="w-stream",
        trace_id="tc-stream",
        director_profile_id="fake-director",
        writer_profile_id="fake-writer",
        turn_kind="continuation",
        on_step=lambda name, payload: steps.append((name, payload)),
        on_writer_text=writer_text.append,
    )

    assert result[2]["outcome"] == "success"
    assert [name for name, _payload in steps] == [
        "round_snapshot",
        "director",
        "director_delegation",
        "sub_agents",
        "writer",
        "quality_gate",
        "turn_evolution_curator",
        "state_commit",
        "memory_curator",
    ]
    assert writer_text == [result[4]["writer_output"]]
    writer_payload = dict(steps)["writer"]
    assert "writer_output" not in writer_payload
    assert writer_payload["text_length"] == len(result[4]["writer_output"])
    assert writer_payload["text_hash"] == hashlib.sha256(
        result[4]["writer_output"].encode("utf-8")
    ).hexdigest()[:16]
    director_payload = dict(steps)["director"]
    assert director_payload["call_success"] is True
    assert director_payload["turn_goal"], "director step payload must carry turn_goal"
    assert director_payload["scene_focus"], "director step payload must carry scene_focus"
    assert isinstance(director_payload["must_preserve_facts"], list)
    assert isinstance(director_payload["must_not_do"], list)
    assert isinstance(director_payload["writer_constraints"], list)
    assert isinstance(director_payload["narrative_opportunities"], list)
    quality_payload = dict(steps)["quality_gate"]
    assert quality_payload["verdict"] == "pass"
    assert all(isinstance(payload["duration_ms"], int) for _name, payload in steps)
    _close_db(db)


def test_engine_stream_callback_exception_does_not_abort_turn(tmp_path):
    db = _make_db(str(tmp_path))
    registry = SessionRuntimeStoreRegistry(db)
    _seed_session(registry)
    snapshot = _make_snapshot(registry, "c1", "s1")
    card_state = registry.card_state_store.load("c1", "s1")
    binding = registry.card_session_binding_store.load("s1")

    from awp_rp_runtime_v2.runtime.persistent_turn_engine import PersistentTurnEngine

    def failing_callback(_name: str, _payload: dict) -> None:
        raise RuntimeError("observer failed")

    result = PersistentTurnEngine(registry, profile="test").execute(
        session_id="s1",
        player_input="hello",
        binding=binding,
        snapshot=snapshot,
        card_state=card_state,
        turn_id="t-stream-callback-failure",
        attempt_id="a-stream-callback-failure",
        request_id="r-stream-callback-failure",
        workflow_run_id="w-stream-callback-failure",
        trace_id="tc-stream-callback-failure",
        director_profile_id="fake-director",
        writer_profile_id="fake-writer",
        turn_kind="continuation",
        on_step=failing_callback,
        on_writer_text=lambda _text: None,
    )

    assert result[2]["outcome"] == "success"
    _close_db(db)
