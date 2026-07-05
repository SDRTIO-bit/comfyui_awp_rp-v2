"""SQLite database with explicit migration mechanism.

Uses WAL mode. All writes go through transactions.
Migration versions are tracked in schema_migrations table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# --- Migration definitions ---
# Each migration is a tuple of (version, description, sql).
# Migrations are applied in order. Already-applied versions are skipped.

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "Initial schema: card_states, turn_records, active_memories, rag_memories, execution_traces",
        """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS card_states (
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (card_id, session_id)
);

CREATE TABLE IF NOT EXISTS card_state_patch_receipts (
    patch_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    from_revision INTEGER NOT NULL,
    to_revision INTEGER NOT NULL,
    operations_json TEXT NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (patch_id),
    FOREIGN KEY (card_id, session_id) REFERENCES card_states(card_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_patch_receipts_session
    ON card_state_patch_receipts(card_id, session_id, applied_at);

CREATE TABLE IF NOT EXISTS turn_records (
    turn_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL DEFAULT '',
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL DEFAULT 0,
    parent_turn_id TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'normal',
    record_json TEXT NOT NULL,
    base_card_state_revision INTEGER NOT NULL DEFAULT 0,
    result_card_state_revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    accepted_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_turn_records_session_index
    ON turn_records(card_id, session_id, turn_index);
CREATE INDEX IF NOT EXISTS idx_turn_records_session
    ON turn_records(card_id, session_id, accepted_at DESC);

CREATE TABLE IF NOT EXISTS round_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL DEFAULT '',
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    base_card_state_revision INTEGER NOT NULL DEFAULT 0,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_round_snapshots_session
    ON round_snapshots(card_id, session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS execution_traces (
    trace_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL DEFAULT '',
    card_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    trace_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_execution_traces_turn
    ON execution_traces(turn_id);

CREATE TABLE IF NOT EXISTS active_memory_records (
    memory_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    memory_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (memory_id, card_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_active_memories_session
    ON active_memory_records(card_id, session_id, status);

CREATE TABLE IF NOT EXISTS rag_memory_records (
    memory_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    memory_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rag_memories_session
    ON rag_memory_records(card_id, session_id);
""",
    ),
    (
        2,
        "M1 memory foundation: active/rag columns, FTS5, receipts, recall logs, retention",
        """
-- Active memory: promote retrieval columns + lifecycle metadata.
ALTER TABLE active_memory_records ADD COLUMN kind TEXT NOT NULL DEFAULT '';
ALTER TABLE active_memory_records ADD COLUMN summary TEXT NOT NULL DEFAULT '';
ALTER TABLE active_memory_records ADD COLUMN importance REAL NOT NULL DEFAULT 0.5;
ALTER TABLE active_memory_records ADD COLUMN confidence REAL NOT NULL DEFAULT 0.5;
ALTER TABLE active_memory_records ADD COLUMN source_card_state_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE active_memory_records ADD COLUMN source_turn_ids_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE active_memory_records ADD COLUMN entity_refs_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE active_memory_records ADD COLUMN created_at TEXT NOT NULL DEFAULT '';
ALTER TABLE active_memory_records ADD COLUMN last_recalled_at TEXT NOT NULL DEFAULT '';
ALTER TABLE active_memory_records ADD COLUMN recall_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE active_memory_records ADD COLUMN resolved_at TEXT NOT NULL DEFAULT '';
ALTER TABLE active_memory_records ADD COLUMN expires_at TEXT NOT NULL DEFAULT '';
ALTER TABLE active_memory_records ADD COLUMN eviction_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE active_memory_records ADD COLUMN retention_reason TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_active_memories_importance
    ON active_memory_records(card_id, session_id, importance);
CREATE INDEX IF NOT EXISTS idx_active_memories_kind
    ON active_memory_records(card_id, session_id, kind);

-- RAG memory: scope, status, retrieval columns.
ALTER TABLE rag_memory_records ADD COLUMN scope TEXT NOT NULL DEFAULT 'session';
ALTER TABLE rag_memory_records ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE rag_memory_records ADD COLUMN summary TEXT NOT NULL DEFAULT '';
ALTER TABLE rag_memory_records ADD COLUMN importance REAL NOT NULL DEFAULT 0.5;
ALTER TABLE rag_memory_records ADD COLUMN confidence REAL NOT NULL DEFAULT 0.5;
ALTER TABLE rag_memory_records ADD COLUMN source_card_state_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rag_memory_records ADD COLUMN source_turn_ids_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE rag_memory_records ADD COLUMN entity_refs_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE rag_memory_records ADD COLUMN aliases_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE rag_memory_records ADD COLUMN tags_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE rag_memory_records ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';
ALTER TABLE rag_memory_records ADD COLUMN last_recalled_at TEXT NOT NULL DEFAULT '';
ALTER TABLE rag_memory_records ADD COLUMN recall_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rag_memory_records ADD COLUMN provenance TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_rag_memories_scope
    ON rag_memory_records(card_id, session_id, scope);
CREATE INDEX IF NOT EXISTS idx_rag_memories_status
    ON rag_memory_records(card_id, session_id, status);

-- FTS5 full-text index over RAG content + summary + aliases.
CREATE VIRTUAL TABLE IF NOT EXISTS rag_memory_fts USING fts5(
    memory_id UNINDEXED,
    card_id UNINDEXED,
    session_id UNINDEXED,
    content,
    summary,
    aliases,
    tokenize = 'unicode61'
);

-- Memory commit receipts (idempotency).
CREATE TABLE IF NOT EXISTS active_memory_commit_receipts (
    memory_commit_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    turn_id TEXT NOT NULL DEFAULT '',
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    expected_card_state_revision INTEGER NOT NULL DEFAULT 0,
    quality_decision_ref TEXT NOT NULL DEFAULT '',
    committed_active_ids_json TEXT NOT NULL DEFAULT '[]',
    evicted_active_ids_json TEXT NOT NULL DEFAULT '[]',
    committed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (card_id, session_id, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_receipt_commit
    ON active_memory_commit_receipts(card_id, session_id, memory_commit_id);

CREATE TABLE IF NOT EXISTS rag_memory_commit_receipts (
    memory_commit_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    turn_id TEXT NOT NULL DEFAULT '',
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    expected_card_state_revision INTEGER NOT NULL DEFAULT 0,
    quality_decision_ref TEXT NOT NULL DEFAULT '',
    committed_rag_ids_json TEXT NOT NULL DEFAULT '[]',
    committed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (card_id, session_id, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_receipt_commit
    ON rag_memory_commit_receipts(card_id, session_id, memory_commit_id);

-- Recall diagnostics + retention decisions audit.
CREATE TABLE IF NOT EXISTS memory_recall_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL DEFAULT '',
    layer TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    hits_json TEXT NOT NULL DEFAULT '[]',
    excluded_json TEXT NOT NULL DEFAULT '[]',
    ordered_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_recall_logs_session
    ON memory_recall_logs(card_id, session_id, created_at);

CREATE TABLE IF NOT EXISTS memory_retention_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL DEFAULT '',
    memory_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0.0,
    decided_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_retention_session
    ON memory_retention_decisions(card_id, session_id, turn_id);
""",
    ),
    (
        3,
        "Card import pipeline: definitions, source snapshots, import reports, quarantine",
        """
CREATE TABLE IF NOT EXISTS card_definitions (
    card_id TEXT NOT NULL,
    card_version INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'staged',
    definition_json TEXT NOT NULL,
    import_report_ref TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (card_id, card_version)
);
CREATE INDEX IF NOT EXISTS idx_card_definitions_source_hash ON card_definitions(source_hash);
CREATE INDEX IF NOT EXISTS idx_card_definitions_status ON card_definitions(status);

CREATE TABLE IF NOT EXISTS card_source_snapshots (
    source_id TEXT PRIMARY KEY,
    source_hash TEXT NOT NULL,
    source_filename TEXT NOT NULL DEFAULT '',
    source_format TEXT NOT NULL DEFAULT '',
    source_size_bytes INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT '',
    spec TEXT NOT NULL DEFAULT '',
    raw_payload_ref TEXT NOT NULL DEFAULT '',
    snapshot_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_card_source_hash ON card_source_snapshots(source_hash);

CREATE TABLE IF NOT EXISTS card_import_reports (
    report_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    card_id TEXT NOT NULL DEFAULT '',
    card_version INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_card_import_reports_card ON card_import_reports(card_id, card_version);

CREATE TABLE IF NOT EXISTS card_quarantine_records (
    record_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL DEFAULT '',
    card_version INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'medium',
    evidence_preview TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT 'quarantined',
    reason TEXT NOT NULL DEFAULT '',
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_quarantine_card ON card_quarantine_records(card_id, card_version);
""",
    ),
    (
        4,
        "Session bootstrap persistence: bindings, openings, worldbook bindings, bootstrap receipts",
        """
CREATE TABLE IF NOT EXISTS card_session_bindings (
    session_id TEXT PRIMARY KEY,
    logical_card_id TEXT NOT NULL,
    card_version INTEGER NOT NULL DEFAULT 0,
    source_hash TEXT NOT NULL DEFAULT '',
    binding_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_bindings_card
    ON card_session_bindings(logical_card_id, status);

CREATE TABLE IF NOT EXISTS opening_records (
    opening_record_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    logical_card_id TEXT NOT NULL DEFAULT '',
    greeting_id TEXT NOT NULL DEFAULT '',
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_opening_records_session
    ON opening_records(session_id);

CREATE TABLE IF NOT EXISTS worldbook_bindings (
    worldbook_binding_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    logical_card_id TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL DEFAULT '',
    binding_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_worldbook_bindings_session
    ON worldbook_bindings(session_id);

CREATE TABLE IF NOT EXISTS bootstrap_receipts (
    receipt_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL,
    logical_card_id TEXT NOT NULL DEFAULT '',
    receipt_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bootstrap_receipts_request
    ON bootstrap_receipts(request_id);
CREATE INDEX IF NOT EXISTS idx_bootstrap_receipts_session
    ON bootstrap_receipts(session_id);
""",
    ),
    (
        5,
        "Novel mode tables: projects, volumes, chapter plans, drafts, ledger, characters, batches, references",
        """
CREATE TABLE IF NOT EXISTS novel_projects (
    project_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planning',
    project_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS novel_volumes (
    volume_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    volume_index INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    volume_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES novel_projects(project_id)
);
CREATE INDEX IF NOT EXISTS idx_novel_volumes_project ON novel_volumes(project_id);

CREATE TABLE IF NOT EXISTS novel_chapter_plans (
    chapter_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_index INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES novel_projects(project_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_novel_chapter_plans_index
    ON novel_chapter_plans(project_id, chapter_index);

CREATE TABLE IF NOT EXISTS novel_chapter_drafts (
    draft_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    draft_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (chapter_id) REFERENCES novel_chapter_plans(chapter_id)
);
CREATE INDEX IF NOT EXISTS idx_novel_drafts_chapter ON novel_chapter_drafts(chapter_id, revision DESC);

CREATE TABLE IF NOT EXISTS novel_ledger_items (
    item_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT '',
    entity TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    source_chapter INTEGER NOT NULL DEFAULT 0,
    item_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES novel_projects(project_id)
);
CREATE INDEX IF NOT EXISTS idx_novel_ledger_project ON novel_ledger_items(project_id, section);
CREATE INDEX IF NOT EXISTS idx_novel_ledger_entity ON novel_ledger_items(project_id, entity);

CREATE TABLE IF NOT EXISTS novel_characters (
    character_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'supporting',
    character_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES novel_projects(project_id)
);
CREATE INDEX IF NOT EXISTS idx_novel_characters_project ON novel_characters(project_id);

CREATE TABLE IF NOT EXISTS novel_batch_progress (
    batch_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_start INTEGER NOT NULL DEFAULT 0,
    chapter_end INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    progress_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES novel_projects(project_id)
);
CREATE INDEX IF NOT EXISTS idx_novel_batch_project ON novel_batch_progress(project_id);

CREATE TABLE IF NOT EXISTS novel_reference_books (
    book_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'benchmark',
    book_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES novel_projects(project_id)
);
CREATE INDEX IF NOT EXISTS idx_novel_references_project ON novel_reference_books(project_id);
""",
    ),
]


class Database:
    """SQLite database connection manager with migration support."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def get_applied_versions(self) -> set[int]:
        """Get set of already-applied migration versions."""
        conn = self.connect()
        # Check if schema_migrations table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not row:
            return set()
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {r["version"] for r in rows}

    def apply_migrations(self) -> list[int]:
        """Apply all pending migrations. Returns list of newly applied versions.

        Idempotent: already-applied versions are skipped.
        Each migration runs in its own transaction.
        """
        applied = self.get_applied_versions()
        newly_applied: list[int] = []

        for version, description, sql in MIGRATIONS:
            if version in applied:
                continue

            conn = self.connect()
            try:
                conn.executescript(sql)
                # Record migration (may fail if schema_migrations was just created,
                # but that's fine since the migration SQL creates it)
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)",
                        (version, description),
                    )
                except sqlite3.OperationalError:
                    pass  # Table may not exist yet in edge case
                conn.commit()
                newly_applied.append(version)
            except Exception:
                conn.rollback()
                raise

        return newly_applied

    def initialize(self) -> None:
        """Initialize database: apply all migrations."""
        self.apply_migrations()

    def get_schema_version(self) -> int:
        """Get the latest applied migration version."""
        applied = self.get_applied_versions()
        return max(applied) if applied else 0
