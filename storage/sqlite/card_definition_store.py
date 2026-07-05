"""SQLite CardDefinitionStore."""

from __future__ import annotations

import json

from ..card_import_interfaces import CardDefinitionStore
from ...contracts.card_definition import CardDefinition
from .database import Database


class SqliteCardDefinitionStore(CardDefinitionStore):
    """SQLite-backed card definition store."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, definition: CardDefinition) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT OR REPLACE INTO card_definitions "
            "(card_id, card_version, source_id, source_hash, name, display_name, "
            "status, definition_json, import_report_ref, trace_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (
                definition.logical_card_id,
                definition.card_version,
                definition.source_id,
                definition.source_hash,
                definition.name,
                definition.display_name,
                definition.status,
                json.dumps(definition.to_dict(), ensure_ascii=False),
                definition.import_report_ref,
                definition.trace_id,
            ),
        )
        conn.commit()

    def load(self, logical_card_id: str, card_version: int) -> CardDefinition | None:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT definition_json FROM card_definitions "
            "WHERE card_id=? AND card_version=?",
            (logical_card_id, card_version),
        ).fetchone()
        if not row:
            return None
        return CardDefinition.from_dict(json.loads(row["definition_json"]))

    def get_latest(self, logical_card_id: str) -> CardDefinition | None:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT definition_json FROM card_definitions "
            "WHERE card_id=? ORDER BY card_version DESC LIMIT 1",
            (logical_card_id,),
        ).fetchone()
        if not row:
            return None
        return CardDefinition.from_dict(json.loads(row["definition_json"]))

    def get_by_source_hash(self, source_hash: str) -> CardDefinition | None:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT definition_json FROM card_definitions "
            "WHERE source_hash=? ORDER BY card_version DESC LIMIT 1",
            (source_hash,),
        ).fetchone()
        if not row:
            return None
        return CardDefinition.from_dict(json.loads(row["definition_json"]))

    def list_all(self, status: str = "") -> list[CardDefinition]:
        conn = self.db.connect()
        if status:
            rows = conn.execute(
                "SELECT definition_json FROM card_definitions "
                "WHERE status=? ORDER BY card_id, card_version",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT definition_json FROM card_definitions "
                "ORDER BY card_id, card_version",
            ).fetchall()
        return [CardDefinition.from_dict(json.loads(r["definition_json"])) for r in rows]

    def list_by_card(self, logical_card_id: str) -> list[CardDefinition]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT definition_json FROM card_definitions "
            "WHERE card_id=? ORDER BY card_version",
            (logical_card_id,),
        ).fetchall()
        return [CardDefinition.from_dict(json.loads(r["definition_json"])) for r in rows]

    def delete(self, logical_card_id: str) -> None:
        conn = self.db.connect()
        conn.execute(
            "DELETE FROM card_definitions WHERE card_id=?",
            (logical_card_id,),
        )
        conn.commit()

    def update_status(self, logical_card_id: str, card_version: int, status: str) -> None:
        conn = self.db.connect()
        conn.execute(
            "UPDATE card_definitions SET status=?, updated_at=datetime('now') "
            "WHERE card_id=? AND card_version=?",
            (status, logical_card_id, card_version),
        )
        conn.commit()

    def get_next_version(self, logical_card_id: str) -> int:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT MAX(card_version) as max_ver FROM card_definitions "
            "WHERE card_id=?",
            (logical_card_id,),
        ).fetchone()
        return (row["max_ver"] or 0) + 1
