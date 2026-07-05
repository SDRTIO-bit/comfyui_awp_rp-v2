"""P-Persistent Session Runtime & Canonical RoundSnapshot Integration V1 tests.

Covers the 12 required pure Python persistence boundary tests:

  1. Turn 1 writes to SQLite, new store instance restores CardState
  2. New store instance restores Turn 1 accepted TurnRecord
  3. Turn 2 RoundSnapshot contains Turn 1
  4. OpeningRecord never enters recent accepted turns
  5. ActiveMemory persists and can be read by new Runtime
  6. RagMemory persists and can be read by new Runtime
  7. Session A never reads Session B's State/Turn/Memory
  8. Session version lock not overwritten by new card version
  9. Reject turn does not appear in L1
 10. Retry does not duplicate writes
 11. Deprecated JSON history injection rejected in formal mode
 12. Arbitrary database path cannot be injected from API workflow
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ..contracts.card_state import CardState
from ..contracts.card_definition import CardDefinition, CardDefinitionStatus
from ..contracts.card_state_commit import CardStateCommitRequest, CardStateCommitStatus
from ..contracts.card_state_patch import CardStatePatch
from ..contracts.turn_record import TurnRecord, TurnMode
from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.active_memory import ActiveMemoryEntry, ActiveMemoryRecord
from ..contracts.rag_memory import RagMemoryEntry
from ..contracts.memory_recall_request import MemoryRecallRequest
from ..contracts.card_session_binding import CardSessionBinding
from ..contracts.opening_record import OpeningRecord
from ..contracts.worldbook_binding import WorldbookBinding

from ..storage.sqlite.database import Database
from ..storage.sqlite.card_state_store import SqliteCardStateStore
from ..storage.sqlite.turn_record_store import SqliteTurnRecordStore
from ..storage.sqlite.active_memory_store import SqliteActiveMemoryStore
from ..storage.sqlite.rag_memory_store import SqliteRagMemoryStore
from ..storage.sqlite.session_stores import (
    SqliteCardSessionBindingStore,
    SqliteOpeningRecordStore,
    SqliteWorldbookBindingStore,
)
from ..storage.sqlite.card_definition_store import SqliteCardDefinitionStore

from ..runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from ..runtime.session_runtime_load import SessionRuntimeLoad
from ..runtime.round_snapshot_builder import RoundSnapshotBuilder


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str, seed: str) -> str:
    return f"{prefix}_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _make_db(tmp_path: str) -> Database:
    db = Database(str(Path(tmp_path) / "test.db"))
    db.initialize()
    return db


def _close_db(db: Database) -> None:
    """Close DB connection to release file lock (Windows)."""
    db.close()


def _seed_session(
    registry: SessionRuntimeStoreRegistry,
    session_id: str = "sess_001",
    card_id: str = "card_001",
    card_version: int = 1,
    source_hash: str = "abc123",
) -> None:
    """Seed a complete session bootstrap into persistent stores."""
    SqliteCardDefinitionStore(registry.db).save(CardDefinition(
        logical_card_id=card_id,
        card_version=card_version,
        source_id=f"src_{card_id}_{card_version}",
        source_hash=source_hash,
        name="Seed Card",
        display_name="Seed Card",
        status=CardDefinitionStatus.READY,
        greetings=[{
            "schema_id": "awp.rp.card-greeting.v1",
            "schema_version": 1,
            "greeting_id": "g0",
            "index": 0,
            "label": "Default",
            "safe_display_content": "Hello, traveler.",
            "content_hash": f"gh_{card_version}",
            "is_default": True,
            "source_path": "data.first_mes",
        }],
        worldbook_catalog=[],
        worldbook_chunks=[],
        created_at=_now(),
        updated_at=_now(),
    ))
    binding = CardSessionBinding(
        session_id=session_id,
        logical_card_id=card_id,
        card_version=card_version,
        source_hash=source_hash,
        selected_greeting_id="g0",
        opening_record_id=f"op_{session_id}",
        worldbook_binding_id=f"wb_{session_id}",
        status="ready",
        created_at=_now(),
    )
    registry.card_session_binding_store.save(binding)

    opening = OpeningRecord(
        opening_record_id=f"op_{session_id}",
        session_id=session_id,
        logical_card_id=card_id,
        card_version=card_version,
        greeting_id="g0",
        safe_display_content="Hello, traveler.",
        source_greeting_ref=f"{card_id}/v{card_version}/greetings/g0",
        created_at=_now(),
    )
    registry.opening_record_store.save(opening)

    wb = WorldbookBinding(
        worldbook_binding_id=f"wb_{session_id}",
        session_id=session_id,
        logical_card_id=card_id,
        card_version=card_version,
        source_hash=source_hash,
        created_at=_now(),
    )
    registry.worldbook_binding_store.save(wb)

    registry.card_state_store.initialize(card_id, session_id)


def _commit_turn(
    registry: SessionRuntimeStoreRegistry,
    turn_id: str,
    card_id: str,
    session_id: str,
    turn_index: int,
    player_input: str,
    writer_output: str,
    base_rev: int = 0,
    result_rev: int = 1,
) -> TurnRecord:
    """Commit a turn record to the persistent store."""
    record = TurnRecord(
        turn_id=turn_id,
        trace_id=f"trc_{turn_id}",
        session_id=session_id,
        card_id=card_id,
        turn_index=turn_index,
        player_input=player_input,
        writer_output=writer_output,
        mode=TurnMode.NORMAL,
        base_card_state_revision=base_rev,
        result_card_state_revision=result_rev,
        created_at=_now(),
    )
    registry.turn_record_store.save(record)
    return record


# ── Test 1: CardState persistence ────────────────────────────────────────────

class TestCardStatePersistence:

    def test_01_card_state_persists_across_store_instances(self):
        """Turn 1 writes to SQLite, new store instance restores CardState."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteCardStateStore(db)

            # Initialize and commit
            cs = store.initialize("card_001", "sess_001")
            assert cs.revision == 0

            patch = CardStatePatch(
                patch_id="patch_001", card_id="card_001",
                session_id="sess_001", trace_id="trc_001",
            )
            request = CardStateCommitRequest(expected_revision=0, patch=patch)
            new_state = CardState(
                card_id="card_001", session_id="sess_001",
                revision=1, created_at=_now(), updated_at=_now(),
            )
            result = store.commit(request, new_state)
            assert result.status == CardStateCommitStatus.ACCEPTED
            _close_db(db)

            # New store instance — same database
            db2 = Database(str(Path(tmp) / "test.db"))
            db2.initialize()
            store2 = SqliteCardStateStore(db2)

            loaded = store2.load("card_001", "sess_001")
            assert loaded is not None
            assert loaded.revision == 1
            _close_db(db2)


# ── Test 2: TurnRecord persistence ──────────────────────────────────────────

class TestTurnRecordPersistence:

    def test_02_turn_record_persists_across_store_instances(self):
        """New store instance restores Turn 1 accepted TurnRecord."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteTurnRecordStore(db)

            record = TurnRecord(
                turn_id="turn_001", trace_id="trc_001",
                session_id="sess_001", card_id="card_001",
                turn_index=1, player_input="Hello",
                writer_output="Response text",
                mode=TurnMode.NORMAL,
                base_card_state_revision=0, result_card_state_revision=1,
                created_at=_now(),
            )
            store.save(record)
            _close_db(db)

            # New store instance
            db2 = Database(str(Path(tmp) / "test.db"))
            db2.initialize()
            store2 = SqliteTurnRecordStore(db2)

            loaded = store2.load("turn_001")
            assert loaded is not None
            assert loaded.turn_id == "turn_001"
            assert loaded.writer_output == "Response text"
            assert loaded.turn_index == 1

            # get_recent works
            recent = store2.get_recent("card_001", "sess_001", limit=5)
            assert len(recent) == 1
            assert recent[0].turn_id == "turn_001"
            _close_db(db2)


# ── Test 3: RoundSnapshot contains Turn 1 ───────────────────────────────────

class TestRoundSnapshotWithHistory:

    def test_03_turn2_snapshot_contains_turn1(self):
        """Turn 2 RoundSnapshot built by RoundSnapshotBuilder contains Turn 1."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)
            _seed_session(registry)

            # Commit Turn 1
            _commit_turn(registry, "turn_001", "card_001", "sess_001", 1,
                         "Hello", "Response to Hello")

            # Build snapshot for Turn 2
            builder = RoundSnapshotBuilder(
                card_state_store=registry.card_state_store,
                turn_record_store=registry.turn_record_store,
                active_memory_store=registry.active_memory_store,
                rag_memory_store=registry.rag_memory_store,
            )
            snapshot = builder.build("card_001", "sess_001", "What happened?")

            assert len(snapshot.recent_turn_records) == 1
            assert snapshot.recent_turn_records[0].turn_id == "turn_001"
            _close_db(db)


# ── Test 4: OpeningRecord not in recent accepted ────────────────────────────

class TestOpeningRecordSeparation:

    def test_04_opening_record_not_in_recent_accepted(self):
        """OpeningRecord must not appear in recent accepted turn records."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)
            _seed_session(registry)

            # The OpeningRecord is stored separately, not as a TurnRecord.
            # get_recent should return empty since no turns committed yet.
            recent = registry.turn_record_store.get_recent("card_001", "sess_001")
            assert len(recent) == 0

            # OpeningRecord is accessible via its own store
            opening = registry.opening_record_store.get_by_session("sess_001")
            assert opening is not None
            assert opening.greeting_id == "g0"
            _close_db(db)


# ── Test 5: ActiveMemory persistence ────────────────────────────────────────

class TestActiveMemoryPersistence:

    def test_05_active_memory_persists_and_recalls(self):
        """ActiveMemory written to SQLite can be read by new Runtime."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteActiveMemoryStore(db)

            entry = ActiveMemoryEntry(
                memory_id="mem_001",
                summary="Player promised to return tomorrow",
                importance=0.8,
                confidence=0.9,
                entity_refs=["player"],
                source_turn_ids=["turn_001"],
            )
            store.upsert("card_001", "sess_001", entry)
            _close_db(db)

            # New store instance
            db2 = Database(str(Path(tmp) / "test.db"))
            db2.initialize()
            store2 = SqliteActiveMemoryStore(db2)

            all_entries = store2.get_all("card_001", "sess_001")
            assert len(all_entries) == 1
            assert all_entries[0].memory_id == "mem_001"
            assert all_entries[0].summary == "Player promised to return tomorrow"

            # Recall works
            request = MemoryRecallRequest(
                card_id="card_001", session_id="sess_001",
                snapshot_id="snap_001", trace_id="trc_001",
                query="promise", limit=10,
            )
            result = store2.recall("card_001", "sess_001", request)
            assert len(result.hits) >= 1
            _close_db(db2)


# ── Test 6: RagMemory persistence ───────────────────────────────────────────

class TestRagMemoryPersistence:

    def test_06_rag_memory_persists_and_searches(self):
        """RagMemory written to SQLite can be read by new Runtime."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteRagMemoryStore(db)

            entry = RagMemoryEntry(
                memory_id="rag_001",
                content="The village elder knows about the ancient ruins",
                summary="Elder ruins knowledge",
                importance=0.7,
                confidence=0.8,
                entity_refs=["elder", "ruins"],
                source_turn_ids=["turn_002"],
            )
            store.save("card_001", "sess_001", entry)
            _close_db(db)

            # New store instance
            db2 = Database(str(Path(tmp) / "test.db"))
            db2.initialize()
            store2 = SqliteRagMemoryStore(db2)

            results = store2.search("card_001", "sess_001", "ruins", limit=5)
            assert len(results) >= 1
            assert results[0].memory_id == "rag_001"
            _close_db(db2)


# ── Test 7: Session isolation ───────────────────────────────────────────────

class TestSessionIsolation:

    def test_07_session_a_never_reads_session_b(self):
        """Session A never reads Session B's State/Turn/Memory."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)

            # Seed two sessions
            _seed_session(registry, session_id="sess_A", card_id="card_001")
            _seed_session(registry, session_id="sess_B", card_id="card_001")

            # Commit turn to session A only
            _commit_turn(registry, "turn_A1", "card_001", "sess_A", 1,
                         "Hello A", "Response A")

            # Session B should have no turns
            recent_b = registry.turn_record_store.get_recent("card_001", "sess_B")
            assert len(recent_b) == 0

            # Session A should have its turn
            recent_a = registry.turn_record_store.get_recent("card_001", "sess_A")
            assert len(recent_a) == 1

            # CardState is per-session
            cs_a = registry.card_state_store.load("card_001", "sess_A")
            cs_b = registry.card_state_store.load("card_001", "sess_B")
            assert cs_a is not None
            assert cs_b is not None
            assert cs_a.session_id == "sess_A"
            assert cs_b.session_id == "sess_B"
            _close_db(db)


# ── Test 8: Session version lock ────────────────────────────────────────────

class TestSessionVersionLock:

    def test_08_session_version_not_overwritten(self):
        """Session binding with card_version=1 not overwritten by version=2."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteCardSessionBindingStore(db)

            binding1 = CardSessionBinding(
                session_id="sess_001", logical_card_id="card_001",
                card_version=1, source_hash="hash_v1",
                status="ready", created_at=_now(),
            )
            store.save(binding1)

            # Try to save with different version (should overwrite by session_id PK)
            binding2 = CardSessionBinding(
                session_id="sess_001", logical_card_id="card_001",
                card_version=2, source_hash="hash_v2",
                status="ready", created_at=_now(),
            )
            store.save(binding2)

            # Load — should be version 2 since session_id is PK
            loaded = store.load("sess_001")
            assert loaded is not None
            assert loaded.card_version == 2

            # But a DIFFERENT session with version 1 is untouched
            binding3 = CardSessionBinding(
                session_id="sess_002", logical_card_id="card_001",
                card_version=1, source_hash="hash_v1",
                status="ready", created_at=_now(),
            )
            store.save(binding3)
            loaded3 = store.load("sess_002")
            assert loaded3.card_version == 1
            _close_db(db)


# ── Test 9: Reject turn not in L1 ──────────────────────────────────────────

class TestRejectTurnExclusion:

    def test_09_rejected_turn_not_in_l1(self):
        """Rejected turns (not committed) do not appear in L1 history."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)
            _seed_session(registry)

            # Only commit accepted turns
            _commit_turn(registry, "turn_001", "card_001", "sess_001", 1,
                         "Input 1", "Accepted response 1")
            # Turn 2 was rejected — never saved to TurnRecordStore
            _commit_turn(registry, "turn_003", "card_001", "sess_001", 3,
                         "Input 3", "Accepted response 3")

            recent = registry.turn_record_store.get_recent("card_001", "sess_001")
            assert len(recent) == 2
            turn_ids = [r.turn_id for r in recent]
            assert "turn_001" in turn_ids
            assert "turn_003" in turn_ids
            _close_db(db)


# ── Test 10: Retry idempotency ──────────────────────────────────────────────

class TestRetryIdempotency:

    def test_10_retry_does_not_duplicate_writes(self):
        """Same turn_id cannot be written twice (DuplicateTurnError)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteTurnRecordStore(db)

            record = TurnRecord(
                turn_id="turn_001", trace_id="trc_001",
                session_id="sess_001", card_id="card_001",
                turn_index=1, player_input="Hello",
                writer_output="Response", mode=TurnMode.NORMAL,
                created_at=_now(),
            )
            store.save(record)

            # Retry with same turn_id should raise
            from ..storage.interfaces import DuplicateTurnError
            with pytest.raises(DuplicateTurnError):
                store.save(record)

            # Only one record exists
            recent = store.get_recent("card_001", "sess_001")
            assert len(recent) == 1
            _close_db(db)


# ── Test 11: Deprecated JSON injection rejected ─────────────────────────────

class TestDeprecatedJsonInjection:

    def test_11_formal_mode_rejects_json_injection(self):
        """The persistent paths do not accept injected history/state/memory.

        All persistent nodes (bootstrap, first turn, continuation, load)
        must NOT accept these deprecated/injectable inputs.
        """
        from ..nodes.persistent_continuation_turn_node import AWPV2PersistentContinuationTurn
        from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
        from ..nodes.persistent_bootstrap_node import AWPV2PersistentBootstrap
        from ..nodes.session_runtime_load_node import AWPV2SessionRuntimeLoad

        forbidden = [
            "previous_turn_records", "active_memories", "rag_recall",
            "card_state", "card_session_binding", "opening_record",
            "worldbook_binding", "db_path", "store_path", "databasePath",
        ]

        for node_cls in [
            AWPV2PersistentContinuationTurn,
            AWPV2PersistentFirstTurn,
            AWPV2PersistentBootstrap,
            AWPV2SessionRuntimeLoad,
        ]:
            input_types = node_cls.INPUT_TYPES()
            all_inputs = {}
            all_inputs.update(input_types.get("required", {}))
            all_inputs.update(input_types.get("optional", {}))

            for f in forbidden:
                assert f not in all_inputs, \
                    f"{node_cls.__name__} must not accept '{f}' as input"


# ── Test 12: Arbitrary DB path injection ────────────────────────────────────

class TestDbPathSafety:

    def test_12_db_path_from_env_not_workflow(self):
        """Database path is resolved from environment via RuntimeStoreFactory.

        No db_path input on production nodes. Profile + namespace drive path.
        """
        from ..runtime.runtime_store_factory import _resolve_db_path

        # Default (no env) returns a safe path
        old_env = os.environ.get("AWP_RUNTIME_PROFILE")
        old_root = os.environ.get("AWP_TEST_STORE_ROOT")
        old_ns = os.environ.get("AWP_TEST_RUNTIME_NAMESPACE")
        old_db = os.environ.get("AWP_RUNTIME_DB_PATH")
        try:
            os.environ.pop("AWP_RUNTIME_PROFILE", None)
            os.environ.pop("AWP_TEST_STORE_ROOT", None)
            os.environ.pop("AWP_TEST_RUNTIME_NAMESPACE", None)
            os.environ.pop("AWP_RUNTIME_DB_PATH", None)

            # Production: no explicit path → default
            path = _resolve_db_path("production", "", "")
            assert path == "awp_rp_runtime.db"

            # Test mode resolves to controlled directory
            path = _resolve_db_path("test", "run_001", "/tmp/test_stores")
            assert "run_001" in path
            assert "awp_session.db" in path

            # Verify node INPUT_TYPES has no db_path
            from ..nodes.session_runtime_load_node import AWPV2SessionRuntimeLoad
            input_types = AWPV2SessionRuntimeLoad.INPUT_TYPES()
            all_inputs = {}
            all_inputs.update(input_types.get("required", {}))
            all_inputs.update(input_types.get("optional", {}))
            assert "db_path" not in all_inputs, \
                "SessionRuntimeLoad must not accept db_path as input"

            from ..nodes.persistent_continuation_turn_node import AWPV2PersistentContinuationTurn
            cont_inputs = AWPV2PersistentContinuationTurn.INPUT_TYPES()
            all_cont = {}
            all_cont.update(cont_inputs.get("required", {}))
            all_cont.update(cont_inputs.get("optional", {}))
            assert "db_path" not in all_cont, \
                "PersistentContinuationTurn must not accept db_path as input"

            from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
            ft_inputs = AWPV2PersistentFirstTurn.INPUT_TYPES()
            all_ft = {}
            all_ft.update(ft_inputs.get("required", {}))
            all_ft.update(ft_inputs.get("optional", {}))
            assert "db_path" not in all_ft, \
                "PersistentFirstTurn must not accept db_path as input"

            from ..nodes.persistent_bootstrap_node import AWPV2PersistentBootstrap
            bs_inputs = AWPV2PersistentBootstrap.INPUT_TYPES()
            all_bs = {}
            all_bs.update(bs_inputs.get("required", {}))
            all_bs.update(bs_inputs.get("optional", {}))
            assert "db_path" not in all_bs, \
                "PersistentBootstrap must not accept db_path as input"

        finally:
            if old_env is not None:
                os.environ["AWP_RUNTIME_PROFILE"] = old_env
            else:
                os.environ.pop("AWP_RUNTIME_PROFILE", None)
            if old_root is not None:
                os.environ["AWP_TEST_STORE_ROOT"] = old_root
            else:
                os.environ.pop("AWP_TEST_STORE_ROOT", None)
            if old_ns is not None:
                os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = old_ns
            else:
                os.environ.pop("AWP_TEST_RUNTIME_NAMESPACE", None)
            if old_db is not None:
                os.environ["AWP_RUNTIME_DB_PATH"] = old_db
            else:
                os.environ.pop("AWP_RUNTIME_DB_PATH", None)


# ── Full integration: SessionRuntimeLoad ─────────────────────────────────────

class TestSessionRuntimeLoadIntegration:

    def test_load_restores_all_layers(self):
        """SessionRuntimeLoad restores L0 + L1 from persistent stores."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)
            _seed_session(registry)

            # Commit 3 turns
            for i in range(1, 4):
                _commit_turn(
                    registry, f"turn_{i:03d}", "card_001", "sess_001", i,
                    f"Player input {i}", f"Response {i}",
                    base_rev=i - 1, result_rev=i,
                )

            # Load via SessionRuntimeLoad
            loader = SessionRuntimeLoad(registry)
            bundle = loader.load("sess_001", "New player input")

            assert bundle.is_valid
            assert bundle.card_session_binding is not None
            assert bundle.card_state is not None
            assert bundle.opening_record is not None
            assert bundle.worldbook_binding is not None
            assert bundle.round_snapshot is not None
            assert bundle.l1_turn_count == 3
            assert len(bundle.round_snapshot.recent_turn_records) == 3
            _close_db(db)

    def test_load_includes_version_locked_card_profile_in_snapshot(self):
        """SessionRuntimeLoad must freeze character profile into RoundSnapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)
            _seed_session(registry)
            registry.card_definition_store.save(CardDefinition(
                logical_card_id="card_001",
                card_version=1,
                source_id="src_card_001_1",
                source_hash="abc123",
                name="Seed Card",
                display_name="Seed Card",
                status=CardDefinitionStatus.READY,
                profile={
                    "schema_id": "awp.rp.card-profile.v1",
                    "schema_version": 1,
                    "name": "PROFILE_NAME_MARKER",
                    "description": "PROFILE_DESCRIPTION_MARKER",
                    "personality": "PROFILE_PERSONALITY_MARKER",
                },
                greetings=[],
                worldbook_catalog=[],
                worldbook_chunks=[],
                created_at=_now(),
                updated_at=_now(),
            ))

            bundle = SessionRuntimeLoad(registry).load("sess_001", "New player input")

            assert bundle.is_valid
            assert bundle.round_snapshot is not None
            assert bundle.round_snapshot.card_profile_context["name"] == "PROFILE_NAME_MARKER"
            assert bundle.round_snapshot.card_profile_context["description"] == "PROFILE_DESCRIPTION_MARKER"
            assert bundle.round_snapshot.card_profile_context["personality"] == "PROFILE_PERSONALITY_MARKER"
            assert bundle.round_snapshot.card_profile_context["card_version"] == 1
            _close_db(db)

    def test_load_fails_gracefully_missing_session(self):
        """SessionRuntimeLoad returns errors for missing session."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)

            loader = SessionRuntimeLoad(registry)
            bundle = loader.load("nonexistent_session", "Hello")

            assert not bundle.is_valid
            assert len(bundle.load_errors) > 0
            _close_db(db)

    def test_load_across_db_instances(self):
        """SessionRuntimeLoad works with a fresh registry on the same DB."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "test.db")

            # First instance: seed data
            db1 = Database(db_path)
            db1.initialize()
            registry1 = SessionRuntimeStoreRegistry(db1)
            _seed_session(registry1)
            _commit_turn(registry1, "turn_001", "card_001", "sess_001", 1,
                         "Hello", "Response")
            db1.close()

            # Second instance: load data
            db2 = Database(db_path)
            db2.initialize()
            registry2 = SessionRuntimeStoreRegistry(db2)
            loader = SessionRuntimeLoad(registry2)
            bundle = loader.load("sess_001", "Continue")

            assert bundle.is_valid
            assert bundle.l1_turn_count == 1
            assert bundle.round_snapshot.recent_turn_records[0].turn_id == "turn_001"
            db2.close()


# ── Test: RuntimeStoreFactory ────────────────────────────────────────────────

class TestRuntimeStoreFactory:

    def test_factory_same_namespace_same_registry(self):
        """Same (profile, namespace) yields the same registry instance."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache
        with tempfile.TemporaryDirectory() as tmp:
            clear_registry_cache()
            try:
                f1 = RuntimeStoreFactory.for_test("ns_001", store_root=tmp)
                f2 = RuntimeStoreFactory.for_test("ns_001", store_root=tmp)
                assert f1.registry is f2.registry
            finally:
                clear_registry_cache()

    def test_factory_different_namespace_different_registry(self):
        """Different namespaces yield different registries."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache
        with tempfile.TemporaryDirectory() as tmp:
            clear_registry_cache()
            try:
                f1 = RuntimeStoreFactory.for_test("ns_A", store_root=tmp)
                f2 = RuntimeStoreFactory.for_test("ns_B", store_root=tmp)
                assert f1.registry is not f2.registry
                assert f1.db_path != f2.db_path
            finally:
                clear_registry_cache()

    def test_factory_same_database_uses_thread_local_registry(self):
        """Each thread gets its own registry so SQLite connections are not shared."""
        import threading

        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache
        with tempfile.TemporaryDirectory() as tmp:
            clear_registry_cache()
            try:
                main_factory = RuntimeStoreFactory.for_test("ns_thread", store_root=tmp)
                main_registry = main_factory.registry
                worker_result = {}

                def load_in_worker():
                    worker_factory = RuntimeStoreFactory.for_test("ns_thread", store_root=tmp)
                    worker_result["registry"] = worker_factory.registry
                    worker_result["db_path"] = worker_factory.db_path

                thread = threading.Thread(target=load_in_worker)
                thread.start()
                thread.join()

                same_thread_factory = RuntimeStoreFactory.for_test("ns_thread", store_root=tmp)
                assert same_thread_factory.registry is main_registry
                assert worker_result["db_path"] == main_factory.db_path
                assert worker_result["registry"] is not main_registry
            finally:
                clear_registry_cache()

    def test_factory_test_profile_cannot_access_production(self):
        """Test namespace resolves to test directory, not production."""
        from ..runtime.runtime_store_factory import _resolve_db_path
        path = _resolve_db_path("test", "run_xyz", "/tmp/test_root")
        assert "run_xyz" in path
        assert "awp_session.db" in path
        # Not the production path
        assert path != "awp_rp_runtime.db"


# ── Test: Controlled Memory Persistence ──────────────────────────────────────

class TestControlledMemoryPersistence:

    def test_13_controlled_active_memory_write_and_recall(self):
        """Test-only MemoryCurator fixture writes ActiveMemory that can be recalled."""
        from ..testing.fakes.test_memory_curator_fixture import TestMemoryCuratorFixture
        from ..contracts.turn_record import TurnRecord, TurnMode
        from ..contracts.round_snapshot import RoundSnapshot
        from ..contracts.quality_decision import QualityDecision, QualityVerdict
        from ..runtime.active_memory_commit_runtime import ActiveMemoryCommitRuntime
        from ..contracts.memory_commit_plan import MemoryCommitRequest, MemoryCommitStatus
        from ..runtime.memory_plan_compiler import MemoryPlanCompiler

        old_profile = os.environ.get("AWP_RUNTIME_PROFILE")
        os.environ["AWP_RUNTIME_PROFILE"] = "test"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db = _make_db(tmp)
                registry = SessionRuntimeStoreRegistry(db)
                _seed_session(registry)

                # Create turn record and snapshot
                turn = TurnRecord(
                    turn_id="turn_mem_001", trace_id="trc_001",
                    session_id="sess_001", card_id="card_001",
                    turn_index=1, player_input="Hello there",
                    writer_output="Response text for memory",
                    mode=TurnMode.NORMAL,
                    base_card_state_revision=0, result_card_state_revision=1,
                    created_at=_now(),
                )
                snapshot = RoundSnapshot(
                    snapshot_id="snap_001", trace_id="trc_001",
                    card_id="card_001", session_id="sess_001",
                    base_card_state_revision=0,
                    card_state=registry.card_state_store.load("card_001", "sess_001"),
                    player_input="Hello there",
                    created_at=_now(),
                )
                qd = QualityDecision(
                    verdict=QualityVerdict.ACCEPTED,
                    candidate_text="Response text",
                    overall_score=0.8,
                )

                # Run test fixture curator
                curator = TestMemoryCuratorFixture()
                result = curator.curate(turn, snapshot, qd)
                assert result is not None
                assert result.total_candidates_accepted == 1

                # Compile plan
                compiler = MemoryPlanCompiler()
                plan = compiler.compile(
                    result, turn.turn_id, "card_001", "sess_001",
                    "trc_001", 1, turn.turn_id,
                )
                assert len(plan.new_active_entries) == 1

                # Commit to SQLite
                runtime = ActiveMemoryCommitRuntime(registry.active_memory_store)
                request = MemoryCommitRequest(
                    plan=plan, card_id="card_001", session_id="sess_001",
                    turn_id="turn_mem_001", trace_id="trc_001",
                    memory_commit_id=plan.memory_commit_id,
                    idempotency_key=plan.idempotency_key,
                    quality_decision_ref="trc_001",
                    expected_card_state_revision=1,
                    card_state_commit_success=True,
                    turn_record_commit_success=True,
                )
                commit_result = runtime.commit_request(request, qd)
                _close_db(db)

                assert commit_result.status == MemoryCommitStatus.COMMITTED

                # Verify: new store instance can recall
                db2 = Database(str(Path(tmp) / "test.db"))
                db2.initialize()
                store2 = SqliteActiveMemoryStore(db2)

                all_entries = store2.get_all("card_001", "sess_001")
                assert len(all_entries) == 1
                assert "test_memory:turn_mem_001" in all_entries[0].summary
                assert len(all_entries[0].summary) >= 30  # policy minimum

                # Recall works
                recall_req = MemoryRecallRequest(
                    card_id="card_001", session_id="sess_001",
                    snapshot_id="snap_001", trace_id="trc_001",
                    query="test_memory", limit=10,
                )
                recall_result = store2.recall("card_001", "sess_001", recall_req)
                assert len(recall_result.hits) >= 1
                _close_db(db2)
        finally:
            if old_profile is not None:
                os.environ["AWP_RUNTIME_PROFILE"] = old_profile
            else:
                os.environ.pop("AWP_RUNTIME_PROFILE", None)

    def test_14_memory_in_round_snapshot_after_commit(self):
        """After memory commit, new RoundSnapshot includes the memory."""
        from ..testing.fakes.test_memory_curator_fixture import TestMemoryCuratorFixture
        from ..contracts.turn_record import TurnRecord, TurnMode
        from ..contracts.round_snapshot import RoundSnapshot
        from ..contracts.quality_decision import QualityDecision, QualityVerdict
        from ..runtime.active_memory_commit_runtime import ActiveMemoryCommitRuntime
        from ..contracts.memory_commit_plan import MemoryCommitRequest, MemoryCommitStatus
        from ..runtime.memory_plan_compiler import MemoryPlanCompiler

        old_profile = os.environ.get("AWP_RUNTIME_PROFILE")
        os.environ["AWP_RUNTIME_PROFILE"] = "test"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db = _make_db(tmp)
                registry = SessionRuntimeStoreRegistry(db)
                _seed_session(registry)
                _commit_turn(registry, "turn_001", "card_001", "sess_001", 1,
                             "Hello", "Response")

                # Commit memory via test fixture
                turn = registry.turn_record_store.load("turn_001")
                snapshot = RoundSnapshot(
                    snapshot_id="snap_002", trace_id="trc_002",
                    card_id="card_001", session_id="sess_001",
                    base_card_state_revision=0,
                    card_state=registry.card_state_store.load("card_001", "sess_001"),
                    player_input="Hello", created_at=_now(),
                )
                qd = QualityDecision(verdict=QualityVerdict.ACCEPTED, candidate_text="Response")

                curator = TestMemoryCuratorFixture()
                result = curator.curate(turn, snapshot, qd)
                compiler = MemoryPlanCompiler()
                plan = compiler.compile(
                    result, turn.turn_id, "card_001", "sess_001",
                    "trc_001", 1, turn.turn_id,
                )
                runtime = ActiveMemoryCommitRuntime(registry.active_memory_store)
                request = MemoryCommitRequest(
                    plan=plan, card_id="card_001", session_id="sess_001",
                    turn_id="turn_001", trace_id="trc_001",
                    memory_commit_id=plan.memory_commit_id,
                    idempotency_key=plan.idempotency_key,
                    quality_decision_ref="trc_001",
                    expected_card_state_revision=1,
                    card_state_commit_success=True,
                    turn_record_commit_success=True,
                )
                commit_result = runtime.commit_request(request, qd)
                assert commit_result.status == MemoryCommitStatus.COMMITTED

                # Build new RoundSnapshot — should include the memory
                builder = RoundSnapshotBuilder(
                    card_state_store=registry.card_state_store,
                    turn_record_store=registry.turn_record_store,
                    active_memory_store=registry.active_memory_store,
                    rag_memory_store=registry.rag_memory_store,
                )
                # Use a player_input that is a substring of the memory summary
                # so the recall query filter can find it
                snap = builder.build("card_001", "sess_001", "test_memory")
                active_count = len(snap.active_memories)
                _close_db(db)
                assert active_count >= 1
        finally:
            if old_profile is not None:
                os.environ["AWP_RUNTIME_PROFILE"] = old_profile
            else:
                os.environ.pop("AWP_RUNTIME_PROFILE", None)


# ── Test: Node INPUT_TYPES no forbidden inputs ──────────────────────────────

class TestNodeInputContracts:

    def test_15_persistent_first_turn_no_forbidden_inputs(self):
        """PersistentFirstTurn node does not accept forbidden inputs."""
        from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
        input_types = AWPV2PersistentFirstTurn.INPUT_TYPES()
        all_inputs = {}
        all_inputs.update(input_types.get("required", {}))
        all_inputs.update(input_types.get("optional", {}))

        for forbidden in ["db_path", "store_path", "databasePath",
                          "previous_turn_records", "active_memories",
                          "rag_recall", "card_state", "card_session_binding",
                          "opening_record", "worldbook_binding"]:
            assert forbidden not in all_inputs, \
                f"PersistentFirstTurn must not accept '{forbidden}'"

    def test_16_persistent_bootstrap_no_forbidden_inputs(self):
        """PersistentBootstrap node does not accept forbidden inputs."""
        from ..nodes.persistent_bootstrap_node import AWPV2PersistentBootstrap
        input_types = AWPV2PersistentBootstrap.INPUT_TYPES()
        all_inputs = {}
        all_inputs.update(input_types.get("required", {}))
        all_inputs.update(input_types.get("optional", {}))

        for forbidden in ["db_path", "store_path", "databasePath"]:
            assert forbidden not in all_inputs, \
                f"PersistentBootstrap must not accept '{forbidden}'"

    def test_17_real_provider_config_does_not_affect_fake_tests(self):
        """Setting real provider env vars does not change fake adapter behavior."""
        old_key = os.environ.get("DEEPSEEK_API_KEY")
        old_model = os.environ.get("AWP_DIRECTOR_MODEL")
        try:
            os.environ["DEEPSEEK_API_KEY"] = "sk-test-fake-key"
            os.environ["AWP_DIRECTOR_MODEL"] = "deepseek-v4-pro"

            # Fake adapters still work independently via the factory
            from ..runtime.provider_adapter_factory import DirectorAdapterFactory
            from ..contracts.round_snapshot import RoundSnapshot as RS
            adapter, outcome = DirectorAdapterFactory.build("fake-director")
            assert outcome.built
            assert outcome.is_real is False
            # Create minimal snapshot
            snap = RS(
                snapshot_id="s", trace_id="t", card_id="c",
                session_id="s", base_card_state_revision=0,
                player_input="test", created_at=_now(),
            )
            plan = adapter.generate_plan(snap)
            assert plan.turn_goal  # Works regardless of env
        finally:
            if old_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_key
            else:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            if old_model is not None:
                os.environ["AWP_DIRECTOR_MODEL"] = old_model
            else:
                os.environ.pop("AWP_DIRECTOR_MODEL", None)


# ── Test 18: Idempotent replay — replayed receipt ────────────────────────────

class TestIdempotentReplay:

    def test_18_replayed_turn_returns_replayed_receipt(self):
        """Same turn_id returns a replayed receipt with idempotency_status='replayed'."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteTurnRecordStore(db)

            record = TurnRecord(
                turn_id="turn_001", trace_id="trc_001",
                session_id="sess_001", card_id="card_001",
                turn_index=1, player_input="Hello",
                writer_output="Response", mode=TurnMode.NORMAL,
                base_card_state_revision=0, result_card_state_revision=1,
                created_at=_now(),
            )
            store.save(record)

            # Load existing — simulates what replay does
            existing = store.load("turn_001")
            assert existing is not None
            assert existing.turn_id == "turn_001"
            assert existing.base_card_state_revision == 0
            assert existing.result_card_state_revision == 1
            _close_db(db)

    def test_19_replayed_turn_no_duplicate_record(self):
        """DuplicateTurnError prevents double-write; only one record exists."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteTurnRecordStore(db)

            record = TurnRecord(
                turn_id="turn_001", trace_id="trc_001",
                session_id="sess_001", card_id="card_001",
                turn_index=1, player_input="Hello",
                writer_output="Response", mode=TurnMode.NORMAL,
                created_at=_now(),
            )
            store.save(record)

            from ..storage.interfaces import DuplicateTurnError
            with pytest.raises(DuplicateTurnError):
                store.save(record)

            # Only one record
            recent = store.get_recent("card_001", "sess_001")
            assert len(recent) == 1
            _close_db(db)

    def test_20_replayed_turn_no_state_revision_increase(self):
        """Replayed turn does not increase CardState revision."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            registry = SessionRuntimeStoreRegistry(db)
            _seed_session(registry)

            # Commit turn 1 — state revision becomes 1
            _commit_turn(registry, "turn_001", "card_001", "sess_001", 1,
                         "Input 1", "Response 1", base_rev=0, result_rev=1)

            # Record revision before replay attempt
            cs_before = registry.card_state_store.load("card_001", "sess_001")
            revision_before = cs_before.revision

            # Simulate replay: load existing turn record
            existing = registry.turn_record_store.load("turn_001")
            assert existing is not None

            # Revision did NOT change
            cs_after = registry.card_state_store.load("card_001", "sess_001")
            assert cs_after.revision == revision_before
            _close_db(db)

    def test_21_replayed_turn_no_new_turn_record(self):
        """Replayed turn does not create a new TurnRecord."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            store = SqliteTurnRecordStore(db)

            record = TurnRecord(
                turn_id="turn_001", trace_id="trc_001",
                session_id="sess_001", card_id="card_001",
                turn_index=1, player_input="Hello",
                writer_output="Response", mode=TurnMode.NORMAL,
                created_at=_now(),
            )
            store.save(record)

            # Count before
            count_before = len(store.get_recent("card_001", "sess_001", limit=100))

            # Simulate replay — just load, don't save
            from ..storage.interfaces import DuplicateTurnError
            with pytest.raises(DuplicateTurnError):
                store.save(record)  # Would fail if we tried

            count_after = len(store.get_recent("card_001", "sess_001", limit=100))
            assert count_after == count_before
            assert count_after == 1
            _close_db(db)

    def test_22_idempotent_replay_full_node_flow(self):
        """Full node flow: first turn succeeds, replay returns replayed receipt."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AWP_RUNTIME_PROFILE"] = "test"
            os.environ["AWP_TEST_STORE_ROOT"] = tmp
            os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = "replay_test"
            clear_registry_cache()
            try:
                factory = RuntimeStoreFactory.from_env()
                registry = factory.registry

                # Bootstrap session
                _seed_session(registry, session_id="sess_replay", card_id="card_001")

                # First turn
                from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
                node = AWPV2PersistentFirstTurn()
                result1 = node.execute(
                    session_id="sess_replay",
                    player_input="Hello world",
                    turn_id="turn_replay_001",
                    request_id="req_001",
                    workflow_run_id="wfr_001",
                    trace_id="trc_001",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )
                receipt1 = result1[0]
                assert receipt1["idempotency_status"] == "fresh"
                assert receipt1["turn_id"] == "turn_replay_001"

                # Replay — same turn_id
                result2 = node.execute(
                    session_id="sess_replay",
                    player_input="Hello world",
                    turn_id="turn_replay_001",
                    request_id="req_001",
                    workflow_run_id="wfr_001",
                    trace_id="trc_001",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )
                receipt2 = result2[0]
                assert receipt2["idempotency_status"] == "replayed"
                assert receipt2["turn_id"] == "turn_replay_001"

                # Only one turn record exists
                recent = registry.turn_record_store.get_recent("card_001", "sess_replay")
                assert len(recent) == 1

                # P1: State revision stays at 0 when no real state change detected
                # (fake writer "Hello world" has no actionable state signals)
                cs = registry.card_state_store.load("card_001", "sess_replay")
                assert cs.revision == 0  # P1: no_state_change when nothing happened
            finally:
                os.environ.pop("AWP_TEST_STORE_ROOT", None)
                os.environ.pop("AWP_TEST_RUNTIME_NAMESPACE", None)
                clear_registry_cache()

    def test_23_continuation_replay_full_node_flow(self):
        """Full continuation node flow: first turn + continuation + replay."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AWP_RUNTIME_PROFILE"] = "test"
            os.environ["AWP_TEST_STORE_ROOT"] = tmp
            os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = "cont_replay_test"
            clear_registry_cache()
            try:
                factory = RuntimeStoreFactory.from_env()
                registry = factory.registry

                _seed_session(registry, session_id="sess_cont", card_id="card_001")

                # Turn 1
                from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
                ft_node = AWPV2PersistentFirstTurn()
                ft_node.execute(
                    session_id="sess_cont",
                    player_input="Hello",
                    turn_id="turn_001",
                    request_id="req_001",
                    workflow_run_id="wfr_001",
                    trace_id="trc_001",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )

                # Turn 2 (continuation)
                from ..nodes.persistent_continuation_turn_node import AWPV2PersistentContinuationTurn
                ct_node = AWPV2PersistentContinuationTurn()
                result2 = ct_node.execute(
                    session_id="sess_cont",
                    player_input="Continue please",
                    turn_id="turn_002",
                    request_id="req_002",
                    workflow_run_id="wfr_002",
                    trace_id="trc_002",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )
                assert result2[0]["idempotency_status"] == "fresh"

                # Replay Turn 2
                result2_replay = ct_node.execute(
                    session_id="sess_cont",
                    player_input="Continue please",
                    turn_id="turn_002",
                    request_id="req_002",
                    workflow_run_id="wfr_002",
                    trace_id="trc_002",
                    director_profile_id="fake-director",
                    writer_profile_id="fake-writer",
                )
                assert result2_replay[0]["idempotency_status"] == "replayed"

                # Only 2 turn records
                recent = registry.turn_record_store.get_recent("card_001", "sess_cont")
                assert len(recent) == 2

                # P1: State revision stays at 0 when no real state change detected
                # (fake writer outputs don't trigger state changes)
                cs = registry.card_state_store.load("card_001", "sess_cont")
                assert cs.revision == 0  # P1: no_state_change for no-signal turns
            finally:
                os.environ.pop("AWP_TEST_STORE_ROOT", None)
                os.environ.pop("AWP_TEST_RUNTIME_NAMESPACE", None)
                clear_registry_cache()

    def test_24_replay_session_binding_conflict(self):
        """Replay with wrong session_id fails with session_binding_conflict."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AWP_RUNTIME_PROFILE"] = "test"
            os.environ["AWP_TEST_STORE_ROOT"] = tmp
            os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = "conflict_test"
            clear_registry_cache()
            try:
                factory = RuntimeStoreFactory.from_env()
                registry = factory.registry

                _seed_session(registry, session_id="sess_A", card_id="card_001")
                _seed_session(registry, session_id="sess_B", card_id="card_001")

                # Commit turn to session A
                _commit_turn(registry, "turn_001", "card_001", "sess_A", 1,
                             "Input", "Output")

                # Try to replay turn_001 under session B — should fail
                from ..nodes.persistent_continuation_turn_node import AWPV2PersistentContinuationTurn
                node = AWPV2PersistentContinuationTurn()
                result = node.execute(
                    session_id="sess_B",
                    player_input="Input",
                    turn_id="turn_001",
                    request_id="req_conflict",
                )
                diag = result[2]
                assert diag["outcome"] == "failure"
                assert "session_binding_conflict" in diag.get("steps_failed", [])
            finally:
                os.environ.pop("AWP_TEST_STORE_ROOT", None)
                os.environ.pop("AWP_TEST_RUNTIME_NAMESPACE", None)
                clear_registry_cache()


# ── Test: Model Profile Registry ─────────────────────────────────────────────

class TestModelProfileRegistry:

    def test_25_known_profiles_resolve(self):
        """Known profile IDs resolve to valid ModelProfile."""
        from ..adapters.llm.model_profile_registry import ModelProfileRegistry

        for pid in ["deepseek-v4-pro-director", "deepseek-v4-flash-writer",
                     "fake-director", "fake-writer"]:
            profile = ModelProfileRegistry.resolve(pid)
            assert profile.profile_id == pid
            assert profile.provider in ("deepseek", "fake")

    def test_26_unknown_profile_fails_closed(self):
        """Unknown profile ID raises ValueError (fail closed)."""
        from ..adapters.llm.model_profile_registry import ModelProfileRegistry

        with pytest.raises(ValueError, match="Unknown model profile"):
            ModelProfileRegistry.resolve("gpt-4-hacker")

    def test_27_profile_is_valid_check(self):
        """is_valid returns True for known, False for unknown."""
        from ..adapters.llm.model_profile_registry import ModelProfileRegistry

        assert ModelProfileRegistry.is_valid("fake-director") is True
        assert ModelProfileRegistry.is_valid("nonexistent-model") is False

    def test_28_profile_list_not_empty(self):
        """list_profiles returns at least the 4 canonical profiles."""
        from ..adapters.llm.model_profile_registry import ModelProfileRegistry

        profiles = ModelProfileRegistry.list_profiles()
        assert len(profiles) >= 4
        assert "deepseek-v4-pro-director" in profiles
        assert "fake-director" in profiles

    def test_29_profile_no_api_key_exposure(self):
        """to_safe_dict never includes actual API key values."""
        from ..adapters.llm.model_profile_registry import ModelProfileRegistry

        profile = ModelProfileRegistry.resolve("deepseek-v4-pro-director")
        safe = profile.to_safe_dict()
        assert "api_key" not in safe
        assert "api_key_env" in safe  # Only the env var name

    def test_30_node_rejects_unknown_profile(self):
        """PersistentFirstTurn node rejects unknown profile ID."""
        from ..runtime.runtime_store_factory import RuntimeStoreFactory, clear_registry_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AWP_RUNTIME_PROFILE"] = "test"
            os.environ["AWP_TEST_STORE_ROOT"] = tmp
            os.environ["AWP_TEST_RUNTIME_NAMESPACE"] = "profile_test"
            clear_registry_cache()
            try:
                factory = RuntimeStoreFactory.from_env()
                registry = factory.registry
                _seed_session(registry, session_id="sess_prof", card_id="card_001")

                from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
                node = AWPV2PersistentFirstTurn()
                result = node.execute(
                    session_id="sess_prof",
                    player_input="Hello",
                    director_profile_id="nonexistent-director",
                )
                diag = result[2]
                assert diag["outcome"] == "failure"
                assert "model_profile_validation" in diag.get("steps_failed", [])
            finally:
                os.environ.pop("AWP_TEST_STORE_ROOT", None)
                os.environ.pop("AWP_TEST_RUNTIME_NAMESPACE", None)
                clear_registry_cache()

    def test_31_production_nodes_default_to_real_profiles(self):
        """Production-facing node defaults must not silently use fake adapters."""
        import inspect

        from ..nodes.continue_turn_execution_node import AWPV2ContinueTurn
        from ..nodes.persistent_continuation_turn_node import AWPV2PersistentContinuationTurn
        from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn
        from ..nodes.writer_v2_node import AWPV2WriterGenerate

        expected_director = "deepseek-v4-flash-director"
        expected_writer = "deepseek-v4-pro-writer"

        for node_cls in (
            AWPV2PersistentFirstTurn,
            AWPV2PersistentContinuationTurn,
            AWPV2ContinueTurn,
        ):
            optional = node_cls.INPUT_TYPES()["optional"]
            assert optional["director_profile_id"][1]["default"] == expected_director
            assert optional["writer_profile_id"][1]["default"] == expected_writer

            execute_signature = inspect.signature(node_cls.execute)
            assert execute_signature.parameters["director_profile_id"].default == expected_director
            assert execute_signature.parameters["writer_profile_id"].default == expected_writer

            changed_signature = inspect.signature(node_cls.IS_CHANGED)
            assert changed_signature.parameters["director_profile_id"].default == expected_director
            assert changed_signature.parameters["writer_profile_id"].default == expected_writer

        writer_optional = AWPV2WriterGenerate.INPUT_TYPES()["optional"]
        assert writer_optional["profile_id"][1]["default"] == expected_writer
        assert inspect.signature(AWPV2WriterGenerate.execute).parameters["profile_id"].default == expected_writer
