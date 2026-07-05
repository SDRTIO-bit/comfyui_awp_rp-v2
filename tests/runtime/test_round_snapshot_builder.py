"""Tests for RoundSnapshotBuilder."""

import pytest
from awp_rp_runtime_v2.runtime.round_snapshot_builder import RoundSnapshotBuilder
from awp_rp_runtime_v2.testing.fakes.fake_stores import (
    FakeCardStateStore, FakeTurnRecordStore, FakeActiveMemoryStore, FakeRagMemoryStore,
)
from awp_rp_runtime_v2.contracts.turn_record import TurnRecord


class TestRoundSnapshotBuilder:

    def setup_method(self):
        self.card_store = FakeCardStateStore()
        self.turn_store = FakeTurnRecordStore()
        self.active_store = FakeActiveMemoryStore()
        self.rag_store = FakeRagMemoryStore()
        self.builder = RoundSnapshotBuilder(
            self.card_store, self.turn_store, self.active_store, self.rag_store,
        )

    def test_build_creates_snapshot(self):
        snapshot = self.builder.build("card1", "sess1", "Hello")
        assert snapshot.card_id == "card1"
        assert snapshot.player_input == "Hello"
        assert snapshot.snapshot_id != ""

    def test_build_initializes_state_if_missing(self):
        snapshot = self.builder.build("card1", "sess1", "Hello")
        assert snapshot.card_state.revision == 0

    def test_build_loads_existing_state(self):
        self.card_store.initialize("card1", "sess1")
        snapshot = self.builder.build("card1", "sess1", "Hello")
        assert snapshot.card_state.card_id == "card1"

    def test_snapshot_frozen(self):
        snapshot = self.builder.build("card1", "sess1", "Hello")
        with pytest.raises(AttributeError):
            snapshot.player_input = "Changed"

    def test_build_includes_turn_records(self):
        record = TurnRecord(turn_id="t1", card_id="card1", session_id="sess1",
                            player_input="prev", writer_output="response")
        self.turn_store.save(record)
        snapshot = self.builder.build("card1", "sess1", "Hello")
        assert len(snapshot.recent_turn_records) == 1

    def test_build_keeps_latest_five_and_summarizes_older_turns(self):
        for i in range(1, 7):
            self.turn_store.save(TurnRecord(
                turn_id=f"t{i}",
                card_id="card1",
                session_id="sess1",
                turn_index=i,
                player_input=f"player turn {i}",
                writer_output=f"writer turn {i} full text",
            ))

        snapshot = self.builder.build("card1", "sess1", "Hello")

        assert [turn.turn_index for turn in snapshot.recent_turn_records] == [6, 5, 4, 3, 2]
        assert all(turn.turn_index != 1 for turn in snapshot.recent_turn_records)
        assert "Turn 1" in snapshot.older_turns_summary
        assert "player turn 1" in snapshot.older_turns_summary
        assert "writer turn 1 full text" in snapshot.older_turns_summary
        assert "Turn 2" not in snapshot.older_turns_summary

    def test_memory_recall_query_preserves_full_player_input(self):
        player_input = "A" * 80 + " CRITICAL_MEMORY_TAIL"

        self.builder.build("card1", "sess1", player_input)

        assert self.active_store.recall_log[-1].request.query == player_input
        assert self.rag_store.recall_log[-1].request.query == player_input
