"""SQLite TurnRecordStore."""

from __future__ import annotations

import json

from ..interfaces import TurnRecordStore, DuplicateTurnError
from ...contracts.turn_record import TurnRecord
from .database import Database


class SqliteTurnRecordStore(TurnRecordStore):

    def __init__(self, db: Database):
        self.db = db

    def save(self, record: TurnRecord) -> None:
        conn = self.db.connect()
        existing = conn.execute(
            "SELECT turn_id FROM turn_records WHERE turn_id=?", (record.turn_id,)
        ).fetchone()
        if existing:
            raise DuplicateTurnError(record.turn_id)

        conn.execute(
            "INSERT INTO turn_records "
            "(turn_id, trace_id, card_id, session_id, turn_index, parent_turn_id, mode, "
            "record_json, base_card_state_revision, result_card_state_revision, created_at, accepted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record.turn_id, record.trace_id, record.card_id, record.session_id,
             record.turn_index, record.parent_turn_id, record.mode.value,
             json.dumps(record.to_dict()),
             record.base_card_state_revision, record.result_card_state_revision,
             record.created_at, record.accepted_at),
        )
        conn.commit()

    def load(self, turn_id: str) -> TurnRecord | None:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT record_json FROM turn_records WHERE turn_id=?", (turn_id,)
        ).fetchone()
        return TurnRecord.from_dict(json.loads(row["record_json"])) if row else None

    def get_recent(self, card_id: str, session_id: str, limit: int = 5) -> list[TurnRecord]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT record_json FROM turn_records "
            "WHERE card_id=? AND session_id=? ORDER BY turn_index DESC LIMIT ?",
            (card_id, session_id, limit),
        ).fetchall()
        return [TurnRecord.from_dict(json.loads(r["record_json"])) for r in rows]

    def get_last_accepted(self, card_id: str, session_id: str) -> TurnRecord | None:
        records = self.get_recent(card_id, session_id, limit=1)
        return records[0] if records else None

    def get_next_turn_index(self, card_id: str, session_id: str) -> int:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT MAX(turn_index) as max_idx FROM turn_records "
            "WHERE card_id=? AND session_id=?",
            (card_id, session_id),
        ).fetchone()
        return (row["max_idx"] or 0) + 1

    def list_by_session(self, session_id: str) -> list[TurnRecord]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT record_json FROM turn_records "
            "WHERE session_id=? ORDER BY turn_index ASC",
            (session_id,),
        ).fetchall()
        return [TurnRecord.from_dict(json.loads(r["record_json"])) for r in rows]

    def delete_by_session(self, session_id: str) -> None:
        conn = self.db.connect()
        conn.execute(
            "DELETE FROM turn_records WHERE session_id=?",
            (session_id,),
        )
        conn.commit()
