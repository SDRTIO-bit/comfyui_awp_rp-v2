"""SQLite implementations for CardSession bootstrap stores.

Covers: CardSessionBindingStore, OpeningRecordStore,
        WorldbookBindingStore, BootstrapReceiptStore.
"""

from __future__ import annotations

import json
from typing import Any

from ..card_session_interfaces import (
    CardSessionBindingStore, OpeningRecordStore,
    WorldbookBindingStore, BootstrapReceiptStore,
)
from ...contracts.card_session_binding import CardSessionBinding
from ...contracts.opening_record import OpeningRecord
from ...contracts.worldbook_binding import WorldbookBinding
from ...contracts.card_session_bootstrap_receipt import CardSessionBootstrapReceipt

from .database import Database


class SqliteCardSessionBindingStore(CardSessionBindingStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, binding: CardSessionBinding) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO card_session_bindings
               (session_id, logical_card_id, card_version, source_hash,
                binding_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                binding.session_id,
                binding.logical_card_id,
                binding.card_version,
                binding.source_hash,
                json.dumps(binding.to_dict(), ensure_ascii=False),
                binding.status,
                binding.created_at,
            ),
        )
        conn.commit()

    def load(self, session_id: str) -> CardSessionBinding | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT binding_json FROM card_session_bindings WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return CardSessionBinding.from_dict(json.loads(row["binding_json"]))

    def exists(self, session_id: str) -> bool:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT 1 FROM card_session_bindings WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row is not None

    def list_all(self) -> list[CardSessionBinding]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT binding_json FROM card_session_bindings ORDER BY created_at DESC"
        ).fetchall()
        return [CardSessionBinding.from_dict(json.loads(r["binding_json"])) for r in rows]

    def list_by_card(self, logical_card_id: str) -> list[CardSessionBinding]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT binding_json FROM card_session_bindings "
            "WHERE logical_card_id = ? ORDER BY created_at DESC",
            (logical_card_id,),
        ).fetchall()
        return [CardSessionBinding.from_dict(json.loads(r["binding_json"])) for r in rows]

    def delete(self, session_id: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "DELETE FROM card_session_bindings WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()


class SqliteOpeningRecordStore(OpeningRecordStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, record: OpeningRecord) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO opening_records
               (opening_record_id, session_id, logical_card_id,
                greeting_id, record_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                record.opening_record_id,
                record.session_id,
                record.logical_card_id,
                record.greeting_id,
                json.dumps(record.to_dict(), ensure_ascii=False),
                record.created_at,
            ),
        )
        conn.commit()

    def load(self, opening_record_id: str) -> OpeningRecord | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT record_json FROM opening_records WHERE opening_record_id = ?",
            (opening_record_id,),
        ).fetchone()
        if not row:
            return None
        return OpeningRecord.from_dict(json.loads(row["record_json"]))

    def get_by_session(self, session_id: str) -> OpeningRecord | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT record_json FROM opening_records WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return OpeningRecord.from_dict(json.loads(row["record_json"]))

    def delete_by_session(self, session_id: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "DELETE FROM opening_records WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()


class SqliteWorldbookBindingStore(WorldbookBindingStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, binding: WorldbookBinding) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO worldbook_bindings
               (worldbook_binding_id, session_id, logical_card_id,
                source_hash, binding_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                binding.worldbook_binding_id,
                binding.session_id,
                binding.logical_card_id,
                binding.source_hash,
                json.dumps(binding.to_dict(), ensure_ascii=False),
                binding.created_at,
            ),
        )
        conn.commit()

    def load(self, worldbook_binding_id: str) -> WorldbookBinding | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT binding_json FROM worldbook_bindings WHERE worldbook_binding_id = ?",
            (worldbook_binding_id,),
        ).fetchone()
        if not row:
            return None
        return WorldbookBinding.from_dict(json.loads(row["binding_json"]))

    def get_by_session(self, session_id: str) -> WorldbookBinding | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT binding_json FROM worldbook_bindings WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return WorldbookBinding.from_dict(json.loads(row["binding_json"]))

    def delete_by_session(self, session_id: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "DELETE FROM worldbook_bindings WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()


class SqliteBootstrapReceiptStore(BootstrapReceiptStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, receipt: CardSessionBootstrapReceipt) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO bootstrap_receipts
               (receipt_id, request_id, session_id, logical_card_id,
                receipt_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                receipt.receipt_id,
                receipt.request_id,
                receipt.session_id,
                receipt.logical_card_id,
                json.dumps(receipt.to_dict(), ensure_ascii=False),
                receipt.created_at,
            ),
        )
        conn.commit()

    def load(self, receipt_id: str) -> CardSessionBootstrapReceipt | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT receipt_json FROM bootstrap_receipts WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        if not row:
            return None
        return CardSessionBootstrapReceipt.from_dict(json.loads(row["receipt_json"]))

    def get_by_request(self, request_id: str) -> CardSessionBootstrapReceipt | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT receipt_json FROM bootstrap_receipts WHERE request_id = ? LIMIT 1",
            (request_id,),
        ).fetchone()
        if not row:
            return None
        return CardSessionBootstrapReceipt.from_dict(json.loads(row["receipt_json"]))

    def delete_by_session(self, session_id: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "DELETE FROM bootstrap_receipts WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
