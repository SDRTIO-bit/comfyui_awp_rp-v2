"""Tests for RoundSnapshot contract."""

import pytest
from awp_rp_runtime_v2.contracts.round_snapshot import RoundSnapshot
from awp_rp_runtime_v2.contracts.card_state import CardState
from awp_rp_runtime_v2.contracts.turn_record import TurnRecord


class TestRoundSnapshotContract:

    def test_immutability(self):
        snapshot = RoundSnapshot(card_id="c", session_id="s", player_input="test")
        with pytest.raises(AttributeError):
            snapshot.player_input = "changed"

    def test_serialize_roundtrip(self):
        state = CardState(card_id="c", session_id="s", revision=3)
        turn = TurnRecord(turn_id="t1", card_id="c", session_id="s",
                          player_input="hello", writer_output="world")
        snapshot = RoundSnapshot(
            snapshot_id="snap1", trace_id="trace1",
            card_id="c", session_id="s",
            base_card_state_revision=3, card_state=state,
            player_input="test input", recent_turn_records=[turn],
            card_profile_context={"name": "Ari", "personality": "guarded"},
        )
        restored = RoundSnapshot.from_dict(snapshot.to_dict())
        assert restored.snapshot_id == "snap1"
        assert restored.card_id == "c"
        assert restored.base_card_state_revision == 3
        assert restored.card_profile_context["name"] == "Ari"
        assert restored.card_profile_context["personality"] == "guarded"

    def test_empty_snapshot(self):
        snapshot = RoundSnapshot()
        restored = RoundSnapshot.from_dict(snapshot.to_dict())
        assert restored.card_id == ""
