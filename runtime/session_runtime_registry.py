"""SessionRuntimeStoreRegistry — holds all persistent stores for a session.

A single registry instance per Database, shared across all sessions.
Stores are resolved by (card_id, session_id) at the store interface level.
"""

from __future__ import annotations

from ..storage.sqlite.database import Database
from ..storage.sqlite.card_state_store import SqliteCardStateStore
from ..storage.sqlite.turn_record_store import SqliteTurnRecordStore
from ..storage.sqlite.round_snapshot_store import SqliteRoundSnapshotStore
from ..storage.sqlite.active_memory_store import SqliteActiveMemoryStore
from ..storage.sqlite.rag_memory_store import SqliteRagMemoryStore
from ..storage.sqlite.trace_store import SqliteTraceStore
from ..storage.sqlite.card_definition_store import SqliteCardDefinitionStore
from ..storage.sqlite.session_stores import (
    SqliteCardSessionBindingStore,
    SqliteOpeningRecordStore,
    SqliteWorldbookBindingStore,
    SqliteBootstrapReceiptStore,
)
from ..storage.sqlite.novel_stores import (
    SqliteNovelProjectStore,
    SqliteNovelVolumeStore,
    SqliteNovelChapterPlanStore,
    SqliteNovelChapterDraftStore,
    SqliteNovelLedgerStore,
    SqliteNovelCharacterStore,
    SqliteNovelBatchProgressStore,
    SqliteNovelReferenceBookStore,
)


class SessionRuntimeStoreRegistry:
    """Holds all persistent SQLite stores for a runtime session.

    Constructed once per Database instance. All stores share the same
    underlying SQLite connection. Thread-safe via SQLite's WAL mode.
    """

    def __init__(self, db: Database):
        self._db = db
        # L0: session bootstrap stores
        self.card_session_binding_store = SqliteCardSessionBindingStore(db)
        self.opening_record_store = SqliteOpeningRecordStore(db)
        self.worldbook_binding_store = SqliteWorldbookBindingStore(db)
        self.bootstrap_receipt_store = SqliteBootstrapReceiptStore(db)
        # L0+L1: core state stores
        self.card_state_store = SqliteCardStateStore(db)
        self.turn_record_store = SqliteTurnRecordStore(db)
        # Snapshot + trace
        self.round_snapshot_store = SqliteRoundSnapshotStore(db)
        self.trace_store = SqliteTraceStore(db)
        # L2+L3: memory stores
        self.active_memory_store = SqliteActiveMemoryStore(db)
        self.rag_memory_store = SqliteRagMemoryStore(db)
        # Card catalog
        self.card_definition_store = SqliteCardDefinitionStore(db)
        # Novel mode stores
        self.novel_project_store = SqliteNovelProjectStore(db)
        self.novel_volume_store = SqliteNovelVolumeStore(db)
        self.novel_chapter_plan_store = SqliteNovelChapterPlanStore(db)
        self.novel_chapter_draft_store = SqliteNovelChapterDraftStore(db)
        self.novel_ledger_store = SqliteNovelLedgerStore(db)
        self.novel_character_store = SqliteNovelCharacterStore(db)
        self.novel_batch_progress_store = SqliteNovelBatchProgressStore(db)
        self.novel_reference_book_store = SqliteNovelReferenceBookStore(db)

    @property
    def db(self) -> Database:
        return self._db
