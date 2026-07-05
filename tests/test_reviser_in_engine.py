from awp_rp_runtime_v2.runtime.provider_adapter_factory import AdapterOutcome
from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.tests.test_long_session_v1 import (
    _close_db,
    _make_db,
    _make_snapshot,
    _seed_session,
)


class _SequentialWriterAdapter:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls = 0

    def generate(self, bundle):
        self.calls += 1
        if self._outputs:
            return self._outputs.pop(0)
        return "Fallback accepted narrative. " * 20


def test_engine_revises_when_quality_fails_then_passes(monkeypatch, tmp_path):
    db = _make_db(str(tmp_path))
    registry = SessionRuntimeStoreRegistry(db)
    _seed_session(registry)
    snapshot = _make_snapshot(registry, "c1", "s1")
    card_state = registry.card_state_store.load("c1", "s1")
    binding = registry.card_session_binding_store.load("s1")
    bad_text = '{"bad": true}'
    revised_text = (
        "The scene settles into a grounded roleplay exchange with clear sensory "
        "detail, responsive pacing, and no system data. The character keeps the "
        "moment focused on the player input, preserves continuity, and leaves "
        "space for the next action. "
    ) * 3
    adapter = _SequentialWriterAdapter([bad_text, revised_text])

    from awp_rp_runtime_v2.runtime import persistent_turn_engine as engine_module

    monkeypatch.setattr(
        engine_module.WriterAdapterFactory,
        "build",
        staticmethod(
            lambda profile_id, preset_text="": (
                adapter,
                AdapterOutcome(
                    is_real=False,
                    provider="fake",
                    model="test-sequential-writer",
                    profile_id=profile_id,
                    api_key_env="",
                    built=True,
                ),
            )
        ),
    )

    engine = engine_module.PersistentTurnEngine(registry, profile="test")
    result = engine.execute(
        session_id="s1",
        player_input="hello",
        binding=binding,
        snapshot=snapshot,
        card_state=card_state,
        turn_id="t-revise",
        attempt_id="a-revise",
        request_id="r-revise",
        workflow_run_id="w-revise",
        trace_id="tc-revise",
        director_profile_id="fake-director",
        writer_profile_id="fake-writer",
        turn_kind="first",
    )
    diag = result[2]
    turn_record = result[4]

    assert diag["outcome"] == "success"
    assert adapter.calls == 2
    assert turn_record["writer_output"] == revised_text
    assert registry.turn_record_store.load("t-revise").writer_output == revised_text

    _close_db(db)
