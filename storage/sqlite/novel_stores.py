"""SQLite implementations for novel mode stores.

Covers: NovelProjectStore, NovelVolumeStore, NovelChapterPlanStore,
        NovelChapterDraftStore, NovelLedgerStore, NovelCharacterStore,
        NovelBatchProgressStore, NovelReferenceBookStore.
"""

from __future__ import annotations

import json
from typing import Any

from ..novel_interfaces import (
    NovelProjectStore, NovelVolumeStore, NovelChapterPlanStore,
    NovelChapterDraftStore, NovelLedgerStore, NovelCharacterStore,
    NovelBatchProgressStore, NovelReferenceBookStore,
)
from ...contracts.novel_project import NovelProject
from ...contracts.novel_volume import VolumePlan
from ...contracts.novel_chapter import ChapterPlan
from ...contracts.novel_draft import ChapterDraft
from ...contracts.novel_ledger import LedgerItem
from ...contracts.novel_character import NovelCharacter
from ...contracts.novel_batch import BatchProgress
from ...contracts.novel_reference import ReferenceBook

from .database import Database


class SqliteNovelProjectStore(NovelProjectStore):

    def __init__(self, db: Database):
        self._db = db

    def create(self, project: NovelProject) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_projects
               (project_id, title, genre, status, project_json, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (
                project.project_id,
                project.title,
                project.genre,
                project.status,
                json.dumps(project.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, project_id: str) -> NovelProject | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT project_json FROM novel_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if not row:
            return None
        return NovelProject.from_dict(json.loads(row["project_json"]))

    def list_all(self) -> list[NovelProject]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT project_json FROM novel_projects ORDER BY created_at DESC"
        ).fetchall()
        return [NovelProject.from_dict(json.loads(r["project_json"])) for r in rows]

    def update(self, project: NovelProject) -> None:
        self.create(project)  # INSERT OR REPLACE

    def delete(self, project_id: str) -> None:
        conn = self._db.connect()
        conn.execute("DELETE FROM novel_projects WHERE project_id = ?", (project_id,))
        conn.commit()


class SqliteNovelVolumeStore(NovelVolumeStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, volume: VolumePlan) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_volumes
               (volume_id, project_id, volume_index, title, volume_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                volume.volume_id,
                volume.project_id,
                volume.index,
                volume.title,
                json.dumps(volume.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, volume_id: str) -> VolumePlan | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT volume_json FROM novel_volumes WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()
        if not row:
            return None
        return VolumePlan.from_dict(json.loads(row["volume_json"]))

    def list_by_project(self, project_id: str) -> list[VolumePlan]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT volume_json FROM novel_volumes WHERE project_id = ? ORDER BY volume_index",
            (project_id,),
        ).fetchall()
        return [VolumePlan.from_dict(json.loads(r["volume_json"])) for r in rows]

    def delete(self, volume_id: str) -> None:
        conn = self._db.connect()
        conn.execute("DELETE FROM novel_volumes WHERE volume_id = ?", (volume_id,))
        conn.commit()


class SqliteNovelChapterPlanStore(NovelChapterPlanStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, plan: ChapterPlan) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_chapter_plans
               (chapter_id, project_id, chapter_index, title, plan_json, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (
                plan.chapter_id,
                plan.project_id,
                plan.chapter_index,
                plan.title,
                json.dumps(plan.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, chapter_id: str) -> ChapterPlan | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT plan_json FROM novel_chapter_plans WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()
        if not row:
            return None
        return ChapterPlan.from_dict(json.loads(row["plan_json"]))

    def load_by_index(self, project_id: str, chapter_index: int) -> ChapterPlan | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT plan_json FROM novel_chapter_plans WHERE project_id = ? AND chapter_index = ?",
            (project_id, chapter_index),
        ).fetchone()
        if not row:
            return None
        return ChapterPlan.from_dict(json.loads(row["plan_json"]))

    def list_by_project(self, project_id: str) -> list[ChapterPlan]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT plan_json FROM novel_chapter_plans WHERE project_id = ? ORDER BY chapter_index",
            (project_id,),
        ).fetchall()
        return [ChapterPlan.from_dict(json.loads(r["plan_json"])) for r in rows]

    def get_next_index(self, project_id: str) -> int:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT MAX(chapter_index) as max_idx FROM novel_chapter_plans WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return (row["max_idx"] or 0) + 1


class SqliteNovelChapterDraftStore(NovelChapterDraftStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, draft: ChapterDraft) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_chapter_drafts
               (draft_id, chapter_id, revision, status, draft_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                draft.draft_id,
                draft.chapter_id,
                draft.revision,
                draft.status,
                json.dumps(draft.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, draft_id: str) -> ChapterDraft | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT draft_json FROM novel_chapter_drafts WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()
        if not row:
            return None
        return ChapterDraft.from_dict(json.loads(row["draft_json"]))

    def load_latest(self, chapter_id: str) -> ChapterDraft | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT draft_json FROM novel_chapter_drafts WHERE chapter_id = ? ORDER BY revision DESC LIMIT 1",
            (chapter_id,),
        ).fetchone()
        if not row:
            return None
        return ChapterDraft.from_dict(json.loads(row["draft_json"]))

    def list_by_chapter(self, chapter_id: str) -> list[ChapterDraft]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT draft_json FROM novel_chapter_drafts WHERE chapter_id = ? ORDER BY revision DESC",
            (chapter_id,),
        ).fetchall()
        return [ChapterDraft.from_dict(json.loads(r["draft_json"])) for r in rows]


class SqliteNovelLedgerStore(NovelLedgerStore):

    def __init__(self, db: Database):
        self._db = db

    def upsert(self, item: LedgerItem) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_ledger_items
               (item_id, project_id, section, entity, status, source_chapter, item_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                item.item_id,
                item.project_id,
                item.section,
                item.entity,
                item.status,
                item.source_chapter,
                json.dumps(item.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, item_id: str) -> LedgerItem | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT item_json FROM novel_ledger_items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if not row:
            return None
        return LedgerItem.from_dict(json.loads(row["item_json"]))

    def list_by_project(self, project_id: str, section: str = "") -> list[LedgerItem]:
        conn = self._db.connect()
        if section:
            rows = conn.execute(
                "SELECT item_json FROM novel_ledger_items WHERE project_id = ? AND section = ? ORDER BY source_chapter",
                (project_id, section),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT item_json FROM novel_ledger_items WHERE project_id = ? ORDER BY section, source_chapter",
                (project_id,),
            ).fetchall()
        return [LedgerItem.from_dict(json.loads(r["item_json"])) for r in rows]

    def resolve(self, item_id: str) -> None:
        conn = self._db.connect()
        # Load current item, update status in JSON, then write back
        row = conn.execute(
            "SELECT item_json FROM novel_ledger_items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if row:
            data = json.loads(row["item_json"])
            data["status"] = "resolved"
            conn.execute(
                "UPDATE novel_ledger_items SET status = 'resolved', item_json = ?, updated_at = datetime('now') WHERE item_id = ?",
                (json.dumps(data, ensure_ascii=False), item_id),
            )
            conn.commit()

    def search(self, project_id: str, query: str) -> list[LedgerItem]:
        conn = self._db.connect()
        # Escape LIKE wildcards
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = conn.execute(
            "SELECT item_json FROM novel_ledger_items WHERE project_id = ? AND (entity LIKE ? ESCAPE '\\' OR item_json LIKE ? ESCAPE '\\')",
            (project_id, f"%{escaped}%", f"%{escaped}%"),
        ).fetchall()
        return [LedgerItem.from_dict(json.loads(r["item_json"])) for r in rows]


class SqliteNovelCharacterStore(NovelCharacterStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, character: NovelCharacter) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_characters
               (character_id, project_id, name, role, character_json, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (
                character.character_id,
                character.project_id,
                character.name,
                character.role,
                json.dumps(character.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, character_id: str) -> NovelCharacter | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT character_json FROM novel_characters WHERE character_id = ?",
            (character_id,),
        ).fetchone()
        if not row:
            return None
        return NovelCharacter.from_dict(json.loads(row["character_json"]))

    def list_by_project(self, project_id: str) -> list[NovelCharacter]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT character_json FROM novel_characters WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [NovelCharacter.from_dict(json.loads(r["character_json"])) for r in rows]

    def delete(self, character_id: str) -> None:
        conn = self._db.connect()
        conn.execute("DELETE FROM novel_characters WHERE character_id = ?", (character_id,))
        conn.commit()


class SqliteNovelBatchProgressStore(NovelBatchProgressStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, progress: BatchProgress) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_batch_progress
               (batch_id, project_id, chapter_start, chapter_end, status, progress_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                progress.batch_id,
                progress.project_id,
                progress.chapter_start,
                progress.chapter_end,
                progress.status,
                json.dumps(progress.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, batch_id: str) -> BatchProgress | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT progress_json FROM novel_batch_progress WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        if not row:
            return None
        return BatchProgress.from_dict(json.loads(row["progress_json"]))

    def list_by_project(self, project_id: str) -> list[BatchProgress]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT progress_json FROM novel_batch_progress WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [BatchProgress.from_dict(json.loads(r["progress_json"])) for r in rows]


class SqliteNovelReferenceBookStore(NovelReferenceBookStore):

    def __init__(self, db: Database):
        self._db = db

    def save(self, book: ReferenceBook) -> None:
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO novel_reference_books
               (book_id, project_id, name, role, book_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                book.book_id,
                book.project_id,
                book.name,
                book.role,
                json.dumps(book.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()

    def load(self, book_id: str) -> ReferenceBook | None:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT book_json FROM novel_reference_books WHERE book_id = ?",
            (book_id,),
        ).fetchone()
        if not row:
            return None
        return ReferenceBook.from_dict(json.loads(row["book_json"]))

    def list_by_project(self, project_id: str) -> list[ReferenceBook]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT book_json FROM novel_reference_books WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [ReferenceBook.from_dict(json.loads(r["book_json"])) for r in rows]

    def delete(self, book_id: str) -> None:
        conn = self._db.connect()
        conn.execute("DELETE FROM novel_reference_books WHERE book_id = ?", (book_id,))
        conn.commit()
